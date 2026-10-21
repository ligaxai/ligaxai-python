"""The shared request pipeline behind ``BaseProject`` and ``AsyncBaseProject``.

Layering: ``_client`` (public constructors, env, resource mounting) → ``resources/*``
(one method per endpoint, sync + async) → this module (headers, retries, error mapping,
parsing). Resources never touch ``httpx2`` directly.

Retry policy, in the order it is evaluated:

1. ``x-should-retry: true|false`` on the response is an explicit server override.
2. Transport errors (connect, read, write, timeout) are retried — a POST carries an
   ``Idempotency-Key`` that is minted once and reused across attempts, so a replayed
   write is safe.
3. 408, 409, 429 and every 5xx are retried. 402 and 403 never are: payment and permission
   failures do not fix themselves on a second attempt.
4. Nothing is retried once a stream has started — the consumer resumes with
   ``last_event_id`` instead.

Delay: ``retry-after-ms``, then ``retry-after`` (integer seconds or an HTTP-date), honoured
when ``0 < value <= 120`` s; otherwise exponential ``0.5 s → 8 s`` with 25 % jitter.
"""

from __future__ import annotations

import email.utils
import json
import platform
import random
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar

import anyio
import httpx2

from ._exceptions import (
    APIConnectionError,
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
    extract_error,
)
from ._logging import logger
from ._models import BaseModel
from ._pagination import AsyncPage, PageRequest, SyncPage
from ._streaming import AsyncStream, EventRegistry, Stream
from ._types import RequestOptions
from ._version import __version__

__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "AsyncBaseClient",
    "BaseClient",
    "SyncBaseClient",
]

DEFAULT_TIMEOUT = httpx2.Timeout(600.0, connect=5.0)
DEFAULT_MAX_RETRIES = 2
INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
MAX_RETRY_AFTER = 120.0
RETRYABLE_STATUS = frozenset({408, 409, 429})
NEVER_RETRY_STATUS = frozenset({402, 403})
IDEMPOTENT_METHODS = frozenset({"POST"})

USER_AGENT_TEMPLATE = "base-project-slug-python/{version} (python/{py}; {os}/{arch})"

ModelT = TypeVar("ModelT", bound=BaseModel)
SyncPageT = TypeVar("SyncPageT", bound="SyncPage[Any]")
AsyncPageT = TypeVar("AsyncPageT", bound="AsyncPage[Any]")

# Module-level so tests can monkeypatch them and run the retry loop without sleeping.
_sleep = time.sleep
_async_sleep = anyio.sleep


def _user_agent() -> str:
    return USER_AGENT_TEMPLATE.format(
        version=__version__,
        py=f"{sys.version_info.major}.{sys.version_info.minor}",
        os=sys.platform,
        arch=platform.machine() or "unknown",
    )


class BaseClient:
    """Configuration and the pure (I/O-free) parts of the pipeline."""

    api_key: str
    base_url: httpx2.URL
    timeout: httpx2.Timeout | float
    max_retries: int

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: httpx2.Timeout | float | None,
        max_retries: int,
        default_headers: dict[str, str] | None,
    ) -> None:
        self.api_key = api_key
        self.base_url = httpx2.URL(base_url if base_url.endswith("/") else base_url + "/")
        self.timeout = DEFAULT_TIMEOUT if timeout is None else timeout
        self.max_retries = max_retries
        self._default_headers: dict[str, str] = dict(default_headers or {})

    # -- request construction -------------------------------------------------------

    @property
    def user_agent(self) -> str:
        return _user_agent()

    def default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {self.api_key}",
            **self._default_headers,
        }

    def _build_headers(self, method: str, options: RequestOptions, stream: bool) -> dict[str, str]:
        headers = self.default_headers()
        if stream:
            headers["Accept"] = "text/event-stream"
        headers.update(options.headers)
        if method.upper() in IDEMPOTENT_METHODS and "Idempotency-Key" not in headers:
            headers["Idempotency-Key"] = options.idempotency_key or f"sdk-{uuid.uuid4()}"
        return headers

    def _build_url(self, path: str) -> httpx2.URL:
        return self.base_url.join(path.lstrip("/"))

    # -- retry decisions -------------------------------------------------------------

    def _should_retry(self, response: httpx2.Response) -> bool:
        override = response.headers.get("x-should-retry", "").strip().lower()
        if override == "true":
            return True
        if override == "false":
            return False
        status = response.status_code
        if status in NEVER_RETRY_STATUS:
            return False
        return status in RETRYABLE_STATUS or status >= 500

    def _retry_delay(self, retries_taken: int, response: httpx2.Response | None) -> float:
        if response is not None:
            hinted = _parse_retry_after(response.headers)
            if hinted is not None and 0 < hinted <= MAX_RETRY_AFTER:
                return hinted
        base = min(INITIAL_RETRY_DELAY * (2**retries_taken), MAX_RETRY_DELAY)
        jitter: float = 1 - 0.25 * random.random()
        return float(base * jitter)

    # -- response handling -----------------------------------------------------------

    def _make_status_error(self, response: httpx2.Response) -> APIStatusError:
        body = _safe_json(response)
        raw_message = extract_error(body).get("message")
        message: str | None = raw_message if isinstance(raw_message, str) else None
        if message is None:
            message = response.text.strip() or f"Error code: {response.status_code}"
        cls = _status_error_class(response.status_code)
        return cls(message, response=response, body=body)

    def _parse(self, response: httpx2.Response, cast_to: type[ModelT]) -> ModelT:
        value = cast_to.model_validate(_safe_json(response))
        value.attach_request_id(response.headers.get("x-request-id"))
        return value


