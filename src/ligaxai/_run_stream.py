"""A run's event stream: ``RunEvent``, the offset-addressed ``TextAssembler``, and
``RunStream`` / ``AsyncRunStream``.

The server passes the engine's LAE frames through unchanged::

    id: <engine run id>:<seq>          (absent on stream.* control frames)
    event: text.delta
    data: {"v": 1, "type": "text.delta", "seq": 12, "ts": "…", "run": {"id": …},
           "payload": {"part_id": "…", "offset": 147, "text": "…"}}

**Text is a fold, not a concatenation.** A ``text.delta`` says *write this text at this
offset of this part*, and the engine's delivery is at-least-once: a resumed stream re-sends
frames the client already saw. Appending deltas reads correctly on a clean run and
duplicates text on a replay — the bug the platform shipped once and documented in its own
reducer (``turn-state.ts``). ``TextAssembler`` makes every write positional, keyed by
``part_id``, so a replay is a no-op, and it reports only text that is new and contiguous.

``offset`` counts **UTF-16 code units** (the engine and the browser are JavaScript-native),
not Python code points: an emoji outside the Basic Multilingual Plane is one ``str``
character and two offset units. The assembler therefore stores each part as UTF-16 and only
decodes to ``str`` on the way out, never splitting a surrogate pair.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from pydantic import Field, field_validator, model_validator

from ._generated.models import Run
from ._logging import logger
from ._models import BaseModel
from ._streaming import ServerSentEvent

if TYPE_CHECKING:
    import httpx2

    from ._streaming import AsyncStream, Stream

__all__ = [
    "TERMINAL_EVENT",
    "AsyncRunStream",
    "AsyncRunStreamManager",
    "RunEvent",
    "RunEventList",
    "RunStream",
    "TextAssembler",
]

#: The frame that ends a run. ``seq`` on it is always the run's maximum.
TERMINAL_EVENT = "run.end"
_CONTROL_PREFIX = "stream."
_HIGH_SURROGATE = range(0xD800, 0xDC00)


class RunEvent(BaseModel):
    """One frame of a run, live (``runs.stream`` / ``runs.follow_events``) or recorded
    (``runs.events``).

    ``seq`` is the frame's position in the run, gapless from 1; it is ``None`` for the
    transient ``stream.*`` control frames (ready, heartbeat, gap, caught_up), which are never
    stored and cannot be resumed from. ``run_id`` is the LigaX run id — the one ``runs.get``
    takes — not the engine's internal id.
    """

    type: str
    seq: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict[str, Any])
    run_id: str | None = None
    ts: str | None = None
    created_at: str | None = None

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_is_a_dict(cls, value: Any) -> Any:
        # The recorded-events endpoint declares `payload: unknown`; every engine payload is
        # an object, and a missing one is an empty object, not an error.
        return {} if value is None else value

    @property
    def is_control(self) -> bool:
        """True for ``stream.*`` frames: transport bookkeeping, not part of the run."""
        return self.type.startswith(_CONTROL_PREFIX)

    @classmethod
    def from_sse(cls, sse: ServerSentEvent, run_id: str | None = None) -> RunEvent | None:
        """Parse one SSE block. Returns ``None`` for a block that carries no frame."""
        if not sse.data:
            return None
        try:
            frame = json.loads(sse.data)
        except json.JSONDecodeError:
            logger.debug("Skipping a non-JSON SSE block (event=%s)", sse.event)
            return None
        if not isinstance(frame, dict):
            return None
        data: dict[str, Any] = frame  # pyright: ignore[reportUnknownVariableType]
        run: Any = data.get("run")
        engine_run_id = cast("dict[str, Any]", run).get("id") if isinstance(run, dict) else None
        return cls.model_validate(
            {
                "type": data.get("type") or sse.event or "",
                "seq": data.get("seq"),
                "payload": data.get("payload"),
                "run_id": run_id or engine_run_id,
                "ts": data.get("ts"),
            }
        )


class RunEventList(BaseModel):
    """``GET /runs/{run_id}/events``: frames recorded after ``after``, oldest first, at most
    1,000 per call. When ``has_more`` is true, call again with ``after=events[-1].seq``."""

    object: str = "list"
    run_id: str
    data: list[RunEvent]
    has_more: bool

    @model_validator(mode="after")
    def _stamp_run_id(self) -> RunEventList:
        for event in self.data:
            if event.run_id is None:
                event.run_id = self.run_id
        return self


# -- text assembly ---------------------------------------------------------------------


@dataclass
class _Part:
    kind: str = "text"
    started: bool = False
    units: bytearray = field(default_factory=bytearray)  # UTF-16-LE, 2 bytes per unit
    frontier: int = 0  # end of the contiguous run of written units from 0
    pending: list[tuple[int, int]] = field(default_factory=list[tuple[int, int]])
    emitted: int = 0  # units already handed out as "new text"


class TextAssembler:
    """Builds a run's answer from ``part.start`` / ``text.delta`` frames.

    * **Positional.** ``text.delta {part_id, offset, text}`` writes ``text`` at ``offset``
      (UTF-16 code units) of that part. Writing the same delta twice changes nothing.
    * **Replay-safe.** Frames are also de-duplicated by ``seq``.
    * **Only new text out.** ``apply`` / ``write`` return the text that just became
      readable: contiguous from the start of the part and not returned before. A delta that
      lands past a gap is held until the gap fills; a surrogate pair is never split.
    * **Answer order.** ``answer()`` joins the ``text`` parts in the order their
      ``part.start`` arrived (a part seen only through deltas sorts after, by first sight).
      ``reasoning.*`` frames and unknown types are ignored.

    Use it directly over ``runs.events(...)`` replays, or let ``RunStream`` drive it.
    """

    def __init__(self) -> None:
        self._parts: dict[str, _Part] = {}
        self._order: list[str] = []  # part.start order
        self._seen_order: list[str] = []  # first sight, for parts with no part.start
        self._seen_seq: set[int] = set()

    # -- feeding ------------------------------------------------------------------------

    def apply(self, event: RunEvent) -> str:
        """Fold one frame; return the text it made newly readable (often ``""``)."""
        if event.seq is not None:
            if event.seq in self._seen_seq:
                return ""
            self._seen_seq.add(event.seq)
        payload = event.payload
        part_id = payload.get("part_id")
        if not isinstance(part_id, str) or not part_id:
            return ""
        if event.type == "part.start":
            kind = payload.get("kind")
            self.start_part(part_id, kind if isinstance(kind, str) and kind else "text")
            return ""
        if event.type == "text.delta":
            offset = payload.get("offset")
            text = payload.get("text")
            if not isinstance(offset, int) or offset < 0 or not isinstance(text, str):
                return ""
            return self.write(part_id, offset, text)
        return ""

    def start_part(self, part_id: str, kind: str = "text") -> None:
        """Record a ``part.start``. A replayed start keeps the first one's position."""
        part = self._part(part_id)
        if not part.started:
            part.started = True
            part.kind = kind
            self._order.append(part_id)

    def write(self, part_id: str, offset: int, text: str) -> str:
        """Write ``text`` at UTF-16 ``offset`` of ``part_id``; return newly readable text."""
        part = self._part(part_id)
        data = text.encode("utf-16-le", "surrogatepass")
        start, end = offset * 2, offset * 2 + len(data)
        if start > len(part.units):
            # A delta past the end: pad, as the platform's reducer does, so its answer and
            # this one agree byte for byte even on a stream with a hole in it.
            part.units.extend(" ".encode("utf-16-le") * ((start - len(part.units)) // 2))
        part.units[start:end] = data
        self._advance(part, offset, offset + len(data) // 2)
        if part.kind != "text":
            part.emitted = part.frontier
            return ""
        return self._take_new(part)

    # -- reading ------------------------------------------------------------------------

    def text(self, part_id: str) -> str:
        """Everything written to one part so far."""
        part = self._parts.get(part_id)
        return "" if part is None else _decode(part.units)

    def answer(self) -> str:
        """The visible answer: ``text`` parts joined in ``part.start`` order."""
        ordered = self._order + [p for p in self._seen_order if not self._parts[p].started]
        return "".join(
            _decode(self._parts[p].units) for p in ordered if self._parts[p].kind == "text"
        )

    @property
    def part_ids(self) -> list[str]:
        """Every part seen, in answer order."""
        return self._order + [p for p in self._seen_order if not self._parts[p].started]

    # -- internals ----------------------------------------------------------------------

    def _part(self, part_id: str) -> _Part:
        part = self._parts.get(part_id)
        if part is None:
            part = self._parts[part_id] = _Part()
            self._seen_order.append(part_id)
        return part

    @staticmethod
    def _advance(part: _Part, start: int, end: int) -> None:
        if start > part.frontier:
            part.pending.append((start, end))
            return
        part.frontier = max(part.frontier, end)
        changed = True
        while changed and part.pending:
            changed = False
            for span in list(part.pending):
                if span[0] <= part.frontier:
                    part.frontier = max(part.frontier, span[1])
                    part.pending.remove(span)
                    changed = True

    @staticmethod
    def _take_new(part: _Part) -> str:
        upto = part.frontier
        # Never hand out half a surrogate pair: hold a trailing high surrogate back until
        # the low one is written.
        if upto > part.emitted and _unit(part.units, upto - 1) in _HIGH_SURROGATE:
            upto -= 1
        if upto <= part.emitted:
            return ""
        out = _decode(part.units[part.emitted * 2 : upto * 2])
        part.emitted = upto
        return out


def _unit(units: bytearray, index: int) -> int:
    return units[index * 2] | (units[index * 2 + 1] << 8)


def _decode(units: bytes | bytearray) -> str:
    return bytes(units).decode("utf-16-le", "surrogatepass")


# -- streams ---------------------------------------------------------------------------


def _is_json(response: httpx2.Response) -> bool:
    return response.headers.get("content-type", "").split(";")[0].strip() == "application/json"


class _RunStreamBase:
    """State shared by the sync and async streams."""

    response: httpx2.Response
    assembler: TextAssembler
    run: Run | None
    """Set when the server answered with a run object instead of a stream — an
    ``Idempotency-Key`` replay of an earlier request, or a run that could not stream."""
    end: RunEvent | None
    """The ``run.end`` frame, once it has arrived."""
    last_seq: int
    """The highest ``seq`` seen. Resume a dropped stream with
    ``runs.follow_events(stream.run_id, after=stream.last_seq)``."""

    def __init__(self, response: httpx2.Response, *, run_id: str | None = None) -> None:
        self.response = response
        self.assembler = TextAssembler()
        self.run = None
        self.end = None
        self.last_seq = 0
        self._run_id = run_id or response.headers.get("x-run-id")
        self._new_text = ""
        self._closed = False

    @property
    def run_id(self) -> str | None:
        """The LigaX run id (``X-Run-Id``) — pass it to ``runs.get`` / ``runs.cancel``."""
        if self._run_id is None and self.run is not None:
            return self.run.id
        return self._run_id

    @property
    def conversation_id(self) -> str | None:
        """``X-Conversation-Id``: pass it to the next ``runs.create`` to continue."""
        header = self.response.headers.get("x-conversation-id")
        if header is None and self.run is not None:
            return self.run.conversation_id
        return header

    @property
    def request_id(self) -> str | None:
        return self.response.headers.get("x-request-id")

    @property
    def status(self) -> str | None:
        """``run.end``'s status (``completed`` / ``failed`` / …) once the run has ended."""
        if self.end is not None:
            value = self.end.payload.get("status")
            return value if isinstance(value, str) else None
        if self.run is not None:
            return self.run.status
        return None

    def _consume(self, sse: ServerSentEvent) -> RunEvent | None:
        event = RunEvent.from_sse(sse, self._run_id)
        if event is None:
            return None
        if event.seq is not None and event.seq > self.last_seq:
            self.last_seq = event.seq
        self._new_text = self.assembler.apply(event)
        if event.type == TERMINAL_EVENT:
            self.end = event
        return event

    def _load_run(self, body: bytes) -> None:
        self.run = Run.model_validate_json(body)
        self.run.attach_request_id(self.request_id)

    def _fallback_text(self) -> str:
        return self.run.output.text if self.run is not None else ""


class RunStream(_RunStreamBase):
    """A run's live frames. Iterate for ``RunEvent`` s, or use the helpers::

        with client.runs.stream(profile_id="prf_…", input="Hi") as stream:
            for text in stream.text_stream():
                print(text, end="", flush=True)
        print(stream.run_id, stream.status)

    Iteration ends after ``run.end`` (or when the server closes the stream). The stream is
    single-pass: ``text_stream()`` and ``final_text()`` continue from wherever plain
    iteration stopped, and the assembler sees every frame either way.
    """

    def __init__(self, stream: Stream[ServerSentEvent], *, run_id: str | None = None) -> None:
        super().__init__(stream.response, run_id=run_id)
        self._stream = stream
        self._iterator: Iterator[RunEvent] | None = None

    def __iter__(self) -> Iterator[RunEvent]:
        if self._iterator is None:
            self._iterator = self._events()
        return self._iterator

    def _events(self) -> Iterator[RunEvent]:
        try:
            if _is_json(self.response):
                self._load_run(self.response.read())
                return
            for item in self._stream:
                event = self._consume(item)
                if event is None:
                    continue
                yield event
                if event.type == TERMINAL_EVENT:
                    return
        finally:
            self.close()

    def text_stream(self) -> Iterator[str]:
        """Yield answer text as it becomes readable — new text only, replays dropped."""
        for _event in self:
            if self._new_text:
                yield self._new_text
        if self.run is not None and self._fallback_text():
            yield self._fallback_text()

    def final_text(self) -> str:
        """Read the stream to its end and return the whole answer."""
        for _event in self:
            pass
        return self.assembler.answer() or self._fallback_text()

    def until_done(self) -> RunStream:
        """Read the stream to its end; return ``self`` for ``.status`` / ``.end``."""
        for _event in self:
            pass
        return self

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.response.close()

    def __enter__(self) -> RunStream:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncRunStream(_RunStreamBase):
    """The async twin of :class:`RunStream`::

    async with client.runs.stream(profile_id="prf_…", input="Hi") as stream:
        async for text in stream.text_stream():
            print(text, end="", flush=True)
    """

    def __init__(self, stream: AsyncStream[ServerSentEvent], *, run_id: str | None = None) -> None:
        super().__init__(stream.response, run_id=run_id)
        self._stream = stream
        self._iterator: AsyncIterator[RunEvent] | None = None

    def __aiter__(self) -> AsyncIterator[RunEvent]:
        if self._iterator is None:
            self._iterator = self._events()
        return self._iterator

    async def _events(self) -> AsyncIterator[RunEvent]:
        try:
            if _is_json(self.response):
                self._load_run(await self.response.aread())
                return
            async for item in self._stream:
                event = self._consume(item)
                if event is None:
                    continue
                yield event
                if event.type == TERMINAL_EVENT:
                    return
        finally:
            await self.close()

    async def text_stream(self) -> AsyncIterator[str]:
        """Yield answer text as it becomes readable — new text only, replays dropped."""
        async for _event in self:
            if self._new_text:
                yield self._new_text
        if self.run is not None and self._fallback_text():
            yield self._fallback_text()

    async def final_text(self) -> str:
        """Read the stream to its end and return the whole answer."""
        async for _event in self:
            pass
        return self.assembler.answer() or self._fallback_text()

    async def until_done(self) -> AsyncRunStream:
        """Read the stream to its end; return ``self`` for ``.status`` / ``.end``."""
        async for _event in self:
            pass
        return self

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            await self.response.aclose()

    async def __aenter__(self) -> AsyncRunStream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class AsyncRunStreamManager:
    """What ``AsyncLigaX.runs.stream(...)`` returns: await it, or enter it.

    ``stream = await client.runs.stream(...)`` and ``async with client.runs.stream(...) as
    stream:`` both work, so the async surface reads like the sync one
    (``with client.runs.stream(...) as stream:``) without an ``await`` inside ``async with``.
    """

    def __init__(self, start: Callable[[], Awaitable[AsyncRunStream]]) -> None:
        self._start = start
        self._stream: AsyncRunStream | None = None

    async def _open(self) -> AsyncRunStream:
        self._stream = await self._start()
        return self._stream

    def __await__(self) -> Generator[Any, None, AsyncRunStream]:
        return self._open().__await__()

    async def __aenter__(self) -> AsyncRunStream:
        return await self._open()

    async def __aexit__(self, *exc: object) -> None:
        if self._stream is not None:
            await self._stream.close()
