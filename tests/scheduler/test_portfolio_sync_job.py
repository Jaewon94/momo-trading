from types import SimpleNamespace

import pytest

from scheduler.jobs.portfolio_sync_job import (
    _backfill_missing_open_buys_from_holdings,
    _check_account_db_consistency,
    _close_open_buys_missing_from_holdings,
    _recover_pending_confirms,
    _repair_confirmed_zero_entry_prices,
)
from trading.enums import BrokerProvider, OrderConfirmStatus
from trading.models import HoldingInfo


@pytest.mark.asyncio
async def test_recover_pending_confirms_uses_kiwoom_holdings_for_filled_buy(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0019412",
        stock_symbol="003280",
        side="BUY",
        quantity=7800,
        entry_price=1895.0,
        exit_price=0.0,
        notes="PENDING_CONFIRM",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="003280",
                    name="흥아해운",
                    quantity=7800,
                    avg_buy_price=1895.0,
                    current_price=1910.0,
                    pnl=117000.0,
                    pnl_rate=0.79,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    await _recover_pending_confirms()

    assert pending_trade.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_trade.quantity == 7800
    assert pending_trade.entry_price == 1895.0
    assert pending_trade.notes is None


@pytest.mark.asyncio
async def test_close_open_buys_missing_from_holdings_dry_run_does_not_mutate(monkeypatch) -> None:
    open_trade = SimpleNamespace(
        id="open-1",
        stock_symbol="010140",
        stock_name="삼성중공업",
        quantity=10,
        entry_price=12000.0,
        entry_at=__import__("datetime").datetime(2026, 4, 23, 9, 10),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        notes=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [open_trade]

        async def get_pending_confirms(self):
            return []

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return []

        async def get_pending_orders(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    result = await _close_open_buys_missing_from_holdings(dry_run=True)

    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["closed_count"] == 0
    assert open_trade.exit_at is None
    assert open_trade.exit_reason == ""


@pytest.mark.asyncio
async def test_close_open_buys_missing_from_holdings_apply_neutral_closes(monkeypatch) -> None:
    open_trade = SimpleNamespace(
        id="open-1",
        stock_symbol="010140",
        stock_name="삼성중공업",
        quantity=10,
        entry_price=12000.0,
        entry_at=__import__("datetime").datetime(2026, 4, 23, 9, 10),
        exit_price=0.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        notes="old",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [open_trade]

        async def get_pending_confirms(self):
            return []

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return []

        async def get_pending_orders(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job.now_kst",
        lambda: __import__("datetime").datetime(2026, 4, 27, 10, 0),
    )

    result = await _close_open_buys_missing_from_holdings(dry_run=False)

    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["closed_count"] == 1
    assert open_trade.exit_price == 12000.0
    assert open_trade.pnl == 0.0
    assert open_trade.return_pct == 0.0
    assert open_trade.exit_reason == "BROKER_HOLDING_MISSING"
    assert open_trade.exit_at == __import__("datetime").datetime(2026, 4, 27, 10, 0)
    assert open_trade.hold_days == 4
    assert "HOLDING_RECONCILIATION_CLOSE" in open_trade.notes


@pytest.mark.asyncio
async def test_close_open_buys_missing_from_holdings_skips_pending_symbols(monkeypatch) -> None:
    open_trade = SimpleNamespace(
        id="open-1",
        stock_symbol="010140",
        stock_name="삼성중공업",
        quantity=10,
        entry_price=12000.0,
        entry_at=__import__("datetime").datetime(2026, 4, 23, 9, 10),
        exit_at=None,
    )
    pending_trade = SimpleNamespace(stock_symbol="010140")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [open_trade]

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return []

        async def get_pending_orders(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    result = await _close_open_buys_missing_from_holdings(dry_run=False)

    assert result["summary"]["candidate_count"] == 0
    assert result["summary"]["closed_count"] == 0
    assert result["summary"]["skipped_count"] == 1
    assert result["skipped"][0]["reason"] == "db_pending_confirm_exists"
    assert open_trade.exit_at is None


@pytest.mark.asyncio
async def test_recover_pending_confirms_normalizes_a_prefixed_kiwoom_holdings(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0019412",
        stock_symbol="003280",
        side="BUY",
        quantity=7800,
        entry_price=0.0,
        exit_price=0.0,
        notes="PENDING_CONFIRM",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="A003280",
                    name="흥아해운",
                    quantity=7800,
                    avg_buy_price=3926.0,
                    current_price=4295.0,
                    pnl=2878200.0,
                    pnl_rate=9.4,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    summary = await _recover_pending_confirms()

    assert summary["recovered"] == 1
    assert pending_trade.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_trade.entry_price == 3926.0
    assert pending_trade.notes is None


@pytest.mark.asyncio
async def test_recover_pending_confirms_keeps_kiwoom_pending_when_unverifiable(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0018385",
        stock_symbol="215790",
        side="BUY",
        quantity=22000,
        entry_price=671.0,
        exit_price=0.0,
        notes="PENDING_CONFIRM: 체결 확인 대기 중",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    await _recover_pending_confirms()

    assert pending_trade.status == OrderConfirmStatus.PENDING_CONFIRM.value
    assert pending_trade.notes == "PENDING_CONFIRM: 체결 확인 대기 중"


@pytest.mark.asyncio
async def test_recover_pending_confirms_recovers_kiwoom_full_sell_when_holding_is_gone(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0099007",
        stock_symbol="215790",
        side="SELL",
        quantity=22000,
        entry_price=0.0,
        exit_price=1574.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        notes="PENDING_CONFIRM: 체결 확인 대기 중",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )
    open_buy = SimpleNamespace(
        stock_symbol="215790",
        side="BUY",
        quantity=22000,
        entry_price=1023.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        entry_at=__import__("datetime").datetime(2026, 4, 2, 9, 8, 50),
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

        async def get_all_open_buys(self, symbol):
            assert symbol == "215790"
            return [open_buy]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return []

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job.now_kst",
        lambda: __import__("datetime").datetime(2026, 4, 6, 11, 25, 0),
    )

    summary = await _recover_pending_confirms()

    assert summary["recovered"] == 1
    assert pending_trade.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_trade.notes is None


@pytest.mark.asyncio
async def test_recover_pending_confirms_recovers_kiwoom_partial_sell_from_remaining_holding(monkeypatch) -> None:
    pending_trade = SimpleNamespace(
        order_id="0099008",
        stock_symbol="215790",
        stock_name="이노인스트루먼트",
        side="SELL",
        strategy_type="SWING",
        quantity=8,
        entry_price=0.0,
        exit_price=1574.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        notes="PENDING_CONFIRM: 체결 확인 대기 중",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )
    open_buy_1 = SimpleNamespace(
        id="buy-1",
        stock_symbol="215790",
        stock_name="이노인스트루먼트",
        side="BUY",
        strategy_type="SWING",
        quantity=5,
        entry_price=1023.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        entry_at=__import__("datetime").datetime(2026, 4, 2, 9, 8, 50),
        status="CONFIRMED",
        notes=None,
    )
    open_buy_2 = SimpleNamespace(
        id="buy-2",
        stock_symbol="215790",
        stock_name="이노인스트루먼트",
        side="BUY",
        strategy_type="SWING",
        quantity=3,
        entry_price=1100.0,
        pnl=0.0,
        return_pct=0.0,
        is_win=False,
        hold_days=0,
        exit_reason="",
        exit_at=None,
        entry_at=__import__("datetime").datetime(2026, 4, 2, 9, 20, 0),
        status="CONFIRMED",
        notes=None,
    )

    class FakeSession:
        def __init__(self) -> None:
            self.added = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

        def add(self, obj):
            self.added.append(obj)

    session = FakeSession()

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending_trade]

        async def get_all_open_buys(self, symbol):
            assert symbol == "215790"
            return [open_buy_1, open_buy_2]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_pending_orders(self):
            return []

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="215790",
                    name="이노인스트루먼트",
                    quantity=2,
                    avg_buy_price=1100.0,
                    current_price=1500.0,
                    pnl=800.0,
                    pnl_rate=36.36,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: session)
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr(
        "scheduler.jobs.portfolio_sync_job.now_kst",
        lambda: __import__("datetime").datetime(2026, 4, 6, 11, 35, 0),
    )

    summary = await _recover_pending_confirms()

    assert summary["recovered"] == 1
    assert pending_trade.status == OrderConfirmStatus.CONFIRMED.value
    assert pending_trade.quantity == 6
    assert "PARTIAL_EXIT" in (pending_trade.notes or "")
    assert open_buy_1.exit_at is not None
    assert open_buy_2.quantity == 2
    assert open_buy_2.exit_at is None
    assert len(session.added) == 1
    partial_close = session.added[0]
    assert partial_close.exit_price == 1574.0
    assert partial_close.exit_reason == "SIGNAL"


@pytest.mark.asyncio
async def test_repair_confirmed_zero_entry_prices_backfills_reconcilable_symbol(monkeypatch) -> None:
    zero_a = SimpleNamespace(
        stock_symbol="005930",
        side="BUY",
        quantity=2,
        entry_price=0.0,
        status=OrderConfirmStatus.CONFIRMED.value,
        exit_at=None,
    )
    zero_b = SimpleNamespace(
        stock_symbol="005930",
        side="BUY",
        quantity=4,
        entry_price=0.0,
        status=OrderConfirmStatus.CONFIRMED.value,
        exit_at=None,
    )
    known = SimpleNamespace(
        stock_symbol="005930",
        side="BUY",
        quantity=4,
        entry_price=9000.0,
        status=OrderConfirmStatus.CONFIRMED.value,
        exit_at=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_confirmed_open_buys_with_zero_entry_price(self):
            return [zero_a, zero_b]

        async def get_pending_confirms(self):
            return []

        async def get_all_open_buys(self, symbol):
            assert symbol == "005930"
            return [zero_a, zero_b, known]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="A005930",
                    name="삼성전자",
                    quantity=10,
                    avg_buy_price=10000.0,
                    current_price=10100.0,
                    pnl=1000.0,
                    pnl_rate=1.0,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    summary = await _repair_confirmed_zero_entry_prices()

    assert summary["repaired"] == 2
    assert summary["skipped"] == 0
    assert zero_a.entry_price == pytest.approx((10000.0 * 10 - 9000.0 * 4) / 6)
    assert zero_b.entry_price == pytest.approx((10000.0 * 10 - 9000.0 * 4) / 6)


@pytest.mark.asyncio
async def test_repair_confirmed_zero_entry_prices_skips_symbol_with_pending_confirm(monkeypatch) -> None:
    zero_trade = SimpleNamespace(
        stock_symbol="065440",
        side="BUY",
        quantity=5,
        entry_price=0.0,
        status=OrderConfirmStatus.CONFIRMED.value,
        exit_at=None,
    )
    pending_trade = SimpleNamespace(
        stock_symbol="065440",
        side="BUY",
        quantity=1,
        entry_price=0.0,
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
        exit_at=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_confirmed_open_buys_with_zero_entry_price(self):
            return [zero_trade]

        async def get_pending_confirms(self):
            return [pending_trade]

        async def get_all_open_buys(self, symbol):
            assert symbol == "065440"
            return [zero_trade]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="065440",
                    name="종목",
                    quantity=5,
                    avg_buy_price=3200.0,
                    current_price=3250.0,
                    pnl=250.0,
                    pnl_rate=1.56,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    summary = await _repair_confirmed_zero_entry_prices()

    assert summary["repaired"] == 0
    assert summary["skipped"] == 1
    assert zero_trade.entry_price == 0.0


@pytest.mark.asyncio
async def test_backfill_missing_open_buys_from_holdings_creates_synthetic_trade(monkeypatch) -> None:
    created = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

        def add(self, obj):
            created.append(obj)

    existing = SimpleNamespace(
        stock_symbol="003280",
        quantity=100,
        entry_price=3926.0,
        status=OrderConfirmStatus.CONFIRMED.value,
        exit_at=None,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return []

        async def get_all_open_buys(self, symbol):
            assert symbol == "003280"
            return [existing]

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="A003280",
                    name="흥아해운",
                    quantity=140,
                    avg_buy_price=3926.0,
                    current_price=4295.0,
                    pnl=51660.0,
                    pnl_rate=9.4,
                )
            ]

    class FakeTradeResult:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())
    monkeypatch.setattr("models.trade_result.TradeResult", FakeTradeResult)

    summary = await _backfill_missing_open_buys_from_holdings()

    assert summary["backfilled"] == 1
    assert len(created) == 1
    assert created[0].stock_symbol == "003280"
    assert created[0].quantity == 40
    assert created[0].entry_price == 3926.0
    assert created[0].notes.startswith("HOLDING_SYNC_BACKFILL")


@pytest.mark.asyncio
async def test_backfill_missing_open_buys_from_holdings_skips_symbol_with_pending(monkeypatch) -> None:
    created = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return self

        def add(self, obj):
            created.append(obj)

    pending = SimpleNamespace(
        stock_symbol="003280",
        side="BUY",
        status=OrderConfirmStatus.PENDING_CONFIRM.value,
    )

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_pending_confirms(self):
            return [pending]

        async def get_all_open_buys(self, symbol):
            return []

    class FakeBrokerAdapter:
        provider = BrokerProvider.KIWOOM

        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="A003280",
                    name="흥아해운",
                    quantity=140,
                    avg_buy_price=3926.0,
                    current_price=4295.0,
                    pnl=51660.0,
                    pnl_rate=9.4,
                )
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.broker_factory.get_broker_adapter", lambda: FakeBrokerAdapter())

    summary = await _backfill_missing_open_buys_from_holdings()

    assert summary["backfilled"] == 0
    assert summary["skipped"] == 1
    assert created == []


@pytest.mark.asyncio
async def test_check_account_db_consistency_normalizes_a_prefixed_holdings(monkeypatch) -> None:
    warnings = []
    debugs = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _session) -> None:
            pass

        async def get_all_open(self):
            return [SimpleNamespace(stock_symbol="003280"), SimpleNamespace(stock_symbol="065440")]

    class FakeAccountManager:
        async def get_holdings(self):
            return [
                HoldingInfo(
                    symbol="A003280",
                    name="흥아해운",
                    quantity=10,
                    avg_buy_price=3926.0,
                    current_price=4295.0,
                    pnl=1000.0,
                    pnl_rate=1.0,
                ),
                HoldingInfo(
                    symbol="A065440",
                    name="이루온",
                    quantity=5,
                    avg_buy_price=3031.0,
                    current_price=2970.0,
                    pnl=-305.0,
                    pnl_rate=-2.0,
                ),
            ]

    monkeypatch.setattr("core.database.AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr("repositories.trade_result_repository.TradeResultRepository", FakeRepo)
    monkeypatch.setattr("trading.account_manager.account_manager", FakeAccountManager())
    monkeypatch.setattr("scheduler.jobs.portfolio_sync_job.logger.warning", lambda *args, **kwargs: warnings.append(args))
    monkeypatch.setattr("scheduler.jobs.portfolio_sync_job.logger.debug", lambda *args, **kwargs: debugs.append(args))

    await _check_account_db_consistency()

    assert warnings == []
    assert any("계좌/DB 포지션 일치" in args[0] for args in debugs)
