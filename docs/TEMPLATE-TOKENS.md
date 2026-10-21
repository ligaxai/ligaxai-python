# Template tokens

This repository is a base template for an "OpenAI/Anthropic-shaped" Python SDK. Every
project-specific name is a placeholder token so one `scripts/bootstrap.sh` run turns the
template into a real repo.

```bash
./scripts/bootstrap.sh <slug> <module> <ClassPrefix> "<Title>" <github-org> <base-url>
```

| Token                  | Argument         | Replace with                                   | Where it appears                                                                 |
| ---------------------- | ---------------- | ---------------------------------------------- | -------------------------------------------------------------------------------- |
| `base-project-slug`    | `<slug>`         | kebab-case distribution and repo name          | `pyproject.toml` `name`, PyPI URLs, badges, `User-Agent` (`<slug>-python/<ver>`) |
| `base_project_module`  | `<module>`       | snake_case import package                      | `src/<module>/` (directory is renamed), every `import`, mypy/pyright config       |
| `BaseProject`          | `<ClassPrefix>`  | PascalCase client class prefix                 | `BaseProject`, `AsyncBaseProject`                                                |
| `BASE_PROJECT`         | derived          | UPPER_SNAKE of the class prefix                | `BASE_PROJECT_API_KEY`, `BASE_PROJECT_BASE_URL`, `BASE_PROJECT_LOG`              |
| `__PROJECT_TITLE__`    | `"<Title>"`      | human-readable product name                    | README heading, `pyproject.toml` description, LICENSE copyright line             |
| `__GITHUB_ORG__`       | `<github-org>`   | GitHub org or user                             | badge and repo URLs, release workflow comment, `scripts/sync_spec.py` default    |
| `__DEFAULT_BASE_URL__` | `<base-url>`     | default API root, e.g. `https://api.x.com/v1`  | `_client.DEFAULT_BASE_URL`, README configuration table                           |

The spec repo name is derived: `__GITHUB_ORG__/base-project-slug-spec-source` (override with
`SPEC_REPO` or `SPEC_ASSET_BASE` when running `make sync-spec`).

## Rules

- A token has exactly one spelling. Do not write `Base Project`, `baseProject` or
  `base-project` anywhere — the script will not find them.
- The script is idempotent: it only touches files that still contain a token, so running it
  on an already-bootstrapped repo is a no-op.
- `BASE_PROJECT` is replaced **before** `BaseProject` on purpose: the env-var prefix must not
  be rewritten by the class-prefix rule.
- After bootstrapping: delete the "How to use this template" section of README.md and this
  file, set `SPEC_VERSION`, and replace `security@ligaments.ai` in SECURITY.md.
