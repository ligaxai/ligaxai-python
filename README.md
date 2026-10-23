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
export LIGAX_BASE_URL="https://<dev-host>/api/public/v1"
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
| `runs.create(profile_id=, input=, conversation_id=, end_user=, model=, mode="wait"\|"async", metadata=, attachments=, idempotency_key=)` | `POST /runs` | `Run` |
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
| `files.create(file=, end_user_id=None)` | `POST /files` (multipart) | `FileObject` |
| `files.get(file_id)` / `files.delete(file_id)` | `GET` / `DELETE /files/{id}` | `FileObject` / `FileDeleted` |
| `webhooks.create(url=, event_types=, description=, profile_ids=, idempotency_key=)` | `POST /webhooks` | `WebhookEndpointWithSecret` |
| `webhooks.list()` / `webhooks.get(webhook_id)` | `GET /webhooks[/{id}]` | `WebhookEndpointList` / `WebhookEndpoint` |
| `webhooks.update(webhook_id, url=, description=, event_types=, profile_ids=, status=)` | `PATCH /webhooks/{id}` | `WebhookEndpoint` |
| `webhooks.delete(webhook_id)` | `DELETE /webhooks/{id}` | `WebhookEndpointDeleted` |
| `webhooks.test(webhook_id)` | `POST /webhooks/{id}/test` | `WebhookDelivery` |
| `client_tokens.create(profile_id=, end_user=, conversation_id=, expires_in=)` | `POST /client_tokens` | `ClientToken` |
| `connect_sessions.create(connector_key=, profile_id=, end_user=)` | `POST /connect_sessions` | `ConnectSession` |
| `connect_sessions.get(session_id, end_user_id=None)` | `GET /connect_sessions/{id}` | `ConnectSession` |
| `connect_sessions.wait(session_id, end_user_id=None, poll_interval=2, timeout=600)` — poll `get` until the session leaves `pending` | `GET /connect_sessions/{id}` | `ConnectSession` |
| `end_users.connections.list(end_user_id)` | `GET /end_users/{id}/connections` | `EndUserConnectionList` |
| `end_users.connections.delete(end_user_id, connection_id)` | `DELETE /end_users/{id}/connections/{cid}` | `EndUserConnectionDeleted` |

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

## Before you integrate: security

An agent you run through this SDK acts with your workspace's connected accounts (mail, files,
tickets) and spends your credit. The rules that matter:

- **Secret keys (`lgx_sk_…`) stay on your server.** Never in a browser, mobile app, repository or
  log; the SDK and the API both refuse one in a browser. A secret key can act as **any** of your end
  users, so restrict it to the profiles it needs and only the scopes it uses, and give it a spend
  limit.
- **Website keys (`lgx_pk_…`) are public.** Anyone can copy one from your page. Visitors on a website
  key can only chat (no account connections, uploads or approvals); give the key a small spend limit
  and attach it only to profiles anyone may use.
- **Say who the user is from your own session.** The server helpers require it (or an explicit
  anonymous opt-in) and answer 401 otherwise. Never take the end user from the request body or a
  header the browser sets.
- **Anything the agent reads can try to instruct it** — emails, documents, web pages, tool results.
  Keep approvals on for sending, writing and deleting, and answer them from your server or a
  signed-in user, never automatically.
- **Treat the agent's answer as untrusted input** to your app: never `eval` it or put it into HTML
  unescaped; don't auto-load links or images it writes.
- **Verify every webhook** with the SDK's verifier, deduplicate on `webhook-id`, and answer fast.
- **Pin versions** and commit your lockfile. Releases carry provenance: `npm audit signatures`
  (npm) or the PyPI attestation. Report vulnerabilities to security@ligaments.ai.

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

## Files

Upload a file, then attach its id to a run so the agent can read it (scope `files:write`):

```python
f = client.files.create(file="contract.pdf")      # a path, bytes, a file opened "rb",
                                                  # or ("name.pdf", data, "application/pdf")
run = client.runs.wait(profile_id="prf_...", input="Summarise the termination clause",
                       attachments=[f.id])
client.files.delete(f.id)                         # optional: files expire after 30 days
```

- **Limits:** up to 25 MB per file — a larger one raises `ValueError` before anything is
  uploaded — and up to 10 attachments per run. `runs.stream` takes `attachments=` too.
- **Types:** whether a type can be read depends on the profile's model; a model that can't
  read it refuses the attachment.
- **No download:** `files.get` returns metadata only (`filename`, `content_type`,
  `size_bytes`, `expires_at`).
