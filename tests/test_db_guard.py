"""The test-database guard accepts local test databases and nothing else."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.db_guard import is_disposable, require_disposable

PROD_LIKE = "postgresql+psycopg://nitro:secret@db.internal.example:5432/nitro"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://test:test@localhost:5432/test",
        "postgresql+psycopg://test:test@localhost:5433/nitro_test",
        "postgresql://me@127.0.0.1/nitro_test_utils_test",
        "postgresql://me@[::1]/scratch_test",
    ],
)
def test_local_test_databases_are_accepted(url: str) -> None:
    assert is_disposable(url)
    assert require_disposable(url, "TEST_DATABASE_URL") == url


@pytest.mark.parametrize(
    "url",
    [
        PROD_LIKE,
        "postgresql://me@localhost/nitro",
        "postgresql://me@db.internal.example/nitro_test",
        "postgresql://me@localhost",
    ],
)
def test_anything_else_is_refused(url: str) -> None:
    assert not is_disposable(url)
    with pytest.raises(ValueError, match="refusing to run the suite"):
        require_disposable(url, "TEST_DATABASE_URL")


def test_refusal_message_hides_the_password() -> None:
    with pytest.raises(ValueError) as caught:
        require_disposable(PROD_LIKE, "TEST_DATABASE_URL")

    assert "secret" not in str(caught.value)


def test_an_exported_production_dsn_does_not_reach_the_app_engine() -> None:
    """Import conftest in a fresh interpreter with a production DSN exported."""
    test_url = "postgresql+psycopg://test:test@localhost:5432/test"
    env = {**os.environ, "NITRO_DATABASE_URL": PROD_LIKE, "TEST_DATABASE_URL": test_url}
    code = "import tests.conftest, os; print(os.environ['NITRO_DATABASE_URL'])"

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent.parent,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == test_url
