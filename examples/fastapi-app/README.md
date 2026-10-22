# FastAPI example

A small backend showing the recommended integration: the API key lives on the server, the
browser talks to your app, and a run's frames are proxied to the browser as SSE.

```bash
cd examples/fastapi-app
export LIGAX_API_KEY=lgx_sk_...   # never commit it; local env files are git-ignored
export LIGAX_PROFILE_ID=prf_...   # a published profile this key may run
# Optional — the development platform:
export LIGAX_BASE_URL=https://ligax-ai-dev-2p3fwh332a-uc.a.run.app/api/public/v1
uv run uvicorn main:app --reload
```

Then open <http://localhost:8000/> for a one-file chat page, or:

```bash
curl localhost:8000/me
curl -s localhost:8000/ask -H 'content-type: application/json' -d '{"input":"Hello"}'
curl -N localhost:8000/chat -H 'content-type: application/json' -d '{"input":"Hello"}'
```

| Route | What it shows |
| --- | --- |
| `GET /me` | `client.keys.self()` — the key's scopes and remaining spend |
| `POST /ask` | `client.runs.wait(...)` — one JSON answer, polling past the 240 s server wait |
| `POST /chat` | `run_stream_route(...)` — the browser streams a run without ever holding the key |

`current_user()` stands in for your own authentication: the end user decides which
conversations a request may continue, so it must come from your session, never from the
request body.

The example is not part of the repo's test suite or workspace; it installs the SDK from the
parent directory in editable mode.
