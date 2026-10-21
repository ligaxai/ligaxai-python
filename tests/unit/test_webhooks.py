from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from standardwebhooks import Webhook

from ligaxai import WebhookVerificationError, webhooks

SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
PAYLOAD = json.dumps({"type": "run.completed", "data": {"id": "run_1"}}).encode()


def signed_headers(
    payload: bytes = PAYLOAD, *, at: datetime | None = None, msg_id: str = "msg_1"
) -> dict[str, str]:
    ts = at or datetime.now(UTC)
    sig = Webhook(SECRET).sign(msg_id, ts, payload.decode())
    return {
        "Webhook-Id": msg_id,
        "Webhook-Timestamp": str(int(ts.timestamp())),
        "Webhook-Signature": sig,
    }


def test_valid_signature_returns_parsed_body() -> None:
    body = webhooks.verify(PAYLOAD, signed_headers(), SECRET)
    assert body["type"] == "run.completed"


def test_header_case_is_insensitive() -> None:
    headers = {k.lower(): v for k, v in signed_headers().items()}
    assert webhooks.verify(PAYLOAD, headers, SECRET)["data"]["id"] == "run_1"


def test_tampered_payload_fails() -> None:
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(PAYLOAD + b" ", signed_headers(), SECRET)


def test_wrong_secret_fails() -> None:
    other = "whsec_" + base64.b64encode(b"x" * 32).decode()
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(PAYLOAD, signed_headers(), other)


def test_expired_timestamp_fails() -> None:
    old = datetime.now(UTC) - timedelta(minutes=10)
    with pytest.raises(WebhookVerificationError):
        webhooks.verify(PAYLOAD, signed_headers(at=old), SECRET)


def test_missing_headers_fail_with_clear_message() -> None:
    with pytest.raises(WebhookVerificationError, match="webhook-signature"):
        webhooks.verify(PAYLOAD, {"webhook-id": "x", "webhook-timestamp": "1"}, SECRET)
