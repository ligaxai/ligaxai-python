"""``/runs`` — run an agent profile, read it, follow its events, cancel it, answer it.

Three ways to get an answer, all over ``POST /runs``:

* ``create(mode="wait")`` — one request; the server holds it until the run finishes, or
  answers ``202`` with the run so far after 240 s.
* ``wait(...)`` — ``create`` plus polling, so a long run still comes back finished (or
  waiting on you: ``status == "requires_action"``).
* ``stream(...)`` — ``text/event-stream`` of the engine's frames as they happen.

Every ``POST`` carries an ``Idempotency-Key`` (minted once per call and reused across
retries by the pipeline), so a retried ``create`` can never start a second run.
"""

from __future__ import annotations

import time
from typing import Any, Literal, NotRequired, Required, TypeAlias

import anyio
from typing_extensions import TypedDict

from .._generated.models import Run
from .._run_stream import AsyncRunStream, AsyncRunStreamManager, RunEventList, RunStream
from .._streaming import AsyncStream, ServerSentEvent, Stream
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, merge_options, path_segment

__all__ = [
    "TERMINAL_STATUSES",
    "AsyncRuns",
    "EndUserParam",
    "InputParam",
    "InterruptDecision",
    "Runs",
]

#: Statuses a run never leaves.
TERMINAL_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})

InterruptDecision: TypeAlias = Literal["approve", "reject", "answer"]

# Module-level so tests can patch them; same pattern as `_base_client._sleep`.
_sleep = time.sleep
_async_sleep = anyio.sleep


class EndUserParam(TypedDict):
    """Who the run is for, in your system. ``id`` scopes the conversation to that person."""

    id: Required[str]
    name: NotRequired[str]


class _TextInput(TypedDict):
    text: str


InputParam: TypeAlias = str | _TextInput


def _run_body(
    *,
    profile_id: str,
    input: InputParam,
    conversation_id: str | None,
    end_user: EndUserParam | str | None,
    model: str | None,
    mode: str,
    metadata: dict[str, str] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"profile_id": profile_id, "input": input, "mode": mode}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    if end_user is not None:
        body["end_user"] = {"id": end_user} if isinstance(end_user, str) else dict(end_user)
    if model is not None:
        body["model"] = model
    if metadata is not None:
        body["metadata"] = dict(metadata)
    return body


def _check_wait_mode(mode: str) -> None:
    if mode not in ("wait", "async"):
        raise ValueError(
            f"runs.create takes mode='wait' or mode='async', not {mode!r}; "
            "use runs.stream(...) for a stream."
        )


