"""Shared fixtures. Every test talks to an ``httpx2.MockTransport`` — never the network."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import pytest

from ligaxai import AsyncLigaX, BaseModel, LigaX, RequestOptions
from ligaxai import _base_client as base_client_module
from ligaxai.resources import runs as runs_module

TEST_API_KEY = "test-key-not-a-secret"
TEST_BASE_URL = "https://api.test.invalid/api/public/v1"

Handler = Callable[[httpx2.Request], httpx2.Response]


@dataclass
class Recorder:
    """Records every request a mock transport saw and serves scripted responses in order.

    The last response is repeated once the script is exhausted, so a test can script
    ``[429, 200]`` and let retries land on the 200.
    """

    responses: list[httpx2.Response | Exception] = field(default_factory=list)
    requests: list[httpx2.Request] = field(default_factory=list)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        idx = min(len(self.requests) - 1, len(self.responses) - 1)
        item = self.responses[idx]
        if isinstance(item, Exception):
            raise item
        return item


def json_response(
    status: int = 200, body: Any = None, headers: dict[str, str] | None = None
) -> httpx2.Response:
    return httpx2.Response(
        status,
        content=json.dumps(body if body is not None else {"status": "ok"}).encode(),
        headers={"content-type": "application/json", **(headers or {})},
    )


def error_body(
    message: str, *, type_: str = "api_error", code: str = "bad", request_id: str = "req_1"
) -> dict[str, Any]:
    return {"error": {"type": type_, "code": code, "message": message, "request_id": request_id}}


class Status(BaseModel):
    """Response of the probe endpoint the pipeline tests call."""

    status: str
    version: str | None = None


def ping(client: LigaX, *, options: RequestOptions | None = None) -> Status:
    """One GET through the whole pipeline. The pipeline tests need *an* endpoint, not a
    particular one, so they do not depend on a resource's response shape."""
    return client.request("GET", "/health", cast_to=Status, options=options)


async def aping(client: AsyncLigaX, *, options: RequestOptions | None = None) -> Status:
    return await client.request("GET", "/health", cast_to=Status, options=options)


def make_sync_client(recorder: Recorder, **kwargs: Any) -> LigaX:
    kwargs.setdefault("api_key", TEST_API_KEY)
    kwargs.setdefault("base_url", TEST_BASE_URL)
    return LigaX(
        http_client=httpx2.Client(transport=httpx2.MockTransport(recorder.handler)), **kwargs
    )


def make_async_client(recorder: Recorder, **kwargs: Any) -> AsyncLigaX:
    kwargs.setdefault("api_key", TEST_API_KEY)
    kwargs.setdefault("base_url", TEST_BASE_URL)
    return AsyncLigaX(
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(recorder.handler)),
        **kwargs,
    )


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Capture retry delays instead of sleeping."""
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(base_client_module, "_sleep", fake_sleep)
    monkeypatch.setattr(base_client_module, "_async_sleep", fake_async_sleep)
    monkeypatch.setattr(runs_module, "_sleep", fake_sleep)
    monkeypatch.setattr(runs_module, "_async_sleep", fake_async_sleep)
    yield delays


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIGAX_API_KEY", raising=False)
    monkeypatch.delenv("LIGAX_BASE_URL", raising=False)


# -- run and SSE fixtures ------------------------------------------------------------------

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RUN_ID = "0b6c1d2e-3f40-4a5b-8c6d-7e8f90a1b2c3"
ENGINE_RUN_ID = "309177e6-7f96-41ea-9602-5b1c5263e4f1"
PROFILE_ID = "prf_" + "A" * 20
CONVERSATION_ID = "conv_" + "B" * 24


def run_body(**overrides: Any) -> dict[str, Any]:
    """A complete, valid ``Run`` as the server presents it (``presentRun``)."""
    body: dict[str, Any] = {
        "object": "run",
        "id": RUN_ID,
        "status": "completed",
        "profile_id": PROFILE_ID,
        "conversation_id": CONVERSATION_ID,
        "end_user_id": None,
        "model": "gemini/gemini-flash/latest",
        "created_at": "2026-10-22T08:00:00.000Z",
        "completed_at": "2026-10-22T08:00:05.000Z",
        "output": {"text": "Hello there.", "artifacts": [], "sources": [], "tool_calls": []},
        "required_action": None,
        "usage": {"input_tokens": 10, "output_tokens": 3, "cost_usd": "0.000120"},
        "error": None,
        "metadata": {},
    }
    body.update(overrides)
    return body


def frame(
    type_: str, seq: int | None, payload: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    """An LAE frame as the engine serialises it."""
    return {
        "v": 1,
        "type": type_,
        "seq": seq,
        "ts": "2026-10-22T08:00:00+00:00",
        "run": {"id": ENGINE_RUN_ID, "root_id": ENGINE_RUN_ID, "parent_id": None, "depth": 0},
        "payload": payload or {},
        **extra,
    }


def sse(frames: list[dict[str, Any]]) -> bytes:
    """Frames on the wire exactly as ``event_stream.to_sse`` writes them."""
    out = []
    for f in frames:
        lines = []
        if f["seq"] is not None:
            lines.append(f"id: {ENGINE_RUN_ID}:{f['seq']}")
        lines.append(f"event: {f['type']}")
        lines.append("data: " + json.dumps(f, ensure_ascii=False))
        out.append("\n".join(lines) + "\n\n")
    return "".join(out).encode()


def recorded_frames() -> list[dict[str, Any]]:
    """A real dev-engine run (copied from the platform's protocol fixtures), as frames."""
    rows = json.loads((FIXTURES / "chat-turn-long.json").read_text(encoding="utf-8"))
    return [frame(r["type"], r["seq"], r["payload"]) for r in rows]


class SyncChunks(httpx2.SyncByteStream):
    def __init__(self, body: bytes, size: int) -> None:
        self._body, self._size = body, size

    def __iter__(self) -> Iterator[bytes]:
        for i in range(0, len(self._body), self._size):
            yield self._body[i : i + self._size]


class AsyncChunks(httpx2.AsyncByteStream):
    def __init__(self, body: bytes, size: int) -> None:
        self._body, self._size = body, size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for i in range(0, len(self._body), self._size):
            yield self._body[i : i + self._size]


def sse_response(
    body: bytes,
    *,
    is_async: bool = False,
    chunk: int = 7,
    headers: dict[str, str] | None = None,
) -> httpx2.Response:
    """A ``text/event-stream`` response delivered in ``chunk``-byte pieces."""
    stream: httpx2.SyncByteStream | httpx2.AsyncByteStream = (
        AsyncChunks(body, chunk) if is_async else SyncChunks(body, chunk)
    )
    return httpx2.Response(
        200,
        headers={
            "content-type": "text/event-stream; charset=utf-8",
            "x-request-id": "req_stream",
            "x-run-id": RUN_ID,
            "x-conversation-id": CONVERSATION_ID,
            **(headers or {}),
        },
        stream=stream,
    )
