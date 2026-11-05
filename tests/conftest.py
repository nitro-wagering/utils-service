"""Shared fixtures for utils-service tests.

Integration tests run against a real Postgres. There is no skip: if the database is not
reachable the tests fail with the connection error, so a missing database cannot pass as
green.

CI provides a Postgres service container with the real schema applied by the migrate image.
When that schema is already present (the ``races`` table exists) the fixtures use it as it
is and create nothing. Only against an empty database, for example locally, they bootstrap
the tables the bet endpoints use from the shared nitro_common models:

    createdb nitro_test_utils
    TEST_DATABASE_URL=postgresql+psycopg://localhost/nitro_test_utils pytest

For the most faithful local run, build the database with the migrate binary instead.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterator

    from sqlalchemy.engine import Engine

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://test:test@localhost:5433/nitro_test"

# nitro_utils.config requires a database URL at import time. Set it from the test database
# before any test module imports the app, so tests never reach for a different database.
os.environ.setdefault(
    "NITRO_DATABASE_URL", os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: needs a real Postgres (deselect with '-m \"not integration\"')",
    )


def _normalise(url: str) -> str:
    for prefix in ("postgresql://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return url.replace(prefix, "postgresql+psycopg://", 1)
    return url


@pytest.fixture(scope="session")
def database_url() -> str:
    return _normalise(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL))


_ENUM_AND_FUNCTIONS = (
    """
    DO $$ BEGIN
        CREATE TYPE race_status AS ENUM
            ('open', 'closed', 'interim', 'final', 'abandoned', 'resulted');
    EXCEPTION WHEN duplicate_object THEN NULL;
    END $$
    """,
    """
    CREATE OR REPLACE FUNCTION to_date_immutable(text) RETURNS date
    LANGUAGE SQL IMMUTABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$ SELECT $1::date $$
    """,
    """
    CREATE OR REPLACE FUNCTION to_timestamptz_immutable(text) RETURNS timestamptz
    LANGUAGE SQL IMMUTABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT AS $$ SELECT $1::timestamptz $$
    """,
    """
    CREATE OR REPLACE FUNCTION resolve_race_status(pf_data JSONB, bm_data JSONB)
    RETURNS race_status LANGUAGE SQL IMMUTABLE PARALLEL SAFE AS $$
      SELECT COALESCE(
        NULLIF(bm_data->>'race_status', ''), NULLIF(pf_data->>'race_status', '')
      )::race_status
    $$
    """,
)


# The shared tables the bet endpoints read, in the form the integration tests seed them.
_SHARED_TABLES = ("tracks", "meetings", "races", "horses", "jockeys", "trainers", "race_entries")


@pytest.fixture(scope="session")
def database_schema(database_url: str) -> Iterator[None]:
    """Make sure the tables the integration tests use exist, once per session.

    A database that already has the migrate-built schema is left exactly as it is: nothing is
    created and no function or type is replaced. An empty database is bootstrapped from the
    shared nitro_common models.
    """
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            has_schema = conn.execute(text("SELECT to_regclass('public.races')")).scalar_one()
        if has_schema is None:
            _bootstrap_schema(engine)
    finally:
        engine.dispose()
    yield


def _bootstrap_schema(engine: Engine) -> None:
    import nitro_common.models  # noqa: F401  (registers every shared model)
    from nitro_common.models.base import Base as CommonBase

    from nitro_utils.models import Base as UtilsBase
    from nitro_utils.models import TrackerUser, UserBet

    shared = [CommonBase.metadata.tables[name] for name in _SHARED_TABLES]
    with engine.begin() as conn:
        for statement in _ENUM_AND_FUNCTIONS:
            conn.execute(text(statement))
        CommonBase.metadata.create_all(conn, tables=shared)
        UtilsBase.metadata.create_all(conn, tables=[TrackerUser.__table__, UserBet.__table__])


@pytest_asyncio.fixture
async def async_session(
    database_url: str, database_schema: None
) -> AsyncGenerator[AsyncSession, None]:
    """An AsyncSession whose work, including the tests' own commit() calls, is rolled back.

    The session joins an outer transaction through a savepoint, so ``commit()`` inside a test
    releases the savepoint and the outer transaction is rolled back when the test ends.
    """
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()
