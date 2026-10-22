"""``client.connect_sessions`` and ``client.end_users.connections`` — an end user connecting
and managing their own accounts, sync and async alike."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx2
import pytest

from ligaxai import (
    AsyncLigaX,
    ConflictError,
    LigaX,
    NotFoundError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from ligaxai.resources import connect_sessions as connect_sessions_module
from ligaxai.types import (
    ConnectSession,
    EndUserConnection,
    EndUserConnectionDeleted,
    EndUserConnectionList,
)
from tests.conftest import (
    PROFILE_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_sync_client,
)

SESSION_ID = "flow_123"
CONNECTION_ID = "conn_456"


def session_body(**overrides: Any) -> dict[str, Any]:
    """A complete ``ConnectSession`` as the server presents it."""
    body: dict[str, Any] = {
        "object": "connect_session",
        "id": SESSION_ID,
        "status": "pending",
        "connect_url": "https://enterprise.ligax.ai/connect/flow_123",
        "expires_at": "2026-10-22T08:10:00.000Z",
        "connector_key": "gmail",
        "end_user_id": "user-42",
        "connection_id": None,
        "failure_code": None,
    }
    body.update(overrides)
    return body


def connection_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "object": "connection",
        "id": CONNECTION_ID,
        "connector_key": "gmail",
        "display_name": "ada@example.com",
        "status": "active",
        "status_code": None,
    }
    body.update(overrides)
    return body


ClientFactory = Callable[..., LigaX | AsyncLigaX]


@pytest.fixture(params=[make_sync_client, make_async_client], ids=["sync", "async"])
def factory(request: pytest.FixtureRequest) -> ClientFactory:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture
def poll_sleeps(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[float]]:
    """Capture the polling delays of ``connect_sessions.wait`` instead of sleeping."""
    delays: list[float] = []

    def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(connect_sessions_module, "_sleep", fake_sleep)
    monkeypatch.setattr(connect_sessions_module, "_async_sleep", fake_async_sleep)
    yield delays


async def resolve(result: Any) -> Any:
    if hasattr(result, "__await__"):
        return await result
    return result


def body_of(req: httpx2.Request) -> Any:
    return json.loads(req.content)


# -- connect_sessions.create ---------------------------------------------------------------


async def test_create_with_string_end_user(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(201, session_body(), {"x-request-id": "req_cs"})]
    client = factory(recorder)
    session = await resolve(
        client.connect_sessions.create(
            connector_key="gmail", profile_id=PROFILE_ID, end_user="user-42"
        )
    )
    req = recorder.requests[0]
    assert req.method == "POST" and req.url.path.endswith("/connect_sessions")
    assert body_of(req) == {
        "connector_key": "gmail",
        "profile_id": PROFILE_ID,
        "end_user": {"id": "user-42"},
    }
    assert isinstance(session, ConnectSession)
    assert session.status == "pending" and session.connect_url is not None
    assert session.connection_id is None and session.request_id == "req_cs"


async def test_create_sends_only_what_is_given(recorder: Recorder, factory: ClientFactory) -> None:
    # A client token names its own profile and end user, so neither is required.
    recorder.responses = [json_response(201, session_body())]
    await resolve(factory(recorder).connect_sessions.create(connector_key="gmail"))
    assert body_of(recorder.requests[0]) == {"connector_key": "gmail"}


async def test_create_with_end_user_mapping(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(201, session_body())]
    await resolve(
        factory(recorder).connect_sessions.create(
            connector_key="outlook", end_user={"id": "user-42", "name": "Ada"}
        )
    )
    assert body_of(recorder.requests[0]) == {
        "connector_key": "outlook",
        "end_user": {"id": "user-42", "name": "Ada"},
    }


async def test_create_refuses_an_empty_connector_key(
    recorder: Recorder, factory: ClientFactory
) -> None:
    with pytest.raises(ValueError, match="connector_key"):
        await resolve(factory(recorder).connect_sessions.create(connector_key=""))
    assert recorder.requests == []


@pytest.mark.parametrize(
    ("status", "code", "exc", "attempts"),
    [
        # 409 is retryable by the shared policy (an idempotent request still in flight), and
        # the platform does not send `x-should-retry: false` with this one, so it is tried
        # three times before it surfaces. 403 and 422 are never retried.
        (409, "end_user_connections_off", ConflictError, 3),
        (422, "connector_not_available", UnprocessableEntityError, 1),
        (422, "connector_not_connectable", UnprocessableEntityError, 1),
        (403, "token_scope", PermissionDeniedError, 1),
    ],
)
async def test_create_errors(
    recorder: Recorder,
    factory: ClientFactory,
    no_sleep: list[float],
    status: int,
    code: str,
    exc: type[Exception],
    attempts: int,
) -> None:
    recorder.responses = [json_response(status, error_body("no", code=code))]
    with pytest.raises(exc) as info:
        await resolve(factory(recorder).connect_sessions.create(connector_key="gmail"))
    assert getattr(info.value, "code", None) == code
    assert len(recorder.requests) == attempts


async def test_create_conflict_honours_should_retry_false(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(
            409, error_body("off", code="end_user_connections_off"), {"x-should-retry": "false"}
        )
    ]
    with pytest.raises(ConflictError):
        await resolve(factory(recorder).connect_sessions.create(connector_key="gmail"))
    assert len(recorder.requests) == 1


# -- connect_sessions.get / wait -----------------------------------------------------------


async def test_get_passes_end_user_id(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, session_body(status="succeeded"))]
    session = await resolve(
        factory(recorder).connect_sessions.get(SESSION_ID, end_user_id="user-42")
    )
    req = recorder.requests[0]
    assert req.method == "GET" and req.url.path.endswith(f"/connect_sessions/{SESSION_ID}")
    assert req.url.params["end_user_id"] == "user-42"
    assert session.status == "succeeded"


async def test_get_without_end_user_id_sends_no_query(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(200, session_body())]
    await resolve(factory(recorder).connect_sessions.get(SESSION_ID))
    assert "end_user_id" not in recorder.requests[0].url.params


async def test_get_refuses_an_empty_id(recorder: Recorder, factory: ClientFactory) -> None:
    with pytest.raises(ValueError, match="session_id"):
        await resolve(factory(recorder).connect_sessions.get(""))
    assert recorder.requests == []


async def test_wait_polls_until_succeeded(
    recorder: Recorder, factory: ClientFactory, poll_sleeps: list[float]
) -> None:
    recorder.responses = [
        json_response(200, session_body()),
        json_response(200, session_body()),
        json_response(
            200,
            session_body(status="succeeded", connect_url=None, connection_id=CONNECTION_ID),
        ),
    ]
    session = await resolve(
        factory(recorder).connect_sessions.wait(
            SESSION_ID, end_user_id="user-42", poll_interval=0.5
        )
    )
    assert session.status == "succeeded" and session.connection_id == CONNECTION_ID
    assert len(recorder.requests) == 3
    assert all(r.url.params["end_user_id"] == "user-42" for r in recorder.requests)
    assert poll_sleeps == [0.5, 0.5]


@pytest.mark.parametrize("outcome", ["denied", "failed", "expired"])
async def test_wait_returns_other_outcomes(
    recorder: Recorder, factory: ClientFactory, poll_sleeps: list[float], outcome: str
) -> None:
    recorder.responses = [
        json_response(200, session_body(status=outcome, failure_code="access_denied"))
    ]
    session = await resolve(factory(recorder).connect_sessions.wait(SESSION_ID))
    assert session.status == outcome and session.failure_code == "access_denied"
    assert poll_sleeps == []


async def test_wait_times_out(
    recorder: Recorder, factory: ClientFactory, poll_sleeps: list[float]
) -> None:
    # timeout=0: the deadline has passed by the first check, so no clock patching is needed.
    recorder.responses = [json_response(200, session_body())]
    with pytest.raises(TimeoutError, match=SESSION_ID):
        await resolve(factory(recorder).connect_sessions.wait(SESSION_ID, timeout=0))
    assert len(recorder.requests) == 1 and poll_sleeps == []


async def test_wait_without_timeout_keeps_polling(
    recorder: Recorder, factory: ClientFactory, poll_sleeps: list[float]
) -> None:
    recorder.responses = [json_response(200, session_body())] * 4 + [
        json_response(200, session_body(status="expired"))
    ]
    session = await resolve(factory(recorder).connect_sessions.wait(SESSION_ID, timeout=None))
    assert session.status == "expired" and poll_sleeps == [2.0] * 4


# -- end_users.connections -----------------------------------------------------------------


async def test_list_connections(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, {"object": "list", "data": [connection_body()], "has_more": False})
    ]
    page = await resolve(factory(recorder).end_users.connections.list("user/42"))
    req = recorder.requests[0]
    assert req.method == "GET"
    # The end user id is your system's id: anything goes, so it is percent-encoded.
    assert req.url.raw_path.endswith(b"/end_users/user%2F42/connections")
    assert isinstance(page, EndUserConnectionList)
    assert isinstance(page.data[0], EndUserConnection)
    assert page.data[0].display_name == "ada@example.com" and page.has_more is False


async def test_delete_connection(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, {"object": "connection", "id": CONNECTION_ID, "deleted": True})
    ]
    deleted = await resolve(
        factory(recorder).end_users.connections.delete("user-42", CONNECTION_ID)
    )
    req = recorder.requests[0]
    assert req.method == "DELETE"
    assert req.url.path.endswith(f"/end_users/user-42/connections/{CONNECTION_ID}")
    assert isinstance(deleted, EndUserConnectionDeleted) and deleted.deleted is True


async def test_delete_unknown_connection(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(404, error_body("gone", type_="not_found_error", code="connection_not_found"))
    ]
    with pytest.raises(NotFoundError):
        await resolve(factory(recorder).end_users.connections.delete("user-42", "conn_x"))


async def test_connections_refuse_empty_ids(recorder: Recorder, factory: ClientFactory) -> None:
    client = factory(recorder)
    with pytest.raises(ValueError, match="end_user_id"):
        await resolve(client.end_users.connections.list(""))
    with pytest.raises(ValueError, match="connection_id"):
        await resolve(client.end_users.connections.delete("user-42", ""))
    assert recorder.requests == []
