from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from personalization_core.infrastructure.persistence.database import (
    DatabaseSettings,
    create_postgres_engine,
    probe_database,
)
from personalization_core.ports.unit_of_work import UnitOfWorkFactory
from personalization_core.sdk import PersonalizationEngine
from tests.contract.repositories.suite import ALL_REPOSITORY_CONTRACTS
from tests.e2e.test_embedded_sdk import make_event, make_memory, make_subject

Contract = Callable[[UnitOfWorkFactory], Awaitable[None]]

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_postgres_probe_and_engine(postgres_test_url: str) -> None:
    engine = create_postgres_engine(
        postgres_test_url,
        settings=DatabaseSettings.from_env(postgres_test_url),
    )
    try:
        assert await probe_database(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contract", ALL_REPOSITORY_CONTRACTS, ids=lambda contract: contract.__name__
)
async def test_postgres_repository_contract(
    postgres_factory: UnitOfWorkFactory, contract: Contract
) -> None:
    await contract(postgres_factory)


@pytest.mark.asyncio
async def test_postgres_sdk_business_e2e(
    postgres_test_url: str, postgres_engine: AsyncEngine
) -> None:
    assert await probe_database(postgres_engine)
    subject = make_subject()
    async with PersonalizationEngine.from_postgres(postgres_test_url) as engine:
        batch = await engine.events.ingest_batch(subject, [make_event()])
        memory = await engine.memories.add(subject, make_memory())
        profile = await engine.profiles.refresh(subject)

        assert batch.created_count == 1
        assert profile.subject == subject
        assert (await engine.memories.list(subject)).items[0].id == memory.id
