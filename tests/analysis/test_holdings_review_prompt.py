from analysis.llm.prompts.holdings_review import HOLDINGS_REVIEW_SYSTEM, build_holdings_review_prompt


def test_holdings_review_prompt_includes_per_symbol_news_context() -> None:
    prompt = build_holdings_review_prompt(
        [
            {
                "symbol": "005930",
                "stock_name": "삼성전자",
                "avg_price": 70_000,
                "current_price": 73_000,
                "pnl_rate": 4.28,
                "quantity": 2,
                "hold_days": 1,
                "max_hold_days": 15,
                "trade_horizon": "MID",
                "min_hold_minutes_before_review_exit": 120,
                "min_hold_minutes_before_profit_exit": 180,
                "min_hold_minutes_before_soft_stop_exit": 60,
                "confidence": 0.82,
                "target_price": 75_000,
                "stop_loss_price": 68_000,
                "active_stop_loss": 69_000,
                "active_take_profit": 75_000,
                "strategy_type": "STABLE_SHORT",
                "news_context_prompt": (
                    "### 최근 뉴스 보조 컨텍스트\n"
                    "- 뉴스 보조 판단: POSITIVE_SUPPORT\n"
                    "1. [POSITIVE] 신규 공급계약 체결"
                ),
            }
        ],
        market_regime="BULLISH",
        market_context="강세 유지",
        minutes_left=80,
    )

    assert "### 최근 뉴스 보조 컨텍스트" in prompt
    assert "POSITIVE_SUPPORT" in prompt
    assert "신규 공급계약 체결" in prompt


def test_holdings_review_prompt_exposes_horizon_contract() -> None:
    prompt = build_holdings_review_prompt(
        [
            {
                "symbol": "052710",
                "stock_name": "아모텍",
                "avg_price": 24_881,
                "current_price": 24_400,
                "pnl_rate": -2.82,
                "quantity": 40,
                "hold_days": 0,
                "max_hold_days": 15,
                "trade_horizon": "MID",
                "min_hold_minutes_before_review_exit": 120,
                "min_hold_minutes_before_profit_exit": 180,
                "min_hold_minutes_before_soft_stop_exit": 60,
                "confidence": 0.57,
                "target_price": 30_100,
                "stop_loss_price": 23_655,
                "active_stop_loss": 23_655,
                "active_take_profit": 30_100,
                "strategy_type": "STABLE_SHORT",
            }
        ],
        market_regime="THEME",
        market_context="테마 강세",
        minutes_left=80,
    )

    assert "호라이즌: MID" in prompt
    assert "리뷰매도 120분" in prompt
    assert "수익/부분익절 180분" in prompt
    assert "소프트손절 60분" in prompt
    assert "전략 프로파일: STABLE_SHORT" in prompt
    assert "보유기간 아님" in prompt
    assert "trade_horizon이 보유기간 판단의 우선 기준" in HOLDINGS_REVIEW_SYSTEM
    assert "STABLE_SHORT/AGGRESSIVE_SHORT는 legacy 실행/위험 프로파일" in HOLDINGS_REVIEW_SYSTEM
