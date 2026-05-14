from pathlib import Path

import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def engine(tmp_path_factory) -> AsyncEngine:
    temp_dir = tmp_path_factory.mktemp("db")
    db_path = temp_dir / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    async with engine.begin() as conn:
        await conn.run_sync(_run_migrations)

    yield engine
    await engine.dispose()


def _run_migrations(connection):
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncSession:
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            session_maker = async_sessionmaker(bind=connection, class_=AsyncSession, expire_on_commit=False)
            async with session_maker() as session:
                yield session
            await transaction.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_database_session] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
