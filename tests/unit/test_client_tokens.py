"""``client.client_tokens`` — minting a browser token, sync and async alike — and a client
that presents such a token instead of a secret key."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from ligaxai import AsyncLigaX, BadRequestError, LigaX, PermissionDeniedError
from ligaxai.types import ClientToken
from tests.conftest import (
    CONVERSATION_ID,
    PROFILE_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_sync_client,
    run_body,
)

# Not a real token: the documented prefix and an obviously fake body.
TEST_CLIENT_TOKEN = "lgx_ct_" + "e30" + "." + "A" * 43


def token_body(**overrides: Any) -> dict[str, Any]:
    """A complete ``ClientToken`` as the server presents it."""
    body: dict[str, Any] = {
        "object": "client_token",
        "token": TEST_CLIENT_TOKEN,
        "expires_at": "2026-10-22T08:10:00.000Z",
        "profile_id": PROFILE_ID,
        "end_user_id": "user_42",
        "conversation_id": None,
    }
    body.update(overrides)
    return body


async def call(client: LigaX | AsyncLigaX, *args: Any, **kwargs: Any) -> Any:
    result = client.client_tokens.create(*args, **kwargs)
    if isinstance(client, AsyncLigaX):
        result = await result
    return result


ClientFactory = Callable[..., LigaX | AsyncLigaX]


@pytest.fixture(params=[make_sync_client, make_async_client], ids=["sync", "async"])
def factory(request: pytest.FixtureRequest) -> ClientFactory:
    return request.param  # type: ignore[no-any-return]


def body_of(req: httpx2.Request) -> Any:
    return json.loads(req.content)


async def test_create_with_string_end_user(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(201, token_body(), {"x-request-id": "req_ct"})]
    token = await call(factory(recorder), profile_id=PROFILE_ID, end_user="user_42")
    req = recorder.requests[0]
    assert req.method == "POST" and req.url.path.endswith("/client_tokens")
    # Server defaults apply: nothing optional is sent.
    assert body_of(req) == {"profile_id": PROFILE_ID, "end_user": {"id": "user_42"}}
    assert isinstance(token, ClientToken)
    assert token.token == TEST_CLIENT_TOKEN and token.end_user_id == "user_42"
    assert token.conversation_id is None and token.request_id == "req_ct"


async def test_create_with_every_field(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(201, token_body(conversation_id=CONVERSATION_ID))]
    token = await call(
        factory(recorder),
        profile_id=PROFILE_ID,
        end_user={"id": "user_42", "name": "Ada"},
        conversation_id=CONVERSATION_ID,
        expires_in=120,
    )
    assert body_of(recorder.requests[0]) == {
        "profile_id": PROFILE_ID,
        "end_user": {"id": "user_42", "name": "Ada"},
        "conversation_id": CONVERSATION_ID,
        "expires_in": 120,
    }
    assert token.conversation_id == CONVERSATION_ID


async def test_empty_end_user_is_refused_before_a_request(
    recorder: Recorder, factory: ClientFactory
) -> None:
    with pytest.raises(ValueError, match="end_user"):
        await call(factory(recorder), profile_id=PROFILE_ID, end_user="")
    assert recorder.requests == []


async def test_missing_scope_is_permission_denied(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(
            403,
            error_body(
                "This key lacks client_tokens:write.",
                type_="permission_error",
                code="insufficient_scope",
            ),
        )
    ]
    with pytest.raises(PermissionDeniedError) as info:
        await call(factory(recorder), profile_id=PROFILE_ID, end_user="user_42")
    assert info.value.code == "insufficient_scope"
    # 403 is never retried.
    assert len(recorder.requests) == 1


async def test_out_of_range_expiry_surfaces_the_param(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(
            400,
            error_body(
                "Number must be less than or equal to 3600",
                type_="invalid_request_error",
                code="invalid_request",
            ),
        )
    ]
    with pytest.raises(BadRequestError):
        await call(factory(recorder), profile_id=PROFILE_ID, end_user="user_42", expires_in=7200)
    assert body_of(recorder.requests[0])["expires_in"] == 7200


async def test_a_client_token_authenticates_a_run(
    recorder: Recorder, factory: ClientFactory
) -> None:
    """A client constructed with ``lgx_ct_…`` presents it as the bearer, like a secret key."""
    recorder.responses = [json_response(200, run_body(end_user_id="user_42"))]
    client = factory(recorder, api_key=TEST_CLIENT_TOKEN)
    result = client.runs.create(profile_id=PROFILE_ID, input="Hi", end_user="user_42")
    run = await result if isinstance(client, AsyncLigaX) else result
    assert recorder.requests[0].headers["authorization"] == f"Bearer {TEST_CLIENT_TOKEN}"
    assert run.end_user_id == "user_42"


def test_client_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGAX_API_KEY", TEST_CLIENT_TOKEN)
    assert LigaX().api_key == TEST_CLIENT_TOKEN
