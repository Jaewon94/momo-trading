from services.holdings_review_cache_service import HoldingsReviewCacheService


def test_holdings_review_cache_returns_copy(monkeypatch) -> None:
    service = HoldingsReviewCacheService()
    monkeypatch.setattr("services.holdings_review_cache_service.settings.HOLDINGS_REVIEW_CACHE_ENABLED", True, raising=False)
    monkeypatch.setattr("services.holdings_review_cache_service.settings.HOLDINGS_REVIEW_CACHE_TTL_SEC", 60, raising=False)

    key = service.build_key(
        holding_data={
            "symbol": "A005930",
            "stock_name": "삼성전자",
            "strategy_type": "stable_short",
            "avg_price": 70_000,
            "current_price": 72_000,
            "pnl_rate": 2.857,
            "quantity": 2,
            "hold_days": 1,
            "max_hold_days": 5,
            "confidence": 0.71,
            "target_price": 74_500,
            "stop_loss_price": 69_000,
            "active_stop_loss": 69_000,
            "active_take_profit": 74_500,
        },
        market_regime="bullish",
        market_context="강세 유지",
        minutes_left=70,
    )

    service.put(
        key,
        {
            "action": "HOLD",
            "reason": "상승 추세",
            "confidence": 0.88,
            "adjusted_stop_loss_price": 69_000,
            "adjusted_take_profit_price": 74_500,
        },
    )

    cached = service.get(key)
    assert cached == {
        "action": "HOLD",
        "reason": "상승 추세",
        "confidence": 0.88,
        "adjusted_stop_loss_price": 69_000,
        "adjusted_take_profit_price": 74_500,
    }

    cached["reason"] = "mutated"
    assert service.get(key)["reason"] == "상승 추세"


def test_holdings_review_cache_key_changes_when_minutes_left_changes() -> None:
    service = HoldingsReviewCacheService()
    kwargs = {
        "holding_data": {
            "symbol": "005930",
            "stock_name": "삼성전자",
            "strategy_type": "STABLE_SHORT",
            "avg_price": 70_000,
            "current_price": 72_000,
            "pnl_rate": 2.857,
            "quantity": 2,
            "hold_days": 1,
            "max_hold_days": 5,
            "confidence": 0.71,
        },
        "market_regime": "RANGE",
        "market_context": "변동성 확대",
    }

    assert service.build_key(**kwargs, minutes_left=70) != service.build_key(**kwargs, minutes_left=40)
