"""The integration tests fail loudly when the database is missing; nothing may skip them."""

from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).parent
SKIP_CALLS = {"skip", "importorskip", "skipif"}


def _skip_sites(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sites: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in SKIP_CALLS:
            sites.append(f"{path.name}:{node.lineno} {node.attr}")
    return sites


def test_no_test_module_can_skip_for_a_missing_database() -> None:
    sites = [site for path in sorted(TESTS.glob("*.py")) for site in _skip_sites(path)]

    assert sites == [], f"skips hide a missing database as green: {sites}"
