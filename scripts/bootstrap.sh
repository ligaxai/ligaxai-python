#!/usr/bin/env bash
# Turn a clone of this template into a real SDK repo by replacing every placeholder token.
#
# Usage:
#   ./scripts/bootstrap.sh <slug> <module> <ClassPrefix> "<Title>" <github-org> <base-url>
# Example:
#   ./scripts/bootstrap.sh acme acme Acme "Acme" acme-inc https://api.acme.com/api/public/v1
#
# Tokens (see docs/TEMPLATE-TOKENS.md):
#   base-project-slug     -> <slug>         distribution / repo name (kebab-case)
#   base_project_module   -> <module>       import package (snake_case); src/ dir is renamed
#   BaseProject           -> <ClassPrefix>  client classes BaseProject / AsyncBaseProject
#   BASE_PROJECT          -> <CLASS_PREFIX> env vars (derived from the class prefix)
#   __PROJECT_TITLE__     -> <Title>
#   __GITHUB_ORG__        -> <github-org>
#   __DEFAULT_BASE_URL__  -> <base-url>
#
# Idempotent: running it twice (or on an already-bootstrapped repo) changes nothing.
set -euo pipefail

if [[ $# -ne 6 ]]; then
  sed -n '2,20p' "$0" >&2
  exit 1
fi

SLUG="$1" MODULE="$2" PREFIX="$3" TITLE="$4" ORG="$5" BASE_URL="$6"

[[ "$SLUG" =~ ^[a-z][a-z0-9-]*$ ]] || { echo "slug must be kebab-case" >&2; exit 1; }
[[ "$MODULE" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "module must be snake_case" >&2; exit 1; }
[[ "$PREFIX" =~ ^[A-Z][A-Za-z0-9]*$ ]] || { echo "ClassPrefix must be PascalCase" >&2; exit 1; }
[[ "$BASE_URL" =~ ^https?:// ]] || { echo "base-url must start with http(s)://" >&2; exit 1; }

# PascalCase -> UPPER_SNAKE for the env-var prefix: AcmeCloud -> ACME_CLOUD.
ENV_PREFIX="${7:-$(printf '%s' "$PREFIX" | tr '[:lower:]' '[:upper:]')}"

cd "$(git rev-parse --show-toplevel)"

# Escape for use in a sed replacement (the URL contains '/' and may contain '&').
esc() { printf '%s' "$1" | sed -e 's/[\/&|]/\\&/g'; }

if sed --version >/dev/null 2>&1; then SED_I=(sed -i); else SED_I=(sed -i ''); fi

echo "==> Replacing tokens"
changed=0
# This script and the token reference must keep the ORIGINAL token spellings, otherwise a
# second run would search for the new names and rewrite every file again.
SKIP=("scripts/bootstrap.sh" "docs/TEMPLATE-TOKENS.md")
while IFS= read -r -d '' f; do
  [[ -f "$f" ]] || continue
  for s in "${SKIP[@]}"; do [[ "$f" == "$s" ]] && continue 2; done
  if grep -qE 'base-project-slug|base_project_module|BaseProject|BASE_PROJECT|__PROJECT_TITLE__|__GITHUB_ORG__|__DEFAULT_BASE_URL__' "$f" 2>/dev/null; then
    "${SED_I[@]}" \
      -e "s|base-project-slug|$(esc "$SLUG")|g" \
      -e "s|base_project_module|$(esc "$MODULE")|g" \
      -e "s|BASE_PROJECT|$(esc "$ENV_PREFIX")|g" \
      -e "s|BaseProject|$(esc "$PREFIX")|g" \
      -e "s|__PROJECT_TITLE__|$(esc "$TITLE")|g" \
      -e "s|__GITHUB_ORG__|$(esc "$ORG")|g" \
      -e "s|__DEFAULT_BASE_URL__|$(esc "$BASE_URL")|g" \
      "$f"
    echo "    updated $f"
    changed=$((changed + 1))
  fi
done < <(git ls-files -z)

if [[ -d src/base_project_module && "$MODULE" != "base_project_module" ]]; then
  echo "==> Renaming src/base_project_module -> src/$MODULE"
  git mv src/base_project_module "src/$MODULE"
fi

if command -v uv >/dev/null 2>&1; then
  echo "==> Regenerating lockfile"
  uv lock
  # Renamed identifiers sort differently; keep the tree ruff-clean without a manual pass.
  echo "==> Re-sorting imports and formatting"
  uv run ruff check --fix --quiet src tests scripts examples || true
  uv run ruff format --quiet src tests scripts examples || true
else
  echo "    (uv not found; run 'uv lock' and 'make format' yourself)"
fi

cat <<EOF
==> Done.
    files updated : $changed
    distribution  : $SLUG
    module        : $MODULE
    classes       : $PREFIX / Async$PREFIX
    env vars      : ${ENV_PREFIX}_API_KEY, ${ENV_PREFIX}_BASE_URL, ${ENV_PREFIX}_LOG
    title         : $TITLE
    github        : https://github.com/$ORG/$SLUG
    base url      : $BASE_URL

Next: review 'git diff', run 'make setup && make check && make test', then delete the
"How to use this template" section of README.md, the "Template tokens" section of
CLAUDE.md, and docs/TEMPLATE-TOKENS.md.
EOF
