"""Resource base classes.

A resource is a thin namespace of endpoint methods. It holds a reference to the client and
delegates every call to ``client.request`` / ``request_stream`` / ``request_page`` — it
never builds an ``httpx2.Request`` itself, so retries, headers and error mapping stay in
one place. Every resource ships a sync and an async class with the same method names.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .._types import RequestOptions

if TYPE_CHECKING:
    from .._base_client import AsyncBaseClient, SyncBaseClient

__all__ = ["AsyncAPIResource", "SyncAPIResource", "merge_options", "path_segment"]


class SyncAPIResource:
    _client: SyncBaseClient

    def __init__(self, client: SyncBaseClient) -> None:
        self._client = client


class AsyncAPIResource:
    _client: AsyncBaseClient

    def __init__(self, client: AsyncBaseClient) -> None:
        self._client = client


def merge_options(
    options: RequestOptions | None,
    *,
    params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> RequestOptions:
    """The caller's ``options`` plus an endpoint's own query parameters / idempotency key.

    The caller's values win: an explicit ``RequestOptions(params=…)`` is a deliberate
    override, and so is ``RequestOptions(idempotency_key=…)``.
    """
    base = options or RequestOptions()
    merged_params = {k: v for k, v in (params or {}).items() if v is not None}
    merged_params.update(base.params)
    return dataclasses.replace(
        base,
        headers=dict(base.headers),
        params=merged_params,
        idempotency_key=base.idempotency_key or idempotency_key,
    )


def path_segment(value: str, name: str) -> str:
    """Percent-encode one path segment, refusing an empty id before a request is made."""
    if not isinstance(value, str) or not value:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return quote(value, safe="")
