from analysis.llm.prompts.holdings_review import build_holdings_review_prompt


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
                "max_hold_days": 5,
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
