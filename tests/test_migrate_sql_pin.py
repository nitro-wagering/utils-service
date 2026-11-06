"""tests/sql holds migrate's ``resolve_race_status`` functions, byte for byte.

The conftest applies these two files when it bootstraps an empty database, so a local run uses the
status precedence prod uses (resulted, then abandoned, interim, final, closed, open, then any other
status; the override beating all of them). An approximation of its own would give a different
``races.race_status`` for the same ``pf_data`` and ``bm_data``: for example pf ``resulted`` with bm
``open`` is ``resulted`` in prod and ``open`` under a bm-first COALESCE, and auto-settlement reads
that status.

CI checks out migrate at the commit in ``MIGRATE_REF`` (``MIGRATE_PATH``) and these tests compare
the copies with migrate's ``cmd/migrate/schema`` files at that commit. Without ``MIGRATE_PATH`` the
comparison fails (this repo allows no skips, see ``test_no_silent_skip.py``), so a missing checkout
cannot silently stop it; locally, point it at a clone of migrate that has the pinned commit.
To update: copy the two files from migrate at the new commit, raise ``MIGRATE_REF`` in
``.github/workflows/test.yml`` to it, and run these tests.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

SQL_DIR = Path(__file__).parent / "sql"
FILES = ("resolve_race_status_2arg.sql", "resolve_race_status_3arg.sql")
MIGRATE_PATH = os.environ.get("MIGRATE_PATH")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"


def _pinned_ref() -> str:
    ref = str((yaml.safe_load(WORKFLOW.read_text()).get("env") or {}).get("MIGRATE_REF", ""))
    assert re.fullmatch(r"[0-9a-f]{40}", ref), "test.yml env.MIGRATE_REF must be a full SHA"
    return ref


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    assert MIGRATE_PATH
    return subprocess.run(["git", "-C", MIGRATE_PATH, *args], capture_output=True, check=False)


@pytest.fixture
def migrate_checkout() -> str:
    if not MIGRATE_PATH:
        pytest.fail(
            "MIGRATE_PATH must point at a checkout of nitro-wagering/migrate with full history "
            "(CI sets it); the SQL pin cannot be checked without it"
        )
    return MIGRATE_PATH


def test_the_workflow_pins_migrate_to_a_full_sha() -> None:
    assert _pinned_ref()


def test_both_functions_are_present_and_qualified() -> None:
    two, three = ((SQL_DIR / name).read_text() for name in FILES)
    assert "public.resolve_race_status(pf_data jsonb, bm_data jsonb)" in two
    assert "public.resolve_race_status(pf_data jsonb, bm_data jsonb, nitro_data jsonb)" in three
    assert "public.resolve_race_status(pf_data, bm_data)" in three


@pytest.mark.parametrize("name", FILES)
def test_the_copy_is_byte_equal_to_migrates_file_at_the_pinned_commit(
    migrate_checkout: str, name: str
) -> None:
    shown = _git("show", f"{_pinned_ref()}:cmd/migrate/schema/{name}")

    assert shown.returncode == 0, shown.stderr.decode()
    assert shown.stdout == (SQL_DIR / name).read_bytes()


def test_the_pinned_commit_is_on_migrate_main(migrate_checkout: str) -> None:
    result = _git("merge-base", "--is-ancestor", _pinned_ref(), "origin/main")

    assert result.returncode == 0, result.stderr.decode() or "not an ancestor of origin/main"
