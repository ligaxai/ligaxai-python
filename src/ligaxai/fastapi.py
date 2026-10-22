"""Optional FastAPI helpers. Import only when ``fastapi`` is installed
(``pip install ligaxai[fastapi]``).

* ``client_dependency()`` builds one ``AsyncLigaX`` per process and hands it to
  route functions through ``Depends``.
* ``run_stream_route()`` builds a ``POST`` endpoint that starts a run for one fixed
  profile and proxies its frames to the browser as ``text/event-stream``. The secret key
  stays on the server; the browser chooses only the input and which of its own
  conversations to continue.
* ``stream_proxy()`` re-encodes any SDK stream as ``text/event-stream``.
* ``client_token_route()`` builds an endpoint that mints a short-lived client token
  (``lgx_ct_…``) for the signed-in user, so the browser can call the API directly
  without ever seeing the secret key.
* ``webhook_dependency()`` verifies a webhook delivery against the request's raw body and
  hands the route a typed event, or answers ``400``.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any, TypeAlias

from pydantic import Field

try:
    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse
except ImportError:  # pragma: no cover - exercised only without the extra
    raise ImportError("ligaxai.fastapi requires fastapi; install ligaxai[fastapi]") from None

from ._client import AsyncLigaX
from ._exceptions import APIStatusError, WebhookVerificationError
from ._models import BaseModel
from ._run_stream import AsyncRunStream, RunEvent
from ._streaming import ServerSentEvent
from ._webhooks import WebhookEvent, parse_event, verify_signature
from .resources.runs import EndUserParam

__all__ = [
    "ClientTokenUserResolver",
    "EndUserResolver",
    "RunStreamBody",
    "client_dependency",
    "client_token_route",
    "encode_run_event",
    "encode_sse",
    "run_stream_route",
    "stream_proxy",
    "webhook_dependency",
]

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

#: Maps the incoming request to the end user the run is for — from *your* session, never
#: from anything the browser sends. Sync or async; ``None`` for no end user.
EndUserResolver: TypeAlias = Callable[
    [Request], EndUserParam | str | Awaitable[EndUserParam | str | None] | None
]

#: Maps the incoming request to the signed-in user a client token is for: an id, an
#: ``(id, name)`` pair, or ``{"id", "name"}`` — or ``None`` when nobody is signed in (401).
#: Sync or async; read from *your* session, never from anything the browser sends.
ClientTokenUser: TypeAlias = EndUserParam | str | tuple[str, str | None] | None
ClientTokenUserResolver: TypeAlias = Callable[
    [Request], ClientTokenUser | Awaitable[ClientTokenUser]
]

_NO_STORE = {"Cache-Control": "no-store"}


def client_dependency(**client_kwargs: Any) -> Callable[[], AsyncLigaX]:
    """Return a FastAPI dependency that yields a shared ``AsyncLigaX``.

    Usage::

        get_client = client_dependency()

        @app.get("/me")
        async def me(client: AsyncLigaX = Depends(get_client)):
            return await client.keys.self()
    """
    cached: AsyncLigaX | None = None

    def _dependency() -> AsyncLigaX:
        nonlocal cached
        if cached is None:
            cached = AsyncLigaX(**client_kwargs)
        return cached

    return _dependency


def encode_sse(item: Any) -> bytes:
    """Serialise one stream item back into SSE wire format."""
    if isinstance(item, ServerSentEvent):
        lines: list[str] = []
        if item.event:
            lines.append(f"event: {item.event}")
        if item.id:
            lines.append(f"id: {item.id}")
        if item.retry is not None:
            lines.append(f"retry: {item.retry}")
        lines.extend(f"data: {part}" for part in item.data.split("\n"))
        return ("\n".join(lines) + "\n\n").encode()
    payload = item.model_dump_json() if isinstance(item, BaseModel) else json.dumps(item)
    return f"data: {payload}\n\n".encode()


def stream_proxy(iterator: AsyncIterator[Any] | Iterator[Any]) -> StreamingResponse:
    """Wrap an SDK stream (sync or async) in a ``text/event-stream`` response."""

    async def _agen() -> AsyncIterator[bytes]:
        if isinstance(iterator, AsyncIterator):
            async for item in iterator:
                yield encode_sse(item)
        else:
            for item in iterator:
                yield encode_sse(item)
        yield b"data: [DONE]\n\n"

    return StreamingResponse(_agen(), media_type="text/event-stream", headers=dict(_SSE_HEADERS))


def encode_run_event(event: RunEvent) -> bytes:
    """One run frame as SSE: ``event: <type>``, ``id: <seq>`` (persisted frames only) and
    ``data: {"type", "seq", "payload", "run_id", "ts"}`` — the shape ``RunEvent`` parses,
    without the engine's internal run references."""
    lines = [f"event: {event.type}"]
    if event.seq is not None:
        lines.append(f"id: {event.seq}")
    lines.append(
        "data: " + event.model_dump_json(include={"type", "seq", "payload", "run_id", "ts"})
    )
    return ("\n".join(lines) + "\n\n").encode()


