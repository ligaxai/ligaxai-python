.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck check test test-unit test-conf test-cov build \
        gen-types sync-spec clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependency groups + pre-commit hooks
	uv sync --all-groups
	uv run pre-commit install || true

lint: ## Ruff lint + format check
	uv run ruff check src tests scripts examples
	uv run ruff format --check src tests scripts examples

format: ## Auto-fix lint issues and format
	uv run ruff check --fix src tests scripts examples
	uv run ruff format src tests scripts examples

typecheck: ## mypy (strict) + pyright (strict) + public-API completeness >= 95%
	uv run mypy
	uv run pyright
	uv run python scripts/verify_types.py --min 95

check: lint typecheck ## Lint + typecheck — run before pushing

test: ## All tests (unit + conformance); HTTP is always mocked
	uv run pytest

test-unit: ## Unit tests only
	uv run pytest tests/unit

test-conf: ## Conformance cases only (conformance/cases/*.json)
	uv run pytest tests/conformance

test-cov: ## All tests with the coverage gate (fail under 85%)
	uv run pytest --cov --cov-report=term-missing

build: ## Build sdist + wheel into dist/
	uv build --no-sources

gen-types: ## Regenerate src/base_project_module/_generated/models.py from openapi/openapi.json
	uv run python scripts/gen_types.py

sync-spec: ## Download openapi.json + conformance fixtures for SPEC_VERSION
	uv run python scripts/sync_spec.py

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist
	find . -type d -name __pycache__ -not -path './.venv/*' -exec rm -rf {} +
