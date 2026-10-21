"""Resource base classes.

A resource is a thin namespace of endpoint methods. It holds a reference to the client and
delegates every call to ``client.request`` / ``request_stream`` / ``request_page`` — it
never builds an ``httpx2.Request`` itself, so retries, headers and error mapping stay in
one place. Every resource ships a sync and an async class with the same method names.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._base_client import AsyncBaseClient, SyncBaseClient

__all__ = ["AsyncAPIResource", "SyncAPIResource"]


class SyncAPIResource:
    _client: SyncBaseClient

    def __init__(self, client: SyncBaseClient) -> None:
        self._client = client


class AsyncAPIResource:
    _client: AsyncBaseClient

    def __init__(self, client: AsyncBaseClient) -> None:
        self._client = client
