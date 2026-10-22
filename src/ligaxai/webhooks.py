"""Receive LigaX webhooks: verify the Standard Webhooks signature, get a typed event.

Usage::

    from ligaxai import webhooks
    from ligaxai.types import RunWebhookEvent

    event = webhooks.verify(raw_body, request_headers, secret="whsec_...")
    if isinstance(event, RunWebhookEvent) and event.type == "run.completed":
        run = client.runs.get(event.data.id)   # payloads are thin: fetch the answer

Always verify against the **raw** request bytes. Deliveries are at-least-once: dedupe on
the ``webhook-id`` header, and answer 2xx within 15 s (do the work afterwards).
"""

from ._webhooks import (
    ConnectionCreatedWebhookEvent,
    ConnectionDeletedWebhookEvent,
    UnknownWebhookEvent,
    WebhookEvent,
    WebhookTestEvent,
    parse_event,
    verify,
    verify_signature,
)

__all__ = [
    "ConnectionCreatedWebhookEvent",
    "ConnectionDeletedWebhookEvent",
    "UnknownWebhookEvent",
    "WebhookEvent",
    "WebhookTestEvent",
    "parse_event",
    "verify",
    "verify_signature",
]
