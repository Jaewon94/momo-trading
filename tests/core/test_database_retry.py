import asyncio

import pytest
from sqlalchemy.exc import OperationalError

from core.database import is_sqlite_database_locked, run_sqlite_write_with_retry


def _sqlite_locked_error() -> OperationalError:
    return OperationalError(
        "INSERT INTO example VALUES (?)",
        {},
        Exception("database is locked"),
    )


@pytest.mark.asyncio
async def test_run_sqlite_write_with_retry_retries_locked_errors(monkeypatch) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _sqlite_locked_error()
        return "ok"

    monkeypatch.setattr("core.database.asyncio.sleep", fake_sleep)

    result = await run_sqlite_write_with_retry(
        operation,
        retry_count=3,
        retry_delay_ms=100,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [0.1, 0.2]


@pytest.mark.asyncio
async def test_run_sqlite_write_with_retry_does_not_retry_other_errors() -> None:
    async def operation() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await run_sqlite_write_with_retry(operation, retry_count=3, retry_delay_ms=100)


@pytest.mark.asyncio
async def test_run_sqlite_write_with_retry_serializes_sqlite_writes() -> None:
    events: list[str] = []

    async def operation(name: str) -> str:
        events.append(f"{name}:start")
        await asyncio.sleep(0)
        events.append(f"{name}:end")
        return name

    results = await asyncio.gather(
        run_sqlite_write_with_retry(lambda: operation("first")),
        run_sqlite_write_with_retry(lambda: operation("second")),
    )

    assert sorted(results) == ["first", "second"]
    assert events in (
        ["first:start", "first:end", "second:start", "second:end"],
        ["second:start", "second:end", "first:start", "first:end"],
    )


def test_is_sqlite_database_locked_detects_operational_error() -> None:
    assert is_sqlite_database_locked(_sqlite_locked_error()) is True
    assert is_sqlite_database_locked(RuntimeError("database is locked")) is False
