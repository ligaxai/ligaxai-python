# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased] — 0.1.0

### Changed

- CI runs on pushes to `main` and `dev` and ends in one `ci-gate` job for branch protection.
  Pull requests from logins outside `.github/CONTRIBUTORS` are closed; issues stay open.
- Spec pinned to `public-api-spec-v0.7.0`: a profile reports `tool_access` (`read_only`,
  `read_write` or `custom`) and `approvals` (`server` or `end_users`).
- **Security defaults.** `run_stream_route` needs `resolve_end_user` (or `allow_anonymous=True`)
  and answers 401 without a signed-in user; it and `client_token_route` refuse cross-site requests
  and no longer pass refusals about your own key to the browser (a generic 502 with the request id;
  spend refusals keep their code). `webhook_dependency` reads at most 1 MB. A key with whitespace
  is refused at construction; ids of `.`/`..` are refused; logs redact any LigaX key, client token
  or webhook secret; a 409 is retried only when the API marks it retryable; oversized stream lines
  and absurd text offsets are refused. Dependencies are bounded by their next major. The example
  app takes its user from one replaceable `current_user()` and no longer exposes `keys.self()`.
- Spec pinned to `public-api-spec-v0.6.0`. A run's `Idempotency-Key` replay that arrives while the
  first request is still starting answers `409 idempotency_in_progress` with `x-should-retry: true`,
  which the client retries. Run events are a safe subset: tool events carry name, status and
  duration only, and `reasoning.delta` / `usage.delta` are no longer sent. Anonymous website visitors
  can chat only; answering an approval with their token is `403 approval_not_allowed`.

### Added

- **Agent API v0.1** (`SPEC_VERSION` = `public-api-spec-v0.1.0`), identical on `LigaX` and
  `AsyncLigaX`: `runs.create` / `wait` / `stream` / `get` / `events` / `follow_events` /
  `cancel` / `resolve_interrupt`, `conversations.get`, `profiles.list` / `get`,
  `keys.self`, `usage.get`. Response models are generated from the pinned spec and
  re-exported in `ligaxai.types`.
