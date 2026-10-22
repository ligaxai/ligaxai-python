"""``/connect_sessions`` — an end user connects **their own** account (Gmail, Outlook, …).

Your server creates a session for the signed-in user and hands its ``connect_url`` to their
browser, which opens it in a popup. The popup shows the provider's own consent screen and
closes itself when the user finishes; the session's ``status`` then leaves ``pending`` for
``succeeded`` (with ``connection_id``), ``denied``, ``failed`` or ``expired``. LigaX never
redirects back to an address taken from the request, so popup-and-poll is the only way to
learn how it ended — ``get`` once, or ``wait`` to poll until it settles.

The profile must have *End users can connect their own accounts* switched on
(``ConflictError`` ``end_user_connections_off`` otherwise), and the connector must be one
its agent uses and one an end user can connect without typed credentials
(``UnprocessableEntityError`` ``connector_not_available`` / ``connector_not_connectable``).
Scopes: ``connections:write`` to create, ``connections:read`` to read.
"""

from __future__ import annotations

import time
from typing import Any, Literal, TypeAlias

import anyio

from .._generated.models import ConnectSession
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, merge_options, path_segment
from .runs import EndUserParam

__all__ = [
    "CONNECT_SESSION_TERMINAL_STATUSES",
    "AsyncConnectSessions",
    "ConnectSessionStatus",
    "ConnectSessions",
]

ConnectSessionStatus: TypeAlias = Literal["pending", "succeeded", "denied", "failed", "expired"]

#: Statuses a connect session never leaves — everything but ``pending``.
CONNECT_SESSION_TERMINAL_STATUSES = frozenset({"succeeded", "denied", "failed", "expired"})

# Module-level so tests can patch them; same pattern as `runs._sleep`.
_sleep = time.sleep
_async_sleep = anyio.sleep


def _create_body(
    connector_key: str, profile_id: str | None, end_user: EndUserParam | str | None
) -> dict[str, Any]:
    if not connector_key:
        raise ValueError("connector_key must be a non-empty string")
    body: dict[str, Any] = {"connector_key": connector_key}
    if profile_id is not None:
        body["profile_id"] = profile_id
    # Optional because a client token already names its end user; a secret key must send
    # one (the server answers 400 otherwise). A bare string is shorthand for `{"id": …}`.
    if end_user is not None:
        body["end_user"] = {"id": end_user} if isinstance(end_user, str) else dict(end_user)
    return body


def _session_path(session_id: str) -> str:
    return f"/connect_sessions/{path_segment(session_id, 'session_id')}"


def _deadline(timeout: float | None) -> float | None:
    return None if timeout is None else time.monotonic() + timeout


def _timed_out(session: ConnectSession, timeout: float | None) -> TimeoutError:
    return TimeoutError(
        f"Connect session {session.id} was still {session.status!r} after {timeout} s."
    )


class ConnectSessions(SyncAPIResource):
    def create(
        self,
        *,
        connector_key: str,
        profile_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """Start ``end_user`` connecting their own ``connector_key`` account.

        Args:
            connector_key: The connector, e.g. ``"gmail"``.
            profile_id: The profile (``prf_…``) whose agent will use the account. A client
                token's own profile is used when omitted.
            end_user: The signed-in user, from *your* session — an id, or
                ``{"id", "name"}``. Required with a secret key; a client token already
                names its user.

        Open ``.connect_url`` in a popup in that user's browser, then ``get`` or ``wait``.
        """
        return self._client.request(
            "POST",
            "/connect_sessions",
            cast_to=ConnectSession,
            json=_create_body(connector_key, profile_id, end_user),
            options=options,
        )

    def get(
        self,
        session_id: str,
        *,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """How a connect session stands. ``end_user_id`` is required with a secret key (the
        user the session was created for); a client token needs none."""
        return self._client.request(
            "GET",
            _session_path(session_id),
            cast_to=ConnectSession,
            options=merge_options(options, params={"end_user_id": end_user_id}),
        )

    def wait(
        self,
        session_id: str,
        *,
        end_user_id: str | None = None,
        poll_interval: float = 2.0,
        timeout: float | None = 600.0,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """Poll ``get`` every ``poll_interval`` seconds until the session leaves ``pending``.

        Returns the settled session — check ``.status``: only ``"succeeded"`` carries a
        ``connection_id``. ``denied``, ``failed`` and ``expired`` are outcomes, not errors.

        Raises:
            TimeoutError: still ``pending`` after ``timeout`` seconds (``None`` waits for as
                long as the session lives; the server expires it on its own).
        """
        deadline = _deadline(timeout)
        session = self.get(session_id, end_user_id=end_user_id, options=options)
        while session.status not in CONNECT_SESSION_TERMINAL_STATUSES:
            if deadline is not None and time.monotonic() >= deadline:
                raise _timed_out(session, timeout)
            _sleep(poll_interval)
            session = self.get(session_id, end_user_id=end_user_id, options=options)
        return session


class AsyncConnectSessions(AsyncAPIResource):
    async def create(
        self,
        *,
        connector_key: str,
        profile_id: str | None = None,
        end_user: EndUserParam | str | None = None,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """Start an end user connecting their own account. See :meth:`ConnectSessions.create`."""
        return await self._client.request(
            "POST",
            "/connect_sessions",
            cast_to=ConnectSession,
            json=_create_body(connector_key, profile_id, end_user),
            options=options,
        )

    async def get(
        self,
        session_id: str,
        *,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """How a connect session stands. See :meth:`ConnectSessions.get`."""
        return await self._client.request(
            "GET",
            _session_path(session_id),
            cast_to=ConnectSession,
            options=merge_options(options, params={"end_user_id": end_user_id}),
        )

    async def wait(
        self,
        session_id: str,
        *,
        end_user_id: str | None = None,
        poll_interval: float = 2.0,
        timeout: float | None = 600.0,
        options: RequestOptions | None = None,
    ) -> ConnectSession:
        """Poll until the session leaves ``pending``. See :meth:`ConnectSessions.wait`."""
        deadline = _deadline(timeout)
        session = await self.get(session_id, end_user_id=end_user_id, options=options)
        while session.status not in CONNECT_SESSION_TERMINAL_STATUSES:
            if deadline is not None and time.monotonic() >= deadline:
                raise _timed_out(session, timeout)
            await _async_sleep(poll_interval)
            session = await self.get(session_id, end_user_id=end_user_id, options=options)
        return session
