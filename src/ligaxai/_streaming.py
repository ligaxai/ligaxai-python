"""Server-sent events: a vendored parser plus ``Stream`` / ``AsyncStream`` iterators.

The parser is vendored (rather than ``httpx-sse``) so the SDK owns reconnection: every
stream exposes ``last_event_id`` and the caller can pass it back as ``after=`` to resume.
It follows the WHATWG EventSource rules that matter on the wire: ``event``/``data``/``id``/
``retry`` fields, multi-line ``data`` joined with ``\\n``, comment lines (``:``) ignored,
``\\r\\n`` / ``\\n`` / ``\\r`` line endings, and chunks that split a line or an event at any
byte boundary.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import Field

from ._models import BaseModel

if TYPE_CHECKING:
    import httpx2

__all__ = [
    "DONE_SENTINEL",
    "AsyncStream",
    "EventRegistry",
    "SSEDecoder",
    "ServerSentEvent",
    "Stream",
]

DONE_SENTINEL = "[DONE]"

T = TypeVar("T")


class ServerSentEvent(BaseModel):
    """One decoded SSE frame."""

    event: str | None = None
    data: str = ""
    id: str | None = None
    retry: int | None = None
    # Not in the spec's data model: filled by the registry hook so a consumer can read the
    # JSON body without re-parsing.
    parsed: Any = Field(default=None, exclude=True)

    def json_data(self) -> Any:
        return json.loads(self.data)


#: Longest single SSE line, and largest single event, the decoder holds. LigaX frames are a
#: few KB; anything near these limits is a broken or hostile stream, not data.
MAX_LINE_BYTES = 8 * 1024 * 1024
MAX_EVENT_BYTES = 16 * 1024 * 1024


class StreamTooLargeError(ValueError):
    """A stream sent a line or an event larger than the decoder will hold in memory."""


class SSEDecoder:
    """Incremental line-oriented SSE decoder. Feed chunks, collect events."""

    def __init__(self) -> None:
        self._buffer = b""
        self._event: str | None = None
        self._data: list[str] = []
        self._id: str | None = None
        self._retry: int | None = None
        self._data_bytes = 0
        self.last_event_id: str | None = None

    def feed(self, chunk: bytes) -> list[ServerSentEvent]:
        """Consume a chunk; return every event completed by it."""
        self._buffer += chunk
        events: list[ServerSentEvent] = []
        if b"\n" not in chunk and b"\r" not in chunk:
            # No line ended in this chunk: nothing to split, so do not rescan the whole buffer.
            if len(self._buffer) > MAX_LINE_BYTES:
                raise StreamTooLargeError("An SSE line exceeded the size limit.")
            return events
        while True:
            line, sep, rest = _split_line(self._buffer)
            if not sep:
                if len(self._buffer) > MAX_LINE_BYTES:
                    raise StreamTooLargeError("An SSE line exceeded the size limit.")
                break
            self._buffer = rest
            event = self._feed_line(line)
            if event is not None:
                events.append(event)
        return events

    def flush(self) -> list[ServerSentEvent]:
        """Dispatch whatever is pending at EOF (a stream that ended without a blank line)."""
        events: list[ServerSentEvent] = []
        if self._buffer:
            event = self._feed_line(self._buffer)
            self._buffer = b""
            if event is not None:
                events.append(event)
        event = self._dispatch()
        if event is not None:
            events.append(event)
        return events

    def _feed_line(self, raw: bytes) -> ServerSentEvent | None:
        line = raw.decode("utf-8", errors="replace")
        if line == "":
            return self._dispatch()
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._data_bytes += len(value) + 1
            if self._data_bytes > MAX_EVENT_BYTES:
                raise StreamTooLargeError("An SSE event exceeded the size limit.")
            self._data.append(value)
        elif field == "id":
            # A NUL in the id means "ignore" per the spec.
            if "\0" not in value:
                self._id = value
                self.last_event_id = value
        elif field == "retry" and value.isdigit():
            self._retry = int(value)
        return None

    def _dispatch(self) -> ServerSentEvent | None:
        if not self._data and self._event is None and self._id is None and self._retry is None:
            return None
        event = ServerSentEvent(
            event=self._event,
            data="\n".join(self._data),
            id=self._id,
            retry=self._retry,
        )
        self._event = None
        self._data = []
        self._data_bytes = 0
        self._id = None
        self._retry = None
        return event


def _split_line(buf: bytes) -> tuple[bytes, bytes, bytes]:
    """Split off the first complete line, honouring ``\\r\\n``, ``\\n`` and lone ``\\r``.

    A trailing lone ``\\r`` is *not* treated as a terminator yet — the next chunk may
    start with ``\\n`` and complete a CRLF.
    """
    n = buf.find(b"\n")
    r = buf.find(b"\r")
    if r != -1 and (n == -1 or r < n):
        if r == len(buf) - 1:
            return b"", b"", buf  # wait for more bytes
        if buf[r + 1 : r + 2] == b"\n":
            return buf[:r], b"\r\n", buf[r + 2 :]
        return buf[:r], b"\r", buf[r + 1 :]
    if n == -1:
        return b"", b"", buf
    return buf[:n], b"\n", buf[n + 1 :]


class EventRegistry(Generic[T]):
    """Maps SSE ``event`` names to typed models.

    ``convert`` turns a raw frame into the registered model (parsed from the JSON
    ``data``); unregistered events fall through to ``default`` so an SDK built on this
    template keeps working when the server adds a new event type.
    """

    def __init__(
        self,
        models: dict[str, type[Any]] | None = None,
        *,
        default: Callable[[ServerSentEvent], T] | None = None,
    ) -> None:
        self._models: dict[str, type[Any]] = dict(models or {})
        self._default = default

    def register(self, event_name: str, model: type[Any]) -> None:
        self._models[event_name] = model

    def convert(self, sse: ServerSentEvent) -> T | ServerSentEvent:
        model = self._models.get(sse.event or "")
        if model is not None:
            value: Any = model.model_validate_json(sse.data)
            return value  # type: ignore[no-any-return]
        if self._default is not None:
            return self._default(sse)
        return sse


class _StreamBase(Generic[T]):
    response: httpx2.Response

    def __init__(
        self,
        *,
        response: httpx2.Response,
        registry: EventRegistry[T] | None = None,
    ) -> None:
        self.response = response
        self._registry: EventRegistry[T] = registry or EventRegistry()
        self._decoder = SSEDecoder()
        self._done = False

    @property
    def last_event_id(self) -> str | None:
        """The most recent ``id:`` seen — pass it as ``after=`` to resume."""
        return self._decoder.last_event_id

    @property
    def request_id(self) -> str | None:
        return self.response.headers.get("x-request-id")

    def _handle(self, sse: ServerSentEvent) -> T | ServerSentEvent | None:
        if sse.data == DONE_SENTINEL:
            self._done = True
            return None
        return self._registry.convert(sse)


class Stream(_StreamBase[T]):
    """Synchronous SSE stream. Iterate it, or use it as a context manager to close early."""

    def __iter__(self) -> Iterator[T | ServerSentEvent]:
        return self._iter()

    def _iter(self) -> Iterator[T | ServerSentEvent]:
        try:
            for chunk in self.response.iter_bytes():
                for sse in self._decoder.feed(chunk):
                    item = self._handle(sse)
                    if self._done:
                        return
                    if item is not None:
                        yield item
            for sse in self._decoder.flush():
                item = self._handle(sse)
                if self._done:
                    return
                if item is not None:
                    yield item
        finally:
            self.response.close()

    def close(self) -> None:
        self.response.close()

    def __enter__(self) -> Stream[T]:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncStream(_StreamBase[T]):
    """Asynchronous SSE stream."""

    def __aiter__(self) -> AsyncIterator[T | ServerSentEvent]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[T | ServerSentEvent]:
        try:
            async for chunk in self.response.aiter_bytes():
                for sse in self._decoder.feed(chunk):
                    item = self._handle(sse)
                    if self._done:
                        return
                    if item is not None:
                        yield item
            for sse in self._decoder.flush():
                item = self._handle(sse)
                if self._done:
                    return
                if item is not None:
                    yield item
        finally:
            await self.response.aclose()

    async def close(self) -> None:
        await self.response.aclose()

    async def __aenter__(self) -> AsyncStream[T]:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
