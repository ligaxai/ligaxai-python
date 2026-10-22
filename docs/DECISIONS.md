# Decisions

Append-only. Each entry: Context / Options / Decision / Consequences / Reference.

## 2026-10-22 — Transport is `httpx2`, tests use `httpx2.MockTransport`, not respx

**Context.** The design brief calls for `httpx2` (Pydantic's maintained continuation of
httpx). `uv add httpx2` resolves on PyPI (2.16.0, ships `py.typed`). The usual mocking
libraries (`respx`, `pytest-httpx`) patch the `httpx` module, which is a *different* module
from `httpx2`; they only work with `httpx2.alias_httpx()`, which must run before any
`httpx` import and which a library must never call.

**Options.** (a) respx + `alias_httpx()` in `conftest.py`; (b) plain `httpx>=0.28` + respx;
(c) `httpx2.MockTransport` injected through the public `http_client=` argument.

**Decision.** (c). No mocking dependency at all; tests exercise the same injection seam
users rely on.

**Consequences.** `respx` is not a dev dependency. A test scripts responses with the
`Recorder` helper in `tests/conftest.py`. Users who need one httpx stack across their app
call `httpx2.alias_httpx()` themselves (documented in README).

## 2026-10-22 — `MissingAPIKeyError` is `APIError + ValueError`, not `AuthenticationError`

**Context.** The brief asks for an "AuthenticationError-style ValueError" when no key is
configured. `AuthenticationError` is an `APIStatusError`, whose contract is "a response
exists" (`.response`, `.status_code`); faking those for a construction-time failure
produced partially-unknown types under pyright strict and a misleading object.

**Decision.** `MissingAPIKeyError(APIError, ValueError)` raised from the constructor. One
`except APIError` still catches everything the library raises; `except ValueError` catches
misconfiguration.

## 2026-10-22 — Pydantic `BaseModel` subclass with `extra="allow"` and a `request_id` property

**Context.** Responses must carry the server's `X-Request-Id`; generated models must not be
hand-edited. **Decision.** `_models.BaseModel` holds a private `_request_id` and
`attach_request_id()`; `gen_types.py` passes `--base-class ligaxai._models.BaseModel`.
`extra="allow"` keeps old clients working when the server adds fields.

## 2026-10-22 — Vendored SSE parser instead of `httpx-sse`

**Context.** The brief wants resume via `after=<last_event_id>`; `httpx-sse` is beta and has
no reconnection story. **Decision.** ~100-line decoder in `_streaming.py` covering split
chunks, CRLF/CR, multi-line data, comments, NUL-in-id and `[DONE]`. `EventRegistry` maps
event names to models so generated types plug in without touching the parser.

## 2026-10-22 — Coverage excludes only `_generated/`

`fastapi.py` is covered by a real ASGI test (`httpx2.ASGITransport`) rather than omitted, so
the optional helper cannot silently rot.

## 2026-10-22 — The spec is normalised before code generation

**Context.** The platform's generator (Zod `toJSONSchema`, `reused: 'inline'`) writes every
request and response body inline; datamodel-codegen only names what is in
`components/schemas`. The first v0.1.0 copy also referenced `#/$defs/...`, which does not
resolve in an OpenAPI document; the platform fixed that at the source (components +
`#/components/schemas/X`) and the workaround here was removed.

**Decision.** `scripts/gen_types.py` keeps a small normalisation pass: hoist and name the
inline bodies (refusing two different bodies under one name), inline bare enums so fields
are `Literal`s, name nested objects, type integer counts as `int`, open response objects
(no `extra="forbid"`), drop `propertyNames`, skip error envelopes (they are exceptions, and
their `request_id` field would collide with `BaseModel.request_id`). `--check` guards drift.

**Consequences.** The generator flags and the normaliser are the only place to change
generated output; `_generated/` stays untouched by hand.

## 2026-10-22 — Streamed text is folded by offset, in UTF-16 units

**Context.** `text.delta {part_id, offset, text}` is a positional write and engine delivery
is at-least-once; the platform once shipped an appending client that duplicated text on
resume. Offsets are UTF-16 code units (JavaScript-native).

