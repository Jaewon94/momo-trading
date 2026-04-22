import copy
import sys
import asyncio as _asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import StaticPool, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.database import get_async_db, get_async_db_with_transaction
import models  # noqa: F401
from models.base import Base

# ── Async Test DB (in-memory SQLite) ──
ASYNC_TEST_DB_URL = "sqlite+aiosqlite://"

test_async_engine = create_async_engine(
    ASYNC_TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestAsyncSessionLocal = async_sessionmaker(
    test_async_engine, expire_on_commit=False
)
ORIGINAL_ASYNCIO_CREATE_TASK = _asyncio.create_task
ORIGINAL_ASYNCIO_SHIELD = _asyncio.shield


async def override_get_async_db():
    async with TestAsyncSessionLocal() as session:
        yield session


async def override_get_async_db_with_transaction():
    async with TestAsyncSessionLocal() as session:
        async with session.begin():
            yield session


async def _clear_all_tables() -> None:
    current_create_task = _asyncio.create_task
    current_shield = _asyncio.shield
    _asyncio.create_task = ORIGINAL_ASYNCIO_CREATE_TASK
    _asyncio.shield = ORIGINAL_ASYNCIO_SHIELD
    try:
        async with test_async_engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(delete(table))
    finally:
        _asyncio.create_task = current_create_task
        _asyncio.shield = current_shield


def _restore_settings(snapshot: dict) -> None:
    for key, value in snapshot.items():
        setattr(settings, key, copy.deepcopy(value))


def _clear_cached_singletons() -> None:
    from realtime.realtime_factory import get_realtime_adapter
    from realtime.stream_backend import get_stream_backend
    from trading.broker_factory import get_broker_adapter

    if hasattr(get_realtime_adapter, "cache_clear"):
        get_realtime_adapter.cache_clear()
    if hasattr(get_stream_backend, "cache_clear"):
        get_stream_backend.cache_clear()
    if hasattr(get_broker_adapter, "cache_clear"):
        get_broker_adapter.cache_clear()


def _patch_async_session_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.database as database_module

    monkeypatch.setattr(database_module, "AsyncSessionLocal", TestAsyncSessionLocal)

    prefixes = (
        "agent.",
        "analysis.",
        "api.",
        "scheduler.",
        "services.",
        "strategy.",
    )
    for module_name, module in list(sys.modules.items()):
        if module is None or not module_name.startswith(prefixes):
            continue
        if hasattr(module, "AsyncSessionLocal"):
            monkeypatch.setattr(module, "AsyncSessionLocal", TestAsyncSessionLocal, raising=False)


@pytest.fixture()
def override_runtime_settings_session(monkeypatch):
    import services.runtime_settings_service as runtime_settings_service_module

    monkeypatch.setattr(
        runtime_settings_service_module,
        "AsyncSessionLocal",
        TestAsyncSessionLocal,
    )


@pytest.fixture()
async def reset_runtime_settings(override_runtime_settings_session):
    from models.runtime_setting import RuntimeSetting

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(RuntimeSetting))
        await session.commit()

    yield

    async with TestAsyncSessionLocal() as session:
        await session.execute(delete(RuntimeSetting))
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def isolate_test_state(monkeypatch):
    settings_snapshot = copy.deepcopy(settings.model_dump())
    _patch_async_session_aliases(monkeypatch)
    _clear_cached_singletons()
    await _clear_all_tables()

    yield

    await _clear_all_tables()
    _restore_settings(settings_snapshot)
    _clear_cached_singletons()


@pytest.fixture()
async def client(override_runtime_settings_session, reset_runtime_settings):
    from main import app

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_async_db_with_transaction] = (
        override_get_async_db_with_transaction
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
