from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx2
from fastapi import Depends, FastAPI, Request
from standardwebhooks import Webhook

from ligaxai import AsyncLigaX, RunEvent, ServerSentEvent, TextAssembler
from ligaxai._streaming import SSEDecoder
from ligaxai.fastapi import (
    client_dependency,
    client_token_route,
    encode_run_event,
    encode_sse,
    run_stream_route,
    stream_proxy,
    webhook_dependency,
)
from ligaxai.types import WebhookEvent, WebhookTestEvent
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


# -- webhook_dependency ---------------------------------------------------------------


def _webhook_app(secret: str) -> tuple[FastAPI, list[tuple[str, WebhookEvent]]]:
    from fastapi import Header

    seen: list[tuple[str, WebhookEvent]] = []
    app = FastAPI()
    verified = webhook_dependency(lambda: secret)

    @app.post("/hooks", status_code=204)
    async def hook(
        event: WebhookEvent = Depends(verified),  # noqa: B008
        webhook_id: str = Header(),
    ) -> None:
        seen.append((webhook_id, event))

    return app, seen


async def test_webhook_dependency_verifies_the_raw_body() -> None:
    secret = "whsec_" + base64.b64encode(b"k" * 32).decode()
    app, seen = _webhook_app(secret)
    # Deliberately non-canonical JSON: re-serialising it would break the signature.
    raw = (
        b'{"type":"webhook.test",  "timestamp":"2026-10-22T08:00:00.000Z",'
        b'"data":{"object":"webhook_endpoint","id":"we_1"}}'
    )
    now = datetime.now(UTC)
    headers = {
        "webhook-id": "msg_1",
        "webhook-timestamp": str(int(now.timestamp())),
        "webhook-signature": Webhook(secret).sign("msg_1", now, raw.decode()),
        "content-type": "application/json",
    }
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://app") as http:
        ok = await http.post("/hooks", content=raw, headers=headers)
        forged = await http.post("/hooks", content=raw + b" ", headers=headers)
        unsigned = await http.post("/hooks", content=raw)
    assert ok.status_code == 204
    assert forged.status_code == 400 and unsigned.status_code == 400
    assert "webhook-signature" in unsigned.json()["detail"]
    assert len(seen) == 1
    webhook_id, event = seen[0]
    assert webhook_id == "msg_1" and isinstance(event, WebhookTestEvent)


async def test_webhook_dependency_rejects_a_signed_non_event() -> None:
    secret = "whsec_" + base64.b64encode(b"k" * 32).decode()
    app, seen = _webhook_app(secret)
    raw = b'{"hello": "world"}'
    now = datetime.now(UTC)
    headers = {
        "webhook-id": "msg_2",
        "webhook-timestamp": str(int(now.timestamp())),
        "webhook-signature": Webhook(secret).sign("msg_2", now, raw.decode()),
    }
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://app") as http:
        res = await http.post("/hooks", content=raw, headers=headers)
    assert res.status_code == 400 and res.json()["detail"] == "Webhook body is not an event."
    assert seen == []


# -- client_token_route --------------------------------------------------------------------

CLIENT_TOKEN = "lgx_ct_" + "e30" + "." + "A" * 43


def _token_body(**overrides: object) -> dict[str, object]:
    return {
        "object": "client_token",
        "token": CLIENT_TOKEN,
        "expires_at": "2026-10-22T08:10:00.000Z",
        "profile_id": PROFILE_ID,
        "end_user_id": "user_42",
        "conversation_id": None,
        **overrides,
    }


async def test_client_token_route_mints_for_the_signed_in_user(recorder: Recorder) -> None:
    recorder.responses = [json_response(201, _token_body())]
    upstream = _upstream(recorder)
    app = FastAPI()

    async def current_user(request: Request) -> tuple[str, str]:
        return (request.headers["x-user"], "Ada")

    app.post("/token")(
        client_token_route(lambda: upstream, PROFILE_ID, current_user, expires_in=300)
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://t"
    ) as http:
        r = await http.post("/token", headers={"x-user": "user_42"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"token": CLIENT_TOKEN, "expires_at": "2026-10-22T08:10:00.000Z"}
    sent = json.loads(recorder.requests[0].content)
    assert recorder.requests[0].url.path.endswith("/client_tokens")
    assert sent == {
        "profile_id": PROFILE_ID,
        "end_user": {"id": "user_42", "name": "Ada"},
        "expires_in": 300,
    }


async def test_client_token_route_accepts_a_sync_resolver_and_plain_id(
    recorder: Recorder,
) -> None:
    recorder.responses = [json_response(201, _token_body())]
    app = FastAPI()
    app.post("/token")(
        client_token_route(_upstream(recorder), PROFILE_ID, lambda _request: "user_42")
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://t"
    ) as http:
        r = await http.post("/token")
    assert r.status_code == 200
    # No `expires_in` given: the server's default applies.
    assert json.loads(recorder.requests[0].content) == {
        "profile_id": PROFILE_ID,
        "end_user": {"id": "user_42"},
    }


async def test_client_token_route_answers_401_without_a_user(recorder: Recorder) -> None:
    app = FastAPI()
    app.post("/token")(client_token_route(_upstream(recorder), PROFILE_ID, lambda _r: None))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://t"
    ) as http:
        r = await http.post("/token")
    assert r.status_code == 401
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["error"]["code"] == "unauthenticated"
    assert recorder.requests == []  # the API was never called


async def test_client_token_route_forwards_refusals(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(
            403,
            {
                "error": {
                    "type": "permission_error",
                    "code": "insufficient_scope",
                    "message": "This key lacks client_tokens:write.",
                    "request_id": "req_ct",
                }
            },
        )
    ]
    app = FastAPI()
    app.post("/token")(client_token_route(_upstream(recorder), PROFILE_ID, lambda _r: "u"))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://t"
    ) as http:
        r = await http.post("/token")
    assert r.status_code == 403
    assert r.json() == {
        "error": {
            "code": "insufficient_scope",
            "message": "This key lacks client_tokens:write.",
            "request_id": "req_ct",
        }
    }
