"""``/usage`` — this key's spend in daily buckets."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypeAlias

from .._generated.models import UsageReport
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, merge_options

__all__ = ["AsyncUsage", "Usage", "UsageGroupBy"]

UsageGroupBy: TypeAlias = Literal["profile", "model", "end_user"]


def _iso(value: str | date | datetime | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.isoformat()


def _params(
    start: str | date | datetime | None,
    end: str | date | datetime | None,
    group_by: UsageGroupBy | None,
) -> dict[str, str | None]:
    return {"start": _iso(start), "end": _iso(end), "group_by": group_by}


class Usage(SyncAPIResource):
    def get(
        self,
        *,
        start: str | date | datetime | None = None,
        end: str | date | datetime | None = None,
        group_by: UsageGroupBy | None = None,
        options: RequestOptions | None = None,
    ) -> UsageReport:
        """This key's spend in daily buckets.

        ``start`` / ``end`` are ISO dates or datetimes (default: the last 7 days; at most
        31). Give a datetime a timezone — a naive one is read in the server's. ``group_by``
        splits each bucket by ``profile``, ``model`` or ``end_user``.
        """
        return self._client.request(
            "GET",
            "/usage",
            cast_to=UsageReport,
            options=merge_options(options, params=_params(start, end, group_by)),
        )


class AsyncUsage(AsyncAPIResource):
    async def get(
        self,
        *,
        start: str | date | datetime | None = None,
        end: str | date | datetime | None = None,
        group_by: UsageGroupBy | None = None,
        options: RequestOptions | None = None,
    ) -> UsageReport:
        """This key's spend in daily buckets. See :meth:`Usage.get`."""
        return await self._client.request(
            "GET",
            "/usage",
            cast_to=UsageReport,
            options=merge_options(options, params=_params(start, end, group_by)),
        )
