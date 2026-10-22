"""Response and parameter types, for annotations: ``from ligaxai.types import Run``.

The response models are generated from the pinned OpenAPI spec (``_generated/``), as are
the webhook events in its ``webhooks`` section. The run stream's event types are
hand-written because the spec describes that stream only as ``text/event-stream``, and so
is ``UnknownWebhookEvent`` (the fallback for a webhook type added later). Every model
inherits ``ligaxai.BaseModel``: unknown fields are kept rather than rejected, and
``.request_id`` carries the server's ``X-Request-Id``.
"""

from ._generated.models import (
    ApiKey,
    ApiKeyLimit,
    ApiKeyLimitWebhookEvent,
    ApiKeyLimitWebhookEventData,
    ClientToken,
    ConnectSession,
    Conversation,
    EndUserConnection,
    EndUserConnectionDeleted,
    EndUserConnectionList,
    Profile,
    ProfileConnector,
    ProfileList,
    ProfileModels,
    RequiredAction,
    Run,
    RunArtifact,
    RunError,
    RunOutput,
    RunSource,
    RunToolCall,
    RunUsage,
    RunWebhookEvent,
    RunWebhookEventData,
    UsageBucket,
    UsageReport,
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEndpointDeleted,
    WebhookEndpointList,
    WebhookEndpointWithSecret,
    WebhookTestEvent,
    WebhookTestEventData,
)
from ._run_stream import RunEvent, RunEventList
from ._webhooks import UnknownWebhookEvent, WebhookEvent
from .resources.connect_sessions import CONNECT_SESSION_TERMINAL_STATUSES, ConnectSessionStatus
from .resources.runs import TERMINAL_STATUSES, EndUserParam, InputParam, InterruptDecision
from .resources.usage import UsageGroupBy
from .resources.webhooks import WebhookEndpointStatus, WebhookEventType

__all__ = [
    "CONNECT_SESSION_TERMINAL_STATUSES",
    "TERMINAL_STATUSES",
    "ApiKey",
    "ApiKeyLimit",
    "ApiKeyLimitWebhookEvent",
    "ApiKeyLimitWebhookEventData",
    "ClientToken",
    "ConnectSession",
    "ConnectSessionStatus",
    "Conversation",
    "EndUserConnection",
    "EndUserConnectionDeleted",
    "EndUserConnectionList",
    "EndUserParam",
    "InputParam",
    "InterruptDecision",
    "Profile",
    "ProfileConnector",
    "ProfileList",
    "ProfileModels",
    "RequiredAction",
    "Run",
    "RunArtifact",
    "RunError",
    "RunEvent",
    "RunEventList",
    "RunOutput",
    "RunSource",
    "RunToolCall",
    "RunUsage",
    "RunWebhookEvent",
    "RunWebhookEventData",
    "UnknownWebhookEvent",
    "UsageBucket",
    "UsageGroupBy",
    "UsageReport",
    "WebhookDelivery",
    "WebhookEndpoint",
    "WebhookEndpointDeleted",
    "WebhookEndpointList",
    "WebhookEndpointStatus",
    "WebhookEndpointWithSecret",
    "WebhookEvent",
    "WebhookEventType",
    "WebhookTestEvent",
    "WebhookTestEventData",
]
