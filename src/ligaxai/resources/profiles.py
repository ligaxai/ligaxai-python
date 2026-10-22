"""``/profiles`` — the published agent profiles this key may run."""

from __future__ import annotations

from .._generated.models import Profile, ProfileList
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, path_segment

__all__ = ["AsyncProfiles", "Profiles"]


class Profiles(SyncAPIResource):
    def list(self, *, options: RequestOptions | None = None) -> ProfileList:
        """Every profile this key may run, as capability cards (``.data``)."""
        return self._client.request("GET", "/profiles", cast_to=ProfileList, options=options)

    def get(self, profile_id: str, *, options: RequestOptions | None = None) -> Profile:
        """One profile. ``NotFoundError`` both for a missing profile and one this key may
        not use, so a key cannot probe outside its allow-list."""
        return self._client.request(
            "GET",
            f"/profiles/{path_segment(profile_id, 'profile_id')}",
            cast_to=Profile,
            options=options,
        )


class AsyncProfiles(AsyncAPIResource):
    async def list(self, *, options: RequestOptions | None = None) -> ProfileList:
        """Every profile this key may run. See :meth:`Profiles.list`."""
        return await self._client.request("GET", "/profiles", cast_to=ProfileList, options=options)

    async def get(self, profile_id: str, *, options: RequestOptions | None = None) -> Profile:
        """One profile. See :meth:`Profiles.get`."""
        return await self._client.request(
            "GET",
            f"/profiles/{path_segment(profile_id, 'profile_id')}",
            cast_to=Profile,
            options=options,
        )
