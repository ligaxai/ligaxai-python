"""__PROJECT_TITLE__ Python SDK.

from base_project_module import BaseProject

client = BaseProject()  # reads BASE_PROJECT_API_KEY
client.health.get()
"""

from ._client import (
    API_KEY_ENV_VAR,
    BASE_URL_ENV_VAR,
    DEFAULT_BASE_URL,
    AsyncBaseProject,
    BaseProject,
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
    "AsyncBaseProject",
    "AsyncPage",
    "AsyncStream",
    "AuthenticationError",
    "BadRequestError",
    "BaseModel",
    "BaseProject",
    "ConflictError",
    "EventRegistry",
    "InternalServerError",
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