class RunStreamBody(BaseModel):
    """What the browser may send to a ``run_stream_route`` endpoint."""

    input: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = None


def run_stream_route(
    client: AsyncLigaX | Callable[[], AsyncLigaX],
    profile_id: str,
    resolve_end_user: EndUserResolver | None = None,
    *,
    model: str | None = None,
) -> Callable[[RunStreamBody, Request], Awaitable[Response]]:
    """Build a FastAPI endpoint that streams a run of ``profile_id`` to the browser.

    Usage::

        get_client = client_dependency()

        async def current_user(request: Request) -> str:
            return request.state.user_id          # from your auth, never the body

        app.post("/chat")(run_stream_route(get_client, "prf_…", current_user))

    The browser ``POST`` s ``{"input": "…", "conversation_id": "conv_…"?}`` and reads
    ``text/event-stream`` (see :func:`encode_run_event`); ``X-Run-Id`` and
    ``X-Conversation-Id`` come back as headers. The profile and model are fixed here, on
    the server. Because the run is started before the response begins, a refusal (unknown
    profile, spend limit, rate limit) arrives as a plain HTTP error with the API's status and
    ``{"error": {"code", "message", "request_id"}}`` instead of a broken stream.

    Pass ``resolve_end_user`` whenever more than one person uses your app: conversations
    are scoped to the end user, so one person cannot continue another's conversation.
    """

    def _client() -> AsyncLigaX:
        return client if isinstance(client, AsyncLigaX) else client()

    async def endpoint(body: RunStreamBody, request: Request) -> Response:
        end_user: EndUserParam | str | None = None
        if resolve_end_user is not None:
            resolved = resolve_end_user(request)
            end_user = await resolved if inspect.isawaitable(resolved) else resolved
        try:
            stream = await _client().runs.stream(
                profile_id=profile_id,
                input=body.input,
                conversation_id=body.conversation_id,
                end_user=end_user,
                model=model,
            )
        except APIStatusError as exc:
            return JSONResponse(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": exc.request_id,
                    }
                },
                status_code=exc.status_code,
            )
        headers = dict(_SSE_HEADERS)
        for name, value in (
            ("X-Run-Id", stream.run_id),
            ("X-Conversation-Id", stream.conversation_id),
        ):
            if value:
                headers[name] = value
        return StreamingResponse(_relay(stream), media_type="text/event-stream", headers=headers)

    return endpoint


async def _relay(stream: AsyncRunStream) -> AsyncIterator[bytes]:
    try:
        async for event in stream:
            yield encode_run_event(event)
        if stream.run is not None:
            # The server answered with a finished run (an idempotent replay): hand the
            # browser the answer as one synthetic frame rather than an empty stream.
            yield encode_run_event(
                RunEvent(
                    type="run.end",
                    run_id=stream.run.id,
                    payload={"status": stream.run.status, "text": stream.run.output.text},
                )
            )
    finally:
        await stream.close()


