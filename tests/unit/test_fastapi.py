from __future__ import annotations

from collections.abc import AsyncIterator

import httpx2
from fastapi import Depends, FastAPI

from ligaxai import AsyncLigaX, ServerSentEvent
from ligaxai.fastapi import client_dependency, encode_sse, stream_proxy
from tests.conftest import Status


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
