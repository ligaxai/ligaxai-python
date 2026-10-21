# CLAUDE.md

`base-project-slug` — the __PROJECT_TITLE__ Python SDK (import `base_project_module`).
Python ≥ 3.11, uv-managed, hatchling build, published to PyPI by tag. Setup and usage live in
README.md; this file holds the invariants.

**Ground truth:** `docs/ai-stack.md` for stack facts, `docs/SUMMARY.md` + `docs/STATUS.md` for
where the project stands, `docs/DECISIONS.md` for why things are the way they are.

## Commands

- `make check` — ruff + mypy strict + pyright strict + `--verifytypes ≥ 95 %`. The gate.
- `make test` / `test-unit` / `test-conf` / `test-cov` (85 % floor) — HTTP is always mocked.
- `make build` — `uv build --no-sources`; the wheel must contain `py.typed`.
- `make sync-spec` → `make gen-types` — pull the pinned spec and regenerate models.
- Always `uv run …` / `uv add …`. Never pip, never edit `uv.lock` by hand.

## Layering — dependency direction ↓ only

```
_client.py          public constructors, env resolution, resource mounting, with_options
resources/*.py      one class per API namespace, sync + async, one method per endpoint
_base_client.py     the pipeline: headers, idempotency, retries, error mapping, parsing
_streaming.py · _pagination.py · _exceptions.py · _models.py · _types.py · _logging.py
_generated/         models produced by scripts/gen_types.py from openapi/openapi.json
```

- Resources call `self._client.request / request_stream / request_page` only. They never
  build an `httpx2.Request`, never read headers, never catch transport errors.
- The pipeline never knows endpoint names. Anything endpoint-specific belongs in a resource.
- `webhooks.py` and `fastapi.py` are leaves: they import from the package, nothing imports
  them. `fastapi.py` must stay importable **only** when `fastapi` is installed.

## Invariants

1. **Every public method exists in sync and async form** with the same name, parameters
   and return type. Add both in the same commit; the conformance harness runs each case
   against both clients.
2. **Generated models are never hand-edited.** `src/base_project_module/_generated/` is
   written by `make gen-types`; fix the spec or the generator flags instead. Hand-written
   models inherit from `_models.BaseModel` so `request_id` works everywhere.
3. **Tests never hit the network.** Inject `httpx2.MockTransport` through `http_client=`;
   see `tests/conftest.py`. A test that needs a sleep patches `_base_client._sleep`.
4. **One retry policy.** It lives in `_base_client.py` and is covered by
   `tests/unit/test_retries.py`. Never retry 402/403; never retry after a stream started.
5. **No secrets, ever.** No real keys in tests, fixtures, examples or docs. Logging redacts
   `Authorization`; keep it that way when adding log lines.
6. **Public surface is typed.** `pyright --verifytypes` must stay ≥ 95 %: annotate
   everything exported, keep `__all__` current, use `ClassVar` for `model_config`.
7. **Errors are the hierarchy in `_exceptions.py`.** New status → new subclass of
   `APIStatusError` + a row in `_status_error_class` + a test + README table row.
8. **`SPEC_VERSION` is the parity contract** with the other SDKs. Bumping it is its own PR:
   sync, regenerate, run conformance, commit all three together.

## Template tokens

This repo is a template. `base-project-slug`, `base_project_module`, `BaseProject`,
`BASE_PROJECT_*`, `__PROJECT_TITLE__`, `__GITHUB_ORG__`, `__DEFAULT_BASE_URL__` are
placeholders replaced by `scripts/bootstrap.sh`. Never introduce a second spelling of any
of them; see `docs/TEMPLATE-TOKENS.md`.

## Living docs — update in the same change

- `CHANGELOG.md` — always, under `## [Unreleased]`.
- `docs/STATUS.md` — always: what works, what is next.
- `docs/SUMMARY.md` — when the shape of the package changes.
- `docs/DECISIONS.md` — append-only, when a design choice is locked.
- `docs/ai-stack.md` — when a dependency, tool, version floor or command changes.
- `docs/.last-tracked-commit` — advance after the docs reflect the newest commit.
