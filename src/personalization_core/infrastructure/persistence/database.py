from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Runtime settings shared by Embedded and Server database factories."""

    url: str = "sqlite+aiosqlite:///:memory:"
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 1_800
    pool_pre_ping: bool = True
    connect_timeout: float = 10.0
    echo: bool = False

    def __post_init__(self) -> None:
        if self.pool_size < 1:
            raise ValueError("pool_size must be positive")
        if self.max_overflow < 0:
            raise ValueError("max_overflow must be non-negative")
        if self.pool_timeout <= 0 or self.pool_recycle <= 0:
            raise ValueError("pool timeout and recycle must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")

    @classmethod
    def from_env(cls, url: str | None = None) -> DatabaseSettings:
        defaults = cls()

        def integer(name: str, default: int) -> int:
            return int(os.getenv(name, str(default)))

        def number(name: str, default: float) -> float:
            return float(os.getenv(name, str(default)))

        return cls(
            url=url or os.getenv("DATABASE_URL", defaults.url),
            pool_size=integer("DATABASE_POOL_SIZE", defaults.pool_size),
            max_overflow=integer("DATABASE_MAX_OVERFLOW", defaults.max_overflow),
            pool_timeout=number("DATABASE_POOL_TIMEOUT", defaults.pool_timeout),
            pool_recycle=integer("DATABASE_POOL_RECYCLE", defaults.pool_recycle),
            pool_pre_ping=os.getenv("DATABASE_POOL_PRE_PING", "1")
            not in {"0", "false", "False"},
            connect_timeout=number(
                "DATABASE_CONNECT_TIMEOUT", defaults.connect_timeout
            ),
            echo=os.getenv("DATABASE_ECHO", "0") in {"1", "true", "True"},
        )


def create_async_engine_for_url(
    url: str | None = None,
    *,
    settings: DatabaseSettings | None = None,
    **kwargs: Any,
) -> AsyncEngine:
    active = settings or DatabaseSettings.from_env(url)
    database_url = url or active.url
    parsed = make_url(database_url)
    if parsed.get_backend_name() == "sqlite":
        sqlite_path = parsed.database or ":memory:"
        return create_sqlite_engine(sqlite_path, echo=active.echo, **kwargs)
    engine_kwargs: dict[str, Any] = {"echo": active.echo, **kwargs}
    engine_kwargs.update(
        {
            "pool_size": active.pool_size,
            "max_overflow": active.max_overflow,
            "pool_timeout": active.pool_timeout,
            "pool_recycle": active.pool_recycle,
            "pool_pre_ping": active.pool_pre_ping,
            "connect_args": {
                "timeout": active.connect_timeout,
                **engine_kwargs.pop("connect_args", {}),
            },
        }
    )
    return create_async_engine(database_url, **engine_kwargs)


def create_postgres_engine(
    url: str,
    *,
    settings: DatabaseSettings | None = None,
    **kwargs: Any,
) -> AsyncEngine:
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("PostgreSQL URL must use the postgresql+asyncpg driver")
    return create_async_engine_for_url(url, settings=settings, **kwargs)


async def probe_database(engine: AsyncEngine, timeout: float = 5.0) -> bool:
    """Run a minimal query without exposing connection details."""

    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError, TimeoutError):
        return False
    return True


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
        # lets the aiosqlite adapter await the driver operation correctly.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        if enable_wal:
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
