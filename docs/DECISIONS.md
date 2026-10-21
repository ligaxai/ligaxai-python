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
`attach_request_id()`; `gen_types.py` passes `--base-class base_project_module._models.BaseModel`.
`extra="allow"` keeps old clients working when the server adds fields.

## 2026-10-22 — Vendored SSE parser instead of `httpx-sse`

**Context.** The brief wants resume via `after=<last_event_id>`; `httpx-sse` is beta and has
no reconnection story. **Decision.** ~100-line decoder in `_streaming.py` covering split
chunks, CRLF/CR, multi-line data, comments, NUL-in-id and `[DONE]`. `EventRegistry` maps
event names to models so generated types plug in without touching the parser.

## 2026-10-22 — Coverage excludes only `_generated/`

`fastapi.py` is covered by a real ASGI test (`httpx2.ASGITransport`) rather than omitted, so
the optional helper cannot silently rot.
