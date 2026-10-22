"""Every resource method: what it sends and what it parses — sync and async alike."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx2
import pytest

from ligaxai import AsyncLigaX, LigaX, RequestOptions
from ligaxai.types import (
    ApiKey,
    Conversation,
    Profile,
    ProfileList,
    Run,
    RunEventList,
    UsageReport,
)
from tests.conftest import (
    CONVERSATION_ID,
    PROFILE_ID,
    RUN_ID,
    TEST_API_KEY,
    Recorder,
    json_response,
    make_async_client,
    make_sync_client,
    run_body,
)

PROFILE = {
    "object": "profile",
    "id": PROFILE_ID,
    "name": "Support agent",
    "description": None,
    "type": "agent",
    "models": {"default": "gemini/gemini-flash/latest", "allowed": []},
    "connectors": [{"type": "servicenow", "name": "ServiceNow"}],
    "end_user_identity": "optional",
    "published_at": "2026-10-20T00:00:00.000Z",
}
API_KEY = {
    "object": "api_key",
    "id": "key_1",
    "name": "Backend",
    "environment": "dev",
    "scopes": ["runs:write", "runs:read"],
    "allowed_profiles": None,
    "limit": {
        "limit_usd": "50.000000",
        "remaining_usd": "49.990000",
        "spent_usd": "0.010000",
        "reset": "monthly",
        "resets_at": "2026-11-01T00:00:00.000Z",
    },
    "rate_limit_per_minute": 60,
    "expires_at": None,
    "created_at": "2026-10-01T00:00:00.000Z",
    "a_field_from_the_future": True,
}
USAGE = {
    "object": "usage",
    "source": "engine_ledger_projection",
    "start": "2026-10-01T00:00:00.000Z",
    "end": "2026-10-08T00:00:00.000Z",
    "bucket_width": "1d",
    "group_by": "model",
    "total_cost_usd": "0.012000",
    "truncated": False,
    "data": [
        {
            "start": "2026-10-01T00:00:00.000Z",
            "model_calls": 3,
            "input_tokens": 300,
            "output_tokens": 90,
            "cost_usd": "0.012000",
            "model": "gemini/gemini-flash/latest",
        }
    ],
}


async def call(client: LigaX | AsyncLigaX, dotted: str, *args: Any, **kwargs: Any) -> Any:
    target: Any = client
    for part in dotted.split("."):
        target = getattr(target, part)
    result = target(*args, **kwargs)
    if isinstance(client, AsyncLigaX):
        result = await result
    return result


ClientFactory = Callable[[Recorder], LigaX | AsyncLigaX]
CLIENTS: list[ClientFactory] = [make_sync_client, make_async_client]
IDS = ["sync", "async"]


@pytest.fixture(params=CLIENTS, ids=IDS)
def factory(request: pytest.FixtureRequest) -> ClientFactory:
    return request.param  # type: ignore[no-any-return]


def body_of(req: httpx2.Request) -> Any:
    return json.loads(req.content) if req.content else None


# -- runs -----------------------------------------------------------------------------


async def test_runs_create_request_and_response(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, run_body(), {"x-request-id": "req_run"})]
    client = factory(recorder)
    run = await call(
        client,
        "runs.create",
        profile_id=PROFILE_ID,
        input="Hello",
        conversation_id=CONVERSATION_ID,
        end_user={"id": "user-42", "name": "Ada"},
        model="gemini/gemini-flash/latest",
        metadata={"ticket": "T-1"},
    )
    req = recorder.requests[0]
    assert req.method == "POST"
    assert req.url.path == "/api/public/v1/runs"
    assert req.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
    assert req.headers["Content-Type"] == "application/json"
    assert req.headers["Accept"] == "application/json"
    assert req.headers["Idempotency-Key"].startswith("sdk-")
    assert body_of(req) == {
        "profile_id": PROFILE_ID,
        "input": "Hello",
        "mode": "wait",
        "conversation_id": CONVERSATION_ID,
        "end_user": {"id": "user-42", "name": "Ada"},
        "model": "gemini/gemini-flash/latest",
        "metadata": {"ticket": "T-1"},
    }
    assert isinstance(run, Run)
    assert run.id == RUN_ID and run.status == "completed"
    assert run.output.text == "Hello there."
    assert run.usage is not None and run.usage.input_tokens == 10
    assert run.request_id == "req_run"


async def test_runs_create_minimal_body_and_string_end_user(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(202, run_body(status="running"))]
    client = factory(recorder)
    run = await call(
        client,
        "runs.create",
        profile_id=PROFILE_ID,
        input={"text": "Hi"},
        end_user="user-7",
        mode="async",
        idempotency_key="order-1234",
    )
    req = recorder.requests[0]
    assert body_of(req) == {
        "profile_id": PROFILE_ID,
        "input": {"text": "Hi"},
        "mode": "async",
        "end_user": {"id": "user-7"},
    }
    assert req.headers["Idempotency-Key"] == "order-1234"
    assert run.status == "running"


async def test_runs_create_idempotency_key_reused_across_retries(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(503, None, {"retry-after": "5"}),
        httpx2.ConnectError("reset"),
        json_response(200, run_body()),
    ]
    await call(factory(recorder), "runs.create", profile_id=PROFILE_ID, input="Hi")
    keys = {r.headers["Idempotency-Key"] for r in recorder.requests}
    assert len(recorder.requests) == 3 and len(keys) == 1
    assert no_sleep[0] == 5.0  # Retry-After on a 503 is honoured


async def test_runs_create_each_call_gets_its_own_key(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [json_response(200, run_body())]
    client = factory(recorder)
    await call(client, "runs.create", profile_id=PROFILE_ID, input="a")
    await call(client, "runs.create", profile_id=PROFILE_ID, input="a")
    a, b = (r.headers["Idempotency-Key"] for r in recorder.requests)
    assert a != b


async def test_runs_create_rejects_stream_mode(recorder: Recorder, factory: ClientFactory) -> None:
    with pytest.raises(ValueError, match=r"runs\.stream"):
        await call(
            factory(recorder), "runs.create", profile_id=PROFILE_ID, input="x", mode="stream"
        )
    assert recorder.requests == []


async def test_options_idempotency_key_wins(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, run_body())]
    await call(
        factory(recorder),
        "runs.create",
        profile_id=PROFILE_ID,
        input="x",
        idempotency_key="from-argument",
        options=RequestOptions(idempotency_key="from-options", headers={"X-Trace": "t"}),
    )
    req = recorder.requests[0]
    assert req.headers["Idempotency-Key"] == "from-options"
    assert req.headers["X-Trace"] == "t"


async def test_runs_wait_polls_until_settled(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [
        json_response(202, run_body(status="running")),
        json_response(200, run_body(status="running")),
        json_response(200, run_body(status="running")),
        json_response(200, run_body(status="completed")),
    ]
    run = await call(
        factory(recorder),
        "runs.wait",
        profile_id=PROFILE_ID,
        input="long job",
        poll_interval=1.0,
        max_poll_interval=3.0,
    )
    assert run.status == "completed"
    assert [r.method for r in recorder.requests] == ["POST", "GET", "GET", "GET"]
    assert body_of(recorder.requests[0])["mode"] == "wait"
    assert recorder.requests[1].url.path.endswith(f"/runs/{RUN_ID}")
    assert no_sleep == [1.0, 2.0, 3.0]


async def test_runs_wait_stops_at_requires_action(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    action = {
        "type": "interrupt",
        "interrupt_id": "int_1",
        "kind": "approval",
        "prompt": "Create the incident?",
        "preview": None,
        "tool_name": "servicenow_create_incident",
        "response_schema": None,
    }
    recorder.responses = [
        json_response(200, run_body(status="requires_action", required_action=action))
    ]
    run = await call(factory(recorder), "runs.wait", profile_id=PROFILE_ID, input="x")
    assert run.status == "requires_action"
    assert run.required_action is not None and run.required_action.interrupt_id == "int_1"
    assert len(recorder.requests) == 1 and no_sleep == []


async def test_runs_wait_gives_up_after_max_wait(
    recorder: Recorder, factory: ClientFactory, no_sleep: list[float]
) -> None:
    recorder.responses = [json_response(202, run_body(status="running"))]
    run = await call(factory(recorder), "runs.wait", profile_id=PROFILE_ID, input="x", max_wait=0)
    assert run.status == "running"
    assert len(recorder.requests) == 1


async def test_runs_get_cancel_and_path_encoding(
    recorder: Recorder, factory: ClientFactory
) -> None:
    recorder.responses = [
        json_response(200, run_body()),
        json_response(200, run_body(status="canceled")),
    ]
    client = factory(recorder)
    run = await call(client, "runs.get", RUN_ID)
    canceled = await call(client, "runs.cancel", "id/with?odd")
    assert run.id == RUN_ID and canceled.status == "canceled"
    get_req, cancel_req = recorder.requests
    assert (get_req.method, get_req.url.path) == ("GET", f"/api/public/v1/runs/{RUN_ID}")
    assert "Idempotency-Key" not in get_req.headers
    assert cancel_req.method == "POST"
    assert cancel_req.url.raw_path == b"/api/public/v1/runs/id%2Fwith%3Fodd/cancel"
    with pytest.raises(ValueError, match="run_id"):
        await call(client, "runs.get", "")


async def test_runs_events_list(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(
            200,
            {
                "object": "list",
                "run_id": RUN_ID,
                "data": [
                    {
                        "seq": 5,
                        "type": "text.delta",
                        "payload": {"part_id": "p", "offset": 0, "text": "Hi"},
                        "created_at": "2026-10-22T08:00:01.000Z",
                    },
                    {
                        "seq": 6,
                        "type": "run.end",
                        "payload": None,
                        "created_at": "2026-10-22T08:00:02.000Z",
                    },
                ],
                "has_more": False,
            },
        )
    ]
    events = await call(factory(recorder), "runs.events", RUN_ID, after=4)
    req = recorder.requests[0]
    assert req.url.path.endswith(f"/runs/{RUN_ID}/events")
    assert req.url.params["after"] == "4"
    assert "stream" not in req.url.params
    assert isinstance(events, RunEventList)
    assert [e.seq for e in events.data] == [5, 6]
    assert all(e.run_id == RUN_ID for e in events.data)
    assert events.data[1].payload == {}
    assert events.data[0].created_at == "2026-10-22T08:00:01.000Z"


async def test_runs_resolve_interrupt(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, run_body(status="running"))]
    client = factory(recorder)
    await call(client, "runs.resolve_interrupt", RUN_ID, "int_1")
    await call(
        client,
        "runs.resolve_interrupt",
        RUN_ID,
        "int_1",
        decision="answer",
        payload={"choice": "b"},
    )
    approve, answer = recorder.requests
    assert approve.method == "POST"
    assert approve.url.path.endswith(f"/runs/{RUN_ID}/interrupts/int_1")
    assert body_of(approve) == {"decision": "approve"}
    assert body_of(answer) == {"decision": "answer", "payload": {"choice": "b"}}
    with pytest.raises(ValueError, match="payload"):
        await call(client, "runs.resolve_interrupt", RUN_ID, "int_1", decision="answer")
    with pytest.raises(ValueError, match="decision"):
        await call(client, "runs.resolve_interrupt", RUN_ID, "int_1", decision="maybe")
    assert len(recorder.requests) == 2


# -- conversations, profiles, keys, usage ---------------------------------------------


async def test_conversations_get(recorder: Recorder, factory: ClientFactory) -> None:
    conversation = {
        "object": "conversation",
        "id": CONVERSATION_ID,
        "profile_id": PROFILE_ID,
        "end_user_id": "user-42",
        "title": "Hello",
        "created_at": "2026-10-22T08:00:00.000Z",
        "last_run_at": None,
        "runs": [run_body()],
    }
    recorder.responses = [json_response(200, conversation)]
    client = factory(recorder)
    conv = await call(client, "conversations.get", CONVERSATION_ID, end_user_id="user-42")
    await call(client, "conversations.get", CONVERSATION_ID)
    with_user, without = recorder.requests
    assert with_user.url.path.endswith(f"/conversations/{CONVERSATION_ID}")
    assert with_user.url.params["end_user_id"] == "user-42"
    assert "end_user_id" not in without.url.params
    assert isinstance(conv, Conversation)
    assert conv.runs[0].output.text == "Hello there."


async def test_profiles_list_and_get(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [
        json_response(200, {"object": "list", "data": [PROFILE], "has_more": False}),
        json_response(200, PROFILE),
    ]
    client = factory(recorder)
    listed = await call(client, "profiles.list")
    one = await call(client, "profiles.get", PROFILE_ID)
    assert isinstance(listed, ProfileList) and isinstance(one, Profile)
    assert listed.data[0].connectors[0].type == "servicenow"
    assert one.models.default == "gemini/gemini-flash/latest"
    assert [r.url.path for r in recorder.requests] == [
        "/api/public/v1/profiles",
        f"/api/public/v1/profiles/{PROFILE_ID}",
    ]


async def test_keys_self_keeps_unknown_fields(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, API_KEY)]
    key = await call(factory(recorder), "keys.self")
    assert recorder.requests[0].url.path == "/api/public/v1/keys/self"
    assert isinstance(key, ApiKey)
    assert key.limit.remaining_usd == "49.990000"
    assert key.rate_limit_per_minute == 60
    assert key.model_extra == {"a_field_from_the_future": True}


async def test_usage_get(recorder: Recorder, factory: ClientFactory) -> None:
    recorder.responses = [json_response(200, USAGE)]
    client = factory(recorder)
    report = await call(
        client,
        "usage.get",
        start=date(2026, 10, 1),
        end=datetime(2026, 10, 8, tzinfo=UTC),
        group_by="model",
    )
    await call(client, "usage.get")
    await call(client, "usage.get", start="2026-10-01")
    dated, bare, text = recorder.requests
    assert dict(dated.url.params) == {
        "start": "2026-10-01",
        "end": "2026-10-08T00:00:00+00:00",
        "group_by": "model",
    }
    assert dict(bare.url.params) == {}
    assert dict(text.url.params) == {"start": "2026-10-01"}
    assert isinstance(report, UsageReport)
    assert report.data[0].model_calls == 3
    assert report.data[0].model_extra == {"model": "gemini/gemini-flash/latest"}


def test_sync_and_async_surfaces_match() -> None:
    """Invariant 1: every public method exists on both clients with the same parameters."""
    import inspect

    sync = LigaX(api_key="k")
    asyn = AsyncLigaX(api_key="k")
    for name in ("runs", "conversations", "profiles", "keys", "usage"):
        s_res, a_res = getattr(sync, name), getattr(asyn, name)
        s_methods = {m for m in dir(s_res) if not m.startswith("_")}
        a_methods = {m for m in dir(a_res) if not m.startswith("_")}
        assert s_methods == a_methods, name
        for method in s_methods:
            s_sig = inspect.signature(getattr(s_res, method))
            a_sig = inspect.signature(getattr(a_res, method))
            assert list(s_sig.parameters) == list(a_sig.parameters), f"{name}.{method}"
    sync.close()
