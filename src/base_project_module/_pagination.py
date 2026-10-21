"""Cursor pagination.

A list endpoint returns ``{"data": [...], "next_page": "<cursor>" | null}``. The page
object remembers how it was fetched so ``get_next_page()`` can replay the call with the
``page`` query parameter set to the cursor, and ``__iter__`` walks every page.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import PrivateAttr

from ._models import BaseModel
from ._types import RequestOptions

if TYPE_CHECKING:
    from ._base_client import AsyncBaseClient, SyncBaseClient

__all__ = ["AsyncPage", "PageRequest", "SyncPage"]

T = TypeVar("T")

PAGE_PARAM = "page"


@dataclass(slots=True)
class PageRequest:
    """Everything needed to re-issue the request that produced a page."""

    method: str
    path: str
    json: Any = None
    options: RequestOptions = field(default_factory=RequestOptions)

    def for_cursor(self, cursor: str) -> PageRequest:
        opts = RequestOptions(
            headers=dict(self.options.headers),
            params={**self.options.params, PAGE_PARAM: cursor},
            timeout=self.options.timeout,
            max_retries=self.options.max_retries,
            idempotency_key=self.options.idempotency_key,
        )
        return PageRequest(self.method, self.path, self.json, opts)


class _BasePage(BaseModel, Generic[T]):
    data: list[T]
    next_page: str | None = None

    _page_request: PageRequest | None = PrivateAttr(default=None)

    def has_next_page(self) -> bool:
        return bool(self.next_page) and bool(self.data)


class SyncPage(_BasePage[T]):
    _client: SyncBaseClient | None = PrivateAttr(default=None)

    def bind(self, client: SyncBaseClient, request: PageRequest) -> None:
        """Remember how this page was fetched so ``get_next_page`` can replay it."""
        self._client = client
        self._page_request = request

    def get_next_page(self) -> SyncPage[T]:
        if not self.has_next_page() or self._client is None or self._page_request is None:
            raise RuntimeError("No next page available; check has_next_page() first.")
        assert self.next_page is not None
        req = self._page_request.for_cursor(self.next_page)
        return self._client.request_page(type(self), req)

    def __iter__(self) -> Iterator[T]:  # type: ignore[override]
        page: SyncPage[T] = self
        while True:
            yield from page.data
            if not page.has_next_page():
                return
            page = page.get_next_page()


class AsyncPage(_BasePage[T]):
    _client: AsyncBaseClient | None = PrivateAttr(default=None)

    def bind(self, client: AsyncBaseClient, request: PageRequest) -> None:
        """Remember how this page was fetched so ``get_next_page`` can replay it."""
        self._client = client
        self._page_request = request

    async def get_next_page(self) -> AsyncPage[T]:
        if not self.has_next_page() or self._client is None or self._page_request is None:
            raise RuntimeError("No next page available; check has_next_page() first.")
        assert self.next_page is not None
        req = self._page_request.for_cursor(self.next_page)
        return await self._client.request_page(type(self), req)

    async def __aiter__(self) -> AsyncIterator[T]:
        page: AsyncPage[T] = self
        while True:
            for item in page.data:
                yield item
            if not page.has_next_page():
                return
            page = await page.get_next_page()
