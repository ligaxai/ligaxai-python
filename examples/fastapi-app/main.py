"""Minimal FastAPI backend that keeps the API key server-side.

    uv run --project . uvicorn main:app --reload

GET /token-example   -> calls the API with the server's key and returns the result
GET /stream-example  -> proxies an SSE stream to the browser
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ligaxai import AsyncLigaX
from ligaxai.fastapi import client_dependency, stream_proxy

app = FastAPI(title="LigaX AI example")
get_client = client_dependency()  # reads LIGAX_API_KEY / LIGAX_BASE_URL


@app.get("/token-example")
async def token_example(client: AsyncLigaX = Depends(get_client)) -> dict[str, str | None]:  # noqa: B008
    health = await client.health.get()
    return {"status": health.status, "request_id": health.request_id}


@app.get("/stream-example")
async def stream_example(client: AsyncLigaX = Depends(get_client)) -> object:  # noqa: B008
    # Replace "/events" with a real streaming endpoint once the spec is synced.
    stream = await client.request_stream("GET", "/events")
    return stream_proxy(stream)
