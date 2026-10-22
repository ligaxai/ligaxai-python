"""RunStream / AsyncRunStream over LAE frames, as the server passes them through."""

from __future__ import annotations

import json

import pytest

from ligaxai import AsyncRunStream, NotFoundError, RunEvent, RunStream
from ligaxai._streaming import ServerSentEvent
from tests.conftest import (
    CONVERSATION_ID,
    ENGINE_RUN_ID,
    PROFILE_ID,
    RUN_ID,
    Recorder,
    error_body,
    frame,
    json_response,
    make_async_client,
    make_sync_client,
    recorded_frames,
    run_body,
    sse,
    sse_response,
)

PART = "msg-1-0"


def short_run() -> list[dict[str, object]]:
    return [
        frame("stream.ready", None, {"run_ids": [ENGINE_RUN_ID], "heartbeat_ms": 15000}),
        frame("run.start", 1, {"run_id": ENGINE_RUN_ID}),
        frame("part.start", 2, {"part_id": PART, "kind": "text", "ord": 0}),
        frame("reasoning.delta", 3, {"part_id": "r", "offset": 0, "text": "hmm"}),
        frame("text.delta", 4, {"part_id": PART, "offset": 0, "text": "Hello "}),
        frame("stream.heartbeat", None),
        frame("text.delta", 5, {"part_id": PART, "offset": 6, "text": "world 🌍"}),
        frame("part.end", 6, {"part_id": PART}),
        frame("run.end", 7, {"status": "completed", "finish_reason": "stop"}),
        frame("stream.caught_up", None),  # after run.end: never read
    ]


# -- parsing --------------------------------------------------------------------------


def test_run_event_from_sse_frame() -> None:
    raw = frame("text.delta", 4, {"part_id": PART, "offset": 0, "text": "x"})
    sse_event = ServerSentEvent(event="text.delta", id=f"{ENGINE_RUN_ID}:4", data=json.dumps(raw))
    event = RunEvent.from_sse(sse_event, RUN_ID)
    assert event is not None
    assert (event.type, event.seq, event.run_id) == ("text.delta", 4, RUN_ID)
    assert event.payload == {"part_id": PART, "offset": 0, "text": "x"}
    assert event.ts == "2026-10-22T08:00:00+00:00"
    assert not event.is_control
    # Without a LigaX run id, the frame's own run reference is the fallback.
    fallback = RunEvent.from_sse(sse_event)
    assert fallback is not None and fallback.run_id == ENGINE_RUN_ID


def test_run_event_from_sse_tolerates_odd_blocks() -> None:
    assert RunEvent.from_sse(ServerSentEvent(event="x", data="")) is None
    assert RunEvent.from_sse(ServerSentEvent(event="x", data="not json")) is None
    assert RunEvent.from_sse(ServerSentEvent(event="x", data="[1, 2]")) is None
    bare = RunEvent.from_sse(ServerSentEvent(event="stream.heartbeat", data='{"payload": null}'))
    assert bare is not None and bare.type == "stream.heartbeat" and bare.payload == {}
    assert bare.is_control and bare.seq is None


@pytest.mark.parametrize("chunk", [1, 3, 7, 64, 100_000])
def test_stream_parses_frames_split_at_any_byte(recorder: Recorder, chunk: int) -> None:
    recorder.responses = [sse_response(sse(short_run()), chunk=chunk)]
    client = make_sync_client(recorder)
    with client.runs.stream(profile_id=PROFILE_ID, input="Hi") as stream:
        events = list(stream)
    assert [e.type for e in events] == [
        "stream.ready",
        "run.start",
        "part.start",
        "reasoning.delta",
        "text.delta",
        "stream.heartbeat",
        "text.delta",
        "part.end",
        "run.end",
    ]
    assert [e.seq for e in events if e.is_control] == [None, None]
    assert all(e.run_id == RUN_ID for e in events)
    assert stream.final_text() == "Hello world 🌍"
    assert stream.status == "completed"
    assert stream.end is not None and stream.end.seq == 7
    assert stream.last_seq == 7


def test_text_stream_yields_only_new_text(recorder: Recorder) -> None:
    frames = short_run()
    # A resumed engine re-sends frames 4 and 5: nothing new may come out of them.
    frames[7:7] = [frames[4], frames[6]]
    recorder.responses = [sse_response(sse(frames))]
    stream = make_sync_client(recorder).runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert list(stream.text_stream()) == ["Hello ", "world 🌍"]
    assert stream.final_text() == "Hello world 🌍"  # already drained: same answer


def test_stream_headers_and_ids(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()))]
    stream = make_sync_client(recorder).runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert stream.run_id == RUN_ID
    assert stream.conversation_id == CONVERSATION_ID
    assert stream.request_id == "req_stream"
    assert stream.status is None  # not ended yet
    stream.close()
    stream.close()  # idempotent


