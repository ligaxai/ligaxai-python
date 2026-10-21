"""Webhook signature verification (Standard Webhooks).

The server signs each delivery with the ``webhook-id`` / ``webhook-timestamp`` /
``webhook-signature`` headers defined by https://www.standardwebhooks.com. This wraps the
reference ``standardwebhooks`` implementation so the caller gets this SDK's exception type
and a parsed body in one call. Always verify against the **raw** request bytes — any
re-serialisation (even ``json.dumps(json.loads(...))``) changes the signature input.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from standardwebhooks import Webhook
from standardwebhooks import WebhookVerificationError as _UpstreamError

from ._exceptions import WebhookVerificationError

__all__ = ["verify"]

_REQUIRED_HEADERS = ("webhook-id", "webhook-timestamp", "webhook-signature")


def verify(payload: bytes, headers: Mapping[str, str], secret: str) -> Any:
    """Verify ``payload`` against ``headers`` with ``secret``; return the parsed JSON body.

    ``headers`` may be any case (``Webhook-Id`` or ``webhook-id``). ``secret`` is the
    endpoint secret as shown in the dashboard (``whsec_...`` prefix optional).

    Raises:
        WebhookVerificationError: missing headers, bad signature, or a timestamp outside
            the tolerance window (replay protection).
    """
    normalised = {k.lower(): v for k, v in headers.items()}
    missing = [h for h in _REQUIRED_HEADERS if h not in normalised]
    if missing:
        raise WebhookVerificationError(f"Missing webhook headers: {', '.join(missing)}")
    try:
        return Webhook(secret).verify(payload, normalised)
    except _UpstreamError as exc:
        raise WebhookVerificationError(
            str(exc) or "Webhook signature verification failed."
        ) from exc
