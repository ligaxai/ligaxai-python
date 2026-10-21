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
from tests.conftest import Recorder, error_body, json_response, make_async_client, make_sync_client


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
        make_sync_client(recorder, max_retries=0).health.get()
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
        make_sync_client(recorder).health.get()
    assert exc_info.value.request_id == "req_body"


def test_request_id_from_header_when_body_lacks_it(recorder: Recorder) -> None:
    recorder.responses = [
        json_response(404, {"error": {"message": "gone"}}, {"x-request-id": "req_hdr"})
    ]
    with pytest.raises(NotFoundError) as exc_info:
        make_sync_client(recorder).health.get()
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
        make_sync_client(recorder).health.get()
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
        make_sync_client(recorder, max_retries=0).health.get()
    assert exc_info.value.message == "<html>bad gateway</html>"
    assert exc_info.value.body is None


def test_empty_body_uses_status_message(recorder: Recorder) -> None:
    recorder.responses = [httpx2.Response(401)]
    with pytest.raises(AuthenticationError) as exc_info:
        make_sync_client(recorder).health.get()
    assert exc_info.value.message == "Error code: 401"


async def test_async_error_mapping(recorder: Recorder) -> None:
    recorder.responses = [json_response(401, error_body("bad key", code="invalid_api_key"))]
    client = make_async_client(recorder)
    with pytest.raises(AuthenticationError) as exc_info:
        await client.health.get()
    assert exc_info.value.code == "invalid_api_key"
    await client.close()
