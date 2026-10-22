from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

import pytest
import standardwebhooks.webhooks as upstream
from standardwebhooks import Webhook

from ligaxai import WebhookVerificationError, webhooks
from ligaxai.types import (
    ApiKeyLimitWebhookEvent,
    RunWebhookEvent,
    UnknownWebhookEvent,
    WebhookTestEvent,
)
from tests.conftest import CONVERSATION_ID, PROFILE_ID, RUN_ID

SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()
OLD_SECRET = "whsec_" + base64.b64encode(b"fedcba9876543210fedcba9876543210").decode()

RUN_EVENT: dict[str, Any] = {
    "type": "run.completed",
    "timestamp": "2026-10-22T08:00:05.000Z",
    "data": {
        "object": "run",
        "id": RUN_ID,
        "status": "completed",
        "profile_id": PROFILE_ID,
        "conversation_id": CONVERSATION_ID,
        "end_user_id": None,
        "metadata": {"ticket": "INC001"},
    },
}
PAYLOAD = json.dumps(RUN_EVENT).encode()

# The published Standard Webhooks test vector (also pinned by the platform's signer tests).
SPEC_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
SPEC_ID = "msg_p5jXN8AQM9LWM0D4loKWxJek"
SPEC_TS = 1614265330
SPEC_BODY = b'{"test": 2432232314}'
SPEC_SIGNATURE = "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def signed_headers(
    payload: bytes = PAYLOAD,
    *,
    at: datetime | None = None,
    msg_id: str = "msg_1",
    secrets: tuple[str, ...] = (SECRET,),
) -> dict[str, str]:
    ts = at or datetime.now(UTC)
    sigs = " ".join(Webhook(s).sign(msg_id, ts, payload.decode()) for s in secrets)
    return {
        "Webhook-Id": msg_id,
        "Webhook-Timestamp": str(int(ts.timestamp())),
        "Webhook-Signature": sigs,
    }


@pytest.fixture
def spec_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the verifier's clock just after the vector's timestamp (it is from 2021)."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Frozen:
            return cls.fromtimestamp(SPEC_TS + 10, tz=tz)

    monkeypatch.setattr(upstream, "datetime", Frozen)


def spec_headers(signature: str = SPEC_SIGNATURE) -> dict[str, str]:
    return {
        "webhook-id": SPEC_ID,
        "webhook-timestamp": str(SPEC_TS),
        "webhook-signature": signature,
    }


# -- the specification's vector -------------------------------------------------------


@pytest.mark.usefixtures("spec_clock")
def test_spec_vector_verifies() -> None:
    webhooks.verify_signature(SPEC_BODY, spec_headers(), SPEC_SECRET)


def test_spec_vector_signs_identically() -> None:
    at = datetime.fromtimestamp(SPEC_TS, tz=UTC)
    assert Webhook(SPEC_SECRET).sign(SPEC_ID, at, SPEC_BODY.decode()) == SPEC_SIGNATURE


def test_spec_vector_is_refused_on_the_real_clock() -> None:
    with pytest.raises(WebhookVerificationError, match="too old"):
        webhooks.verify_signature(SPEC_BODY, spec_headers(), SPEC_SECRET)


@pytest.mark.usefixtures("spec_clock")
def test_spec_vector_rotation_any_of_several_signatures() -> None:
    stale = "v1," + base64.b64encode(b"\x00" * 32).decode()
    webhooks.verify_signature(SPEC_BODY, spec_headers(f"{stale} {SPEC_SIGNATURE}"), SPEC_SECRET)
    webhooks.verify_signature(SPEC_BODY, spec_headers(f"{SPEC_SIGNATURE} {stale}"), SPEC_SECRET)
    with pytest.raises(WebhookVerificationError):
        webhooks.verify_signature(SPEC_BODY, spec_headers(f"{stale} {stale}"), SPEC_SECRET)


@pytest.mark.usefixtures("spec_clock")
def test_spec_vector_is_not_an_event() -> None:
    with pytest.raises(ValueError, match="not an event"):
        webhooks.verify(SPEC_BODY, spec_headers(), SPEC_SECRET)


