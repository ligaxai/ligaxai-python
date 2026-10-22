"""``/client_tokens`` — mint a short-lived token for one user's browser.

Your **server** calls this with a secret key holding ``client_tokens:write`` and hands the
token (``lgx_ct_…``) to the signed-in user's browser. The browser can then start runs of
that one profile, as that one end user, and read that user's conversations — nothing else:
no other profile, no other person's history, no webhooks, no usage. The token expires in
minutes (default 10, at most 60) and stops at once if its parent key is disabled, revoked
or rotated. The browser therefore never holds your secret key.

The profile must list the website's origin under *allowed origins*, or the platform refuses
the browser's requests. ``POST /widget/sessions`` (publishable keys) is browser-only and has
no method here.
"""

from __future__ import annotations

from typing import Any

from .._generated.models import ClientToken
from .._types import RequestOptions
from ._base import AsyncAPIResource, SyncAPIResource
from .runs import EndUserParam

__all__ = ["AsyncClientTokens", "ClientTokens"]


def _create_body(
    profile_id: str,
    end_user: EndUserParam | str,
    conversation_id: str | None,
    expires_in: int | None,
) -> dict[str, Any]:
    # A token without an end user would be a token for anyone, so `end_user` is required
    # here as it is on the server; a bare string is shorthand for `{"id": …}`.
    if isinstance(end_user, str):
        if not end_user:
            raise ValueError("end_user must be a non-empty id")
        user: dict[str, Any] = {"id": end_user}
    else:
        user = dict(end_user)
    body: dict[str, Any] = {"profile_id": profile_id, "end_user": user}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    if expires_in is not None:
        body["expires_in"] = expires_in
    return body


class ClientTokens(SyncAPIResource):
    def create(
        self,
        *,
        profile_id: str,
        end_user: EndUserParam | str,
        conversation_id: str | None = None,
        expires_in: int | None = None,
        options: RequestOptions | None = None,
    ) -> ClientToken:
        """Mint a token a browser may use to run ``profile_id`` as ``end_user``.

        Args:
            profile_id: The one profile (``prf_…``) the token may run.
            end_user: The signed-in user, from *your* session — an id, or
                ``{"id", "name"}``. Their conversations are the only ones the token reads.
            conversation_id: Pin the token to one existing conversation (``conv_…``).
            expires_in: Lifetime in seconds, 60 to 3600; the server defaults to 600.

        ``.token`` is a bearer credential: send it only to the browser it was minted for
        (with ``Cache-Control: no-store``) and never log it.
        """
        return self._client.request(
            "POST",
            "/client_tokens",
            cast_to=ClientToken,
            json=_create_body(profile_id, end_user, conversation_id, expires_in),
            options=options,
        )


class AsyncClientTokens(AsyncAPIResource):
    async def create(
        self,
        *,
        profile_id: str,
        end_user: EndUserParam | str,
        conversation_id: str | None = None,
        expires_in: int | None = None,
        options: RequestOptions | None = None,
    ) -> ClientToken:
        """Mint a token for one browser. See :meth:`ClientTokens.create`."""
        return await self._client.request(
            "POST",
            "/client_tokens",
            cast_to=ClientToken,
            json=_create_body(profile_id, end_user, conversation_id, expires_in),
            options=options,
        )
