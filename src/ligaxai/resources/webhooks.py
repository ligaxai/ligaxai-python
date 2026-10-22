"""``/webhooks`` — the endpoints the server delivers events to (scope ``webhooks:manage``).

This is the subscribe/unsubscribe pair a REST-Hooks integration (Zapier, Make, n8n) expects:
``create`` points an endpoint at a catch URL, ``delete`` removes it when the workflow is
switched off. ``create`` is the only call that returns the signing secret — store it then.

To *receive* an event, verify it with :func:`ligaxai.webhooks.verify`; this module only
manages endpoints.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypeAlias

from .._generated.models import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointDeleted,
    WebhookEndpointList,
    WebhookEndpointWithSecret,
)
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, path_segment

__all__ = ["AsyncWebhooks", "WebhookEndpointStatus", "WebhookEventType", "Webhooks"]

#: The events an endpoint can subscribe to. ``webhook.test`` is sent only by :meth:`test`.
WebhookEventType: TypeAlias = Literal[
    "run.completed",
    "run.failed",
    "run.canceled",
    "run.requires_action",
    "api_key.limit_reached",
]
WebhookEndpointStatus: TypeAlias = Literal["active", "disabled"]


def _endpoint_path(webhook_id: str, suffix: str = "") -> str:
    return f"/webhooks/{path_segment(webhook_id, 'webhook_id')}{suffix}"


def _create_body(
    url: str,
    event_types: Sequence[WebhookEventType],
    description: str | None,
    profile_ids: Sequence[str] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url, "event_types": list(event_types)}
    if description is not None:
        body["description"] = description
    if profile_ids is not None:
        body["profile_ids"] = list(profile_ids)
    return body


def _update_body(
    url: str | None,
    description: str | None,
    event_types: Sequence[WebhookEventType] | None,
    profile_ids: Sequence[str] | None,
    status: WebhookEndpointStatus | None,
) -> dict[str, Any]:
    # `None` means "leave unchanged", so only what the caller named is sent. An empty
    # `profile_ids` is a real value — every profile — and is sent as `[]`.
    fields: dict[str, Any] = {
        "url": url,
        "description": description,
        "event_types": list(event_types) if event_types is not None else None,
        "profile_ids": list(profile_ids) if profile_ids is not None else None,
        "status": status,
    }
    return {k: v for k, v in fields.items() if v is not None}


class Webhooks(SyncAPIResource):
    def create(
        self,
        *,
        url: str,
        event_types: Sequence[WebhookEventType],
        description: str | None = None,
        profile_ids: Sequence[str] | None = None,
        options: RequestOptions | None = None,
    ) -> WebhookEndpointWithSecret:
        """Create an endpoint. ``.secret`` (``whsec_…``) is returned **once** — store it now.

        Args:
            url: Where to ``POST`` events: public ``https`` only (the server refuses private
                addresses and redirects).
            event_types: At least one of :data:`WebhookEventType`.
            description: Up to 200 characters, shown in Settings → Developers.
            profile_ids: Narrow ``run.*`` events to these profiles (``prf_…``); omitted or
                empty, every profile. ``api_key.limit_reached`` is never narrowed.
        """
        return self._client.request(
            "POST",
            "/webhooks",
            cast_to=WebhookEndpointWithSecret,
            json=_create_body(url, event_types, description, profile_ids),
            options=options,
        )

    def list(self, *, options: RequestOptions | None = None) -> WebhookEndpointList:
        """Every endpoint in the workspace (``.data``). Secrets are never returned."""
        return self._client.request(
            "GET", "/webhooks", cast_to=WebhookEndpointList, options=options
        )

    def get(self, webhook_id: str, *, options: RequestOptions | None = None) -> WebhookEndpoint:
        """One endpoint (``we_…``)."""
        return self._client.request(
            "GET", _endpoint_path(webhook_id), cast_to=WebhookEndpoint, options=options
        )

    def update(
        self,
        webhook_id: str,
        *,
        url: str | None = None,
        description: str | None = None,
        event_types: Sequence[WebhookEventType] | None = None,
        profile_ids: Sequence[str] | None = None,
        status: WebhookEndpointStatus | None = None,
        options: RequestOptions | None = None,
    ) -> WebhookEndpoint:
        """Change an endpoint; only the arguments given are sent.

        ``status="disabled"`` pauses deliveries; ``"active"`` re-enables an endpoint the
        server disabled after it kept failing (``disabled_reason == "failing"``).
        """
        return self._client.request(
            "PATCH",
            _endpoint_path(webhook_id),
            cast_to=WebhookEndpoint,
            json=_update_body(url, description, event_types, profile_ids, status),
            options=options,
        )

    def delete(
        self, webhook_id: str, *, options: RequestOptions | None = None
    ) -> WebhookEndpointDeleted:
        """Delete an endpoint; pending deliveries to it stop."""
        return self._client.request(
            "DELETE", _endpoint_path(webhook_id), cast_to=WebhookEndpointDeleted, options=options
        )

    def test(self, webhook_id: str, *, options: RequestOptions | None = None) -> WebhookDelivery:
        """Send a ``webhook.test`` event now and report how the receiver answered.

        ``ConflictError`` when the endpoint is disabled.
        """
        return self._client.request(
            "POST", _endpoint_path(webhook_id, "/test"), cast_to=WebhookDelivery, options=options
        )


class AsyncWebhooks(AsyncAPIResource):
    async def create(
        self,
        *,
        url: str,
        event_types: Sequence[WebhookEventType],
        description: str | None = None,
        profile_ids: Sequence[str] | None = None,
        options: RequestOptions | None = None,
    ) -> WebhookEndpointWithSecret:
        """Create an endpoint; the secret is returned once. See :meth:`Webhooks.create`."""
        return await self._client.request(
            "POST",
            "/webhooks",
            cast_to=WebhookEndpointWithSecret,
            json=_create_body(url, event_types, description, profile_ids),
            options=options,
        )

    async def list(self, *, options: RequestOptions | None = None) -> WebhookEndpointList:
        """Every endpoint in the workspace. See :meth:`Webhooks.list`."""
        return await self._client.request(
            "GET", "/webhooks", cast_to=WebhookEndpointList, options=options
        )

    async def get(
        self, webhook_id: str, *, options: RequestOptions | None = None
    ) -> WebhookEndpoint:
        """One endpoint. See :meth:`Webhooks.get`."""
        return await self._client.request(
            "GET", _endpoint_path(webhook_id), cast_to=WebhookEndpoint, options=options
        )

    async def update(
        self,
        webhook_id: str,
        *,
        url: str | None = None,
        description: str | None = None,
        event_types: Sequence[WebhookEventType] | None = None,
        profile_ids: Sequence[str] | None = None,
        status: WebhookEndpointStatus | None = None,
        options: RequestOptions | None = None,
    ) -> WebhookEndpoint:
        """Change an endpoint. See :meth:`Webhooks.update`."""
        return await self._client.request(
            "PATCH",
            _endpoint_path(webhook_id),
            cast_to=WebhookEndpoint,
            json=_update_body(url, description, event_types, profile_ids, status),
            options=options,
        )

    async def delete(
        self, webhook_id: str, *, options: RequestOptions | None = None
    ) -> WebhookEndpointDeleted:
        """Delete an endpoint. See :meth:`Webhooks.delete`."""
        return await self._client.request(
            "DELETE", _endpoint_path(webhook_id), cast_to=WebhookEndpointDeleted, options=options
        )

    async def test(
        self, webhook_id: str, *, options: RequestOptions | None = None
    ) -> WebhookDelivery:
        """Send a ``webhook.test`` event now. See :meth:`Webhooks.test`."""
        return await self._client.request(
            "POST", _endpoint_path(webhook_id, "/test"), cast_to=WebhookDelivery, options=options
        )
