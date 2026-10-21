# Summary — what this repo is and what works

`base-project-slug` is a **template** for a hand-written, OpenAI/Anthropic-shaped Python SDK.
It ships a complete, tested client skeleton with one example resource (`health`) and the
tooling to turn an OpenAPI spec plus conformance fixtures into a real, publishable SDK.

## Package shape

```
base_project_module
├── BaseProject / AsyncBaseProject   _client.py     env config, with_options, context managers
├── resources.health                 resources/     Health.get() → HealthResponse (sync + async)
├── _base_client                     pipeline       auth, UA, idempotency, retries, error mapping
├── _streaming                       SSE            vendored parser, Stream/AsyncStream, EventRegistry
├── _pagination                      SyncPage/AsyncPage: has_next_page / get_next_page / iteration
├── _exceptions                      APIError → APIConnectionError/APITimeoutError; APIStatusError → 9 subclasses
├── _generated.models                datamodel-codegen output (placeholder ExampleModel until a spec is synced)
├── webhooks.verify()                Standard Webhooks
└── fastapi                          client_dependency(), stream_proxy(), encode_sse() (optional extra)
```

## What works today

- Full request pipeline with retries, backoff, `retry-after(-ms)`, `x-should-retry`,
  idempotency keys, request-id capture and typed errors — unit-tested sync and async.
- SSE parsing robust to split chunks, CRLF/CR, multi-line data, comments and `[DONE]`.
- Conformance harness: every `conformance/cases/*.json` runs against both clients.
- `make check` (ruff, mypy strict, pyright strict, verifytypes 100 %), `make test`
  (81 tests), `make test-cov` (95 % against an 85 % floor), `make build` (wheel ships `py.typed`).
- CI matrix 3.11–3.14 × three OSes; release by tag with PyPI trusted publishing.

## What is a placeholder

- All project names (see `docs/TEMPLATE-TOKENS.md`).
- `SPEC_VERSION` = `unset`; `openapi/` is empty; `_generated/models.py` has one dummy model.
- `conformance/cases/` holds two local examples, not the published fixture set.
- `examples/fastapi-app` `/stream-example` targets a `/events` path that does not exist yet.