def _interrupt_body(decision: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    if decision not in ("approve", "reject", "answer"):
        raise ValueError(f"decision must be 'approve', 'reject' or 'answer', not {decision!r}")
    if decision == "answer" and payload is None:
        raise ValueError("decision='answer' needs a payload")
    body: dict[str, Any] = {"decision": decision}
    if payload is not None:
        body["payload"] = payload
    return body


def _settled(run: Run) -> bool:
    return run.status in TERMINAL_STATUSES or run.status == "requires_action"


class Runs(SyncAPIResource):
    def create(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        mode: Literal["wait", "async"] = "wait",
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """Run an agent profile.

        Args:
            profile_id: A published profile (``prf_…``) this key may run.
            input: The message, as a string or ``{"text": …}``.
            conversation_id: Continue an earlier run's conversation (``conv_…``). It must
                belong to the same profile and ``end_user``.
            end_user: Your user's id (or ``{"id", "name"}``); required by some profiles.
            model: A model the profile allows; omitted, the agent's default runs.
            mode: ``"wait"`` holds the request until the run finishes (``202`` with the
                run so far after 240 s); ``"async"`` returns at once — poll ``get``.
            metadata: Up to 16 string pairs, returned on the run.
            idempotency_key: Make a retry safe across processes. One is minted per call
                when omitted, and reused by the SDK's own retries.
        """
        _check_wait_mode(mode)
        body = _run_body(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode=mode,
            metadata=metadata,
        )
        return self._client.request(
            "POST",
            "/runs",
            cast_to=Run,
            json=body,
            options=merge_options(options, idempotency_key=idempotency_key),
        )

    def stream(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        options: RequestOptions | None = None,
    ) -> RunStream:
        """Run an agent profile and stream its frames (``mode: "stream"``).

        Returns a :class:`RunStream`; use it as a context manager so the connection is
        released if you stop early. ``stream.run_id`` / ``stream.conversation_id`` are set
        from the response headers before the first frame.
        """
        body = _run_body(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode="stream",
            metadata=metadata,
        )
        stream: Stream[ServerSentEvent] = self._client.request_stream(
            "POST",
            "/runs",
            json=body,
            options=merge_options(options, idempotency_key=idempotency_key),
        )
        return RunStream(stream)

    def wait(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        poll_interval: float = 1.0,
        max_poll_interval: float = 10.0,
        max_wait: float | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """``create(mode="wait")``, then poll ``get`` until the run settles.

        Settled means terminal (``completed``, ``failed``, ``canceled``, ``expired``) or
        ``requires_action`` — the run is waiting on ``resolve_interrupt``. Polling backs
        off from ``poll_interval`` to ``max_poll_interval`` seconds. With ``max_wait``
        (seconds), the run is returned as it stands once that much time has passed.
        """
        run = self.create(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode="wait",
            metadata=metadata,
            idempotency_key=idempotency_key,
            options=options,
        )
        deadline = None if max_wait is None else time.monotonic() + max_wait
        delay = poll_interval
        while not _settled(run):
            if deadline is not None and time.monotonic() >= deadline:
                break
            _sleep(delay)
            delay = min(delay * 2, max_poll_interval)
            run = self.get(run.id, options=options)
        return run

    def get(self, run_id: str, *, options: RequestOptions | None = None) -> Run:
        """A run's status and, once it has one, its answer (``run.output.text``)."""
        return self._client.request(
            "GET", f"/runs/{path_segment(run_id, 'run_id')}", cast_to=Run, options=options
        )

    def events(
        self, run_id: str, *, after: int = 0, options: RequestOptions | None = None
    ) -> RunEventList:
        """The frames recorded so far after ``after`` (exclusive), oldest first, up to 1,000.

        Fold them with :class:`~ligaxai.TextAssembler` to rebuild the answer.
        """
        return self._client.request(
            "GET",
            f"/runs/{path_segment(run_id, 'run_id')}/events",
            cast_to=RunEventList,
            options=merge_options(options, params={"after": after}),
        )

    def follow_events(
        self, run_id: str, *, after: int = 0, options: RequestOptions | None = None
    ) -> RunStream:
        """The live frames after ``after`` — resume a dropped stream with
        ``follow_events(stream.run_id, after=stream.last_seq)``."""
        stream: Stream[ServerSentEvent] = self._client.request_stream(
            "GET",
            f"/runs/{path_segment(run_id, 'run_id')}/events",
            options=merge_options(options, params={"after": after, "stream": "true"}),
        )
        return RunStream(stream, run_id=run_id)

    def cancel(self, run_id: str, *, options: RequestOptions | None = None) -> Run:
        """Stop a run at its next safe point. Cancelling a finished run returns it as is."""
        return self._client.request(
            "POST",
            f"/runs/{path_segment(run_id, 'run_id')}/cancel",
            cast_to=Run,
            options=options,
        )

    def resolve_interrupt(
        self,
        run_id: str,
        interrupt_id: str,
        *,
        decision: InterruptDecision = "approve",
        payload: dict[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """Answer what the run is waiting on (``run.required_action``).

        ``decision="answer"`` needs a ``payload`` matching ``required_action.response_schema``.
        """
        body = _interrupt_body(decision, payload)
        path = (
            f"/runs/{path_segment(run_id, 'run_id')}"
            f"/interrupts/{path_segment(interrupt_id, 'interrupt_id')}"
        )
        return self._client.request("POST", path, cast_to=Run, json=body, options=options)


class AsyncRuns(AsyncAPIResource):
    async def create(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        mode: Literal["wait", "async"] = "wait",
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """Run an agent profile. See :meth:`Runs.create`."""
        _check_wait_mode(mode)
        body = _run_body(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode=mode,
            metadata=metadata,
        )
        return await self._client.request(
            "POST",
            "/runs",
            cast_to=Run,
            json=body,
            options=merge_options(options, idempotency_key=idempotency_key),
        )

    def stream(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        options: RequestOptions | None = None,
    ) -> AsyncRunStreamManager:
        """Run an agent profile and stream its frames. See :meth:`Runs.stream`.

        ``await`` it or ``async with`` it; either way you get an :class:`AsyncRunStream`.
        """
        body = _run_body(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode="stream",
            metadata=metadata,
        )
        opts = merge_options(options, idempotency_key=idempotency_key)

        async def start() -> AsyncRunStream:
            stream: AsyncStream[ServerSentEvent] = await self._client.request_stream(
                "POST", "/runs", json=body, options=opts
            )
            return AsyncRunStream(stream)

        return AsyncRunStreamManager(start)

    async def wait(
        self,
        *,
        profile_id: str,
        input: InputParam,
        conversation_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        model: str | None = None,
        metadata: dict[str, str] | None = None,
        idempotency_key: str | None = None,
        poll_interval: float = 1.0,
        max_poll_interval: float = 10.0,
        max_wait: float | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """``create(mode="wait")``, then poll until settled. See :meth:`Runs.wait`."""
        run = await self.create(
            profile_id=profile_id,
            input=input,
            conversation_id=conversation_id,
            end_user=end_user,
            model=model,
            mode="wait",
            metadata=metadata,
            idempotency_key=idempotency_key,
            options=options,
        )
        deadline = None if max_wait is None else time.monotonic() + max_wait
        delay = poll_interval
        while not _settled(run):
            if deadline is not None and time.monotonic() >= deadline:
                break
            await _async_sleep(delay)
            delay = min(delay * 2, max_poll_interval)
            run = await self.get(run.id, options=options)
        return run

    async def get(self, run_id: str, *, options: RequestOptions | None = None) -> Run:
        """A run's status and answer. See :meth:`Runs.get`."""
        return await self._client.request(
            "GET", f"/runs/{path_segment(run_id, 'run_id')}", cast_to=Run, options=options
        )

    async def events(
        self, run_id: str, *, after: int = 0, options: RequestOptions | None = None
    ) -> RunEventList:
        """The frames recorded after ``after``. See :meth:`Runs.events`."""
        return await self._client.request(
            "GET",
            f"/runs/{path_segment(run_id, 'run_id')}/events",
            cast_to=RunEventList,
            options=merge_options(options, params={"after": after}),
        )

    def follow_events(
        self, run_id: str, *, after: int = 0, options: RequestOptions | None = None
    ) -> AsyncRunStreamManager:
        """The live frames after ``after``. See :meth:`Runs.follow_events`."""
        path = f"/runs/{path_segment(run_id, 'run_id')}/events"
        opts = merge_options(options, params={"after": after, "stream": "true"})

        async def start() -> AsyncRunStream:
            stream: AsyncStream[ServerSentEvent] = await self._client.request_stream(
                "GET", path, options=opts
            )
            return AsyncRunStream(stream, run_id=run_id)

        return AsyncRunStreamManager(start)

    async def cancel(self, run_id: str, *, options: RequestOptions | None = None) -> Run:
        """Stop a run. See :meth:`Runs.cancel`."""
        return await self._client.request(
            "POST",
            f"/runs/{path_segment(run_id, 'run_id')}/cancel",
            cast_to=Run,
            options=options,
        )

    async def resolve_interrupt(
        self,
        run_id: str,
        interrupt_id: str,
        *,
        decision: InterruptDecision = "approve",
        payload: dict[str, Any] | None = None,
        options: RequestOptions | None = None,
    ) -> Run:
        """Answer what the run is waiting on. See :meth:`Runs.resolve_interrupt`."""
        body = _interrupt_body(decision, payload)
        path = (
            f"/runs/{path_segment(run_id, 'run_id')}"
            f"/interrupts/{path_segment(interrupt_id, 'interrupt_id')}"
        )
        return await self._client.request("POST", path, cast_to=Run, json=body, options=options)
