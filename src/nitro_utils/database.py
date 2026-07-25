from collections.abc import AsyncGenerator

from nitro_common.database import (
    create_async_engine_factory,
    create_session_factory,
    get_session,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nitro_utils.config import settings

engine = create_async_engine_factory(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    application_name="utils-service",
)

session_factory = create_session_factory(engine)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_session(session_factory):
        yield s
