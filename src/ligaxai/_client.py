"""Public client classes: ``LigaX`` (sync) and ``AsyncLigaX``.

Both resolve configuration the same way — explicit argument, then environment, then
default — and mount the same resources, so a user can switch between them by changing one
import. The sync and async classes are kept identical by construction: every resource
exists in both flavours (see ``resources/_base.py``).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, TypeVar

import httpx2

from ._base_client import DEFAULT_MAX_RETRIES, AsyncBaseClient, SyncBaseClient
from ._exceptions import APIError
from ._types import NOT_GIVEN, NotGiven, NotGivenOr
from .resources.client_tokens import AsyncClientTokens, ClientTokens
from .resources.connect_sessions import AsyncConnectSessions, ConnectSessions
from .resources.conversations import AsyncConversations, Conversations
from .resources.end_users import AsyncEndUsers, EndUsers
from .resources.files import AsyncFiles, Files
from .resources.keys import AsyncKeys, Keys
from .resources.profiles import AsyncProfiles, Profiles
from .resources.runs import AsyncRuns, Runs
from .resources.usage import AsyncUsage, Usage
from .resources.webhooks import AsyncWebhooks, Webhooks

if TYPE_CHECKING:
    from typing import Self

__all__ = [
    "API_KEY_ENV_VAR",
    "BASE_URL_ENV_VAR",
    "DEFAULT_BASE_URL",
    "AsyncLigaX",
    "LigaX",
]

API_KEY_ENV_VAR = "LIGAX_API_KEY"
BASE_URL_ENV_VAR = "LIGAX_BASE_URL"
DEFAULT_BASE_URL = "https://enterprise.ligax.ai/api/public/v1"

T = TypeVar("T")


class MissingAPIKeyError(APIError, ValueError):
    """Raised at construction when no API key could be found.

    Inherits ``ValueError`` so a bare ``except ValueError`` on misconfiguration still works,
    and ``APIError`` so one handler covers every error this library raises. It is not an
    ``AuthenticationError`` because no request was made — there is no response to carry.
    """

    def __init__(self) -> None:
        super().__init__(
            "No API key provided. Pass `api_key=` or set the "
            f"{API_KEY_ENV_VAR} environment variable."
        )


def _pick(value: NotGivenOr[T], fallback: T) -> T:
    if isinstance(value, NotGiven):
        return fallback
    return value


def _resolve_api_key(api_key: str | None) -> str:
    key = api_key if api_key is not None else os.environ.get(API_KEY_ENV_VAR)
    if not key:
        raise MissingAPIKeyError()
    return key


def _resolve_base_url(base_url: str | None) -> str:
    return base_url or os.environ.get(BASE_URL_ENV_VAR) or DEFAULT_BASE_URL


class LigaX(SyncBaseClient):
    """Synchronous client.

    Args:
        api_key: Organisation secret key (``lgx_sk_…``). Falls back to ``LIGAX_API_KEY``.
            A client token (``lgx_ct_…``) from ``client_tokens.create`` also works, for
            runs, conversations and connect sessions of its one profile and end user
            only — useful to act as the browser in a test or tool. It expires in minutes
            and cannot be refreshed by this client; mint a new one.
        base_url: API root. Falls back to ``LIGAX_BASE_URL`` then the built-in default.
        timeout: ``httpx2.Timeout`` or seconds. Default ``Timeout(600, connect=5)``.
        max_retries: Attempts after the first. Default 2.
        default_headers: Sent on every request (after the SDK's own headers).
        http_client: Bring your own ``httpx2.Client`` (proxies, mounts, test transports).
            The SDK will not close a client it did not create.
    """

    runs: Runs
    conversations: Conversations
    profiles: Profiles
    keys: Keys
    files: Files
    usage: Usage
    webhooks: Webhooks
    client_tokens: ClientTokens
    connect_sessions: ConnectSessions
    end_users: EndUsers

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: httpx2.Timeout | float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: dict[str, str] | None = None,
        http_client: httpx2.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=_resolve_api_key(api_key),
            base_url=_resolve_base_url(base_url),
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        # A plain `httpx.Client` is a different type and would silently bypass our transport.
        if http_client is not None and not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            http_client, httpx2.Client
        ):
            raise TypeError(
                f"http_client must be an httpx2.Client, got {type(http_client).__name__}"
            )
        self._owns_http = http_client is None
        self._http = http_client or httpx2.Client()
        self.runs = Runs(self)
        self.conversations = Conversations(self)
        self.profiles = Profiles(self)
        self.keys = Keys(self)
        self.files = Files(self)
        self.usage = Usage(self)
        self.webhooks = Webhooks(self)
        self.client_tokens = ClientTokens(self)
        self.connect_sessions = ConnectSessions(self)
        self.end_users = EndUsers(self)

    def with_options(
        self,
        *,
        api_key: NotGivenOr[str] = NOT_GIVEN,
        base_url: NotGivenOr[str] = NOT_GIVEN,
        timeout: NotGivenOr[httpx2.Timeout | float | None] = NOT_GIVEN,
        max_retries: NotGivenOr[int] = NOT_GIVEN,
        default_headers: NotGivenOr[dict[str, str]] = NOT_GIVEN,
    ) -> Self:
        """Return a copy with the given settings changed. Shares the HTTP connection pool."""
        return self.__class__(
            api_key=_pick(api_key, self.api_key),
            base_url=_pick(base_url, str(self.base_url)),
            timeout=_pick(timeout, self.timeout),
            max_retries=_pick(max_retries, self.max_retries),
            default_headers=_pick(default_headers, dict(self._default_headers)),
            http_client=self._http,
        )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncLigaX(AsyncBaseClient):
    """Asynchronous client. Same arguments as :class:`LigaX`."""

    runs: AsyncRuns
    conversations: AsyncConversations
    profiles: AsyncProfiles
    keys: AsyncKeys
    files: AsyncFiles
    usage: AsyncUsage
    webhooks: AsyncWebhooks
    client_tokens: AsyncClientTokens
    connect_sessions: AsyncConnectSessions
    end_users: AsyncEndUsers

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: httpx2.Timeout | float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: dict[str, str] | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_key=_resolve_api_key(api_key),
            base_url=_resolve_base_url(base_url),
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
        )
        if http_client is not None and not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            http_client, httpx2.AsyncClient
        ):
            raise TypeError(
                f"http_client must be an httpx2.AsyncClient, got {type(http_client).__name__}"
            )
        self._owns_http = http_client is None
        self._http = http_client or httpx2.AsyncClient()
        self.runs = AsyncRuns(self)
        self.conversations = AsyncConversations(self)
        self.profiles = AsyncProfiles(self)
        self.keys = AsyncKeys(self)
        self.files = AsyncFiles(self)
        self.usage = AsyncUsage(self)
        self.webhooks = AsyncWebhooks(self)
        self.client_tokens = AsyncClientTokens(self)
        self.connect_sessions = AsyncConnectSessions(self)
        self.end_users = AsyncEndUsers(self)

    def with_options(
        self,
        *,
        api_key: NotGivenOr[str] = NOT_GIVEN,
        base_url: NotGivenOr[str] = NOT_GIVEN,
        timeout: NotGivenOr[httpx2.Timeout | float | None] = NOT_GIVEN,
        max_retries: NotGivenOr[int] = NOT_GIVEN,
        default_headers: NotGivenOr[dict[str, str]] = NOT_GIVEN,
    ) -> Self:
        """Return a copy with the given settings changed. Shares the HTTP connection pool."""
        return self.__class__(
            api_key=_pick(api_key, self.api_key),
            base_url=_pick(base_url, str(self.base_url)),
            timeout=_pick(timeout, self.timeout),
            max_retries=_pick(max_retries, self.max_retries),
            default_headers=_pick(default_headers, dict(self._default_headers)),
            http_client=self._http,
        )

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
