"""The README is the user guide and the PyPI page, and AI assistants copy from it — so its code
must stay true to the package. These checks keep it from drifting:

* every ```python block parses (top-level ``await`` allowed);
* every ``from ligaxai… import name`` names something the module really exports;
* every link is absolute — relative links break on PyPI, which does not host repo files.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[2] / "README.md"
TEXT = README.read_text(encoding="utf-8")
BLOCKS = re.findall(r"```python\n(.*?)```", TEXT, flags=re.DOTALL)


def test_the_readme_has_python_examples() -> None:
    assert len(BLOCKS) >= 10


@pytest.mark.parametrize("index", range(len(BLOCKS)))
def test_python_block_parses(index: int) -> None:
    compile(BLOCKS[index], f"README.md block {index}", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)


def _ligaxai_imports() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for block in BLOCKS:
        for node in ast.walk(ast.parse(block)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ligaxai"):
                found.extend((node.module or "", alias.name) for alias in node.names)
    return found


def test_the_readme_imports_from_the_package() -> None:
    assert ("ligaxai", "LigaX") in _ligaxai_imports()


@pytest.mark.parametrize(("module", "name"), sorted(set(_ligaxai_imports())))
def test_imported_name_exists(module: str, name: str) -> None:
    if hasattr(importlib.import_module(module), name):
        return
    # `from ligaxai import webhooks` imports a submodule, which `hasattr` misses until loaded.
    importlib.import_module(f"{module}.{name}")


def test_every_link_is_absolute() -> None:
    targets = re.findall(r"\]\(([^)\s]+)\)", TEXT)
    relative = [t for t in targets if not t.startswith(("https://", "http://", "mailto:"))]
    assert relative == [], f"relative links break on PyPI: {relative}"
