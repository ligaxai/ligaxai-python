"""``client.webhooks``: what each method sends and parses — sync and async alike."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from ligaxai import (
    AsyncLigaX,
    ConflictError,
    LigaX,
    PaymentRequiredError,
    PermissionDeniedError,
    UnprocessableEntityError,
)
from ligaxai.types import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointDeleted,
    WebhookEndpointList,
    WebhookEndpointWithSecret,
)
from tests.conftest import (
    PROFILE_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_sync_client,
)

WEBHOOK_ID = "we_" + "C" * 20
# Not a real secret: the documented shape with a fixed, obviously fake body.
TEST_SECRET = "whsec_" + "A" * 43 + "="


def endpoint_body(**overrides: Any) -> dict[str, Any]:
    """A complete ``WebhookEndpoint`` as the server presents it (``presentOne``)."""
    body: dict[str, Any] = {
        "object": "webhook_endpoint",
        "id": WEBHOOK_ID,
        "url": "https://hooks.example.com/ligax",
        "description": "Zap: new answers",
        "event_types": ["run.completed", "run.failed"],
        "profile_ids": [PROFILE_ID],
        "status": "active",
        "disabled_reason": None,
        "secret_hint": "whsec_…AAA=",
        "created_at": "2026-10-22T08:00:00.000Z",
        "updated_at": "2026-10-22T08:00:00.000Z",
    }
    body.update(overrides)
    return body


DELIVERY = {
    "object": "webhook_delivery",
    "id": "whd_1",
    "event_id": "evt_" + "D" * 24,
    "event_type": "webhook.test",
    "status": "succeeded",
    "attempt": 1,
    "last_status_code": 204,
    "last_error": None,
    "last_attempt_at": "2026-10-22T08:00:01.000Z",
    "next_attempt_at": None,
    "delivered_at": "2026-10-22T08:00:01.000Z",
    "created_at": "2026-10-22T08:00:00.000Z",
}


async def call(client: LigaX | AsyncLigaX, method: str, *args: Any, **kwargs: Any) -> Any:
    result = getattr(client.webhooks, method)(*args, **kwargs)
    if isinstance(client, AsyncLigaX):
        result = await result
    return result


ClientFactory = Callable[[Recorder], LigaX | AsyncLigaX]


@pytest.fixture(params=[make_sync_client, make_async_client], ids=["sync", "async"])
def factory(request: pytest.FixtureRequest) -> ClientFactory:
    return request.param  # type: ignore[no-any-return]


def body_of(req: httpx2.Request) -> Any:
    return json.loads(req.content) if req.content else None


async def test_create_sends_body_and_returns_secret_once(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(201, {**endpoint_body(), "secret": TEST_SECRET}, {"x-request-id": "req_w"})
    ]
    created = await call(
        factory(recorder),
        "create",
        url="https://hooks.example.com/ligax",
        event_types=["run.completed", "run.failed"],
        description="Zap: new answers",
        profile_ids=[PROFILE_ID],
    )
    req = recorder.requests[0]
    assert req.method == "POST" and req.url.path.endswith("/webhooks")
    assert body_of(req) == {
        "url": "https://hooks.example.com/ligax",
        "event_types": ["run.completed", "run.failed"],
        "description": "Zap: new answers",
        "profile_ids": [PROFILE_ID],
    }
    assert req.headers["idempotency-key"].startswith("sdk-")
    assert isinstance(created, WebhookEndpointWithSecret)
    assert created.secret == TEST_SECRET and created.id == WEBHOOK_ID
    assert created.request_id == "req_w"


async def test_create_minimal_body_omits_optional_fields(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(201, {**endpoint_body(), "secret": TEST_SECRET})]
    await call(
        factory(recorder),
        "create",
        url="https://hooks.example.com/ligax",
        event_types=("api_key.limit_reached",),
    )
    assert body_of(recorder.requests[0]) == {
        "url": "https://hooks.example.com/ligax",
        "event_types": ["api_key.limit_reached"],
    }


async def test_list(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, {"object": "list", "data": [endpoint_body()], "has_more": False})
    ]
    page = await call(factory(recorder), "list")
    req = recorder.requests[0]
    assert req.method == "GET" and req.url.path.endswith("/webhooks")
    assert isinstance(page, WebhookEndpointList)
    assert [e.id for e in page.data] == [WEBHOOK_ID]
    assert isinstance(page.data[0], WebhookEndpoint)
    assert "secret" not in page.data[0].model_dump()


async def test_get_and_path_encoding(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, endpoint_body())]
    client = factory(recorder)
    endpoint = await call(client, "get", WEBHOOK_ID)
    assert recorder.requests[0].method == "GET"
    assert recorder.requests[0].url.path.endswith(f"/webhooks/{WEBHOOK_ID}")
    assert isinstance(endpoint, WebhookEndpoint) and endpoint.status == "active"

    await call(client, "get", "we/../x")
    assert recorder.requests[1].url.raw_path.endswith(b"/webhooks/we%2F..%2Fx")
    with pytest.raises(ValueError, match="webhook_id"):
        await call(client, "get", "")


async def test_update_sends_only_named_fields(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, endpoint_body(status="disabled", disabled_reason="manual"))
    ]
    client = factory(recorder)
    endpoint = await call(client, "update", WEBHOOK_ID, status="disabled", profile_ids=[])
    req = recorder.requests[0]
    assert req.method == "PATCH" and req.url.path.endswith(f"/webhooks/{WEBHOOK_ID}")
    # `[]` is a value (every profile), not "unchanged".
    assert body_of(req) == {"status": "disabled", "profile_ids": []}
    assert "idempotency-key" not in req.headers
    assert endpoint.disabled_reason == "manual"

    await call(
        client,
        "update",
        WEBHOOK_ID,
        url="https://hooks.example.com/v2",
        description="",
        event_types=["run.requires_action"],
    )
    assert body_of(recorder.requests[1]) == {
        "url": "https://hooks.example.com/v2",
        "description": "",
        "event_types": ["run.requires_action"],
    }


async def test_delete(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, {"object": "webhook_endpoint", "id": WEBHOOK_ID, "deleted": True})
    ]
    deleted = await call(factory(recorder), "delete", WEBHOOK_ID)
    req = recorder.requests[0]
    assert req.method == "DELETE" and req.url.path.endswith(f"/webhooks/{WEBHOOK_ID}")
    assert isinstance(deleted, WebhookEndpointDeleted)
    assert deleted.deleted is True and deleted.id == WEBHOOK_ID


async def test_test_sends_and_reports_the_delivery(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(200, DELIVERY)]
    delivery = await call(factory(recorder), "test", WEBHOOK_ID)
    req = recorder.requests[0]
    assert req.method == "POST" and req.url.path.endswith(f"/webhooks/{WEBHOOK_ID}/test")
    assert isinstance(delivery, WebhookDelivery)
    assert delivery.status == "succeeded" and delivery.last_status_code == 204


@pytest.mark.parametrize(
    ("status", "code", "exc"),
    [
        (402, "key_limit_reached", PaymentRequiredError),
        (403, "insufficient_scope", PermissionDeniedError),
        (422, "invalid_url", UnprocessableEntityError),
    ],
)
async def test_refusals_are_not_retried(
    recorder: Recorder,
    factory: ClientFactory,
    no_sleep: list[float],
    status: int,
    code: str,
    exc: type[Exception],
) -> None:
    recorder.responses = [
        json_response(status, error_body("no", code=code)),
        json_response(201, {**endpoint_body(), "secret": TEST_SECRET}),
    ]
    with pytest.raises(exc):
        await call(
            factory(recorder),
            "create",
            url="https://hooks.example.com/ligax",
            event_types=["run.completed"],
        )
    assert len(recorder.requests) == 1
    assert no_sleep == []


async def test_test_on_a_disabled_endpoint_is_a_conflict(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(
            409,
            error_body("Enable it first", type_="conflict_error", code="webhook_endpoint_disabled"),
            {"x-should-retry": "false"},
        )
    ]
    with pytest.raises(ConflictError) as info:
        await call(factory(recorder), "test", WEBHOOK_ID)
    assert info.value.code == "webhook_endpoint_disabled"
    assert len(recorder.requests) == 1


# -- webhooks.create is idempotent ----------------------------------------------------

ENDPOINT_WITH_SECRET = {**endpoint_body(), "secret": TEST_SECRET}


async def test_webhooks_create_replay_parses_the_same_endpoint(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(201, ENDPOINT_WITH_SECRET),
        json_response(200, ENDPOINT_WITH_SECRET, {"Idempotent-Replayed": "true"}),
    ]
    client = factory(recorder)
    first = await call(
        client,
        "create",
        url="https://hooks.example.com/ligax",
        event_types=["run.completed"],
        idempotency_key="zap-subscribe-123",
    )
    replay = await call(
        client,
        "create",
        url="https://hooks.example.com/ligax",
        event_types=["run.completed"],
        idempotency_key="zap-subscribe-123",
    )
    assert [r.headers["idempotency-key"] for r in recorder.requests] == ["zap-subscribe-123"] * 2
    assert isinstance(replay, WebhookEndpointWithSecret)
    assert (replay.id, replay.secret) == (first.id, first.secret)


async def test_webhooks_create_concurrent_duplicate_409_is_retried_with_same_key(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(
            409,
            error_body("A request with this key is in progress.", type_="conflict_error"),
            {"x-should-retry": "true", "Retry-After": "1"},
        ),
        json_response(200, ENDPOINT_WITH_SECRET, {"Idempotent-Replayed": "true"}),
    ]
    created = await call(
        factory(recorder),
        "create",
        url="https://hooks.example.com/ligax",
        event_types=["run.completed"],
    )
    keys = {r.headers["idempotency-key"] for r in recorder.requests}
    assert len(recorder.requests) == 2 and len(keys) == 1
    assert next(iter(keys)).startswith("sdk-")
    assert no_sleep == [1.0]
    assert created.secret == TEST_SECRET


async def test_webhooks_create_409_without_retry_hint_after_retries_raises(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(
            409,
            error_body("Key reused with a different body.", type_="conflict_error"),
            {"x-should-retry": "false"},
        )
    ]
    with pytest.raises(ConflictError):
        await call(
            factory(recorder),
            "create",
            url="https://hooks.example.com/ligax",
            event_types=["run.completed"],
        )
    assert len(recorder.requests) == 1