class SyncBaseClient(BaseClient):
    _http: httpx2.Client

    def request(
        self,
        method: str,
        path: str,
        *,
        cast_to: type[ModelT],
        json: Any = None,
        options: RequestOptions | None = None,
    ) -> ModelT:
        response = self._send_with_retries(method, path, json=json, options=options, stream=False)
        return self._parse(response, cast_to)

    def request_stream(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        options: RequestOptions | None = None,
        registry: EventRegistry[ModelT] | None = None,
    ) -> Stream[ModelT]:
        response = self._send_with_retries(method, path, json=json, options=options, stream=True)
        return Stream(response=response, registry=registry)

    def request_page(self, page_cls: type[SyncPageT], req: PageRequest) -> SyncPageT:
        response = self._send_with_retries(req.method, req.path, json=req.json, options=req.options)
        page = self._parse(response, page_cls)
        page.bind(self, req)
        return page

    def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        json: Any,
        options: RequestOptions | None,
        stream: bool = False,
    ) -> httpx2.Response:
        opts = options or RequestOptions()
        max_retries = self.max_retries if opts.max_retries is None else opts.max_retries
        headers = self._build_headers(method, opts, stream)
        timeout = self.timeout if opts.timeout is None else opts.timeout
        retries_taken = 0
        while True:
            request = self._http.build_request(
                method,
                self._build_url(path),
                json=json,
                params=opts.params or None,
                headers=headers,
                timeout=timeout,
            )
            logger.debug("Request %s %s (attempt %d)", method, request.url, retries_taken + 1)
            try:
                response = self._http.send(request, stream=stream)
            except httpx2.TimeoutException as exc:
                if retries_taken >= max_retries:
                    raise APITimeoutError(request) from exc
                _sleep(self._retry_delay(retries_taken, None))
                retries_taken += 1
                continue
            except httpx2.TransportError as exc:
                if retries_taken >= max_retries:
                    raise APIConnectionError(request=request) from exc
                _sleep(self._retry_delay(retries_taken, None))
                retries_taken += 1
                continue

            if response.is_success:
                return response

            if retries_taken < max_retries and self._should_retry(response):
                response.close()
                _sleep(self._retry_delay(retries_taken, response))
                retries_taken += 1
                continue

            response.read()
            raise self._make_status_error(response)


class AsyncBaseClient(BaseClient):
    _http: httpx2.AsyncClient

    async def request(
        self,
        method: str,
        path: str,
        *,
        cast_to: type[ModelT],
        json: Any = None,
        options: RequestOptions | None = None,
    ) -> ModelT:
        response = await self._send_with_retries(
            method, path, json=json, options=options, stream=False
        )
        return self._parse(response, cast_to)

    async def request_stream(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        options: RequestOptions | None = None,
        registry: EventRegistry[ModelT] | None = None,
    ) -> AsyncStream[ModelT]:
        response = await self._send_with_retries(
            method, path, json=json, options=options, stream=True
        )
        return AsyncStream(response=response, registry=registry)

    async def request_page(self, page_cls: type[AsyncPageT], req: PageRequest) -> AsyncPageT:
        response = await self._send_with_retries(
            req.method, req.path, json=req.json, options=req.options
        )
        page = self._parse(response, page_cls)
        page.bind(self, req)
        return page

    async def _send_with_retries(
        self,
        method: str,
        path: str,
        *,
        json: Any,
        options: RequestOptions | None,
        stream: bool = False,
    ) -> httpx2.Response:
        opts = options or RequestOptions()
        max_retries = self.max_retries if opts.max_retries is None else opts.max_retries
        headers = self._build_headers(method, opts, stream)
        timeout = self.timeout if opts.timeout is None else opts.timeout
        retries_taken = 0
        while True:
            request = self._http.build_request(
                method,
                self._build_url(path),
                json=json,
                params=opts.params or None,
                headers=headers,
                timeout=timeout,
            )
            logger.debug("Request %s %s (attempt %d)", method, request.url, retries_taken + 1)
            try:
                response = await self._http.send(request, stream=stream)
            except httpx2.TimeoutException as exc:
                if retries_taken >= max_retries:
                    raise APITimeoutError(request) from exc
                await _async_sleep(self._retry_delay(retries_taken, None))
                retries_taken += 1
                continue
            except httpx2.TransportError as exc:
                if retries_taken >= max_retries:
                    raise APIConnectionError(request=request) from exc
                await _async_sleep(self._retry_delay(retries_taken, None))
                retries_taken += 1
                continue

            if response.is_success:
                return response

            if retries_taken < max_retries and self._should_retry(response):
                await response.aclose()
                await _async_sleep(self._retry_delay(retries_taken, response))
                retries_taken += 1
                continue

            await response.aread()
            raise self._make_status_error(response)


# -- helpers ---------------------------------------------------------------------------


def _status_error_class(status: int) -> type[APIStatusError]:
    mapping: dict[int, type[APIStatusError]] = {
        400: BadRequestError,
        401: AuthenticationError,
        402: PaymentRequiredError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        422: UnprocessableEntityError,
        429: RateLimitError,
    }
    if status >= 500:
        return InternalServerError
    return mapping.get(status, APIStatusError)


def _safe_json(response: httpx2.Response) -> Any:
    try:
        return response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _parse_retry_after(headers: httpx2.Headers) -> float | None:
    """``retry-after-ms`` first, then ``retry-after`` as seconds or an HTTP-date."""
    ms = headers.get("retry-after-ms")
    if ms is not None:
        try:
            return float(ms) / 1000
        except ValueError:
            pass
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - datetime.now(UTC)).total_seconds()
