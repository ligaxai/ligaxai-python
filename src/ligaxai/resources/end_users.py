"""``/end_users/{end_user_id}/connections`` — the accounts an end user connected themselves.

The list holds only connections made through ``connect_sessions``, never the workspace's
shared ones. A client token can see and disconnect only its own user's accounts. Scopes:
``connections:read`` to list, ``connections:write`` to delete.

Mounted as ``client.end_users.connections`` so a later per-user endpoint has a home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._generated.models import EndUserConnectionDeleted, EndUserConnectionList
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, path_segment

if TYPE_CHECKING:
    from .._base_client import AsyncBaseClient, SyncBaseClient

__all__ = [
    "AsyncEndUserConnections",
    "AsyncEndUsers",
    "EndUserConnections",
    "EndUsers",
]


def _connections_path(end_user_id: str, connection_id: str | None = None) -> str:
    path = f"/end_users/{path_segment(end_user_id, 'end_user_id')}/connections"
    if connection_id is not None:
        path += f"/{path_segment(connection_id, 'connection_id')}"
    return path


class EndUserConnections(SyncAPIResource):
    def list(
        self, end_user_id: str, *, options: RequestOptions | None = None
    ) -> EndUserConnectionList:
        """The accounts ``end_user_id`` connected themselves (``.data``)."""
        return self._client.request(
            "GET",
            _connections_path(end_user_id),
            cast_to=EndUserConnectionList,
            options=options,
        )

    def delete(
        self, end_user_id: str, connection_id: str, *, options: RequestOptions | None = None
    ) -> EndUserConnectionDeleted:
        """Disconnect one of ``end_user_id``'s own accounts. ``NotFoundError`` for an id
        that is not theirs. Sends a ``connection.deleted`` webhook."""
        return self._client.request(
            "DELETE",
            _connections_path(end_user_id, connection_id),
            cast_to=EndUserConnectionDeleted,
            options=options,
        )


class AsyncEndUserConnections(AsyncAPIResource):
    async def list(
        self, end_user_id: str, *, options: RequestOptions | None = None
    ) -> EndUserConnectionList:
        """An end user's own accounts. See :meth:`EndUserConnections.list`."""
        return await self._client.request(
            "GET",
            _connections_path(end_user_id),
            cast_to=EndUserConnectionList,
            options=options,
        )

    async def delete(
        self, end_user_id: str, connection_id: str, *, options: RequestOptions | None = None
    ) -> EndUserConnectionDeleted:
        """Disconnect one account. See :meth:`EndUserConnections.delete`."""
        return await self._client.request(
            "DELETE",
            _connections_path(end_user_id, connection_id),
            cast_to=EndUserConnectionDeleted,
            options=options,
        )


class EndUsers(SyncAPIResource):
    """Your end users — people in *your* system, not LigaX members."""

    connections: EndUserConnections

    def __init__(self, client: SyncBaseClient) -> None:
        super().__init__(client)
        self.connections = EndUserConnections(client)


class AsyncEndUsers(AsyncAPIResource):
    """Your end users. See :class:`EndUsers`."""

    connections: AsyncEndUserConnections

    def __init__(self, client: AsyncBaseClient) -> None:
        super().__init__(client)
        self.connections = AsyncEndUserConnections(client)
