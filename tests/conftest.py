import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from nitro_utils.config import settings


@pytest_asyncio.fixture
async def async_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide async database session for tests."""
    engine = create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+psycopg://"),
        pool_pre_ping=True,
    )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()

    await engine.dispose()
