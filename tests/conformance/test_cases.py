"""Conformance harness.

Every ``conformance/cases/*.json`` describes one HTTP exchange and what the SDK must do
with it. The same case runs against the sync and the async client through a mock
transport, so the two can never drift. The case format is documented in
``conformance/README.md``; the files themselves are synced from the spec repo by
``make sync-spec`` once ``SPEC_VERSION`` is set.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest

from ligaxai import APIStatusError, AsyncLigaX, BaseModel, LigaX
from ligaxai import _base_client as base_client_module
from tests.conftest import TEST_API_KEY, TEST_BASE_URL

CASES_DIR = Path(__file__).resolve().parents[2] / "conformance" / "cases"
CASE_FILES = sorted(CASES_DIR.glob("*.json"))


def load(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        case: dict[str, Any] = json.load(fh)
    return case


def make_transport(case: dict[str, Any], seen: list[httpx2.Request]) -> httpx2.MockTransport:
    expected = case["request"]
    resp = case["response"]

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        assert request.method == expected["method"].upper()
        assert request.url.path.endswith(expected["path"])
        for k, v in (expected.get("headers") or {}).items():
            assert request.headers.get(k) == v, f"header {k}"
        if expected.get("body") is not None:
            assert json.loads(request.content) == expected["body"]
        body = resp.get("body")
        content = json.dumps(body).encode() if body is not None else b""
        headers = {"content-type": "application/json", **(resp.get("headers") or {})}
        return httpx2.Response(resp["status"], content=content, headers=headers)

    return httpx2.MockTransport(handler)


def resolve_call(client: object, dotted: str) -> Callable[..., Any]:
    target: Any = client
    for part in dotted.split("."):
        target = getattr(target, part)
    return target  # type: ignore[no-any-return]


def check(case: dict[str, Any], outcome: Any, error: BaseException | None) -> None:
    expect = case["expect"]
    if "error" in expect:
        assert error is not None, f"expected error {expect['error']}, got {outcome!r}"
        assert type(error).__name__ == expect["error"]["type"]
        if isinstance(error, APIStatusError):
            for key in ("status_code", "code", "request_id"):
                if key in expect["error"]:
                    assert getattr(error, key) == expect["error"][key]
        return
    assert error is None, f"unexpected error: {error!r}"
    result = outcome.model_dump(mode="json") if isinstance(outcome, BaseModel) else outcome
    for key, value in expect["result"].items():
        assert result[key] == value, key


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_client_module, "_sleep", lambda _s: None)

    async def _noop(_s: float) -> None:
        return None

    monkeypatch.setattr(base_client_module, "_async_sleep", _noop)


@pytest.mark.parametrize("path", CASE_FILES, ids=[p.stem for p in CASE_FILES])
def test_case_sync(path: Path) -> None:
    case = load(path)
    seen: list[httpx2.Request] = []
    client = LigaX(
        api_key=TEST_API_KEY,
        base_url=TEST_BASE_URL,
        max_retries=case.get("max_retries", 0),
        http_client=httpx2.Client(transport=make_transport(case, seen)),
    )
    outcome: Any = None
    error: BaseException | None = None
    try:
        outcome = resolve_call(client, case["expect"]["call"])(**case.get("args", {}))
    except APIStatusError as exc:
        error = exc
    check(case, outcome, error)
    assert seen, "the SDK never sent a request"
    if "requests" in case["expect"]:
        assert len(seen) == case["expect"]["requests"], "request count"


@pytest.mark.parametrize("path", CASE_FILES, ids=[p.stem for p in CASE_FILES])
async def test_case_async(path: Path) -> None:
    case = load(path)
    seen: list[httpx2.Request] = []
    client = AsyncLigaX(
        api_key=TEST_API_KEY,
        base_url=TEST_BASE_URL,
        max_retries=case.get("max_retries", 0),
        http_client=httpx2.AsyncClient(transport=make_transport(case, seen)),
    )
    outcome: Any = None
    error: BaseException | None = None
    try:
        outcome = await resolve_call(client, case["expect"]["call"])(**case.get("args", {}))
    except APIStatusError as exc:
        error = exc
    check(case, outcome, error)
    assert seen, "the SDK never sent a request"
    if "requests" in case["expect"]:
        assert len(seen) == case["expect"]["requests"], "request count"
