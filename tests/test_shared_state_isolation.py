import pytest
from sqlalchemy import select

from core.config import settings
from models.stock import Stock
from tests.conftest import TestAsyncSessionLocal


ORIGINAL_NEWS_DOMESTIC_MEDIA_ENABLED = settings.NEWS_DOMESTIC_MEDIA_ENABLED


@pytest.mark.asyncio
async def test_test_db_isolation_seeds_shared_state() -> None:
    async with TestAsyncSessionLocal() as session:
        session.add(Stock(symbol="ISOLATION-STOCK", name="Isolation", market="TEST", is_active=True))
        await session.commit()

        stock_id = await session.scalar(select(Stock.id).where(Stock.symbol == "ISOLATION-STOCK"))

    assert stock_id is not None


@pytest.mark.asyncio
async def test_test_db_isolation_clears_previous_rows() -> None:
    async with TestAsyncSessionLocal() as session:
        stock_id = await session.scalar(select(Stock.id).where(Stock.symbol == "ISOLATION-STOCK"))

    assert stock_id is None


def test_test_settings_isolation_mutates_global_settings() -> None:
    settings.NEWS_DOMESTIC_MEDIA_ENABLED = not ORIGINAL_NEWS_DOMESTIC_MEDIA_ENABLED
    assert settings.NEWS_DOMESTIC_MEDIA_ENABLED != ORIGINAL_NEWS_DOMESTIC_MEDIA_ENABLED


def test_test_settings_isolation_restores_global_settings() -> None:
    assert settings.NEWS_DOMESTIC_MEDIA_ENABLED == ORIGINAL_NEWS_DOMESTIC_MEDIA_ENABLED
