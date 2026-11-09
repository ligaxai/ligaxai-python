"""Compute the next dev pre-release version: ``X.Y.Z.dev<run>``.

    python scripts/dev_version.py 0.1.0 42   ->  0.1.0.dev42

**Versions only go up.** The base comes from ``src/ligaxai/_version.py``, which can fall behind
PyPI — most often after a stable release that nobody followed with a bump on ``dev``. Then
``0.1.0.dev50`` would sort *below* the published ``0.1.0`` and ``pip install --pre`` would never
pick it up. So the base is raised to at least:

- the base of the newest dev release already on PyPI, and
- the next patch after the newest stable release on PyPI.

The run number keeps dev releases of one base in order. Offline (a local run), PyPI is skipped and
the committed base stands. Prints only the version, for ``$GITHUB_OUTPUT``.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

PROJECT = "ligaxai"
_RELEASE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$")


def parse(version: str) -> tuple[int, int, int, int | None] | None:
    m = _RELEASE.match(version)
    if not m:
        return None
    dev = int(m.group(4)) if m.group(4) is not None else None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), dev


def published_versions() -> list[str]:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{PROJECT}/json", timeout=15) as res:
            data = json.load(res)
    except Exception:
        return []  # unpublished project or no network: no floor
    return list(data.get("releases", {}))


def next_dev(base: str, run: int, published: list[str]) -> str:
    parsed = parse(base)
    if parsed is None:
        raise SystemExit(f"_version.py holds {base!r}, not X.Y.Z")
    floor = parsed[:3]
    for v in published:
        p = parse(v)
        if p is None:
            continue
        candidate = p[:3] if p[3] is not None else (p[0], p[1], p[2] + 1)
        floor = max(floor, candidate)
    return f"{floor[0]}.{floor[1]}.{floor[2]}.dev{run}"


def main() -> None:
    if len(sys.argv) != 3 or not sys.argv[2].isdigit():
        raise SystemExit("usage: dev_version.py <X.Y.Z> <run-number>")
    version = next_dev(sys.argv[1], int(sys.argv[2]), published_versions())
    if version.split(".dev")[0] != sys.argv[1]:
        print(f"base {sys.argv[1]} is behind PyPI; using {version}", file=sys.stderr)
    print(version)


if __name__ == "__main__":
    main()
