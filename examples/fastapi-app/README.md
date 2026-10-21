# FastAPI example

A two-route backend showing the recommended integration: the API key lives on the server,
the browser talks to your app, and streams are proxied as SSE.

```bash
cd examples/fastapi-app
export LIGAX_API_KEY=...        # never commit this; examples/**/.env is git-ignored
uv run uvicorn main:app --reload
curl localhost:8000/token-example
curl -N localhost:8000/stream-example
```

The example is not part of the repo's test suite or workspace; it installs the SDK from the
parent directory in editable mode.
