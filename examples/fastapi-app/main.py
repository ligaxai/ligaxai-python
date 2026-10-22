"""A FastAPI backend that runs a LigaX agent while the API key stays server-side.

    export LIGAX_API_KEY=lgx_sk_...          # never commit it; local env files are git-ignored
    export LIGAX_PROFILE_ID=prf_...          # a published profile this key may run
    export LIGAX_BASE_URL=...                # optional: the development platform
    uv run uvicorn main:app --reload

GET  /         a one-file chat page that streams through /chat
GET  /me       what the key is allowed to do (keys.self)
POST /ask      {"input": "..."} -> the finished run as JSON (runs.wait)
POST /chat     {"input": "...", "conversation_id"?: "..."} -> text/event-stream (run_stream_route)
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ligaxai import AsyncLigaX
from ligaxai.fastapi import client_dependency, run_stream_route

PROFILE_ID = os.environ.get("LIGAX_PROFILE_ID", "")

app = FastAPI(title="LigaX agent example")
# One AsyncLigaX per process; reads LIGAX_API_KEY / LIGAX_BASE_URL on first use.
get_client = client_dependency()


def current_user(request: Request) -> str:
    """Who the run is for. A real app reads this from its own session or token — never from
    the request body — so one user cannot continue another's conversation."""
    return request.headers.get("x-demo-user", "demo-user")


class Ask(BaseModel):
    input: str
    conversation_id: str | None = None


@app.get("/me")
async def me(client: AsyncLigaX = Depends(get_client)) -> dict[str, object]:  # noqa: B008
    key = await client.keys.self()
    return {
        "name": key.name,
        "environment": key.environment,
        "scopes": key.scopes,
        "remaining_usd": key.limit.remaining_usd,
        "request_id": key.request_id,
    }


@app.post("/ask")
async def ask(
    body: Ask,
    request: Request,
    client: AsyncLigaX = Depends(get_client),  # noqa: B008
) -> dict[str, object]:
    run = await client.runs.wait(
        profile_id=PROFILE_ID,
        input=body.input,
        conversation_id=body.conversation_id,
        end_user=current_user(request),
    )
    return {
        "status": run.status,
        "text": run.output.text,
        "run_id": run.id,
        "conversation_id": run.conversation_id,
        "required_action": run.required_action.model_dump() if run.required_action else None,
    }


app.post("/chat")(run_stream_route(get_client, PROFILE_ID, current_user))


PAGE = """<!doctype html>
<meta charset="utf-8"><title>LigaX agent</title>
<style>
  body { font: 16px system-ui; max-width: 42rem; margin: 2rem auto; padding: 0 1rem }
  #out { white-space: pre-wrap; border: 1px solid #ccc; border-radius: 8px;
         padding: 1rem; min-height: 4rem }
</style>
<form id="f"><input id="q" style="width:80%" placeholder="Ask the agent">
<button>Send</button></form>
<p id="out"></p><small id="meta"></small>
<script>
let conversationId = null;
document.getElementById("f").onsubmit = async (e) => {
  e.preventDefault();
  const out = document.getElementById("out"), meta = document.getElementById("meta");
  out.textContent = "";
  const res = await fetch("/chat", {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({
      input: document.getElementById("q").value, conversation_id: conversationId,
    }),
  });
  if (!res.ok) {
    out.textContent = (await res.json()).error?.message ?? res.statusText;
    return;
  }
  conversationId = res.headers.get("x-conversation-id");
  // Text deltas are offset-addressed in UTF-16 units — the unit JavaScript strings use.
  // Write each at its position so a repeated frame never duplicates text.
  const parts = new Map(), order = [];
  const ensure = (id) => { if (!parts.has(id)) { parts.set(id, ""); order.push(id); } };
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const {value, done} = await reader.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\\n\\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block.split("\\n").filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6)).join("\\n");
      if (!data) continue;
      const ev = JSON.parse(data), p = ev.payload || {};
      if (ev.type === "part.start" && p.kind === "text") ensure(p.part_id);
      if (ev.type === "text.delta") {
        ensure(p.part_id);
        const cur = parts.get(p.part_id).padEnd(p.offset, " ");
        parts.set(p.part_id,
          cur.slice(0, p.offset) + p.text + cur.slice(p.offset + p.text.length));
        out.textContent = order.map((id) => parts.get(id)).join("");
      }
      if (ev.type === "run.end") {
        meta.textContent = `status: ${p.status} · conversation: ${conversationId}`;
      }
    }
  }
};
</script>
"""


@app.get("/", response_class=HTMLResponse)
async def page() -> str:
    return PAGE
