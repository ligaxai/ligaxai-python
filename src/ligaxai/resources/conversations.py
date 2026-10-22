"""``/conversations`` — a conversation and the runs in it."""

from __future__ import annotations

from .._generated.models import Conversation
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource, merge_options, path_segment

__all__ = ["AsyncConversations", "Conversations"]


class Conversations(SyncAPIResource):
    def get(
        self,
        conversation_id: str,
        *,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> Conversation:
        """A conversation and its runs (oldest first, up to 50).

        A conversation started for an end user is only readable by naming that end user;
        one started without an end user is read without ``end_user_id``.
        """
        return self._client.request(
            "GET",
            f"/conversations/{path_segment(conversation_id, 'conversation_id')}",
            cast_to=Conversation,
            options=merge_options(options, params={"end_user_id": end_user_id}),
        )


class AsyncConversations(AsyncAPIResource):
    async def get(
        self,
        conversation_id: str,
        *,
        end_user_id: str | None = None,
        options: RequestOptions | None = None,
    ) -> Conversation:
        """A conversation and its runs. See :meth:`Conversations.get`."""
        return await self._client.request(
            "GET",
            f"/conversations/{path_segment(conversation_id, 'conversation_id')}",
            cast_to=Conversation,
            options=merge_options(options, params={"end_user_id": end_user_id}),
        )