def _end_user_param(user: EndUserParam | str | tuple[str, str | None]) -> EndUserParam | str:
    if isinstance(user, tuple):
        user_id, name = user
        return {"id": user_id, "name": name} if name else {"id": user_id}
    return user


def client_token_route(
    client: AsyncLigaX | Callable[[], AsyncLigaX],
    profile_id: str,
    resolve_end_user: ClientTokenUserResolver,
    *,
    expires_in: int | None = None,
) -> Callable[[Request], Awaitable[Response]]:
    """Build a FastAPI endpoint that mints a client token for the signed-in user.

    Usage::

        get_client = client_dependency()

        async def current_user(request: Request) -> tuple[str, str] | None:
            user = request.state.user                 # from your auth, never the body
            return (user.id, user.name) if user else None

        app.post("/ligax/token")(client_token_route(get_client, "prf_…", current_user))

    The browser calls it (``POST``, with its session cookie) and receives
    ``{"token": "lgx_ct_…", "expires_at": "…"}`` with ``Cache-Control: no-store``, then
    calls the API directly with ``Authorization: Bearer <token>``. The token runs only
    ``profile_id``, only as that user, and expires in minutes (``expires_in``, 60 to 3600
    seconds, server default 600) — have the page fetch a fresh one when it does.

    ``resolve_end_user`` returning ``None`` answers ``401`` without calling the API. A
    refusal from the API (missing ``client_tokens:write`` scope, unknown profile) comes
    back with its status and ``{"error": {"code", "message", "request_id"}}``. The profile
    must list your website under *allowed origins*, or the browser's calls are refused.
    """

    def _client() -> AsyncLigaX:
        return client if isinstance(client, AsyncLigaX) else client()

    async def endpoint(request: Request) -> Response:
        resolved = resolve_end_user(request)
        user = await resolved if inspect.isawaitable(resolved) else resolved
        if not user:  # None, or an empty id: nobody is signed in
            return JSONResponse(
                {"error": {"code": "unauthenticated", "message": "Sign in first."}},
                status_code=401,
                headers=dict(_NO_STORE),
            )
        try:
            minted = await _client().client_tokens.create(
                profile_id=profile_id, end_user=_end_user_param(user), expires_in=expires_in
            )
        except APIStatusError as exc:
            return JSONResponse(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "request_id": exc.request_id,
                    }
                },
                status_code=exc.status_code,
                headers=dict(_NO_STORE),
            )
        # Only what the browser needs; the profile and user it was minted for are the
        # server's business, and a bearer credential is never cached on the way.
        return JSONResponse(
            {"token": minted.token, "expires_at": minted.expires_at}, headers=dict(_NO_STORE)
        )

    return endpoint


def webhook_dependency(
    secret: str | Callable[[], str],
) -> Callable[[Request], Awaitable[WebhookEvent]]:
    """Return a FastAPI dependency that verifies a webhook and yields its typed event.

    Usage::

        verified = webhook_dependency(lambda: settings.ligax_webhook_secret)

        @app.post("/hooks/ligax", status_code=204)
        async def hook(
            background: BackgroundTasks,
            event: WebhookEvent = Depends(verified),
            webhook_id: str = Header(),
        ) -> None:
            background.add_task(handle, webhook_id, event)   # answer fast, work later

    It reads the **raw** body (``await request.body()``), never a parsed model, because the
    signature covers the exact bytes. A bad or missing signature, a stale timestamp, or a
    body that is not an event answers ``400`` before the route runs. ``secret`` may be a
    callable so it is read per request (rotation, settings loaded after import).
    """

    async def _dependency(request: Request) -> WebhookEvent:
        key = secret() if callable(secret) else secret
        body = await request.body()
        try:
            # An invalid `secret` is a configuration error: its ValueError propagates (500).
            verify_signature(body, request.headers, key)
        except WebhookVerificationError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc
        try:
            return parse_event(body)
        except ValueError as exc:
            # Signed but not an event this SDK can parse: 4xx so the server retries it
            # later rather than the receiver dropping it.
            raise HTTPException(status_code=400, detail="Webhook body is not an event.") from exc

    return _dependency
