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


def test_holdings_review_cache_key_changes_when_news_context_changes() -> None:
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
            "news_context_prompt": "### 최근 뉴스 보조 컨텍스트\n- [POSITIVE] 공급계약",
            "news_context_tone": "POSITIVE_SUPPORT",
            "news_context_negative_pressure": 0.0,
            "news_context_item_count": 1,
        },
        "market_regime": "RANGE",
        "market_context": "변동성 확대",
        "minutes_left": 70,
    }
    changed = {
        **kwargs,
        "holding_data": {
            **kwargs["holding_data"],
            "news_context_prompt": "### 최근 뉴스 보조 컨텍스트\n- [NEGATIVE] 소송 리스크",
            "news_context_tone": "MILD_NEGATIVE",
            "news_context_negative_pressure": 0.2,
        },
    }

    assert service.build_key(**kwargs) != service.build_key(**changed)


def test_holdings_review_cache_key_buckets_small_minutes_left_drift(monkeypatch) -> None:
    service = HoldingsReviewCacheService()
    monkeypatch.setattr(
        "services.holdings_review_cache_service.settings.HOLDINGS_REVIEW_CACHE_MINUTES_LEFT_BUCKET_MIN",
        15,
        raising=False,
    )
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

    assert service.build_key(**kwargs, minutes_left=74) == service.build_key(**kwargs, minutes_left=70)
    assert service.build_key(**kwargs, minutes_left=70) != service.build_key(**kwargs, minutes_left=59)
