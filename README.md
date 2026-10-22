# LigaX AI Python SDK

[![CI](https://github.com/ligaxai/ligaxai/actions/workflows/ci.yml/badge.svg)](https://github.com/ligaxai/ligaxai/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ligaxai.svg)](https://pypi.org/project/ligaxai/)
[![Python](https://img.shields.io/pypi/pyversions/ligaxai.svg)](https://pypi.org/project/ligaxai/)

The official Python client for the **LigaX Agent API**: run the agents you configure in
LigaX from your own software. Sync and async clients with the same surface, typed
responses, automatic retries with idempotency keys, and streaming that is safe to resume.

## Install

```bash
pip install ligaxai            # or: uv add ligaxai
pip install "ligaxai[fastapi]" # adds the FastAPI helpers
```

Requires Python 3.11 or newer.

## Quickstart

Create an organisation API key in LigaX under **Settings → Developers**, publish an agent
profile for it, and set the key once:

```bash
export LIGAX_API_KEY="lgx_sk_..."
# Optional — the development platform instead of production:
export LIGAX_BASE_URL="https://ligax-ai-dev-2p3fwh332a-uc.a.run.app/api/public/v1"
```

Run an agent and wait for the answer:

```python
from ligaxai import LigaX

client = LigaX()  # reads LIGAX_API_KEY (and LIGAX_BASE_URL)
run = client.runs.wait(profile_id="prf_...", input="Summarise yesterday's P1 incidents.")
print(run.status, run.output.text)
```

`client.profiles.list()` shows the profiles your key may run, and `client.keys.self()`
shows the key's scopes and remaining spend — a good first call to prove the key works.

### Streaming

```python
with client.runs.stream(profile_id="prf_...", input="Draft a reply to ticket 4411.") as stream:
    for text in stream.text_stream():
        print(text, end="", flush=True)

print()
print(stream.status, stream.run_id, stream.conversation_id)
```

`stream.text_stream()` yields only newly arrived answer text. Iterate the stream itself
for every frame as a `RunEvent(type, seq, payload, run_id)` — tool calls, sources,
artifacts, `run.end` — and call `stream.final_text()` for the whole answer.

If the connection drops, resume from the last frame you saw:

```python
resumed = client.runs.follow_events(stream.run_id, after=stream.last_seq)
```

### Async

```python
import asyncio
from ligaxai import AsyncLigaX

async def main() -> None:
    async with AsyncLigaX() as client:
        run = await client.runs.wait(profile_id="prf_...", input="Hello")
        print(run.output.text)

        async with client.runs.stream(profile_id="prf_...", input="And again") as stream:
            async for text in stream.text_stream():
                print(text, end="", flush=True)

asyncio.run(main())
```

### Conversations, end users and approvals

```python
first = client.runs.wait(profile_id="prf_...", input="Open a ticket for the VPN outage",
                         end_user="user-42")
if first.status == "requires_action":           # the agent is asking before it acts
    action = first.required_action
    print(action.prompt)
    client.runs.resolve_interrupt(first.id, action.interrupt_id, decision="approve")

follow_up = client.runs.wait(profile_id="prf_...", input="Make it P2",
                             conversation_id=first.conversation_id, end_user="user-42")
```

## The surface

Every method exists on `LigaX` and `AsyncLigaX` with the same name and parameters (on the
async client, `await` it; `runs.stream` / `runs.follow_events` can also be used with
`async with`).

| Call | Endpoint | Returns |
| --- | --- | --- |
| `runs.create(profile_id=, input=, conversation_id=, end_user=, model=, mode="wait"\|"async", metadata=, idempotency_key=)` | `POST /runs` | `Run` |
| `runs.wait(...)` — `create` then poll `get` until terminal or `requires_action` | `POST /runs`, `GET /runs/{id}` | `Run` |
| `runs.stream(...)` | `POST /runs` (`mode: "stream"`) | `RunStream` |
| `runs.get(run_id)` | `GET /runs/{id}` | `Run` |
| `runs.events(run_id, after=0)` | `GET /runs/{id}/events` | `RunEventList` |
| `runs.follow_events(run_id, after=0)` | `GET /runs/{id}/events?stream=true` | `RunStream` |
| `runs.cancel(run_id)` | `POST /runs/{id}/cancel` | `Run` |
| `runs.resolve_interrupt(run_id, interrupt_id, decision="approve"\|"reject"\|"answer", payload=)` | `POST /runs/{id}/interrupts/{iid}` | `Run` |
| `conversations.get(conversation_id, end_user_id=None)` | `GET /conversations/{id}` | `Conversation` |
| `profiles.list()` / `profiles.get(profile_id)` | `GET /profiles[/{id}]` | `ProfileList` / `Profile` |
| `keys.self()` | `GET /keys/self` | `ApiKey` |
| `usage.get(start=, end=, group_by=)` | `GET /usage` | `UsageReport` |

Types live in `ligaxai.types`. Fields are snake_case, exactly as on the wire. Every model
keeps fields the server adds later (`model.model_extra`) and carries `.request_id`.

### How streamed text is assembled

Answer text arrives as `text.delta` frames that say *write this text at this offset of
this part*, with offsets in UTF-16 code units. Delivery is at-least-once, so a resumed
stream can repeat frames. `TextAssembler` (used by every `RunStream`) writes each delta at
its position — a repeated frame changes nothing — and only ever reports new text. You can
use it directly over recorded events:

```python
from ligaxai import TextAssembler

assembler = TextAssembler()
for event in client.runs.events(run_id).data:
    assembler.apply(event)
print(assembler.answer())
```

`reasoning.*` frames and frame types this version does not know are ignored, never errors.

## Configuration

| Setting     | Argument           | Environment variable | Default                                     |
| ----------- | ------------------ | -------------------- | ------------------------------------------- |
| API key     | `api_key=`         | `LIGAX_API_KEY`      | — (required)                                |
| Base URL    | `base_url=`        | `LIGAX_BASE_URL`     | `https://enterprise.ligax.ai/api/public/v1` |
| Timeout     | `timeout=`         |                      | `Timeout(600, connect=5)`                   |
| Retries     | `max_retries=`     |                      | `2`                                         |
| Headers     | `default_headers=` |                      | `{}`                                        |
| Logging     |                    | `LIGAX_LOG`          | `off`                                       |
| HTTP client | `http_client=`     |                      | an `httpx2.Client` of our own               |

`client.with_options(max_retries=0, timeout=10)` returns a copy that shares the connection
pool. Every method also takes `options=RequestOptions(headers=…, params=…, timeout=…,
max_retries=…, idempotency_key=…)`.

The default timeout leaves room for `runs.create(mode="wait")`, which the server holds for
up to 240 s before answering `202` with the run so far; `runs.wait` then polls for you.

## Retries and timeouts

Failed requests are retried twice by default with exponential backoff (0.5 s → 8 s, 25 %
jitter). Retried: connection errors, timeouts, 408, 409, 429 and every 5xx. **Never**
retried: 402, 403 and 422, or anything once a stream has started. The server can override
the decision with `x-should-retry: true|false` and steer the delay with `retry-after-ms` or
`retry-after` (seconds or HTTP-date, honoured up to 120 s) — the API sends `Retry-After` on
its 429 and 503 answers.

Every POST carries an `Idempotency-Key` that is minted once per call and reused across
retries, so a retried `runs.create` can never start a second run. Pass your own with
`idempotency_key=` to make a retry safe across processes too; reusing one with a different
request body raises `UnprocessableEntityError` (`code == "idempotency_key_reused"`).

## Errors

```python
from ligaxai import APIConnectionError, APIStatusError, PaymentRequiredError, RateLimitError

try:
    client.runs.create(profile_id="prf_...", input="Hi")
except PaymentRequiredError as e:   # the key or the organisation reached its spend limit
    print(e.code, e.response.headers.get("x-limit-resets-at"))
except RateLimitError as e:
    print(e.status_code, e.code, e.request_id)
except APIStatusError as e:         # any 4xx/5xx
    print(e.status_code, e.code, e.param, e.message)
except APIConnectionError:          # includes APITimeoutError
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
to the `X-Request-Id` header. Successful responses expose it too: `run.request_id`. Quote
it when contacting support.

## Logging

`LIGAX_LOG=debug|info|warn|error|off` configures the `ligaxai`
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
The v0.1 Agent API does not send webhooks yet; the verifier is ready for when it does.

## FastAPI

Keep the secret key on your server and let the browser stream through it:

```python
from fastapi import FastAPI, Request
from ligaxai.fastapi import client_dependency, run_stream_route

app = FastAPI()
get_client = client_dependency()  # one AsyncLigaX per process, from LIGAX_API_KEY

def current_user(request: Request) -> str:
    return request.state.user_id   # from YOUR auth — never from the request body

app.post("/chat")(run_stream_route(get_client, "prf_...", current_user))
```

The browser `POST`s `{"input": "…", "conversation_id": "conv_…"}` to `/chat` and reads
`text/event-stream` frames shaped like `RunEvent` (`X-Run-Id` / `X-Conversation-Id` come
back as headers). The profile and model are fixed on the server, and the end user comes
from your session, so one person cannot continue another's conversation. A refusal (spend
limit, rate limit, unknown profile) arrives as a plain HTTP error with the API's status.

See [`examples/fastapi-app`](examples/fastapi-app) for a runnable app with a minimal page.

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
make setup        # uv sync + pre-commit
make check        # ruff + mypy strict + pyright (+ verifytypes >= 95 %) + generated-model drift
make test         # unit + conformance, HTTP always mocked
make test-cov     # coverage gate (85 %)
make build        # sdist + wheel
make gen-types    # regenerate src/ligaxai/_generated/models.py from openapi/openapi.json
```

The contract is pinned in `SPEC_VERSION` (`public-api-spec-v0.1.0`) and copied to
`openapi/openapi.json` from the platform's `docs/public-api/spec/openapi.json`.
`make check-types` fails if the generated models are stale against it.

Releases: bump `src/ligaxai/_version.py`, update `CHANGELOG.md`, tag `vX.Y.Z`.
`release.yml` builds and publishes through PyPI trusted publishing. This repository was
bootstrapped from an SDK template; its token list is kept in
[`docs/TEMPLATE-TOKENS.md`](docs/TEMPLATE-TOKENS.md).

## License

Apache-2.0 — see [LICENSE](LICENSE).

## Release channels

| Channel | Source | Version shape | Install |
| --- | --- | --- | --- |
| dev | every push to `dev` | `0.1.0.dev42` (PEP 440 pre-release) | `pip install "ligaxai==0.1.0.dev42"` or `pip install --pre ligaxai` |
| stable | tag `vX.Y.Z` on `main` | `0.1.0` | `pip install ligaxai` |

`pip install ligaxai` never selects a `.dev` build. Point a dev install at the development
platform with `LIGAX_BASE_URL=https://ligax-ai-dev-2p3fwh332a-uc.a.run.app/api/public/v1`;
the built-in default is the production host. After a stable tag, bump
`src/ligaxai/_version.py` on `dev` so the next dev build sorts above the release.
