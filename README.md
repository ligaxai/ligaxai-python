# LigaX Python SDK

[![CI](https://github.com/ligaxai/ligaxai-python/actions/workflows/ci.yml/badge.svg)](https://github.com/ligaxai/ligaxai-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ligaxai.svg)](https://pypi.org/project/ligaxai/)
[![Python](https://img.shields.io/pypi/pyversions/ligaxai.svg)](https://pypi.org/project/ligaxai/)

Run the AI agents you build in LigaX from your own Python code.

`ligaxai` is the official Python client for the LigaX Agent API. It has a sync client
(`LigaX`) and an async client (`AsyncLigaX`) with the same methods, typed results, safe
automatic retries, and streaming that can resume after a dropped connection.

**Contents:**
[What you need](https://github.com/ligaxai/ligaxai-python#what-you-need) ·
[Install](https://github.com/ligaxai/ligaxai-python#install) ·
[Configure](https://github.com/ligaxai/ligaxai-python#configure) ·
[Quickstart](https://github.com/ligaxai/ligaxai-python#quickstart) ·
[Common tasks](https://github.com/ligaxai/ligaxai-python#common-tasks) ·
[Web apps](https://github.com/ligaxai/ligaxai-python#web-apps) ·
[Webhooks](https://github.com/ligaxai/ligaxai-python#webhooks) ·
[Configuration reference](https://github.com/ligaxai/ligaxai-python#configuration-reference) ·
[Errors](https://github.com/ligaxai/ligaxai-python#errors) ·
[Retries and timeouts](https://github.com/ligaxai/ligaxai-python#retries-and-timeouts) ·
[Security](https://github.com/ligaxai/ligaxai-python#security) ·
[API reference](https://github.com/ligaxai/ligaxai-python#api-reference) ·
[For AI coding assistants](https://github.com/ligaxai/ligaxai-python#for-ai-coding-assistants)

## What you need

Get these four things from your LigaX workspace before you write any code:

| You need | Looks like | Where to get it |
| --- | --- | --- |
| **API base URL** | `https://<your-ligax-host>/api/public/v1` | Your LigaX administrator. It is the address of *your* LigaX platform. |
| **Secret API key** | `lgx_sk_…` | LigaX → **Settings → Developers → API keys**. Keep it on your server. |
| **Agent profile ID** | `prf_…` | LigaX → **Settings → Developers**. A profile is a published agent your key may run. |
| **Python** | 3.11 or newer | |

Words used on this page:

- **Agent profile** (`prf_…`): an agent you built in LigaX and published for API use.
- **Run**: one request to an agent. You send `input` text and get back `output.text`.
- **Conversation** (`conv_…`): a thread of runs. Pass its id to continue where you left off.
- **End user**: a person in *your* app that a run acts for, named by your own user id.
- **Approval**: a run can stop with status `requires_action` to ask before it acts. You
  approve or reject it.

## Install

```bash
pip install ligaxai
```

Add the FastAPI helpers with `pip install "ligaxai[fastapi]"`. With uv: `uv add ligaxai`.

## Configure

Set two environment variables. Both are required.

| Variable | Required | Value |
| --- | --- | --- |
| `LIGAX_BASE_URL` | yes | Your platform's API root, for example `https://<your-ligax-host>/api/public/v1` |
| `LIGAX_API_KEY` | yes | Your secret API key, `lgx_sk_…` |

```bash
export LIGAX_BASE_URL="https://<your-ligax-host>/api/public/v1"
export LIGAX_API_KEY="lgx_sk_..."
```

`<your-ligax-host>` is a placeholder: replace it with your platform's host. The SDK has **no
built-in address**, for any environment. If the base URL is missing, creating the client
raises `MissingBaseURLError`. If the key is missing, it raises `MissingAPIKeyError`. Both
happen before any network call.

You can also pass both values in code: `LigaX(base_url="...", api_key="...")`. An argument
wins over the environment variable.

## Quickstart

Save this as `hello.py` and run `python hello.py`:

```python
from ligaxai import LigaX

client = LigaX()  # reads LIGAX_BASE_URL and LIGAX_API_KEY

run = client.runs.wait(
    profile_id="prf_...",  # your agent profile ID
    input="Summarise yesterday's P1 incidents.",
)

if run.status == "completed":
    print(run.output.text)
else:
    print("Run ended with status:", run.status, run.error)
```

It prints the agent's answer. `runs.wait` sends the request and waits until the run
finishes or needs your approval.

To check your setup first, call `client.keys.self()`. It returns your key's name, scopes
and spend limit. `client.profiles.list()` returns the profiles your key may run.

## Common tasks

### Stream the answer as it is written

```python
from ligaxai import LigaX

client = LigaX()

with client.runs.stream(profile_id="prf_...", input="Draft a reply to ticket 4411.") as stream:
    for text in stream.text_stream():
        print(text, end="", flush=True)

print()
print(stream.status, stream.run_id, stream.conversation_id)
```

`text_stream()` yields only the new text each time. To see every event (tool calls,
sources, artifacts), iterate `stream` itself: each item is a `RunEvent` with `type`, `seq`,
`payload` and `run_id`. `stream.final_text()` returns the whole answer.

If the connection drops, resume from the last event you received. Nothing is repeated:

```python
resumed = client.runs.follow_events(stream.run_id, after=stream.last_seq)
```

### Use async

`AsyncLigaX` has the same methods. Await them, and use `async with` for streams:

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

### Continue a conversation

Every run belongs to a conversation. Pass `conversation_id` to continue it:

```python
first = client.runs.wait(profile_id="prf_...", input="Open a ticket for the VPN outage")
follow_up = client.runs.wait(
    profile_id="prf_...",
    input="Make it priority 2",
    conversation_id=first.conversation_id,
)
```

### Act for one of your users

Pass `end_user` with your own user id. The run then uses that user's connected accounts
and conversations, and only that user can continue them:

```python
run = client.runs.wait(profile_id="prf_...", input="What is on my calendar?", end_user="user-42")
```

Take the user id from your own login session, never from the browser's request.

### Approve or reject an action

An agent can stop and ask before it acts, for example before it sends an email. The run
then has status `requires_action`:

```python
run = client.runs.wait(profile_id="prf_...", input="Email the team about the outage")

if run.status == "requires_action" and run.required_action:
    print("The agent asks:", run.required_action.prompt)
    run = client.runs.resolve_interrupt(
        run.id, run.required_action.interrupt_id, decision="approve"  # or "reject"
    )
```

### Send a file

Upload a file, then attach its id to a run. The key needs the `files:write` scope:

```python
f = client.files.create(file="contract.pdf")  # a path, bytes, or a file opened in "rb" mode
run = client.runs.wait(
    profile_id="prf_...",
    input="Summarise the termination clause",
    attachments=[f.id],
)
```

- Up to 25 MB per file and 10 files per run. A larger file raises `ValueError` before upload.
- Files are kept for 30 days. `client.files.delete(f.id)` removes one early.
- `files.get(id)` returns metadata only. There is no download.
- Whether a file type can be read depends on the agent's model.

### Check a run later

Start a run without waiting, then read it:

```python
run = client.runs.create(profile_id="prf_...", input="Prepare the weekly report", mode="async")
run = client.runs.get(run.id)       # status: queued, running, completed, ...
client.runs.cancel(run.id)          # stop it if you no longer need it
```

A run's `status` is one of `queued`, `running`, `requires_action`, `completed`, `failed`,
`canceled` or `expired`.

## Web apps

### Stream to a browser with FastAPI

Keep the secret key on your server. The browser talks to your route, and your route talks
to LigaX:

```python
from fastapi import FastAPI, Request
from ligaxai.fastapi import client_dependency, run_stream_route

app = FastAPI()
get_client = client_dependency()  # one AsyncLigaX per process, from the environment


def current_user(request: Request) -> str:
    return request.state.user_id  # from YOUR login session


app.post("/chat")(run_stream_route(get_client, "prf_...", current_user))
```

The browser sends `POST /chat` with `{"input": "…", "conversation_id": "conv_…"}` and reads
a `text/event-stream`. The profile is fixed on the server and the user comes from your
session, so one person cannot read or continue another's conversation. Without a signed-in
user the route answers `401`. A complete app is in
[examples/fastapi-app](https://github.com/ligaxai/ligaxai-python/tree/main/examples/fastapi-app).

### Let a browser call LigaX directly (client tokens)

Your server can mint a short-lived **client token** (`lgx_ct_…`) for the signed-in user.
The browser uses it instead of your secret key:

```python
token = client.client_tokens.create(
    profile_id="prf_...",
    end_user={"id": "user-42", "name": "Ada"},  # or just "user-42"
    expires_in=900,  # seconds, 60 to 3600; default 600
)
# Send token.token and token.expires_at to that user's browser. Never log the token.
```

A client token runs one profile, as one end user, for a few minutes. It cannot manage
keys, webhooks or usage. Two settings must be in place:

- the secret key that mints it needs the `client_tokens:write` scope;
- the profile must list your website's origin (for example `https://app.example.com`)
  under **allowed origins** in Settings → Developers.

With FastAPI, `client_token_route` is that endpoint:

```python
from fastapi import FastAPI, Request
from ligaxai.fastapi import client_dependency, client_token_route

app = FastAPI()
get_client = client_dependency()


def current_user(request: Request) -> tuple[str, str] | None:
    user = request.state.user  # from YOUR login session
    return (user.id, user.name) if user else None  # None answers 401


app.post("/ligax/token")(client_token_route(get_client, "prf_...", current_user))
```

It answers `{"token": "lgx_ct_…", "expires_at": "…"}` with `Cache-Control: no-store`. In
Django or Flask, write the same three steps in your own view: require a signed-in user,
call `client.client_tokens.create(...)`, return `token` and `expires_at`.

### Let your users connect their own accounts

By default an agent uses the workspace's shared connections. If the profile allows it
(*End users can connect their own accounts*, on the agent's **API & Integrations** tab),
each of your users can connect their own Gmail, Outlook and so on. Runs with that
`end_user` then use the user's own account.

Your server starts a **connect session** (scope `connections:write`) and gives the
browser its `connect_url`:

```python
session = client.connect_sessions.create(
    connector_key="gmail",
    profile_id="prf_...",
    end_user="user-42",
)
# In the browser, open session.connect_url in a popup from a click handler.
```

Then wait until the user finishes. `denied`, `failed` and `expired` are results, not
errors. `wait` raises `TimeoutError` if the session is still pending after `timeout`
seconds:

```python
session = client.connect_sessions.wait(session.id, end_user_id="user-42", timeout=300)
if session.status == "succeeded":
    print("Connected:", session.connection_id)
```

List or remove a user's own accounts (never the shared ones):

```python
for conn in client.end_users.connections.list("user-42").data:
    print(conn.id, conn.connector_key, conn.status)
    client.end_users.connections.delete("user-42", conn.id)
```

## Webhooks

LigaX can call your server when something happens, so you don't have to poll. Managing
endpoints needs the `webhooks:manage` scope.

| Event | Sent when |
| --- | --- |
| `run.completed`, `run.failed`, `run.canceled` | a run ends |
| `run.requires_action` | a run waits for your approval |
| `api_key.limit_reached` | a key reaches its spend limit |
| `connection.created`, `connection.deleted` | an end user connects or removes an account |
| `webhook.test` | you call `webhooks.test` |

**1. Create an endpoint and store its secret.** The secret (`whsec_…`) is returned only
once:

```python
endpoint = client.webhooks.create(
    url="https://example.com/hooks/ligax",
    event_types=["run.completed", "run.failed", "run.requires_action"],
    profile_ids=["prf_..."],  # optional: only these profiles' runs
)
print(endpoint.id, endpoint.secret)  # store the secret in your secret manager
client.webhooks.test(endpoint.id)    # sends a webhook.test event now
```

**2. Verify every delivery** against the raw request body. `webhooks.verify` checks the
signature and the timestamp, then returns a typed event:

```python
from ligaxai import WebhookVerificationError, webhooks
from ligaxai.types import RunWebhookEvent


def handle(raw_body: bytes, headers: dict[str, str], secret: str) -> int:
    try:
        event = webhooks.verify(raw_body, headers, secret=secret)
    except WebhookVerificationError:
        return 400
    if isinstance(event, RunWebhookEvent) and event.type == "run.completed":
        run = client.runs.get(event.data.id)  # the event holds ids, not the answer
        print(run.output.text)
    return 204
```

In FastAPI, `ligaxai.fastapi.webhook_dependency(get_secret)` does the reading and
verifying for you and answers `400` on a bad signature.

**3. Follow these rules:**

- **Use the raw bytes.** Re-encoding parsed JSON changes what was signed.
- **Answer 2xx within 15 seconds.** Do slow work in the background. Failed deliveries are
  retried for about 27 hours; an endpoint that keeps failing is disabled.
- **Skip duplicates.** A retry has the same `webhook-id` header. Remember the ids you handled.
- **Fetch the content.** Events carry ids and a status only. Read the run with `runs.get`.

Deliveries follow [Standard Webhooks](https://www.standardwebhooks.com). For Zapier, Make
or n8n, map *subscribe* to `webhooks.create` and *unsubscribe* to `webhooks.delete`.

## Use an agent from MCP or A2A clients

Every published agent profile is also an MCP server and an A2A agent, so Claude Code,
Cursor or another agent can call it without this SDK. Use a secret key with the **Start
runs** and **Read runs** scopes:

```bash
claude mcp add --transport http ligax-support \
  https://<your-ligax-host>/api/public/v1/mcp/prf_... \
  --header "Authorization: Bearer $LIGAX_API_KEY"
```

- MCP endpoint: `https://<your-ligax-host>/api/public/v1/mcp/prf_...` (tools `ask`,
  `get_run`, `respond`).
- A2A agent card: `https://<your-ligax-host>/api/public/v1/a2a/prf_.../.well-known/agent-card.json`
  (A2A 1.0 and 0.3; send the same `Authorization` header).
- Add the header `X-LigaX-End-User: <your user id>` to act for one of your users.

## Configuration reference

| Setting | Argument | Environment variable | Default |
| --- | --- | --- | --- |
| API base URL | `base_url=` | `LIGAX_BASE_URL` | none, **required** |
| API key | `api_key=` | `LIGAX_API_KEY` | none, **required** |
| Timeout | `timeout=` | | 600 s per request, 5 s to connect |
| Retries | `max_retries=` | | `2` |
| Extra headers | `default_headers=` | | none |
| HTTP client | `http_client=` | | the SDK's own `httpx2.Client` |
| Logging | | `LIGAX_LOG` | `off` |

Change options for a few calls with `client.with_options(max_retries=0, timeout=10)`. It
returns a copy that shares the connection pool. Any single call also accepts
`options=RequestOptions(timeout=..., max_retries=..., headers=..., idempotency_key=...)`.

`LIGAX_LOG` takes `debug`, `info`, `warn`, `error` or `off`. Logs never show your key.

## Errors

Every error the SDK raises is a subclass of `ligaxai.APIError`:

```python
from ligaxai import APIConnectionError, APIStatusError, LigaX, PaymentRequiredError, RateLimitError

client = LigaX()

try:
    client.runs.create(profile_id="prf_...", input="Hi")
except PaymentRequiredError as e:  # the key or workspace reached its spend limit
    print(e.code, e.response.headers.get("x-limit-resets-at"))
except RateLimitError as e:  # still limited after the SDK's retries
    print(e.status_code, e.request_id)
except APIStatusError as e:  # any other 4xx or 5xx answer
    print(e.status_code, e.code, e.message, e.request_id)
except APIConnectionError:  # network problem or timeout (APITimeoutError)
    raise
```

| HTTP status | Exception |
| --- | --- |
| 400 | `BadRequestError` |
| 401 | `AuthenticationError` |
| 402 | `PaymentRequiredError` |
| 403 | `PermissionDeniedError` |
| 404 | `NotFoundError` |
| 409 | `ConflictError` |
| 422 | `UnprocessableEntityError` |
| 429 | `RateLimitError` |
| 500 and above | `InternalServerError` |
| no response | `APIConnectionError`, `APITimeoutError` |
| missing setup | `MissingBaseURLError`, `MissingAPIKeyError` (also `ValueError`) |

Each status error has `status_code`, `code`, `message`, `param` and `request_id`. Every
successful result has `request_id` too. Quote it when you contact support.

## Retries and timeouts

- **Retried, 2 times by default:** connection errors, timeouts, and answers 408, 409, 429
  and 5xx. The wait grows from 0.5 s to 8 s, and the SDK honours the server's `Retry-After`.
- **Never retried:** 402, 403 and 422, and a stream that has already started.
- **No duplicate runs:** every `POST` carries an `Idempotency-Key` that stays the same
  across retries. Pass your own `idempotency_key=` to make a retry safe across processes.
- **Timeout:** 600 seconds per request, so `runs.wait` has room. The server answers a long
  run after up to 240 seconds, and `runs.wait` then keeps polling for you.

## Security

An agent run with your key acts with your workspace's connected accounts (mail, files,
tickets) and spends your credit.

- **Keep secret keys (`lgx_sk_…`) on your server.** Never in a browser, a mobile app, a
  repository or a log. Give each key only the profiles and scopes it needs, and a spend limit.
- **Treat website keys (`lgx_pk_…`) as public.** Anyone can copy one from your page.
  Visitors on a website key can only chat. Give it a small spend limit.
- **Take the user's identity from your own session**, never from the request body or a
  header the browser sets.
- **Keep approvals on** for sending, writing and deleting. Anything the agent reads (an
  email, a web page) can try to give it instructions.
- **Treat the agent's answer as untrusted input.** Never `eval` it or insert it into HTML
  unescaped.
- **Verify every webhook** and skip duplicates.
- **Pin the version** in your lockfile. Releases carry PyPI provenance attestations.

Report a vulnerability to security@ligaments.ai (see
[SECURITY.md](https://github.com/ligaxai/ligaxai-python/blob/main/SECURITY.md)).

## API reference

Every method exists on `LigaX` and `AsyncLigaX` with the same name and parameters.
Results are typed models from `ligaxai.types`, with field names exactly as in the API
(snake_case). Fields the server adds later are kept in `model.model_extra`.

| Method | API call | Returns |
| --- | --- | --- |
| `runs.create(profile_id=, input=, conversation_id=, end_user=, model=, mode="wait"\|"async", metadata=, attachments=, idempotency_key=)` | `POST /runs` | `Run` |
| `runs.wait(...)`: create, then poll until the run ends or needs approval | `POST /runs`, `GET /runs/{id}` | `Run` |
| `runs.stream(...)` | `POST /runs` (streamed) | `RunStream` |
| `runs.get(run_id)` | `GET /runs/{id}` | `Run` |
| `runs.events(run_id, after=0)` | `GET /runs/{id}/events` | `RunEventList` |
| `runs.follow_events(run_id, after=0)` | `GET /runs/{id}/events?stream=true` | `RunStream` |
| `runs.cancel(run_id)` | `POST /runs/{id}/cancel` | `Run` |
| `runs.resolve_interrupt(run_id, interrupt_id, decision="approve"\|"reject"\|"answer", payload=)` | `POST /runs/{id}/interrupts/{iid}` | `Run` |
| `conversations.get(conversation_id, end_user_id=None)` | `GET /conversations/{id}` | `Conversation` |
| `profiles.list()`, `profiles.get(profile_id)` | `GET /profiles[/{id}]` | `ProfileList`, `Profile` |
| `keys.self()` | `GET /keys/self` | `ApiKey` |
| `usage.get(start=, end=, group_by=)` | `GET /usage` | `UsageReport` |
| `files.create(file=, end_user_id=None)` | `POST /files` | `FileObject` |
| `files.get(file_id)`, `files.delete(file_id)` | `GET`, `DELETE /files/{id}` | `FileObject`, `FileDeleted` |
| `webhooks.create(url=, event_types=, description=, profile_ids=, idempotency_key=)` | `POST /webhooks` | `WebhookEndpointWithSecret` |
| `webhooks.list()`, `webhooks.get(webhook_id)` | `GET /webhooks[/{id}]` | `WebhookEndpointList`, `WebhookEndpoint` |
| `webhooks.update(webhook_id, url=, description=, event_types=, profile_ids=, status=)` | `PATCH /webhooks/{id}` | `WebhookEndpoint` |
| `webhooks.delete(webhook_id)` | `DELETE /webhooks/{id}` | `WebhookEndpointDeleted` |
| `webhooks.test(webhook_id)` | `POST /webhooks/{id}/test` | `WebhookDelivery` |
| `client_tokens.create(profile_id=, end_user=, conversation_id=, expires_in=)` | `POST /client_tokens` | `ClientToken` |
| `connect_sessions.create(connector_key=, profile_id=, end_user=)` | `POST /connect_sessions` | `ConnectSession` |
| `connect_sessions.get(session_id, end_user_id=None)` | `GET /connect_sessions/{id}` | `ConnectSession` |
| `connect_sessions.wait(session_id, end_user_id=None, poll_interval=2, timeout=600)` | `GET /connect_sessions/{id}` | `ConnectSession` |
| `end_users.connections.list(end_user_id)` | `GET /end_users/{id}/connections` | `EndUserConnectionList` |
| `end_users.connections.delete(end_user_id, connection_id)` | `DELETE /end_users/{id}/connections/{cid}` | `EndUserConnectionDeleted` |

Module-level helpers: `ligaxai.webhooks.verify` (with `verify_signature` and `parse_event`),
`ligaxai.TextAssembler` (rebuilds answer text from recorded events), and
`ligaxai.fastapi` (`client_dependency`, `run_stream_route`, `client_token_route`,
`webhook_dependency`).

## For AI coding assistants

If you are an AI assistant writing code with this package, follow these facts exactly:

1. Install `ligaxai`. Import from the top-level package: `from ligaxai import LigaX, AsyncLigaX`.
2. There is **no default base URL**. The code must read `LIGAX_BASE_URL` from the
   environment or pass `base_url=`. Never invent or hard-code a host. Without it the
   client raises `MissingBaseURLError`.
3. The key comes from `LIGAX_API_KEY` or `api_key=`. A secret key (`lgx_sk_…`) belongs in
   server code only. For a browser, mint a client token with `client.client_tokens.create`.
4. Create the client once and reuse it: `client = LigaX()`.
5. The main call is `client.runs.wait(profile_id="prf_...", input="...")`. The answer is
   `run.output.text` when `run.status == "completed"`. Handle `"requires_action"` with
   `runs.resolve_interrupt`.
6. Parameter and field names are snake_case, exactly as in the API (`profile_id`,
   `conversation_id`, `end_user`). The async client has the same names; `await` each call.
7. Catch `ligaxai.APIStatusError` (or a subclass from the table in
   [Errors](https://github.com/ligaxai/ligaxai-python#errors)). Do not add your own retry
   loop: the client already retries safely.
8. Take `end_user` from the app's login session, never from user input.

## Versions and support

- **Python:** 3.11, 3.12, 3.13 and 3.14, on Linux, macOS and Windows.
- **Release channels:** `pip install ligaxai` installs the latest stable release. Preview
  builds from the `dev` branch are versioned like `0.1.1.dev3`; install one with
  `pip install --pre ligaxai` or an exact pin. Every channel needs `LIGAX_BASE_URL`.
- **Transport:** [`httpx2`](https://pypi.org/project/httpx2/). If your app imports plain
  `httpx` and you want one shared stack, call `httpx2.alias_httpx()` before any `httpx`
  import.
- **Changes:** [CHANGELOG.md](https://github.com/ligaxai/ligaxai-python/blob/main/CHANGELOG.md).
- **Bugs and questions:** [GitHub issues](https://github.com/ligaxai/ligaxai-python/issues).
- **Contributing:** [CONTRIBUTING.md](https://github.com/ligaxai/ligaxai-python/blob/main/CONTRIBUTING.md).

## License

Apache-2.0. See [LICENSE](https://github.com/ligaxai/ligaxai-python/blob/main/LICENSE).
