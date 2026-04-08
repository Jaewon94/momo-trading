import asyncio

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.exc import OperationalError

from core.config import settings

# ── Async Engine & Session ──
async_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.is_local,
    connect_args={"timeout": max(settings.SQLITE_BUSY_TIMEOUT_MS / 1000.0, 0.1)}
    if settings.async_database_url.startswith("sqlite+aiosqlite:///")
    else {},
)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)


if settings.async_database_url.startswith("sqlite+aiosqlite:///"):
    @event.listens_for(async_engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={int(settings.SQLITE_BUSY_TIMEOUT_MS)}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def is_sqlite_database_locked(exc: Exception) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    return "database is locked" in str(exc).lower()


async def run_sqlite_write_with_retry(operation, *, retry_count: int | None = None, retry_delay_ms: int | None = None):
    attempts = max(int(retry_count if retry_count is not None else settings.SQLITE_WRITE_RETRY_COUNT), 1)
    delay_ms = max(int(retry_delay_ms if retry_delay_ms is not None else settings.SQLITE_WRITE_RETRY_DELAY_MS), 0)
    last_exc: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            last_exc = exc
            if not is_sqlite_database_locked(exc) or attempt >= attempts:
                raise
            if delay_ms > 0:
                await asyncio.sleep((delay_ms * attempt) / 1000.0)

    if last_exc is not None:
        raise last_exc


# ── Async DI Generators ──
async def get_async_db():
    """읽기 전용 async 세션"""
    async with AsyncSessionLocal() as session:
        yield session


async def get_async_db_with_transaction():
    """쓰기용 async 세션 — 자동 commit/rollback"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
