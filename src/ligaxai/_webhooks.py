"""Webhook verification and typed events — the implementation behind ``ligaxai.webhooks``.

Private so that ``fastapi.py`` can build on it while both public helper modules stay
leaves (nothing in the package imports ``webhooks.py`` or ``fastapi.py``).

The server signs each delivery per https://www.standardwebhooks.com — ``webhook-id``,
``webhook-timestamp`` (unix seconds) and ``webhook-signature: v1,<base64 HMAC-SHA256>``
over ``id.timestamp.body``, several space-separated signatures during a secret rotation.
This wraps the reference ``standardwebhooks`` implementation rather than re-deriving it,
so the receiver and every other Standard Webhooks consumer agree by construction.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, TypeAlias, cast

from pydantic import Field
from standardwebhooks import Webhook
from standardwebhooks import WebhookVerificationError as _UpstreamError

from ._exceptions import WebhookVerificationError
from ._generated.models import (
    ApiKeyLimitWebhookEvent,
    RunWebhookEvent,
    WebhookTestEvent,
    WebhookTestEventData,
)
from ._models import BaseModel

__all__ = [
    "ConnectionCreatedWebhookEvent",
    "ConnectionCreatedWebhookEventData",
    "ConnectionDeletedWebhookEvent",
    "ConnectionDeletedWebhookEventData",
    "UnknownWebhookEvent",
    "WebhookEvent",
    "WebhookTestEvent",
    "WebhookTestEventData",
    "parse_event",
    "verify",
    "verify_signature",
]

_REQUIRED_HEADERS = ("webhook-id", "webhook-timestamp", "webhook-signature")
_RUN_TYPES = frozenset({"run.completed", "run.failed", "run.canceled", "run.requires_action"})


class UnknownWebhookEvent(BaseModel):
    """An event type this SDK version does not know yet. Signed and genuine — the server
    added a type after this release — so answer 2xx and ignore it, or read ``data``."""

    type: str
    timestamp: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# The `connection.*` events are hand-written: the platform sends them (spec 0.3.0 accepts
# them in `event_types`) but its spec's top-level `webhooks` section does not describe their
# bodies yet, so the generator has nothing to read. Shapes follow `end-user-connections.ts`.
# Move them to `SCHEMA_NAMES` in `scripts/gen_types.py` once the spec carries them.


class ConnectionCreatedWebhookEventData(BaseModel):
    """The connection an end user just made — ids and a status, never the credential."""

    object: Literal["connection"]
    id: str
    end_user_id: str
    status: str


class ConnectionCreatedWebhookEvent(BaseModel):
    """``connection.created``: an end user's connect session was first seen to succeed.
    ``end_users.connections.list(event.data.end_user_id)`` has the details."""

    type: Literal["connection.created"]
    timestamp: str
    data: ConnectionCreatedWebhookEventData


class ConnectionDeletedWebhookEventData(BaseModel):
    object: Literal["connection"]
    id: str
    connector_key: str
    end_user_id: str


class ConnectionDeletedWebhookEvent(BaseModel):
    """``connection.deleted``: an end user's own account was disconnected through the API."""

    type: Literal["connection.deleted"]
    timestamp: str
    data: ConnectionDeletedWebhookEventData


#: Every event ``verify`` can return. Narrow with ``isinstance`` (or ``match``); ``type``
#: tells the four ``run.*`` events apart.
WebhookEvent: TypeAlias = (
    RunWebhookEvent
    | ApiKeyLimitWebhookEvent
    | ConnectionCreatedWebhookEvent
    | ConnectionDeletedWebhookEvent
    | WebhookTestEvent
    | UnknownWebhookEvent
)


def parse_event(payload: bytes | str | Mapping[str, Any]) -> WebhookEvent:
    """Parse an already-verified body into its event model, dispatching on ``type``.

    An unrecognised ``type`` becomes :class:`UnknownWebhookEvent` rather than an error, so a
    receiver keeps working when the server adds an event.

    Raises:
        ValueError: the body is not JSON, has no string ``type``, or a known event is
            missing a required field (``pydantic.ValidationError`` is a ``ValueError``).
    """
    body: Any = json.loads(payload) if isinstance(payload, bytes | str) else payload
    kind: object = (
        cast("Mapping[str, Any]", body).get("type") if isinstance(body, Mapping) else None
    )
    if kind in _RUN_TYPES:
        return RunWebhookEvent.model_validate(body)
    if kind == "api_key.limit_reached":
        return ApiKeyLimitWebhookEvent.model_validate(body)
    if kind == "connection.created":
        return ConnectionCreatedWebhookEvent.model_validate(body)
    if kind == "connection.deleted":
        return ConnectionDeletedWebhookEvent.model_validate(body)
    if kind == "webhook.test":
        return WebhookTestEvent.model_validate(body)
    if isinstance(kind, str):
        return UnknownWebhookEvent.model_validate(body)
    raise ValueError("Webhook body is not an event: expected a JSON object with a 'type'.")


def verify_signature(payload: bytes | str, headers: Mapping[str, str], secret: str) -> None:
    """Check ``payload``'s Standard Webhooks signature and timestamp; return nothing.

    Use it when you want the body as something other than an event model. Accepts any
    header case, any one of several space-separated signatures (a rotation), and a
    timestamp within five minutes of now (replay protection).

    Raises:
        WebhookVerificationError: missing headers, no matching signature, or a timestamp
            outside the tolerance window.
        ValueError: ``secret`` is not a ``whsec_…`` signing secret.
    """
    normalised = {k.lower(): v for k, v in headers.items()}
    missing = [h for h in _REQUIRED_HEADERS if not normalised.get(h)]
    if missing:
        raise WebhookVerificationError(f"Missing webhook headers: {', '.join(missing)}")
    try:
        webhook = Webhook(secret)
    except Exception as exc:  # binascii.Error, EmptyWebhookSecretError
        raise ValueError("secret is not a valid webhook signing secret (whsec_…)") from exc
    try:
        webhook.verify(payload, normalised, json_parse=False)
    except (_UpstreamError, ValueError) as exc:
        # ValueError: a malformed signature list (no `v1,` comma, bad base64) — a forgery
        # or a broken proxy, never a reason to answer 500.
        raise WebhookVerificationError(
            str(exc) or "Webhook signature verification failed."
        ) from exc


def verify(payload: bytes | str, headers: Mapping[str, str], secret: str) -> WebhookEvent:
    """Verify a delivery and return its typed event.

    Pass the **raw** request body: any re-serialisation (even
    ``json.dumps(json.loads(...))``) changes the bytes that were signed. ``headers`` may be
    any case; ``secret`` is the endpoint's ``whsec_…`` secret from ``webhooks.create``.

    Raises:
        WebhookVerificationError: see :func:`verify_signature`.
        ValueError: genuine but not an event body; see :func:`parse_event`.
    """
    verify_signature(payload, headers, secret)
    return parse_event(payload)
