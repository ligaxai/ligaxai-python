"""``GET /health`` — the one example resource. Copy this file when adding a real one."""

from __future__ import annotations

from .._models import BaseModel
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource

__all__ = ["AsyncHealth", "Health", "HealthResponse"]


class HealthResponse(BaseModel):
    status: str
    version: str | None = None


class Health(SyncAPIResource):
    def get(self, *, options: RequestOptions | None = None) -> HealthResponse:
        """Check that the API is reachable and the key is accepted."""
        return self._client.request("GET", "/health", cast_to=HealthResponse, options=options)


class AsyncHealth(AsyncAPIResource):
    async def get(self, *, options: RequestOptions | None = None) -> HealthResponse:
        """Check that the API is reachable and the key is accepted."""
        return await self._client.request("GET", "/health", cast_to=HealthResponse, options=options)
