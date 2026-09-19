from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def sqlite_url(path: str | Path) -> str:
    """Return a safe async SQLite URL for a path or an in-memory database."""
    if str(path) in {":memory:", ""}:
        return "sqlite+aiosqlite:///:memory:"
    resolved = Path(path).expanduser().resolve()
    return f"sqlite+aiosqlite:///{resolved.as_posix()}"


def create_sqlite_engine(path: str | Path = ":memory:", **kwargs: Any) -> AsyncEngine:
    engine = create_async_engine(sqlite_url(path), **kwargs)
    sync_engine = engine.sync_engine
    enable_wal = str(path) not in {":memory:", ""}

    @event.listens_for(sync_engine, "connect")
    def _configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
        # SQLAlchemy invokes this listener in its adapted synchronous
        # connection context.  Calling the DBAPI ``execute`` method directly
        # lets the aiosqlite adapter await the driver operation correctly;
        # nesting ``run_async`` here can deadlock connection acquisition.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        if enable_wal:
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
