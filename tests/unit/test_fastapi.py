from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx2
from fastapi import Depends, FastAPI, Request

from ligaxai import AsyncLigaX, RunEvent, ServerSentEvent, TextAssembler
from ligaxai._streaming import SSEDecoder
from ligaxai.fastapi import (
    client_dependency,
    encode_run_event,
    encode_sse,
    run_stream_route,
    stream_proxy,
)
from tests.conftest import (
    CONVERSATION_ID,
    PROFILE_ID,
    RUN_ID,
    Recorder,
    Status,
    frame,
    json_response,
    make_async_client,
    run_body,
    sse,
    sse_response,
)


def test_encode_sse_round_trips_fields() -> None:
    raw = encode_sse(ServerSentEvent(event="delta", id="3", retry=10, data="a\nb"))
    assert raw == b"event: delta\nid: 3\nretry: 10\ndata: a\ndata: b\n\n"
    assert encode_sse(Status(status="ok")) == b'data: {"status":"ok","version":null}\n\n'
    assert encode_sse({"k": 1}) == b'data: {"k": 1}\n\n'


async def test_dependency_and_stream_proxy() -> None:
    app = FastAPI()
    get_client = client_dependency(api_key="k", base_url="https://api.test.invalid")

    @app.get("/who")
    async def who(client: AsyncLigaX = Depends(get_client)) -> dict[str, str]:  # noqa: B008
        return {"key": client.api_key}

    async def events() -> AsyncIterator[ServerSentEvent]:
        yield ServerSentEvent(data="one")
        yield ServerSentEvent(data="two")

    @app.get("/stream")
    async def stream() -> object:
        return stream_proxy(events())

    @app.get("/stream-sync")
    async def stream_sync() -> object:
        return stream_proxy(iter([{"n": 1}]))

    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as http:
        assert (await http.get("/who")).json() == {"key": "k"}
        assert get_client() is get_client()  # cached per process
        r = await http.get("/stream")
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.text == "data: one\n\ndata: two\n\ndata: [DONE]\n\n"
        r2 = await http.get("/stream-sync")
        assert r2.text == 'data: {"n": 1}\n\ndata: [DONE]\n\n'


# -- run_stream_route ----------------------------------------------------------------------


def _upstream(recorder: Recorder) -> AsyncLigaX:
    return make_async_client(recorder)


async def _post(app: FastAPI, body: dict[str, object]) -> httpx2.Response:
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as http:
        return await http.post("/chat", json=body)


def test_encode_run_event() -> None:
    event = RunEvent(
        type="text.delta", seq=4, payload={"part_id": "p", "offset": 0, "text": "hi"}, run_id=RUN_ID
    )
    wire = encode_run_event(event).decode()
    assert wire.startswith("event: text.delta\nid: 4\ndata: ")
    assert json.loads(wire.split("data: ", 1)[1]) == {
        "type": "text.delta",
        "seq": 4,
        "payload": {"part_id": "p", "offset": 0, "text": "hi"},
        "run_id": RUN_ID,
        "ts": None,
    }
    control = encode_run_event(RunEvent(type="stream.heartbeat")).decode()
    assert "id:" not in control


async def test_run_stream_route_proxies_frames(recorder: Recorder) -> None:
    frames = [
        frame("run.start", 1, {}),
        frame("part.start", 2, {"part_id": "p", "kind": "text"}),
        frame("text.delta", 3, {"part_id": "p", "offset": 0, "text": "Hi 👋"}),
        frame("run.end", 4, {"status": "completed"}),
    ]
    recorder.responses = [sse_response(sse(frames), is_async=True)]
    seen_users: list[str] = []

    async def current_user(request: Request) -> str:
        seen_users.append(request.headers["x-user"])
        return request.headers["x-user"]

    app = FastAPI()
    app.post("/chat")(run_stream_route(_upstream(recorder), PROFILE_ID, current_user, model="m-1"))
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://t") as http:
        r = await http.post(
            "/chat",
            json={"input": "Hello", "conversation_id": CONVERSATION_ID},
            headers={"x-user": "user-42"},
        )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-run-id"] == RUN_ID
    assert r.headers["x-conversation-id"] == CONVERSATION_ID
    # The upstream request: the server's key, the server's profile, the resolved end user.
    upstream = recorder.requests[0]
    assert upstream.headers["Authorization"].startswith("Bearer ")
    assert json.loads(upstream.content) == {
        "profile_id": PROFILE_ID,
        "input": "Hello",
        "mode": "stream",
        "conversation_id": CONVERSATION_ID,
        "end_user": {"id": "user-42"},
        "model": "m-1",
    }
    assert seen_users == ["user-42"]
    # The browser gets RunEvent-shaped frames it can feed straight into a TextAssembler.
    events = [RunEvent.from_sse(e) for e in SSEDecoder().feed(r.content)]
    assert [e.type for e in events if e] == ["run.start", "part.start", "text.delta", "run.end"]
    assembler = TextAssembler()
    for e in events:
        assert e is not None
        assembler.apply(e)
    assert assembler.answer() == "Hi 👋"
    assert "Authorization" not in r.headers


async def test_run_stream_route_forwards_refusals(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(
            402,
            {
                "error": {
                    "type": "billing_error",
                    "code": "key_limit_reached",
                    "message": "This key reached its limit.",
                    "request_id": "req_402",
                }
            },
        )
    ]
    app = FastAPI()
    app.post("/chat")(run_stream_route(lambda: _upstream(recorder), PROFILE_ID))
    r = await _post(app, {"input": "Hello"})
    assert r.status_code == 402
    assert r.json() == {
        "error": {
            "code": "key_limit_reached",
            "message": "This key reached its limit.",
            "request_id": "req_402",
        }
    }
    assert len(recorder.requests) == 1


async def test_run_stream_route_validates_the_browser_body(recorder: Recorder) -> None:
    app = FastAPI()
    app.post("/chat")(run_stream_route(_upstream(recorder), PROFILE_ID, lambda _r: None))
    r = await _post(app, {"input": "", "profile_id": "prf_other"})
    assert r.status_code == 422
    assert recorder.requests == []


async def test_run_stream_route_relays_a_json_replay(recorder: Recorder) -> None:
    recorder.responses = [json_response(200, run_body())]
    app = FastAPI()
    app.post("/chat")(run_stream_route(_upstream(recorder), PROFILE_ID, lambda _r: "u-1"))
    r = await _post(app, {"input": "Hello"})
    assert r.status_code == 200
    (event,) = [e for e in SSEDecoder().feed(r.content)]
    parsed = RunEvent.from_sse(event)
    assert parsed is not None and parsed.type == "run.end"
    assert parsed.payload == {"status": "completed", "text": "Hello there."}
