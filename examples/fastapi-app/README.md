# FastAPI example

A small backend showing the recommended integration: the API key lives on the server, the
browser talks to your app, and a run's frames are proxied to the browser as SSE.

```bash
cd examples/fastapi-app
export LIGAX_API_KEY=lgx_sk_...   # never commit it; local env files are git-ignored
export LIGAX_PROFILE_ID=prf_...   # a published profile this key may run
# Optional — the development platform:
export LIGAX_BASE_URL=https://<dev-host>/api/public/v1
export LIGAX_DEMO_USER=me         # local try-out only: everyone is this one user
uv run uvicorn main:app --reload
```

Then open <http://localhost:8000/> for a one-file chat page, or:

```bash
curl -s localhost:8000/ask -H 'content-type: application/json' -d '{"input":"Hello"}'
curl -N localhost:8000/chat -H 'content-type: application/json' -d '{"input":"Hello"}'
```

| Route | What it shows |
| --- | --- |
| `POST /ask` | `client.runs.wait(...)` — one JSON answer, polling past the 240 s server wait |
| `POST /chat` | `run_stream_route(...)` — the browser streams a run without ever holding the key |

**Before you deploy it, replace `current_user()` with your own authentication.** Every run acts as
the user it returns — with the accounts they connected — and is billed to your key, so it must
come from your session, never from the request body or a header the browser sets. Without a
signed-in user `/ask` and `/chat` answer 401. Give the key a spend limit and only the scopes it
needs, and rate-limit both routes. Never expose `client.keys.self()` to the browser: it shows
the key's scopes and remaining spend.

The example is not part of the repo's test suite or workspace; it installs the SDK from the
parent directory in editable mode.
