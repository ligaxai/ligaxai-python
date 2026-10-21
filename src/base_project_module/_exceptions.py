"""Exception hierarchy.

``APIError`` is the root. Transport problems are ``APIConnectionError`` (and its subclass
``APITimeoutError``); anything the server answered is an ``APIStatusError`` narrowed by
status code so callers can ``except RateLimitError``. Every status error carries the
``request_id`` the server echoed in ``X-Request-Id`` and the machine-readable ``code``
from the JSON body, when present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    import httpx2

__all__ = [
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "InternalServerError",
    "NotFoundError",
    "PaymentRequiredError",
    "PermissionDeniedError",
    "RateLimitError",
    "UnprocessableEntityError",
    "WebhookVerificationError",
]


class APIError(Exception):
    """Base class for every error raised by this library."""

    message: str
    request: httpx2.Request | None
    body: object | None

    def __init__(
        self,
        message: str,
        request: httpx2.Request | None = None,
        *,
        body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.request = request
        self.body = body


class APIConnectionError(APIError):
    """The request never produced a response (DNS, TCP, TLS, connection reset)."""

    def __init__(
        self, *, message: str = "Connection error.", request: httpx2.Request | None = None
    ) -> None:
        super().__init__(message, request)


class APITimeoutError(APIConnectionError):
    """The request exceeded the configured timeout."""

    def __init__(self, request: httpx2.Request | None = None) -> None:
        super().__init__(message="Request timed out.", request=request)


class APIStatusError(APIError):
    """The server answered with a 4xx/5xx status."""

    response: httpx2.Response
    status_code: int
    request_id: str | None
    code: str | None
    type: str | None
    param: str | None

    def __init__(
        self,
        message: str,
        *,
        response: httpx2.Response,
        body: object | None = None,
    ) -> None:
        super().__init__(message, response.request, body=body)
        self.response = response
        self.status_code = response.status_code
        # The body's request_id wins over the header: the header may have been rewritten
        # by an intermediary, the body is what the API logged.
        err = extract_error(body)
        self.request_id = _str_or_none(err.get("request_id")) or response.headers.get(
            "x-request-id"
        )
        self.code = _str_or_none(err.get("code"))
        self.type = _str_or_none(err.get("type"))
        self.param = _str_or_none(err.get("param"))

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"(code={self.code})")
        if self.request_id:
            parts.append(f"(request_id={self.request_id})")
        return " ".join(parts)


class BadRequestError(APIStatusError):
    status_code: int = 400


class AuthenticationError(APIStatusError):
    status_code: int = 401


class PaymentRequiredError(APIStatusError):
    status_code: int = 402


class PermissionDeniedError(APIStatusError):
    status_code: int = 403


class NotFoundError(APIStatusError):
    status_code: int = 404


class ConflictError(APIStatusError):
    status_code: int = 409


class UnprocessableEntityError(APIStatusError):
    status_code: int = 422


class RateLimitError(APIStatusError):
    status_code: int = 429


class InternalServerError(APIStatusError):
    """Any 5xx."""


class WebhookVerificationError(APIError):
    """A webhook payload failed signature or timestamp verification."""

    def __init__(self, message: str = "Webhook signature verification failed.") -> None:
        super().__init__(message)


def extract_error(body: object | None) -> dict[str, Any]:
    """Return the ``error`` object of an API error envelope, or ``{}``."""
    if isinstance(body, dict):
        inner = cast("dict[str, Any]", body).get("error")
        if isinstance(inner, dict):
            return dict(cast("dict[str, Any]", inner))
    return {}


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
