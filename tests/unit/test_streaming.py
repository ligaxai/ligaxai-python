from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import httpx2
import pytest

from ligaxai import (
    BaseModel,
    EventRegistry,
    InternalServerError,
    ServerSentEvent,
)
from ligaxai._streaming import SSEDecoder
from tests.conftest import Recorder, json_response, make_async_client, make_sync_client


def feed_all(chunks: list[bytes]) -> list[ServerSentEvent]:
    dec = SSEDecoder()
    out: list[ServerSentEvent] = []
    for c in chunks:
        out.extend(dec.feed(c))
    out.extend(dec.flush())
    return out


def test_basic_event() -> None:
    (ev,) = feed_all([b"event: ping\ndata: {}\nid: 7\nretry: 3000\n\n"])
    assert ev.event == "ping"
    assert ev.data == "{}"
    assert ev.id == "7"
    assert ev.retry == 3000
    assert ev.json_data() == {}


def test_split_chunks_at_arbitrary_boundaries() -> None:
    wire = b'event: delta\ndata: {"text": "he\xc3\xa9llo"}\n\ndata: second\n\n'
    for n in range(1, len(wire)):
        events = feed_all([wire[:n], wire[n:]])
        assert [e.data for e in events] == ['{"text": "heéllo"}', "second"], n


def test_crlf_and_lone_cr_line_endings() -> None:
    events = feed_all([b"data: a\r\n\r\ndata: b\r\rdata: c\n\n"])
    assert [e.data for e in events] == ["a", "b", "c"]


def test_crlf_split_between_chunks() -> None:
    events = feed_all([b"data: a\r", b"\n\r", b"\ndata: b\n\n"])
    assert [e.data for e in events] == ["a", "b"]


def test_multiline_data_and_comments() -> None:
    (ev,) = feed_all([b": keep-alive\ndata: line1\ndata: line2\ndata:\n\n"])
    assert ev.data == "line1\nline2\n"


def test_field_without_space_and_unknown_field() -> None:
    (ev,) = feed_all([b"data:x\nfoo: bar\n\n"])
    assert ev.data == "x"


def test_flush_dispatches_trailing_event_without_blank_line() -> None:
    events = feed_all([b"data: tail"])
    assert [e.data for e in events] == ["tail"]


def test_last_event_id_tracks_and_ignores_nul() -> None:
    dec = SSEDecoder()
    dec.feed(b"id: 1\ndata: a\n\nid: bad\x00\ndata: b\n\n")
    assert dec.last_event_id == "1"


class Delta(BaseModel):
    text: str


class Done(BaseModel):
    reason: str


def sse_body() -> bytes:
    return (
        b'id: 1\nevent: delta\ndata: {"text": "hi"}\n\n'
        b'id: 2\nevent: done\ndata: {"reason": "stop"}\n\n'
        b'event: unknown\ndata: {"x": 1}\n\n'
        b"data: [DONE]\n\n"
        b"data: after-done-ignored\n\n"
    )


def chunked(body: bytes, size: int) -> Iterator[bytes]:
    for i in range(0, len(body), size):
        yield body[i : i + size]


async def achunked(body: bytes, size: int) -> AsyncIterator[bytes]:
    for i in range(0, len(body), size):
        yield body[i : i + size]


def sse_response(stream: httpx2.SyncByteStream | httpx2.AsyncByteStream) -> httpx2.Response:
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream", "x-request-id": "req_s"}, stream=stream
    )


class _SyncStream(httpx2.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        return chunked(self._body, 7)


class _AsyncStream(httpx2.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __aiter__(self) -> AsyncIterator[bytes]:
        return achunked(self._body, 7)


def test_sync_stream_with_registry(recorder: Recorder) -> None:
    recorder.responses = [sse_response(_SyncStream(sse_body()))]
    client = make_sync_client(recorder)
    registry: EventRegistry[BaseModel] = EventRegistry({"delta": Delta})
    registry.register("done", Done)
    stream = client.request_stream("POST", "/stream", json={}, registry=registry)
    with stream:
        items = list(stream)
    assert recorder.requests[0].headers["Accept"] == "text/event-stream"
    assert "Idempotency-Key" in recorder.requests[0].headers
    assert isinstance(items[0], Delta) and items[0].text == "hi"
    assert isinstance(items[1], Done) and items[1].reason == "stop"
    assert isinstance(items[2], ServerSentEvent) and items[2].event == "unknown"
    assert len(items) == 3  # [DONE] stops the stream
    assert stream.last_event_id == "2"
    assert stream.request_id == "req_s"


def test_registry_default_hook() -> None:
    registry: EventRegistry[str] = EventRegistry(default=lambda sse: sse.data.upper())
    assert registry.convert(ServerSentEvent(data="abc")) == "ABC"


async def test_async_stream(recorder: Recorder) -> None:
    recorder.responses = [sse_response(_AsyncStream(sse_body()))]
    client = make_async_client(recorder)
    stream = await client.request_stream(
        "GET", "/stream", registry=EventRegistry({"delta": Delta, "done": Done})
    )
    async with stream:
        items = [item async for item in stream]
    assert [type(i).__name__ for i in items] == ["Delta", "Done", "ServerSentEvent"]
    assert stream.last_event_id == "2"
    await client.close()


def test_stream_status_error_is_raised_before_iteration(
    recorder: Recorder, no_sleep: list[float]
) -> None:
    recorder.responses = [json_response(500, {"error": {"message": "down"}})]
    with pytest.raises(InternalServerError):
        make_sync_client(recorder, max_retries=1).request_stream("GET", "/stream")
    assert len(recorder.requests) == 2  # retried before the stream started, never after


def test_stream_without_registry_yields_raw_events(recorder: Recorder) -> None:
    recorder.responses = [sse_response(_SyncStream(b"data: a\n\ndata: b\n\n"))]
    stream = make_sync_client(recorder).request_stream("GET", "/stream")
    assert [e.data for e in stream if isinstance(e, ServerSentEvent)] == ["a", "b"]


def test_a_line_or_event_past_the_size_limit_is_refused() -> None:
    from ligaxai._streaming import MAX_LINE_BYTES, SSEDecoder, StreamTooLargeError

    decoder = SSEDecoder()
    with pytest.raises(StreamTooLargeError):
        decoder.feed(b"data: " + b"x" * (MAX_LINE_BYTES + 1))


def test_a_text_offset_past_any_real_answer_is_ignored() -> None:
    from ligaxai import RunEvent, TextAssembler

    assembler = TextAssembler()
    event = RunEvent(
        type="text.delta", seq=1, payload={"part_id": "p", "offset": 10**12, "text": "x"}
    )
    assert assembler.apply(event) == ""
