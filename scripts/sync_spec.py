"""Download the OpenAPI spec and conformance fixtures for the pinned ``SPEC_VERSION``.

The spec repo publishes each version as a GitHub release with two assets:
``openapi.json`` and ``conformance.tar.gz`` (containing ``cases/*.json``). This script
fetches both into ``openapi/`` and ``conformance/``. Tests never call it — fixtures are
committed, so CI is hermetic.

Environment overrides (all optional):
    SPEC_VERSION       release tag, default: contents of the SPEC_VERSION file
    SPEC_REPO          "<org>/<repo>", default ligaxai/ligaxai-spec-source
    SPEC_ASSET_BASE    full URL prefix for the assets (bypasses GitHub entirely)
    GITHUB_TOKEN       sent as a bearer token for private repos / rate limits
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "ligaxai/ligaxai-spec-source"
ASSETS = ("openapi.json", "conformance.tar.gz")


def spec_version() -> str:
    env = os.environ.get("SPEC_VERSION")
    if env:
        return env.strip()
    return (ROOT / "SPEC_VERSION").read_text(encoding="utf-8").strip()


def asset_url(version: str, name: str) -> str:
    base = os.environ.get("SPEC_ASSET_BASE")
    if base:
        return f"{base.rstrip('/')}/{name}"
    repo = os.environ.get("SPEC_REPO", DEFAULT_REPO)
    return f"https://github.com/{repo}/releases/download/{version}/{name}"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ligaxai-sync-spec"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def safe_extract(archive: bytes, dest: Path) -> int:
    """Extract ``cases/*.json`` only, refusing paths that escape ``dest``."""
    count = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name.lstrip("./")
            if not (member.isfile() and name.startswith("cases/") and name.endswith(".json")):
                continue
            target = (dest / name).resolve()
            if dest.resolve() not in target.parents:
                raise RuntimeError(f"refusing to extract {member.name!r} outside {dest}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            target.write_bytes(extracted.read())
            count += 1
    return count


def main() -> int:
    version = spec_version()
    if version == "unset":
        print("sync_spec: SPEC_VERSION is 'unset' — set it to a spec release tag first.")
        return 1
    for name in ASSETS:
        url = asset_url(version, name)
        if not url.startswith("https://"):
            print(f"sync_spec: refusing non-https URL {url}")
            return 1
        print(f"sync_spec: GET {url}")
        data = fetch(url)
        if name == "openapi.json":
            out = ROOT / "openapi" / name
            out.parent.mkdir(exist_ok=True)
            out.write_bytes(data)
            print(f"sync_spec: wrote {out.relative_to(ROOT)} ({len(data)} bytes)")
        else:
            n = safe_extract(data, ROOT / "conformance")
            print(f"sync_spec: extracted {n} conformance cases")
    print(f"sync_spec: done for {version}. Now run `make gen-types` and `make test-conf`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