@pytest.mark.usefixtures("spec_clock")
def test_malformed_signature_list_is_a_verification_error() -> None:
    with pytest.raises(WebhookVerificationError):
        webhooks.verify_signature(SPEC_BODY, spec_headers("garbage"), SPEC_SECRET)


# -- typed events ---------------------------------------------------------------------


def test_valid_signature_returns_typed_run_event() -> None:
    event = webhooks.verify(PAYLOAD, signed_headers(), SECRET)
    assert isinstance(event, RunWebhookEvent)
    assert event.type == "run.completed"
    assert event.data.id == RUN_ID and event.data.metadata == {"ticket": "INC001"}
    assert event.data.error_code is None


def test_rotation_both_old_and_new_secret_verify() -> None:
    headers = signed_headers(secrets=(SECRET, OLD_SECRET))
    assert isinstance(webhooks.verify(PAYLOAD, headers, SECRET), RunWebhookEvent)
    assert isinstance(webhooks.verify(PAYLOAD, headers, OLD_SECRET), RunWebhookEvent)


def test_requires_action_carries_the_interrupt() -> None:
    body = {
        **RUN_EVENT,
        "type": "run.requires_action",
        "data": {
            **RUN_EVENT["data"],
            "status": "requires_action",
            "interrupt_id": "int_1",
            "interrupt_kind": "approval",
        },
    }
    event = webhooks.parse_event(json.dumps(body))
    assert isinstance(event, RunWebhookEvent)
    assert (event.data.interrupt_id, event.data.interrupt_kind) == ("int_1", "approval")


def test_api_key_limit_event() -> None:
    raw = json.dumps(
        {
            "type": "api_key.limit_reached",
            "timestamp": "2026-10-22T08:00:00.000Z",
            "data": {
                "object": "api_key",
                "id": "key_1",
                "name": "Backend",
                "hint": "lgx_sk_…abcd",
                "spent_usd": "50.000000",
                "limit_usd": "50.000000",
                "limit_reset": "monthly",
                "resets_at": "2026-11-01T00:00:00.000Z",
            },
        }
    ).encode()
    event = webhooks.verify(raw, signed_headers(raw), SECRET)
    assert isinstance(event, ApiKeyLimitWebhookEvent)
    assert event.data.limit_usd == "50.000000"


def test_webhook_test_event() -> None:
    body = {
        "type": "webhook.test",
        "timestamp": "2026-10-22T08:00:00.000Z",
        "data": {"object": "webhook_endpoint", "id": "we_" + "C" * 20},
    }
    event = webhooks.parse_event(body)
    assert isinstance(event, WebhookTestEvent) and event.data.id.startswith("we_")


def test_unknown_event_type_is_kept_not_rejected() -> None:
    body = {"type": "run.archived", "timestamp": "t", "data": {"id": "x"}, "extra": 1}
    event = webhooks.parse_event(json.dumps(body).encode())
    assert isinstance(event, UnknownWebhookEvent)
    assert event.type == "run.archived" and event.data == {"id": "x"}


def test_known_event_missing_a_field_fails_validation() -> None:
    body = {"type": "run.failed", "timestamp": "t", "data": {"object": "run", "id": "x"}}
    with pytest.raises(ValueError, match="status"):
        webhooks.parse_event(body)


def test_extra_fields_on_known_events_are_kept() -> None:
    body = {**RUN_EVENT, "data": {**RUN_EVENT["data"], "added_later": True}}
    event = webhooks.parse_event(body)
    assert isinstance(event, RunWebhookEvent)
    assert event.data.model_dump()["added_later"] is True


# -- verification failures ------------------------------------------------------------


def test_header_case_is_insensitive() -> None:
    headers = {k.lower(): v for k, v in signed_headers().items()}
    assert webhooks.verify(PAYLOAD, headers, SECRET).type == "run.completed"


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


def test_invalid_secret_is_a_configuration_error() -> None:
    with pytest.raises(ValueError, match="signing secret"):
        webhooks.verify(PAYLOAD, signed_headers(), "")