- `RunStream` / `AsyncRunStream` over the engine's LAE frames: `RunEvent(type, seq,
  payload, run_id)`, `run_id` / `conversation_id` from `X-Run-Id` / `X-Conversation-Id`,
  `last_seq` for resuming with `follow_events(after=)`, `text_stream()`, `final_text()`,
  context-manager use; a JSON answer (idempotent replay) falls back to `stream.run`.
- `TextAssembler`: offset-addressed text assembly in UTF-16 code units — replay-safe,
  emits only new contiguous text, never splits a surrogate pair, answer in `part.start`
  order.
- `ligaxai.fastapi.run_stream_route()`: a server-side endpoint that streams a run to the
  browser without exposing the key; `encode_run_event()`.
- `gen_types.py --check` (in `make check` and CI): the generated models cannot drift from
  `openapi/openapi.json`.
- Conformance cases for `runs.create`, `runs.get` and a non-retried `402`; the harness
  can assert a request count (`expect.requests`).
- **Webhook endpoints** (scope `webhooks:manage`) on both clients:
  `webhooks.create(url=, event_types=, description=, profile_ids=)` (returns the signing
  `secret` once), `list`, `get`, `update` (only the fields given are sent), `delete`,
  `test` (→ `WebhookDelivery`).
- Typed webhook events, generated from the spec's top-level `webhooks` section:
  `RunWebhookEvent` (`run.completed` / `failed` / `canceled` / `requires_action`),
  `ApiKeyLimitWebhookEvent`, `WebhookTestEvent`; `UnknownWebhookEvent` for a type added
  later. `webhooks.verify_signature()` and `webhooks.parse_event()`.
- `ligaxai.fastapi.webhook_dependency(secret)`: verifies a request's raw body and yields the
  typed event, or answers `400`.
- **Browser access** (platform Phase 5): `client_tokens.create(profile_id=, end_user=,
  conversation_id=, expires_in=)` on both clients mints a short-lived `lgx_ct_…` token for
  one profile and one end user (scope `client_tokens:write`) → `ClientToken`. A client
  constructed with a client token presents it as the bearer, for tests and tools acting as
  the browser. `POST /widget/sessions` is browser-only and not mounted.
- `ligaxai.fastapi.client_token_route(client, profile_id, resolve_end_user, expires_in=)`:
  mints a token for the signed-in user (`None` → `401`) and returns `{token, expires_at}`
  with `Cache-Control: no-store`.
- `openapi/openapi.json` re-pinned with `/client_tokens` and `/widget/sessions`;
  `ClientToken`, `ClientTokenCreateRequest`, `WidgetSession`, `WidgetSessionCreateRequest`
  generated.
- **End users' own accounts** (platform Phase 6; `SPEC_VERSION` = `public-api-spec-v0.3.0`)
  on both clients: `connect_sessions.create(connector_key=, profile_id=, end_user=)`
  (scope `connections:write`) → `ConnectSession` with the `connect_url` a browser opens in a
  popup; `connect_sessions.get(session_id, end_user_id=)`; `connect_sessions.wait(...)`,
  which polls every `poll_interval` (2 s) until the session leaves `pending` and raises
  `TimeoutError` after `timeout` (600 s; `None` waits for the session's own expiry);
  `end_users.connections.list(end_user_id)` → `EndUserConnectionList` and
  `end_users.connections.delete(end_user_id, connection_id)` → `EndUserConnectionDeleted`.
- `connection.created` / `connection.deleted` webhooks: subscribable through
  `webhooks.create(event_types=)`, and `webhooks.verify()` returns the hand-written
  `ConnectionCreatedWebhookEvent` / `ConnectionDeletedWebhookEvent` (the spec's `webhooks`
  section does not describe their bodies yet).
- **Files** (platform Phase 8; `SPEC_VERSION` = `public-api-spec-v0.5.0`) on both clients:
  `files.create(file=, end_user_id=None)` uploads one file as multipart field `file` from a
  path, bytes, a `(filename, bytes[, content_type])` tuple or a binary file object →
  `FileObject`; a file over 25 MB raises `ValueError` before any request. `files.get` →
  `FileObject`, `files.delete` → `FileDeleted`. `runs.create` / `wait` / `stream` take
  `attachments=[file ids]` (up to 10).
- `webhooks.create(idempotency_key=)`. Create was already sent with a minted
  `Idempotency-Key`; the platform now honours it — a replay answers `200` +
  `Idempotent-Replayed: true` with the same endpoint and secret, and a concurrent duplicate's
  `409` + `x-should-retry: true` is retried by the existing policy.
- README: a Files section and "Use from MCP / A2A clients" (Claude Code `claude mcp add`,
  OpenAI Agents SDK `MCPServerStreamableHttp`, the A2A agent-card URL). The protocol
  endpoints are generated into the models (`McpJsonRpcRequest`, `A2aJsonRpcRequest`) but not
  mounted on a client — MCP and A2A client libraries speak them.
- README: an end-user connections section with a FastAPI recipe (a route that starts a
  connect session for the signed-in user and returns `connect_url`, plus a status route)
  and the browser popup-and-poll flow.

### Changed

- `gen_types.py` generates into a temporary directory in both modes, so `--check` no longer
  reports drift for a line between 88 and 100 columns that `make gen-types` wrote unsplit.
- `webhooks.verify()` returns a typed event (dispatched on `type`) instead of the parsed
  JSON, and reports a malformed signature header as `WebhookVerificationError`.
- 422 is never retried (with 402 and 403), matching the TypeScript SDK.
- `examples/fastapi-app` is a working sample: `/me`, `/ask` (`runs.wait`), `/chat`
  (`run_stream_route`) and a one-file streaming chat page.

### Removed

- The template's example `health` resource (the Agent API has no `/health`).

### Template baseline

- Template skeleton: `LigaX` / `AsyncLigaX` clients with env-based
  configuration, `with_options()`, context managers and `http_client` injection.
- Request pipeline: bearer auth, `User-Agent`, `X-Request-Id` capture, auto
  `Idempotency-Key` on POST, retries with `retry-after-ms` / `retry-after` / exponential
  backoff and the `x-should-retry` override.
- Typed exception hierarchy mapped from HTTP status and the JSON error envelope.
- Vendored SSE parser with `Stream` / `AsyncStream`, event registry and `last_event_id`.
- Cursor pagination (`SyncPage` / `AsyncPage`).
- `webhooks.verify()` (Standard Webhooks) and optional `fastapi` helpers.
- Conformance harness over `conformance/cases/*.json`, unit suite, CI matrix and PyPI
  trusted-publishing release workflow.
