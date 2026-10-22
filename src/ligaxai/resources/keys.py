"""``/keys/self`` — the presented API key and what it may still spend."""

from __future__ import annotations

from .._generated.models import ApiKey
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource

__all__ = ["AsyncKeys", "Keys"]


class Keys(SyncAPIResource):
    def self(self, *, options: RequestOptions | None = None) -> ApiKey:
        """Describe this key: scopes, allowed profiles, spend limit and what is left.

        The quickstart's first call — it proves the key works against this deployment.
        Never returns the secret.
        """
        return self._client.request("GET", "/keys/self", cast_to=ApiKey, options=options)


class AsyncKeys(AsyncAPIResource):
    async def self(self, *, options: RequestOptions | None = None) -> ApiKey:
        """Describe this key. See :meth:`Keys.self`."""
        return await self._client.request("GET", "/keys/self", cast_to=ApiKey, options=options)
