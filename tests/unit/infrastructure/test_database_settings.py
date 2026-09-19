import asyncio
from typing import Any, cast

import pytest
from sqlalchemy.dialects.postgresql import JSONB

from personalization_core.infrastructure.persistence.database import (
    DatabaseSettings,
    create_async_engine_for_url,
    create_postgres_engine,
    probe_database,
)
from personalization_core.infrastructure.persistence.sqlalchemy_models import (
    JSONType,
    MemoryRow,
    UUIDType,
)

pytestmark = pytest.mark.unit


def test_database_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
    monkeypatch.setenv("DATABASE_POOL_SIZE", "7")
    settings = DatabaseSettings.from_env()

    assert settings.url.startswith("postgresql+asyncpg://")
    assert settings.pool_size == 7


def test_database_settings_reject_invalid_pool() -> None:
    with pytest.raises(ValueError):
        DatabaseSettings(pool_size=0)


def test_sqlite_factory_uses_sqlite_backend() -> None:
    engine = create_async_engine_for_url("sqlite+aiosqlite:///:memory:")
    assert engine.sync_engine.url.get_backend_name() == "sqlite"
    asyncio.run(engine.dispose())


def test_probe_database_returns_true_for_healthy_connection() -> None:
    class Connection:
        async def __aenter__(self) -> "Connection":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def execute(self, _query: object) -> None:
            return None

    class Engine:
        def connect(self) -> Connection:
            return Connection()

    assert asyncio.run(probe_database(cast(Any, Engine())))


def test_postgres_factory_validates_driver() -> None:
    with pytest.raises(ValueError):
        create_postgres_engine("sqlite+aiosqlite:///:memory:")


def test_postgres_mapping_types_and_partial_index_are_declared() -> None:
    uuid_type = MemoryRow.__table__.c.id.type
    json_type = MemoryRow.__table__.c.structured_value.type
    assert isinstance(uuid_type, UUIDType)
    assert isinstance(json_type, JSONType)
    assert isinstance(JSONType().load_dialect_impl(_postgresql_dialect()), JSONB)
    table = cast(Any, MemoryRow.__table__)
    indexes = list(table.indexes)
    assert any(
        index.unique and index.dialect_options["postgresql"].get("where") is not None
        for index in indexes
    )


def _postgresql_dialect():
    from sqlalchemy.dialects.postgresql import dialect

    return dialect()
