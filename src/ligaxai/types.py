"""Response and parameter types, for annotations: ``from ligaxai.types import Run``.

The response models are generated from the pinned OpenAPI spec (``_generated/``); the run
event types are hand-written because the spec describes the event stream only as
``text/event-stream``. Every model inherits ``ligaxai.BaseModel``: unknown fields
are kept rather than rejected, and ``.request_id`` carries the server's ``X-Request-Id``.
"""

from ._generated.models import (
    ApiKey,
    ApiKeyLimit,
    Conversation,
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
    UsageBucket,
    UsageReport,
)
from ._run_stream import RunEvent, RunEventList
from .resources.runs import TERMINAL_STATUSES, EndUserParam, InputParam, InterruptDecision
from .resources.usage import UsageGroupBy

__all__ = [
    "TERMINAL_STATUSES",
    "ApiKey",
    "ApiKeyLimit",
    "Conversation",
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
    "UsageBucket",
    "UsageGroupBy",
    "UsageReport",
]