**Decision.** `TextAssembler` stores each part as UTF-16-LE bytes, writes at `offset`,
de-duplicates by `seq`, tracks the contiguous written frontier and emits only new text up
to it, holding back a trailing high surrogate. Gaps are padded with spaces, matching the
platform's reducer, so `final_text()` and `run.output.text` agree.

## 2026-10-22 — `AsyncLigaX.runs.stream()` returns an awaitable context manager

**Decision.** `AsyncRunStreamManager` supports both `await client.runs.stream(...)` and
`async with client.runs.stream(...) as s`, mirroring the sync `with` form without an
`await` inside `async with`. The method name and parameters match the sync client.

## 2026-10-22 — `run_stream_route` re-encodes frames as `RunEvent`

**Decision.** The FastAPI proxy starts the run before responding (refusals become plain
HTTP errors) and relays `RunEvent`-shaped frames (`type, seq, payload, run_id, ts`) rather
than raw engine frames, which carry the engine's internal run references. The profile and
model are fixed server-side; the end user comes from a resolver over the request, never
the body.

## 2026-10-22 — `webhooks.verify()` returns a typed event; unknown types do not fail

**Context.** The spec's top-level `webhooks` section (OpenAPI 3.1) declares the events the
server sends, but datamodel-codegen reads only `paths` and `components`.

**Decision.** `gen_types.py` hoists those request bodies into components, so
`RunWebhookEvent`, `ApiKeyLimitWebhookEvent` and `WebhookTestEvent` are generated and
drift-checked like every response. `verify()` (= `verify_signature()` + `parse_event()`)
dispatches on `type`; an unrecognised `type` becomes the hand-written
`UnknownWebhookEvent` rather than an error, because a receiver that 4xx's a new event
type makes the server retry it for 27 hours. A known type missing a required field still
raises — that is contract drift worth seeing. A malformed `webhook-signature` (no `v1,`,
bad base64) is a `WebhookVerificationError`, never a bare `ValueError`.

## 2026-10-22 — `connect_sessions.wait()` raises `TimeoutError`; outcomes are not errors

**Decision.** `wait` polls `get` at a fixed `poll_interval` (default 2 s, the platform
guide's browser cadence; no backoff, because a person is clicking through a consent screen)
until the status leaves `pending`, and returns the settled session. `denied`, `failed` and
`expired` are returned, not raised — they are user outcomes the caller branches on.
Running out of `timeout` (default 600 s) raises the builtin `TimeoutError`, unlike
`runs.wait(max_wait=)`, which returns the run as it stands: a still-pending session has no
useful partial state, and `APITimeoutError` is reserved for a transport timeout with a
request attached. `timeout=None` waits for the server to expire the session itself.

## 2026-10-22 — `connection.*` webhook events are hand-written until the spec has them

**Context.** Spec 0.3.0 accepts `connection.created` / `connection.deleted` in
`event_types`, but its top-level `webhooks` section does not describe their bodies, so the
generator has nothing to emit.

**Decision.** `ConnectionCreatedWebhookEvent` and `ConnectionDeletedWebhookEvent` live in
`_webhooks.py`, shaped from the platform's emitter (`end-user-connections.ts`), and
`parse_event` dispatches on them; any other unknown type still becomes
`UnknownWebhookEvent`. When the spec gains their bodies, they move to `SCHEMA_NAMES` and
are drift-checked like the rest. `end_users.connections` is a nested namespace
(`client.end_users.connections`) mirroring the URL, so a later per-user endpoint has a home.

## 2026-10-22 — `files.create` reads the file into memory; MCP / A2A are not mounted

**Decision.** `files.create` normalises every input (path, bytes, tuple, binary file object)
to `(filename, bytes, content_type)` before the pipeline sees it, and the pipeline's new
`files=` / `data=` parameters accept bytes only. The request is rebuilt on every retry, so a
stream would be empty on the second attempt; at the platform's 25 MB cap, holding the
bytes is cheap. The cap is checked first — a path by `stat`, a file object by reading one
byte past the limit — so an oversized file raises `ValueError` without a request. A larger
file is a usage error, not an API status, which is why it is not an `APIStatusError`.

The spec's `/mcp/{profile_id}` and `/a2a/{profile_id}` endpoints are generated (so the spec
stays whole) but not mounted on a client: MCP and A2A client libraries speak those
protocols, and a JSON-RPC passthrough here would duplicate them badly. The README points
to them instead.
