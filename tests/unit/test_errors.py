from __future__ import annotations

import httpx2
import pytest

from ligaxai import (
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from tests.conftest import (
    Recorder,
    aping,
    error_body,
    json_response,
    make_async_client,
    make_sync_client,
    ping,
    run_body,
)


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (402, PaymentRequiredError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, InternalServerError),
        (502, InternalServerError),
        (599, InternalServerError),
        (418, APIStatusError),
    ],
)
def test_status_mapping(status: int, cls: type[APIStatusError], recorder: Recorder) -> None:
    recorder.responses = [json_response(status, error_body("nope", code=f"c{status}"))]
    with pytest.raises(cls) as exc_info:
        ping(make_sync_client(recorder, max_retries=0))
    err = exc_info.value
    assert type(err) is cls
    assert err.status_code == status
    assert err.code == f"c{status}"
    assert err.message == "nope"
    assert err.response.status_code == status
    assert err.request is not None


def test_request_id_from_body_beats_header(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(400, error_body("x", request_id="req_body"), {"x-request-id": "req_hdr"})
    ]
    with pytest.raises(BadRequestError) as exc_info:
        ping(make_sync_client(recorder))
    assert exc_info.value.request_id == "req_body"


def test_request_id_from_header_when_body_lacks_it(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(404, {"error": {"message": "gone"}}, {"x-request-id": "req_hdr"})
    ]
    with pytest.raises(NotFoundError) as exc_info:
        ping(make_sync_client(recorder))
    err = exc_info.value
    assert err.request_id == "req_hdr"
    assert err.code is None
    assert err.type is None
    assert err.param is None


def test_error_fields_and_str(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(
            422,
            {
                "error": {
                    "type": "invalid_request_error",
                    "code": "param_invalid",
                    "message": "bad param",
                    "param": "name",
                    "request_id": "req_9",
                }
            },
        )
    ]
    with pytest.raises(UnprocessableEntityError) as exc_info:
        ping(make_sync_client(recorder))
    err = exc_info.value
    assert err.type == "invalid_request_error"
    assert err.param == "name"
    assert err.body == {
        "error": {
            "type": "invalid_request_error",
            "code": "param_invalid",
            "message": "bad param",
            "param": "name",
            "request_id": "req_9",
        }
    }
    assert str(err) == "bad param (code=param_invalid) (request_id=req_9)"


def test_non_json_body(recorder: Recorder) -> None:
    recorder.responses = [httpx2.Response(502, content=b"<html>bad gateway</html>")]
    with pytest.raises(InternalServerError) as exc_info:
        ping(make_sync_client(recorder, max_retries=0))
    assert exc_info.value.message == "<html>bad gateway</html>"
    assert exc_info.value.body is None


def test_empty_body_uses_status_message(recorder: Recorder) -> None:
    recorder.responses = [httpx2.Response(401)]
    with pytest.raises(AuthenticationError) as exc_info:
        ping(make_sync_client(recorder))
    assert exc_info.value.message == "Error code: 401"


async def test_async_error_mapping(recorder: Recorder) -> None:
    recorder.responses = [json_response(401, error_body("bad key", code="invalid_api_key"))]
    client = make_async_client(recorder)
    with pytest.raises(AuthenticationError) as exc_info:
        await aping(client)
    assert exc_info.value.code == "invalid_api_key"
    await client.close()


# -- the public API's envelope, on real endpoints ------------------------------------------


def _envelope(type_: str, code: str, message: str, param: str | None = None) -> dict[str, object]:
    err: dict[str, object] = {
        "type": type_,
        "code": code,
        "message": message,
        "request_id": "req_body",
    }
    if param is not None:
        err["param"] = param
    return {"error": err}


def test_envelope_fields_on_runs_create(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [
        json_response(
            422,
            _envelope(
                "invalid_request_error",
                "idempotency_key_reused",
                "This Idempotency-Key was already used with a different request.",
                "Idempotency-Key",
            ),
            {"x-request-id": "req_header"},
        )
    ]
    with pytest.raises(UnprocessableEntityError) as exc_info:
        make_sync_client(recorder).runs.create(profile_id="prf_" + "A" * 20, input="x")
    err = exc_info.value
    assert err.status_code == 422
    assert err.type == "invalid_request_error"
    assert err.code == "idempotency_key_reused"
    assert err.param == "Idempotency-Key"
    assert err.request_id == "req_body"  # the body wins over the header
    assert err.message.startswith("This Idempotency-Key")
    assert len(recorder.requests) == 1  # 422 is never retried
    assert no_sleep == []


@pytest.mark.parametrize("status", [402, 403, 422])
def test_payment_permission_and_validation_are_never_retried(
    recorder: Recorder, no_sleep: list[float], status: int
) -> None:
    recorder.responses = [
        json_response(
            status,
            _envelope("billing_error", "key_limit_reached", "Limit reached."),
            {"retry-after": "1"},
        ),
        json_response(),
    ]
    with pytest.raises(APIStatusError) as exc_info:
        make_sync_client(recorder, max_retries=5).runs.create(profile_id="prf_x", input="x")
    assert exc_info.value.status_code == status
    assert len(recorder.requests) == 1
    assert no_sleep == []


async def test_402_maps_to_payment_required_async(
    recorder: Recorder, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(
            402,
            _envelope("billing_error", "key_limit_reached", "This key reached its limit."),
            {"x-limit-resets-at": "2026-11-01T00:00:00.000Z"},
        )
    ]
    client = make_async_client(recorder, max_retries=3)
    with pytest.raises(PaymentRequiredError) as exc_info:
        await client.runs.create(profile_id="prf_x", input="x")
    assert exc_info.value.code == "key_limit_reached"
    assert exc_info.value.response.headers["x-limit-resets-at"].startswith("2026-11-01")
    assert len(recorder.requests) == 1
    await client.close()


def test_429_retry_after_is_honoured_on_runs_create(
    recorder: Recorder, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(
            429,
            _envelope("rate_limit_error", "rate_limited", "Too many requests."),
            {"retry-after": "60"},
        ),
        json_response(200, run_body()),
    ]
    run = make_sync_client(recorder).runs.create(profile_id="prf_x", input="x")
    assert run.status == "completed"
    assert no_sleep == [60.0]
    keys = {r.headers["Idempotency-Key"] for r in recorder.requests}
    assert len(keys) == 1


def test_429_exhausted_raises_rate_limit_error(recorder: Recorder, no_sleep: list[float]) -> None:
    recorder.responses = [
        json_response(
            429, _envelope("rate_limit_error", "rate_limited", "Slow down."), {"retry-after": "2"}
        )
    ]
    with pytest.raises(RateLimitError) as exc_info:
        make_sync_client(recorder, max_retries=1).keys.self()
    assert exc_info.value.code == "rate_limited"
    assert no_sleep == [2.0]
