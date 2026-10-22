"""LigaX AI Python SDK.

from ligaxai import LigaX

client = LigaX()  # reads LIGAX_API_KEY
run = client.runs.wait(profile_id="prf_...", input="Hello")
print(run.output.text)
"""

from . import types
from ._client import (
    API_KEY_ENV_VAR,
    BASE_URL_ENV_VAR,
    DEFAULT_BASE_URL,
    AsyncLigaX,
    LigaX,
    MissingAPIKeyError,
)
from ._exceptions import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PaymentRequiredError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    WebhookVerificationError,
)
from ._generated.models import Run
from ._models import BaseModel
from ._pagination import AsyncPage, SyncPage
from ._run_stream import (
    AsyncRunStream,
    AsyncRunStreamManager,
    RunEvent,
    RunEventList,
    RunStream,
    TextAssembler,
)
from ._streaming import AsyncStream, EventRegistry, ServerSentEvent, Stream
from ._types import NOT_GIVEN, NotGiven, RequestOptions, Timeout
from ._version import __version__

__all__ = [
    "API_KEY_ENV_VAR",
    "BASE_URL_ENV_VAR",
    "DEFAULT_BASE_URL",
    "NOT_GIVEN",
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AsyncLigaX",
    "AsyncPage",
    "AsyncRunStream",
    "AsyncRunStreamManager",
    "AsyncStream",
    "AuthenticationError",
    "BadRequestError",
    "BaseModel",
    "ConflictError",
    "EventRegistry",
    "InternalServerError",
    "LigaX",
    "MissingAPIKeyError",
    "NotFoundError",
    "NotGiven",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestOptions",
    "Run",
    "RunEvent",
    "RunEventList",
    "RunStream",
    "ServerSentEvent",
    "Stream",
    "SyncPage",
    "TextAssembler",
    "Timeout",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "__version__",
    "types",
]
