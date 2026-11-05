"""Shared fixtures for utils-service tests.

Database tests run against a real PostgreSQL named by ``TEST_DATABASE_URL``
(falling back to ``NITRO_DATABASE_URL``). It is required: a missing URL fails
the DB tests, it never skips them.

Each test runs inside one outer transaction that is rolled back at the end.
The session joins it in ``create_savepoint`` mode, so route code that calls
``commit()`` works on savepoints and nothing is left in the shared database.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring database (deselect with '-m \"not integration\"')",
    )


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("NITRO_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL (or NITRO_DATABASE_URL) is not set. Database tests need a real "
            "PostgreSQL with the Nitro schema applied.",
            pytrace=False,
        )
    return url


@pytest_asyncio.fixture
async def async_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            session = AsyncSession(
                bind=conn,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()
