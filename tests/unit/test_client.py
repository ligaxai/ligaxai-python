from __future__ import annotations

import httpx2
import pytest

from ligaxai import (
    DEFAULT_BASE_URL,
    APIError,
    AsyncLigaX,
    LigaX,
    MissingAPIKeyError,
    RequestOptions,
    __version__,
)
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    Recorder,
    aping,
    json_response,
    make_sync_client,
    ping,
)


def test_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGAX_API_KEY", "env-key")
    monkeypatch.setenv("LIGAX_BASE_URL", "https://env.test.invalid/v1")
    with LigaX() as client:
        assert client.api_key == "env-key"
        assert str(client.base_url) == "https://env.test.invalid/v1/"


def test_explicit_api_key_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGAX_API_KEY", "env-key")
    with LigaX(api_key="arg-key") as client:
        assert client.api_key == "arg-key"


def test_missing_api_key_raises_value_error() -> None:
    with pytest.raises(MissingAPIKeyError) as exc_info:
        LigaX()
    assert isinstance(exc_info.value, ValueError)
    assert isinstance(exc_info.value, APIError)
    assert "LIGAX_API_KEY" in str(exc_info.value)


def test_empty_env_key_is_treated_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGAX_API_KEY", "")
    with pytest.raises(MissingAPIKeyError):
        AsyncLigaX()


def test_default_base_url_and_defaults() -> None:
    with LigaX(api_key="k") as client:
        assert str(client.base_url) == DEFAULT_BASE_URL + "/"
        assert client.max_retries == 2
        assert isinstance(client.timeout, httpx2.Timeout)
        assert client.timeout.connect == 5.0
        assert client.timeout.read == 600.0


def test_rejects_foreign_http_client() -> None:
    with pytest.raises(TypeError):
        LigaX(api_key="k", http_client=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        AsyncLigaX(api_key="k", http_client=object())  # type: ignore[arg-type]


def test_headers_sent(recorder: Recorder) -> None:
    recorder.responses = [json_response()]
    client = make_sync_client(recorder, default_headers={"X-Custom": "1"})
    ping(client, options=RequestOptions(headers={"X-Per-Call": "2"}))
    req = recorder.requests[0]
    assert req.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert req.headers["Accept"] == "application/json"
    assert req.headers["X-Custom"] == "1"
    assert req.headers["X-Per-Call"] == "2"
    assert "Idempotency-Key" not in req.headers  # GET
    assert str(req.url) == TEST_BASE_URL + "/health"


def test_user_agent(recorder: Recorder) -> None:
    recorder.responses = [json_response()]
    ping(make_sync_client(recorder))
    ua = recorder.requests[0].headers["User-Agent"]
    assert ua.startswith(f"ligaxai-python/{__version__} (python/")


def test_with_options_overrides_and_shares_pool(recorder: Recorder) -> None:
    recorder.responses = [json_response()]
    client = make_sync_client(recorder, max_retries=5)
    copy = client.with_options(max_retries=0, api_key="other", default_headers={"X-A": "b"})
    assert copy.max_retries == 0
    assert copy.api_key == "other"
    assert client.max_retries == 5
    assert client.api_key == TEST_API_KEY
    assert copy._http is client._http
    ping(copy)
    assert recorder.requests[0].headers["Authorization"] == "Bearer other"
    assert recorder.requests[0].headers["X-A"] == "b"
    # The copy does not own the pool, so closing it leaves the original usable.
    copy.close()
    ping(client)
    client.close()


def test_response_carries_request_id(recorder: Recorder) -> None:
    recorder.responses = [json_response(headers={"x-request-id": "req_abc"})]
    result = ping(make_sync_client(recorder))
    assert result.status == "ok"
    assert result.request_id == "req_abc"


async def test_async_client_round_trip(recorder: Recorder) -> None:
    recorder.responses = [json_response(body={"status": "ok", "version": "1"})]
    async with AsyncLigaX(
        api_key="k",
        base_url=TEST_BASE_URL,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(recorder.handler)),
    ) as client:
        result = await aping(client)
        assert result.version == "1"
        copy = client.with_options(max_retries=0)
        assert copy.max_retries == 0
        await copy.close()
    assert recorder.requests[0].headers["Authorization"] == "Bearer k"
