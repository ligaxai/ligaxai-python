# Summary — what this repo is and what works

`ligaxai` is the Python SDK for the **LigaX Agent API** (`/api/public/v1`), built from an
OpenAI/Anthropic-shaped template. v0.1 covers runs, conversations, profiles, keys and
usage, webhook endpoints, client tokens, end-user connections and files against the pinned spec
`public-api-spec-v0.5.0`.

## Package shape

```
ligaxai
├── LigaX / AsyncLigaX   _client.py     env config, with_options, context managers
├── resources.runs                   create/wait/stream/get/events/follow_events/cancel/resolve_interrupt
├── resources.{conversations,profiles,keys,usage}
├── resources.files                  create/get/delete (multipart upload, 25 MB client-side guard)
├── resources.webhooks               create/list/get/update/delete/test (webhook endpoints)
├── resources.client_tokens          create (short-lived lgx_ct_ token for one browser)
├── resources.connect_sessions       create/get/wait (an end user connects their own account)
├── resources.end_users              .connections list/delete (an end user's own accounts)
├── _run_stream                      RunEvent, TextAssembler (UTF-16 offsets), RunStream/AsyncRunStream
├── types                            public re-export of generated models + run event types
├── _base_client                     pipeline       auth, UA, idempotency, retries, error mapping
├── _streaming                       SSE            vendored parser, Stream/AsyncStream, EventRegistry
├── _pagination                      SyncPage/AsyncPage: has_next_page / get_next_page / iteration
├── _exceptions                      APIError → APIConnectionError/APITimeoutError; APIStatusError → 9 subclasses
├── _generated.models                datamodel-codegen output from openapi/openapi.json (drift-checked)
├── webhooks                         verify() → typed event, verify_signature(), parse_event() (Standard Webhooks)
└── fastapi                          client_dependency(), run_stream_route(), client_token_route(), stream_proxy(), webhook_dependency() (optional extra)
```

## What works today

- Full request pipeline with retries, backoff, `retry-after(-ms)`, `x-should-retry`,
  idempotency keys, request-id capture and typed errors — unit-tested sync and async.
- SSE parsing robust to split chunks, CRLF/CR, multi-line data, comments and `[DONE]`.
- Conformance harness: every `conformance/cases/*.json` runs against both clients.
- Every Agent API v0.1 endpoint on both clients; streaming with replay-safe text
  assembly checked against a real recorded engine run.
- `make check` (ruff, mypy strict, pyright strict, verifytypes 100 %, generated-model
  drift), `make test` (292 tests), `make test-cov` (96 % against an 85 % floor),
  `make build` (wheel ships `py.typed`).
- CI matrix 3.11–3.14 × three OSes; release by tag with PyPI trusted publishing.

## What is not done

- No live run against the platform yet (all HTTP is mocked).
- `conformance/cases/` are written here against the contract, not synced from a spec repo.
- Webhooks: endpoint management and typed verification are mocked-tested only; no live
  delivery has been received yet.
