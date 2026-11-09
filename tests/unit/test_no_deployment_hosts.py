"""No LigaX deployment host ships in this repository (DECISIONS 2026-11-09).

The SDK is published publicly, so a hard-coded production or development API root would be
advertised by every installed copy, and a silent fallback to one would send a key somewhere
the caller never chose. The caller always names the platform (`base_url=` or
`LIGAX_BASE_URL`); docs use the placeholder `https://<your-ligax-host>`. This test fails if a
real host creeps back in — through a spec sync, an example, or a doc edit.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# A host under one of the company's domains, or a Cloud Run URL. The look-behind lets an
# e-mail address (`security@…`) through: that is a contact, not an API root.
HOST = re.compile(
    r"(?<![@\w.-])(?:[a-z0-9-]+\.)*(?:ligax|ligaments)\.ai\b|[a-z0-9-]+\.[a-z0-9-]+\.run\.app\b",
    re.IGNORECASE,
)

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".yml", ".yaml", ".sh", ".cfg", ".example"}


def _files() -> list[Path]:
    found: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file() and (path.suffix in SUFFIXES or path.name.endswith(".env.example")):
            found.append(path)
    return found


def test_the_scan_sees_the_package_and_spec() -> None:
    names = {p.relative_to(ROOT).as_posix() for p in _files()}
    assert "src/ligaxai/_client.py" in names
    assert "openapi/openapi.json" in names
    assert "README.md" in names


def test_no_deployment_host_in_the_repository() -> None:
    hits = [
        f"{path.relative_to(ROOT).as_posix()}:{n}: {match.group(0)}"
        for path in _files()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1)
        for match in HOST.finditer(line)
    ]
    assert hits == [], "deployment hosts found:\n" + "\n".join(hits)


def test_the_pattern_catches_hosts_and_spares_contacts() -> None:
    # Built from parts so this file does not trip its own scan.
    assert HOST.search("https://api.example-tenant.ligax" + ".ai/api/public/v1")
    assert HOST.search("svc-abc123.us-central1." + "run.app")
    assert not HOST.search("Email security@ligaments.ai")
    assert not HOST.search("import ligaxai")
