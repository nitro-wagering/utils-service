"""The test-database guard accepts local test databases and nothing else."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.db_guard import is_disposable, require_disposable

PROD_LIKE = "postgresql+psycopg://nitro:secret@db.internal.example:5432/nitro"
LOCAL_TEST = "postgresql+psycopg://test:test@localhost:5432/test"

BYPASS_SHAPES = {
    "host_query_key": f"{LOCAL_TEST}?host=db.internal.example",
    "dbname_query_key": f"{LOCAL_TEST}?dbname=nitro",
    "host_and_dbname_query_keys": f"{LOCAL_TEST}?host=db.internal.example&dbname=nitro",
    "hostaddr_query_key": f"{LOCAL_TEST}?hostaddr=10.1.2.3",
    "service_query_key": f"{LOCAL_TEST}?service=prod",
    "multi_host_authority": "postgresql+psycopg://test:test@localhost,db.internal.example/test",
    "multi_host_authority_remote_first": (
        "postgresql+psycopg://test:test@db.internal.example,localhost/test"
    ),
    "loopback_lookalike_host": "postgresql+psycopg://test:test@localhost.evil.example/test",
}


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


@pytest.mark.parametrize("url", BYPASS_SHAPES.values(), ids=BYPASS_SHAPES.keys())
def test_connection_overrides_cannot_redirect_a_disposable_looking_url(url: str) -> None:
    assert not is_disposable(url)
    with pytest.raises(ValueError, match="refusing to run the suite"):
        require_disposable(url, "TEST_DATABASE_URL")


def test_refusal_message_hides_the_password() -> None:
    with pytest.raises(ValueError) as caught:
        require_disposable(PROD_LIKE, "TEST_DATABASE_URL")

    assert "secret" not in str(caught.value)


def test_a_redirecting_test_url_stops_the_suite_before_any_test_runs() -> None:
    """conftest import fails outright when TEST_DATABASE_URL redirects to another database."""
    env = {**os.environ, "TEST_DATABASE_URL": BYPASS_SHAPES["host_and_dbname_query_keys"]}
    env.pop("NITRO_DATABASE_URL", None)

    result = subprocess.run(
        [sys.executable, "-c", "import tests.conftest"],
        cwd=Path(__file__).parent.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "refusing to run the suite" in result.stderr


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
