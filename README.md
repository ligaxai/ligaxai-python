# LigaX AI Python SDK

[![CI](https://github.com/ligaxai/ligaxai/actions/workflows/ci.yml/badge.svg)](https://github.com/ligaxai/ligaxai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ligaxai.svg)](https://pypi.org/project/ligaxai/)
[![Python](https://img.shields.io/pypi/pyversions/ligaxai.svg)](https://pypi.org/project/ligaxai/)

The official Python client for the LigaX AI API. Sync and async clients with the
same surface, typed responses, automatic retries, streaming and webhook verification.

## Install

```bash
pip install ligaxai            # or: uv add ligaxai
pip install "ligaxai[fastapi]" # adds the FastAPI helpers
```

Requires Python 3.11 or newer.

## Quickstart

Set your key once:

```bash
export LIGA_X_API_KEY="..."
```

Sync:

```python
from ligaxai import LigaX

client = LigaX()            # reads LIGA_X_API_KEY
health = client.health.get()
print(health.status, health.request_id)
```

Async:

```python
from ligaxai import AsyncLigaX

async with AsyncLigaX() as client:
    health = await client.health.get()
```

Streaming (server-sent events):

```python
from ligaxai import BaseModel, LigaX, EventRegistry

class Delta(BaseModel):
    text: str

with LigaX() as client:
    stream = client.request_stream("POST", "/runs", json={"input": "hi"},
                                   registry=EventRegistry({"delta": Delta}))
    for event in stream:
        if isinstance(event, Delta):
            print(event.text, end="", flush=True)
    print("resume from", stream.last_event_id)
```

## Configuration

| Setting     | Argument           | Environment variable    | Default                       |
| ----------- | ------------------ | ----------------------- | ----------------------------- |
| API key     | `api_key=`         | `LIGA_X_API_KEY`  | — (required)                  |
| Base URL    | `base_url=`        | `LIGA_X_BASE_URL` | `https://api.ligax.ai/api/public/v1`        |
| Timeout     | `timeout=`         |                         | `Timeout(600, connect=5)`     |
| Retries     | `max_retries=`     |                         | `2`                           |
| Headers     | `default_headers=` |                         | `{}`                          |
| Logging     |                    | `LIGA_X_LOG`      | `off`                         |
| HTTP client | `http_client=`     |                         | an `httpx2.Client` of our own |

`client.with_options(max_retries=0, timeout=10)` returns a copy that shares the connection
pool. Every method also takes `options=RequestOptions(headers=…, params=…, timeout=…,
max_retries=…, idempotency_key=…)`.

## Retries and timeouts

Failed requests are retried twice by default with exponential backoff (0.5 s → 8 s, 25 %
jitter). Retried: connection errors, timeouts, 408, 409, 429 and every 5xx. **Never**
retried: 402 and 403, or anything once a stream has started. The server can override the
decision with `x-should-retry: true|false` and steer the delay with `retry-after-ms` or
`retry-after` (seconds or HTTP-date, honoured up to 120 s).

Every POST carries an `Idempotency-Key` that is reused across retries, so a replayed write
is safe. Pass your own via `RequestOptions(idempotency_key=…)`.

## Errors

```python
from ligaxai import APIConnectionError, APIStatusError, RateLimitError

try:
    client.health.get()
except RateLimitError as e:
    print(e.status_code, e.code, e.request_id, e.response.headers.get("retry-after"))
except APIStatusError as e:   # any 4xx/5xx
    print(e.status_code, e.message, e.body)
except APIConnectionError:    # includes APITimeoutError
    ...
```

| Status | Exception                  |
| ------ | -------------------------- |
| 400    | `BadRequestError`          |
| 401    | `AuthenticationError`      |
| 402    | `PaymentRequiredError`     |
| 403    | `PermissionDeniedError`    |
| 404    | `NotFoundError`            |
| 409    | `ConflictError`            |
| 422    | `UnprocessableEntityError` |
| 429    | `RateLimitError`           |
| ≥ 500  | `InternalServerError`      |

`code`, `type`, `param` and `request_id` come from the JSON error envelope
`{"error": {"type", "code", "message", "request_id", "param"}}`; `request_id` falls back
to the `X-Request-Id` header. Successful responses expose it too: `result.request_id`.

## Logging

`LIGA_X_LOG=debug|info|warn|error|off` configures the `ligaxai`
logger. `Authorization` values are redacted before they reach any handler.

## Webhooks

```python
from ligaxai import WebhookVerificationError, webhooks

try:
    event = webhooks.verify(request.body, request.headers, secret=WEBHOOK_SECRET)
except WebhookVerificationError:
    return 400
```

Follows the [Standard Webhooks](https://www.standardwebhooks.com) spec
(`webhook-id`, `webhook-timestamp`, `webhook-signature`). Verify the **raw** body bytes.

## FastAPI

```python
from fastapi import Depends, FastAPI
from ligaxai import AsyncLigaX
from ligaxai.fastapi import client_dependency, stream_proxy

app = FastAPI()
get_client = client_dependency()

@app.get("/chat")
async def chat(client: AsyncLigaX = Depends(get_client)):
    return stream_proxy(await client.request_stream("POST", "/runs", json={}))
```

See [`examples/fastapi-app`](examples/fastapi-app) for a runnable app.

## Runtime support

| Python | Status                                            |
| ------ | ------------------------------------------------- |
| 3.14   | tested in CI                                      |
| 3.13   | tested in CI                                      |
| 3.12   | tested in CI                                      |
| 3.11   | tested in CI — minimum                            |
| ≤ 3.10 | not supported (3.10 reached end of life Oct 2026) |

Tested on Linux, macOS and Windows. Transport is [`httpx2`](https://pypi.org/project/httpx2/);
if your app still imports plain `httpx` and you want one shared stack, call
`httpx2.alias_httpx()` **before** any `httpx` import — this library never does that for you.

## Development

```bash
make setup      # uv sync + pre-commit
make check      # ruff + mypy strict + pyright (+ verifytypes >= 95 %)
make test       # unit + conformance, HTTP always mocked
make test-cov   # coverage gate (85 %)
make build      # sdist + wheel
```

Releases: bump `src/ligaxai/_version.py`, update `CHANGELOG.md`, tag `vX.Y.Z`.
`release.yml` builds and publishes through PyPI trusted publishing.

## How to use this template

This repository is a **base template**: the names above are placeholder tokens. To start a
real SDK from it:

```bash
./scripts/bootstrap.sh <slug> <module> <ClassPrefix> "<Title>" <github-org> <base-url>
# e.g. ./scripts/bootstrap.sh acme acme Acme "Acme" acme-inc https://api.acme.com/api/public/v1
```

It rewrites every token in tracked files, renames `src/ligaxai`, re-locks and
prints a summary. Then set `SPEC_VERSION`, run `make sync-spec && make gen-types`, add
resources next to `resources/health.py`, and delete this section. The full token list is in
[`docs/TEMPLATE-TOKENS.md`](docs/TEMPLATE-TOKENS.md).

## License

Apache-2.0 — see [LICENSE](LICENSE).
