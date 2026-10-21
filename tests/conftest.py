"""Shared fixtures. Every test talks to an ``httpx2.MockTransport`` — never the network."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest

from base_project_module import AsyncBaseProject, BaseProject
from base_project_module import _base_client as base_client_module

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


def make_sync_client(recorder: Recorder, **kwargs: Any) -> BaseProject:
    kwargs.setdefault("api_key", TEST_API_KEY)
    kwargs.setdefault("base_url", TEST_BASE_URL)
    return BaseProject(
        http_client=httpx2.Client(transport=httpx2.MockTransport(recorder.handler)), **kwargs
    )


def make_async_client(recorder: Recorder, **kwargs: Any) -> AsyncBaseProject:
    kwargs.setdefault("api_key", TEST_API_KEY)
    kwargs.setdefault("base_url", TEST_BASE_URL)
    return AsyncBaseProject(
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
    yield delays


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BASE_PROJECT_API_KEY", raising=False)
    monkeypatch.delenv("BASE_PROJECT_BASE_URL", raising=False)
