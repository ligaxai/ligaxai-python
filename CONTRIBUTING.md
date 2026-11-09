# Contributing to ligaxai

Pull requests are accepted from the logins listed in `.github/CONTRIBUTORS`; others are
closed automatically. Issues are open to everyone.

## Set up and run the gate

```bash
make setup        # uv sync + pre-commit hooks
make check        # ruff + mypy strict + pyright (+ verifytypes >= 95 %) + generated-model drift
make test         # unit + conformance tests; HTTP is always mocked
make test-cov     # the same with the coverage gate (85 %)
make build        # sdist + wheel
```

`make check && make test` must pass before you open a pull request. CI runs the same steps
on Python 3.11 to 3.14 and ends in one `ci-gate` job that branch protection requires.

## The API contract

- `SPEC_VERSION` pins the public API spec tag. `openapi/openapi.json` is that spec, and
  `make gen-types` regenerates `src/ligaxai/_generated/models.py` from it.
  `make check-types` fails when the generated models are stale.
- `make sync-spec` downloads a spec release. It rewrites the spec's `servers` entry to the
  relative `/api/public/v1`: this SDK ships no deployment host (docs/DECISIONS.md,
  2026-11-09), and `tests/unit/test_no_deployment_hosts.py` fails if one appears anywhere.
  Bump `SPEC_VERSION` in its own pull request: sync, regenerate, run conformance, and commit
  all three together.

## Documentation

`README.md` is the user guide and the PyPI project page. Keep it user-facing, and use
**absolute** `https://github.com/ligaxai/ligaxai-python/...` links: relative links break on
PyPI. `tests/unit/test_readme.py` checks that every Python block in it parses and that it
imports only names this package exports. Never write a real host; use
`https://<your-ligax-host>/api/public/v1`.

Update `CHANGELOG.md` for every user-facing change, and the living docs in `docs/`
(`STATUS.md`, `DECISIONS.md`, `SUMMARY.md`, `ai-stack.md`) in the same pull request.

## Releases

| Channel | Source | Version shape | Install |
| --- | --- | --- | --- |
| dev | every push to `dev` | `0.1.0.dev42` (PEP 440 pre-release) | `pip install --pre ligaxai` or an exact pin |
| stable | tag `vX.Y.Z` on `main` | `0.1.0` | `pip install ligaxai` |

`.github/workflows/release.yml` builds and publishes through PyPI trusted publishing; no
token is stored anywhere. Two repository variables switch the channels:
`PUBLISH_DEV_ENABLED` and `PUBLISH_MAIN_ENABLED` (exactly `true` to publish). For a stable
release: bump `src/ligaxai/_version.py`, update `CHANGELOG.md`, merge to `main`, and tag
`vX.Y.Z`. Then bump `_version.py` on `dev` so the next dev build sorts above the release.

## Template

This repository was bootstrapped from an SDK template; its token list is in
`docs/TEMPLATE-TOKENS.md`.
