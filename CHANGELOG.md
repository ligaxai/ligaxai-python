# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Template skeleton: `BaseProject` / `AsyncBaseProject` clients with env-based
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
