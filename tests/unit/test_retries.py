from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx2
import pytest

from ligaxai import (
    APIConnectionError,
    APITimeoutError,
    BaseModel,
    InternalServerError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    RequestOptions,
)
from ligaxai._base_client import BaseClient
from tests.conftest import Recorder, error_body, json_response, make_async_client, make_sync_client


class Thing(BaseModel):
    id: str


def test_429_with_retry_after_seconds(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [
        json_response(429, error_body("slow down"), {"retry-after": "3"}),
        json_response(),
    ]
    assert make_sync_client(recorder).health.get().status == "ok"
    assert len(recorder.requests) == 2
    assert no_sleep == [3.0]


def test_retry_after_ms_wins_over_retry_after(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [
        json_response(429, error_body("x"), {"retry-after-ms": "250", "retry-after": "9"}),
        json_response(),
    ]
    make_sync_client(recorder).health.get()
    assert no_sleep == [0.25]


def test_retry_after_http_date(recorder: Recorder, no_sleep: list[float]) -> None:
    when = datetime.now(UTC) + timedelta(seconds=10)
    recorder.responses = [
        json_response(503, None, {"retry-after": format_datetime(when, usegmt=True)}),
        json_response(),
    ]
    make_sync_client(recorder).health.get()
    assert 8.0 < no_sleep[0] <= 10.0


def test_retry_after_above_cap_falls_back_to_backoff(
    recorder: Recorder, no_sleep: list[float]
) -> None:
    recorder.responses = [json_response(429, None, {"retry-after": "900"}), json_response()]
    make_sync_client(recorder).health.get()
    assert 0.375 <= no_sleep[0] <= 0.5


def test_5xx_exponential_backoff_then_raises(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(500, error_body("boom", code="internal"))]
    with pytest.raises(InternalServerError) as exc_info:
        make_sync_client(recorder, max_retries=3).health.get()
    assert len(recorder.requests) == 4
    # 0.5, 1, 2 seconds, each with up to 25% jitter downwards.
    assert 0.375 <= no_sleep[0] <= 0.5
    assert 0.75 <= no_sleep[1] <= 1.0
    assert 1.5 <= no_sleep[2] <= 2.0
    assert exc_info.value.code == "internal"


def test_backoff_caps_at_8s() -> None:
    client = BaseClient(
        api_key="k", base_url="https://x", timeout=None, max_retries=20, default_headers=None
    )
    assert client._retry_delay(10, None) <= 8.0


def test_never_retries_402(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(402, error_body("pay")), json_response()]
    with pytest.raises(PaymentRequiredError):
        make_sync_client(recorder).health.get()
    assert len(recorder.requests) == 1
    assert no_sleep == []


def test_never_retries_403_even_with_retry_after(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(403, error_body("no"), {"retry-after": "1"})]
    with pytest.raises(PermissionDeniedError):
        make_sync_client(recorder).health.get()
    assert len(recorder.requests) == 1


def test_x_should_retry_false_blocks_retry(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(429, None, {"x-should-retry": "false"}), json_response()]
    with pytest.raises(RateLimitError):
        make_sync_client(recorder).health.get()
    assert len(recorder.requests) == 1


def test_x_should_retry_true_forces_retry(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(400, None, {"x-should-retry": "true"}), json_response()]
    make_sync_client(recorder).health.get()
    assert len(recorder.requests) == 2


def test_max_retries_zero_disables(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(500), json_response()]
    with pytest.raises(InternalServerError):
        make_sync_client(recorder, max_retries=0).health.get()
    assert len(recorder.requests) == 1


def test_per_request_max_retries_override(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(500), json_response(500), json_response()]
    make_sync_client(recorder, max_retries=0).health.get(options=RequestOptions(max_retries=2))
    assert len(recorder.requests) == 3


def test_idempotency_key_minted_on_post_and_reused(
    recorder: Recorder, no_sleep: list[float]
) -> None:
    recorder.responses = [json_response(503), json_response(body={"id": "1"})]
    client = make_sync_client(recorder)
    client.request("POST", "/things", cast_to=Thing, json={"a": 1})
    keys = [r.headers["Idempotency-Key"] for r in recorder.requests]
    assert len(keys) == 2
    assert keys[0] == keys[1]
    assert keys[0].startswith("sdk-")


def test_idempotency_key_override(recorder: Recorder) -> None:
    recorder.responses = [json_response(body={"id": "1"})]
    make_sync_client(recorder).request(
        "POST", "/things", cast_to=Thing, options=RequestOptions(idempotency_key="mine")
    )
    assert recorder.requests[0].headers["Idempotency-Key"] == "mine"


def test_connect_error_retried_then_raised(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [httpx2.ConnectError("refused")]
    with pytest.raises(APIConnectionError):
        make_sync_client(recorder).health.get()
    assert len(recorder.requests) == 3


def test_connect_error_recovers(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [httpx2.ConnectError("refused"), json_response()]
    assert make_sync_client(recorder).health.get().status == "ok"


def test_timeout_maps_to_api_timeout_error(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [httpx2.ReadTimeout("slow")]
    with pytest.raises(APITimeoutError) as exc_info:
        make_sync_client(recorder, max_retries=1).health.get()
    assert isinstance(exc_info.value, APIConnectionError)
    assert len(recorder.requests) == 2


async def test_async_retries_mirror_sync(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [
        json_response(429, None, {"retry-after-ms": "100"}),
        httpx2.ConnectError("blip"),
        json_response(),
    ]
    client = make_async_client(recorder, max_retries=2)
    assert (await client.health.get()).status == "ok"
    assert len(recorder.requests) == 3
    assert no_sleep[0] == 0.1
    await client.close()


async def test_async_never_retries_402(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [json_response(402, error_body("pay"))]
    client = make_async_client(recorder)
    with pytest.raises(PaymentRequiredError):
        await client.health.get()
    assert len(recorder.requests) == 1


async def test_async_timeout_exhausts(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [httpx2.ConnectTimeout("slow")]
    client = make_async_client(recorder, max_retries=0)
    with pytest.raises(APITimeoutError):
        await client.health.get()
