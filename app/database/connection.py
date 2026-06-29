from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite+aiosqlite URLs are supported")
    db_path = database_url.removeprefix(prefix)
    if db_path not in ("", ":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(database_url: str) -> AsyncEngine:
    _ensure_sqlite_parent(database_url)
    return create_async_engine(database_url, future=True)


async def init_database(database_url: str, *, run_migrations: bool = False) -> None:
    global _engine, _session_factory
    _engine = create_engine(database_url)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    if not run_migrations:
        async with _engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database has not been initialized")
    async with _session_factory() as session:
        yield session