def test_iteration_resumes_where_it_stopped(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()))]
    stream = make_sync_client(recorder).runs.stream(profile_id=PROFILE_ID, input="Hi")
    first = next(iter(stream))
    assert first.type == "stream.ready"
    assert stream.until_done() is stream
    assert stream.final_text() == "Hello world 🌍"


def test_recorded_run_end_to_end(recorder: Recorder) -> None:
    frames = recorded_frames()
    message_end = next(f for f in frames if f["type"] == "message.end")
    expected = "".join(p["text"] for p in message_end["payload"]["message"]["parts"])  # type: ignore[index]
    recorder.responses = [sse_response(sse(frames), chunk=13)]
    with make_sync_client(recorder).runs.stream(profile_id=PROFILE_ID, input="Hi") as stream:
        assert "".join(stream.text_stream()) == expected
    assert stream.status == "completed"
    assert stream.last_seq == 22


def test_json_answer_instead_of_a_stream(recorder: Recorder) -> None:
    """An Idempotency-Key replay returns the run as JSON even when a stream was asked for."""
    recorder.responses = [
        json_response(200, run_body(), {"x-request-id": "req_replay"}),
        json_response(200, run_body()),
    ]
    client = make_sync_client(recorder)
    stream = client.runs.stream(profile_id=PROFILE_ID, input="Hi", idempotency_key="key-123456")
    assert list(stream) == []
    assert stream.run is not None and stream.run.request_id == "req_replay"
    assert stream.run_id == RUN_ID
    assert stream.conversation_id == CONVERSATION_ID
    assert stream.status == "completed"
    assert stream.final_text() == "Hello there."
    again = client.runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert list(again.text_stream()) == ["Hello there."]


def test_follow_events_resumes_after_a_seq(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()[5:]), headers={"x-run-id": ""})]
    client = make_sync_client(recorder)
    stream = client.runs.follow_events(RUN_ID, after=4)
    events = list(stream)
    req = recorder.requests[0]
    assert req.method == "GET"
    assert req.url.path.endswith(f"/runs/{RUN_ID}/events")
    assert req.url.params["after"] == "4"
    assert req.url.params["stream"] == "true"
    assert req.headers["Accept"] == "text/event-stream"
    assert stream.run_id == RUN_ID
    assert events[-1].type == "run.end"
    # Only the tail was replayed: the part's start was never seen, its text still lands.
    assert stream.final_text() == "      world 🌍"


def test_stream_error_raised_before_iteration(recorder: Recorder) -> None:
    recorder.responses = [json_response(404, error_body("nope", code="profile_not_found"))]
    with pytest.raises(NotFoundError) as exc_info:
        make_sync_client(recorder, max_retries=0).runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert exc_info.value.code == "profile_not_found"


def test_stream_that_ends_without_run_end(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()[:5]))]
    stream = make_sync_client(recorder).runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert stream.final_text() == "Hello "
    assert stream.end is None and stream.status is None


# -- async ----------------------------------------------------------------------------


async def test_async_stream_parity(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()), is_async=True, chunk=5)]
    client = make_async_client(recorder)
    async with client.runs.stream(profile_id=PROFILE_ID, input="Hi") as stream:
        assert isinstance(stream, AsyncRunStream)
        assert stream.run_id == RUN_ID and stream.conversation_id == CONVERSATION_ID
        texts = [t async for t in stream.text_stream()]
    assert texts == ["Hello ", "world 🌍"]
    assert await stream.final_text() == "Hello world 🌍"
    assert stream.status == "completed" and stream.last_seq == 7
    body = json.loads(recorder.requests[0].content)
    assert body["mode"] == "stream"
    await client.close()


async def test_async_stream_awaitable_and_events(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()), is_async=True)]
    client = make_async_client(recorder)
    stream = await client.runs.stream(profile_id=PROFILE_ID, input="Hi")
    types = [e.type async for e in stream]
    assert types[-1] == "run.end"
    assert (await stream.until_done()) is stream
    await stream.close()


async def test_async_follow_events_and_json_fallback(recorder: Recorder) -> None:
    recorder.responses = [sse_response(sse(short_run()), is_async=True)]
    client = make_async_client(recorder)
    async with client.runs.follow_events(RUN_ID, after=0) as stream:
        assert await stream.final_text() == "Hello world 🌍"
    assert recorder.requests[0].url.params["stream"] == "true"

    recorder.requests.clear()
    recorder.responses = [json_response(200, run_body(status="requires_action"))]
    replay = await client.runs.stream(profile_id=PROFILE_ID, input="Hi")
    assert [e async for e in replay] == []
    assert replay.status == "requires_action"
    assert [t async for t in replay.text_stream()] == ["Hello there."]
    await client.close()


def test_run_stream_is_exported() -> None:
    assert RunStream.__name__ == "RunStream"
