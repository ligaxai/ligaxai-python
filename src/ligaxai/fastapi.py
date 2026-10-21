"""Optional FastAPI helpers. Import only when ``fastapi`` is installed
(``pip install ligaxai[fastapi]``).

* ``client_dependency()`` builds one ``AsyncLigaX`` per process and hands it to
  route functions through ``Depends``.
* ``stream_proxy()`` re-encodes an SDK stream as ``text/event-stream`` so a backend can
  forward events to a browser without the browser ever holding the API key.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

try:
    from fastapi.responses import StreamingResponse
except ImportError:  # pragma: no cover - exercised only without the extra
    raise ImportError("ligaxai.fastapi requires fastapi; install ligaxai[fastapi]") from None

from ._client import AsyncLigaX
from ._models import BaseModel
from ._streaming import ServerSentEvent

__all__ = ["client_dependency", "encode_sse", "stream_proxy"]


def client_dependency(**client_kwargs: Any) -> Callable[[], AsyncLigaX]:
    """Return a FastAPI dependency that yields a shared ``AsyncLigaX``.

    Usage::

        get_client = client_dependency()

        @app.get("/health")
        async def health(client: AsyncLigaX = Depends(get_client)):
            return await client.health.get()
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

    return StreamingResponse(
        _agen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
