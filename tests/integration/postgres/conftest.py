import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from personalization_core.infrastructure.persistence.database import (
    create_postgres_engine,
    create_session_factory,
)
from personalization_core.infrastructure.persistence.sqlalchemy_models import Base
from personalization_core.infrastructure.persistence.sqlalchemy_uow import (
    SQLAlchemyUnitOfWorkFactory,
)


@pytest.fixture(scope="session")
def postgres_test_url() -> str:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL is not configured")
    return url


@pytest_asyncio.fixture
async def postgres_engine(postgres_test_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_postgres_engine(postgres_test_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def postgres_factory(
    postgres_engine: AsyncEngine,
) -> SQLAlchemyUnitOfWorkFactory:
    return SQLAlchemyUnitOfWorkFactory(create_session_factory(postgres_engine))