- **Ownership:** a client token uploads for its own user, and only that user's runs can
  attach the file. A secret key may pass `end_user_id=` to upload for one of your users.
- The file is read into memory before sending, so a retried upload re-sends the same bytes.

## Webhooks

LigaX can `POST` an event to your server when a run finishes, fails, is canceled or waits
on you, and when a key reaches its spend limit — instead of you polling `runs.get`.
Managing endpoints needs a key with the `webhooks:manage` scope (or use Settings →
Developers).

### Create an endpoint and store the secret

```python
from ligaxai import LigaX

client = LigaX()
endpoint = client.webhooks.create(
    url="https://example.com/hooks/ligax",
    event_types=["run.completed", "run.failed", "run.requires_action"],
    profile_ids=["prf_..."],          # optional: only these profiles' runs
)
save_secret(endpoint.id, endpoint.secret)   # whsec_… — returned once, never again
client.webhooks.test(endpoint.id)           # sends a webhook.test event now
```

`create` is idempotent: every call carries an `Idempotency-Key` (reused across the SDK's
own retries), and a retry with the same key gets the endpoint — and secret — the first
attempt created instead of a second endpoint. Pass `idempotency_key=` (for example your
Zap's subscription id) to make that hold across processes too.

Events: `run.completed`, `run.failed`, `run.canceled`, `run.requires_action`,
`api_key.limit_reached`, `connection.created`, `connection.deleted` (plus `webhook.test`,
sent only by `webhooks.test`).
`webhooks.update(id, status="disabled")` pauses an endpoint; an endpoint that keeps failing
for five days is disabled by the server (`disabled_reason == "failing"`) and re-enabled
with `status="active"`. Store the secret like any credential — in your secret manager,
not in code.

### Verify and handle a delivery

Deliveries follow [Standard Webhooks](https://www.standardwebhooks.com) (`webhook-id`,
`webhook-timestamp`, `webhook-signature`). `webhooks.verify` checks the signature and the
five-minute timestamp window, then returns a typed event:

```python
from ligaxai import WebhookVerificationError, webhooks
from ligaxai.types import ApiKeyLimitWebhookEvent, RunWebhookEvent

try:
    event = webhooks.verify(raw_body, request_headers, secret=WEBHOOK_SECRET)
except WebhookVerificationError:
    return 400

if isinstance(event, RunWebhookEvent) and event.type == "run.completed":
    run = client.runs.get(event.data.id)    # payloads are thin: fetch the answer
elif isinstance(event, ApiKeyLimitWebhookEvent):
    alert(event.data.name, event.data.limit_usd)
```

The event types are `RunWebhookEvent` (`type` is one of the four `run.*` values; `data`
carries `id`, `status`, `profile_id`, `conversation_id`, `end_user_id`, `metadata`, and
`error_code` / `interrupt_id` / `interrupt_kind` when they apply),
`ApiKeyLimitWebhookEvent`, `ConnectionCreatedWebhookEvent` (`data`: `id`, `end_user_id`,
`status`), `ConnectionDeletedWebhookEvent` (`data`: `id`, `connector_key`, `end_user_id`),
`WebhookTestEvent`, and `UnknownWebhookEvent` for a type added after your SDK version — answer 2xx and ignore it. `webhooks.verify_signature()` and
`webhooks.parse_event()` are the two halves, if you want the body some other way.

In FastAPI, `webhook_dependency` reads the raw body for you and answers `400` on a bad
signature:

```python
from fastapi import BackgroundTasks, Depends, FastAPI, Header
from ligaxai.fastapi import webhook_dependency
from ligaxai.types import WebhookEvent

app = FastAPI()
verified = webhook_dependency(lambda: settings.ligax_webhook_secret)

@app.post("/hooks/ligax", status_code=204)
async def ligax_hook(
    background: BackgroundTasks,
    event: WebhookEvent = Depends(verified),
    webhook_id: str = Header(),
) -> None:
    background.add_task(handle, webhook_id, event)
```

Rules that keep a receiver correct:

- **Verify the raw bytes.** Never verify `json.dumps(await request.json())` — any
  re-serialisation changes what was signed.
- **Answer 2xx fast.** The server waits 15 s; anything else (including a redirect) is a
  failure and is retried for about 27 hours (5 s, 5 min, 30 min, 2 h, 5 h, 10 h, 10 h).
  Queue the work and return.
- **Dedupe on `webhook-id`.** Delivery is at-least-once; a retry carries the same id.
  Record ids you have processed and skip repeats.
- **Fetch, don't trust the payload for content.** `data` identifies the object and never
  carries the answer; read it with `runs.get` using your key.
- **Rotation.** During a secret rotation a delivery carries two signatures; `verify`
  accepts either secret.

### Zapier, Make and n8n

`POST /webhooks` and `DELETE /webhooks/{id}` are the REST-Hooks subscribe / unsubscribe
pair these tools expect. In a custom integration, the trigger's *subscribe* step calls
`POST /webhooks` with the tool's catch URL and the events it wants, and keeps the returned
`id`; *unsubscribe* calls `DELETE /webhooks/{id}` when the workflow is switched off. Use a
key with only the `webhooks:manage` scope (plus `runs:read` if the workflow fetches the
run). Payloads are thin by design, so a tool's task history holds ids and a status, never a
transcript.

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

## Browser access: minting client tokens

To let a page call the API **directly from the browser** (no proxy route per request), your
server mints a short-lived **client token** for the signed-in user and hands it to the page.
The browser never sees your secret key: a token (`lgx_ct_…`) runs only the one profile it
names, only as that one end user, reads only that user's conversations, and cannot touch
webhooks, usage or other profiles. It expires in minutes (60 to 3600 seconds, default 600)
and stops at once if its parent key is disabled, revoked or rotated — have the page fetch a
fresh one when it expires.

Two settings must be in place:

- the minting secret key needs the `client_tokens:write` scope;
- the profile must list your website's origin (e.g. `https://app.example.com`) under
  **allowed origins** in Settings → Developers, or the platform refuses the browser's calls.

```python
token = client.client_tokens.create(
    profile_id="prf_...",
    end_user={"id": user.id, "name": user.name},  # or just user.id
    expires_in=900,                                # optional; server default 600
)
token.token        # "lgx_ct_…" — send to that user's browser only; never log it
token.expires_at
```

With FastAPI, one line mounts an endpoint the page calls (with its session cookie):

```python
from fastapi import FastAPI, Request
from ligaxai.fastapi import client_dependency, client_token_route

app = FastAPI()
get_client = client_dependency()

def current_user(request: Request) -> tuple[str, str] | None:
    user = request.state.user          # from YOUR auth — never from the request body
    return (user.id, user.name) if user else None   # None → 401

app.post("/ligax/token")(client_token_route(get_client, "prf_...", current_user))
```

It answers `{"token": "lgx_ct_…", "expires_at": "…"}` with `Cache-Control: no-store`; a
refusal from the API (missing scope, unknown profile) keeps its status and error code.

**Django, Flask or anything else:** the same three steps in a view of your own — require a
signed-in user (401 otherwise), call `client_tokens.create(profile_id=..., end_user=...)`
with the id from your session, and return only `token` and `expires_at` with
`Cache-Control: no-store`. Prefer `POST` so the token is never cached or prefetched, and
never take the profile or user id from the request.

A client token also works as `api_key` — `LigaX(api_key="lgx_ct_…")` — for runs and
conversations of its one profile and end user. That is meant for tests and tools that
want to act as the browser; it expires in minutes and the client cannot refresh it.
`POST /widget/sessions` (publishable keys) is for the browser widget only and has no
method here.

## End users' own accounts

By default a profile's agent acts with the workspace's **shared** connections. With
end-user connections switched on for the profile (*End users can connect their own
accounts*, under the agent's API & Integrations), each of your users connects **their own**
Gmail, Outlook, Dynamics and so on, and a run that names `end_user` acts with that user's
account — falling back to the profile's shared one where they have none, if the profile
allows it.

Connecting is a popup the user completes in their browser. Your server starts a **connect
session** for the signed-in user (key scope `connections:write`) and returns its
`connect_url`; the page opens it in a popup and polls until the session settles:

```python
from fastapi import Depends, FastAPI, HTTPException, Request
from ligaxai import APIStatusError, AsyncLigaX
from ligaxai.fastapi import client_dependency

app = FastAPI()
get_client = client_dependency()  # a secret key with connections:write and connections:read


def current_user_id(request: Request) -> str:
    user = request.state.user          # from YOUR auth — never from the request body
    if user is None:
        raise HTTPException(401)
    return user.id


@app.post("/integrations/{connector_key}/connect")
async def start_connect(
    connector_key: str,
    user_id: str = Depends(current_user_id),
    client: AsyncLigaX = Depends(get_client),
) -> dict[str, str | None]:
    try:
        session = await client.connect_sessions.create(
            connector_key=connector_key,   # e.g. "gmail"; check it against your own list
            profile_id="prf_...",
            end_user=user_id,
        )
    except APIStatusError as exc:      # 409 end_user_connections_off, 422 connector_not_…
        raise HTTPException(exc.status_code, exc.code) from exc
    return {"id": session.id, "connect_url": session.connect_url}


@app.get("/integrations/sessions/{session_id}")
async def connect_status(
    session_id: str,
    user_id: str = Depends(current_user_id),
    client: AsyncLigaX = Depends(get_client),
) -> dict[str, str | None]:
    # end_user_id from the session, so one user cannot read another's connect session.
    session = await client.connect_sessions.get(session_id, end_user_id=user_id)
    return {"status": session.status, "failure_code": session.failure_code}
```

In the browser, open the popup **inside the click handler** (or browsers block it), then
poll your status route every two seconds until `status` is no longer `pending`:

```js
const { id, connect_url } = await fetch(`/integrations/gmail/connect`, { method: 'POST' })
  .then(r => r.json());
window.open(connect_url, 'ligax-connect', 'width=520,height=720');
let status = 'pending';
while (status === 'pending') {
  await new Promise(r => setTimeout(r, 2000));
  ({ status } = await fetch(`/integrations/sessions/${id}`).then(r => r.json()));
}
// 'succeeded' — or 'denied', 'failed' (see failure_code), 'expired'
```

The popup shows the provider's own consent screen and closes itself when the user is done.
LigaX never redirects back to an address taken from the request, so popup-and-poll is the
way to learn the outcome; a `connection.created` webhook is also sent the first time a
session is seen to succeed. A connector that needs typed credentials (an API key an admin
must enter) answers `422 connector_not_connectable`.

Server-side code can wait instead of polling by hand — `wait` returns the settled session
(`denied`, `failed` and `expired` are outcomes, not exceptions) and raises `TimeoutError`
if it is still pending after `timeout` seconds:

```python
session = client.connect_sessions.wait(session.id, end_user_id=user_id, timeout=300)
if session.status == "succeeded":
    print(session.connection_id)
```

List and disconnect a user's own accounts (never the workspace's shared ones):

```python
for conn in client.end_users.connections.list(user_id).data:
    print(conn.id, conn.connector_key, conn.display_name, conn.status)
client.end_users.connections.delete(user_id, conn.id)   # sends connection.deleted
```

With a [client token](#browser-access-minting-client-tokens) the browser can call
`POST /connect_sessions` and the list/delete endpoints itself, without `end_user` — the
token already names its user and can reach only that user's accounts.

## Use from MCP / A2A clients

Every published agent profile is also an **MCP server** and an **A2A agent**, so Claude
Code, Cursor, the OpenAI Agents SDK or another agent can call it directly — no SDK needed.
They use the same API key, spend limits, webhooks and audit trail as `runs.create`. Send a
secret key with *Start runs* and *Read runs* as `Authorization: Bearer …`, and add
`X-LigaX-End-User: <your user id>` to act for one of your users. The platform's MCP and A2A
guide (`docs/public-api/mcp-and-a2a.md`) has the tools (`ask`, `get_run`, `respond`), the
task-state mapping and the supported methods.

**Claude Code:**

```bash
claude mcp add --transport http ligax-support \
  https://enterprise.ligax.ai/api/public/v1/mcp/prf_... \
  --header "Authorization: Bearer $LIGAX_API_KEY"
```

**OpenAI Agents SDK:**

```python
import os
from agents.mcp import MCPServerStreamableHttp

ligax = MCPServerStreamableHttp(params={
    "url": "https://enterprise.ligax.ai/api/public/v1/mcp/prf_...",
    "headers": {"Authorization": f"Bearer {os.environ['LIGAX_API_KEY']}"},
})
```

**A2A:** the agent card is at
`https://enterprise.ligax.ai/api/public/v1/a2a/prf_.../.well-known/agent-card.json` (it
needs the API key too); JSON-RPC calls go to `…/a2a/prf_...`, A2A 1.0 and 0.3.

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

The contract is pinned in `SPEC_VERSION` (`public-api-spec-v0.7.0`) and copied to
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
platform with `LIGAX_BASE_URL=https://<dev-host>/api/public/v1`;
the built-in default is the production host. After a stable tag, bump
`src/ligaxai/_version.py` on `dev` so the next dev build sorts above the release.
