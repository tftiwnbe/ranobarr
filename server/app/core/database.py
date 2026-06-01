import contextlib
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from alembic import command, config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings


class DatabaseSessionManager:
    def __init__(self, url: str, engine_kwargs: Mapping[str, Any] | None = None):
        effective_kwargs = {"connect_args": {"timeout": 30}}
        if engine_kwargs:
            effective_kwargs.update(engine_kwargs)
            connect_args = {"timeout": 30}
            connect_args.update(effective_kwargs.get("connect_args", {}))
            effective_kwargs["connect_args"] = connect_args
        self._engine = create_async_engine(url, **effective_kwargs)
        self._sessionmaker = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        self._closed = False
        event.listen(self._engine.sync_engine, "connect", _configure_sqlite_connection)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("DatabaseSessionManager has been closed")

    @property
    def engine(self) -> AsyncEngine:
        self._ensure_open()
        return self._engine

    async def close(self) -> None:
        if self._closed:
            return
        await self._engine.dispose()
        self._closed = True

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        self._ensure_open()
        async with self._engine.begin() as connection:
            yield connection

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        self._ensure_open()
        async with self._sessionmaker() as session:
            yield session


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


sessionmanager = DatabaseSessionManager(get_settings().app.database_url)


async def get_database_session():
    async with sessionmanager.session() as session:
        yield session


def _run_upgrade(connection, cfg):
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


async def run_async_upgrade() -> None:
    server_dir = Path(__file__).resolve().parents[2]
    alembic_ini_path = server_dir / "alembic.ini"
    cfg = config.Config(str(alembic_ini_path))
    cfg.set_main_option("script_location", str(server_dir / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(server_dir))
    cfg.set_main_option("sqlalchemy.url", get_settings().app.database_url)

    async with sessionmanager.connect() as connection:
        await connection.run_sync(_run_upgrade, cfg)
