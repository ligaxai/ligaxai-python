# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

### Changed

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
