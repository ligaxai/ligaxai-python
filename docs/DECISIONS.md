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
