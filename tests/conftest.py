import os
import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as requiring database (deselect with '-m \"not integration\"')"
    )


@pytest.fixture(scope="session")
def database_url():
    """Get test database URL from environment."""
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("NITRO_DATABASE_URL")
    if not url:
        pytest.skip("No TEST_DATABASE_URL or NITRO_DATABASE_URL set - skipping integration tests")
    return url


@pytest_asyncio.fixture
async def async_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session for tests.

    Uses TEST_DATABASE_URL if set, otherwise NITRO_DATABASE_URL.
    Automatically rolls back all changes at test completion.
    """
    engine = create_async_engine(
        database_url.replace("postgresql://", "postgresql+psycopg://"),
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()

    await engine.dispose()
