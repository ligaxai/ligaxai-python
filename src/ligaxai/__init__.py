"""LigaX AI Python SDK.

from ligaxai import LigaX

client = LigaX()  # reads LIGAX_API_KEY
client.health.get()
"""

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
from ._models import BaseModel
from ._pagination import AsyncPage, SyncPage
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
    "ServerSentEvent",
    "Stream",
    "SyncPage",
    "Timeout",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "__version__",
]
