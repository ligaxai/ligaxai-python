# AI context — stack (source of truth)

This file summarises **this repository** for assistants. It is the authoritative stack
reference; other docs defer to it for facts. Layer rules and invariants live in the root
[`CLAUDE.md`](../CLAUDE.md).

## Runtime

| Area            | Choice                                                                                                   |
| --------------- | -------------------------------------------------------------------------------------------------------- |
| Language        | **Python ≥ 3.11** (`.python-version` = 3.11 for local dev; CI matrix 3.11 – 3.14 × Linux/macOS/Windows) |
| Package manager | **uv** (`pyproject.toml` + committed `uv.lock`; dev deps in PEP 735 `[dependency-groups]`)               |
| Build backend   | **hatchling**; version read from `src/ligaxai/_version.py`; `py.typed` shipped              |
| Layout          | `src/ligaxai/` — private modules `_*.py`, public `resources/`, `webhooks`, `fastapi`         |
| Distribution    | PyPI `ligaxai`; extra `[fastapi]`                                                              |

## Runtime dependencies

| Package              | Why                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| `httpx2`             | HTTP transport (sync + async, `MockTransport`, `Timeout`). Pydantic's maintained continuation of httpx |
| `pydantic>=2`        | Response models, generated types, SSE event model                                                     |
| `anyio>=4`           | `anyio.sleep` for async retry backoff                                                                 |
| `typing-extensions`  | `Self` on 3.11                                                                                        |
| `standardwebhooks`   | Reference Standard Webhooks verifier behind `webhooks.verify()`                                       |
| `fastapi` (optional) | `ligaxai.fastapi` helpers                                                                  |

## Dev tooling

| Tool                      | Role                                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------ |
| `ruff`                    | lint + format; rules in `pyproject.toml` (`E F I B UP N W RUF SIM ANN PTH T20`)        |
| `mypy --strict`           | with the pydantic plugin; packages = `ligaxai`                            |
| `pyright` strict          | second checker; `--verifytypes ligaxai --ignoreexternal` must be ≥ 95 %  |
| `pytest` + `pytest-asyncio` (`asyncio_mode=auto`) + `pytest-cov` | tests; coverage `fail_under = 85`; `filterwarnings = error` |
| `datamodel-code-generator` | `scripts/gen_types.py` → `_generated/models.py`                                      |
| `pre-commit`              | hooks for ruff, uv-lock, mypy, pyright                                               |

## Commands

See `Makefile` (`make help`). The gate is `make check && make test`.

## Configuration surface

| Env var                 | Effect                                          |
| ----------------------- | ----------------------------------------------- |
| `LIGAX_API_KEY`  | bearer token (required unless `api_key=`)       |
| `LIGAX_BASE_URL` | overrides `_client.DEFAULT_BASE_URL`            |
| `LIGAX_LOG`      | `debug\|info\|warn\|error\|off` package logging |
| `SPEC_VERSION` (file)   | pinned spec release tag; `unset` until published |

## CI / release

- `.github/workflows/ci.yml`: `uv sync --locked`, `make check`, `pytest --cov`,
  `uv build --no-sources`, `pyright --verifytypes`; plus a `uv lock --check` job.
- `.github/workflows/release.yml`: on tag `v*`, verifies the tag equals `__version__`, builds,
  publishes with `pypa/gh-action-pypi-publish@release/v1` under environment `pypi`,
  `id-token: write`, attestations on.
