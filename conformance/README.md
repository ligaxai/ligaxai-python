# Conformance cases

`cases/*.json` are HTTP exchanges every official SDK must handle identically. They are
authored in the spec repo (`__GITHUB_ORG__/base-project-slug-spec-source`) and copied here
by `make sync-spec` for the tag in `SPEC_VERSION`. The two files checked in are local
examples so the harness has something to run before a spec is published.

`tests/conformance/test_cases.py` runs every case against **both** the sync and the async
client through an in-process mock transport — no network, ever.

## Case format

```json
{
  "name": "human-readable title",
  "max_retries": 0,
  "args": { "options": null },
  "request":  { "method": "GET", "path": "/health", "headers": { "Authorization": "Bearer …" }, "body": null },
  "response": { "status": 200, "headers": { "x-request-id": "req_1" }, "body": { "status": "ok" } },
  "expect": {
    "call": "health.get",
    "result": { "status": "ok" }
  }
}
```

- `request` is what the SDK must send. `headers` and `body` are checked as subsets; `path`
  is matched as a suffix of the URL path so the base URL is irrelevant.
- `response` is what the mock server returns.
- `expect.call` is the dotted method on the client (`resource.method`); `args` are passed
  as keyword arguments.
- `expect.result` is a subset of the returned model's `model_dump(mode="json")`.
- `expect.error` replaces `result` when the call must raise: `type` is the exception class
  name; `status_code`, `code` and `request_id` are checked when present.
- `max_retries` defaults to `0` so a case that scripts a single 5xx fails fast.

Add a case for every endpoint's success path, each error class, the idempotency replay,
`429 Retry-After` and `402`. A case that no SDK can pass is a spec bug — fix it upstream.
