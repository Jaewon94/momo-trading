"""evaluate_overnight_hold / _overnight_loss_threshold_pct 회귀 테스트.

장 마감 보유 심사에서 손절 임계값을 horizon별로 다르게 적용한다는 약속을
지키는지 검증한다. (5/27 데이터에서 MID 매매가 -3% 라는 하드코딩 임계값에
걸려 CLOSE_REVIEW로 강제 청산된 사례가 있었다.)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from strategy.holding_policy import (
    _overnight_loss_threshold_pct,
    evaluate_overnight_hold,
)


def _config(**overrides):
    base = dict(
        DEFAULT_STOP_LOSS_PCT_SHORT=-3.0,
        DEFAULT_STOP_LOSS_PCT_MID=-7.0,
        DEFAULT_STOP_LOSS_PCT_LONG=-10.0,
        MAX_HOLD_DAYS_SHORT=5,
        MAX_HOLD_DAYS_MID=15,
        MAX_HOLD_DAYS_LONG=30,
        MAX_HOLD_DAYS_AGGRESSIVE=10,
        MAX_HOLD_DAYS_STABLE=15,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _trade(horizon: str, *, ai_confidence: float = 0.7, ai_target_price: float = 0.0,
           entry_at: datetime | None = None, strategy_type: str = "STABLE_SHORT"):
    notes = json.dumps({"trade_horizon": horizon})
    # 고정 날짜를 쓰면 달력이 지나며 보유일이 MAX_HOLD_DAYS를 넘어 테스트가 깨진다.
    default_entry_at = datetime.now() - timedelta(days=2)
    return SimpleNamespace(
        ai_confidence=ai_confidence,
        ai_target_price=ai_target_price or None,
        strategy_type=strategy_type,
        notes=notes,
        entry_at=entry_at or default_entry_at,
        created_at=default_entry_at,
    )


def _holding(symbol: str = "018880", avg_buy_price: float = 5_630.0):
    return SimpleNamespace(symbol=symbol, avg_buy_price=avg_buy_price)


def test_overnight_loss_threshold_is_short_horizon_minus_three_percent():
    trade = _trade("SHORT")
    assert _overnight_loss_threshold_pct(trade, _config()) == -3.0


def test_overnight_loss_threshold_is_mid_horizon_minus_seven_percent():
    trade = _trade("MID")
    assert _overnight_loss_threshold_pct(trade, _config()) == -7.0


def test_overnight_loss_threshold_is_long_horizon_minus_ten_percent():
    trade = _trade("LONG")
    assert _overnight_loss_threshold_pct(trade, _config()) == -10.0


def test_overnight_loss_threshold_uses_config_overrides():
    trade = _trade("MID")
    config = _config(DEFAULT_STOP_LOSS_PCT_MID=-5.5)
    assert _overnight_loss_threshold_pct(trade, config) == -5.5


def test_evaluate_overnight_hold_holds_mid_position_above_loss_threshold():
    """5/27 018880 사례: MID 매매가 -3.5%일 때 강제 청산되지 않아야 한다.

    이전 하드코딩 -3% 임계값에서는 SELL로 분류됐지만, horizon-aware 임계값에서는
    MID는 -7%까지 보유 유지가 정상이다.
    """
    trade = _trade("MID", ai_confidence=0.6)
    holding = _holding(avg_buy_price=5_630.0)
    current_price = 5_433.0  # -3.50% from entry
    decision = evaluate_overnight_hold(holding, trade, current_price, _config())
    assert decision.action == "HOLD"


def test_evaluate_overnight_hold_sells_mid_position_below_horizon_threshold():
    """MID 손절 임계값(-7%) 미만이면 SELL로 분류돼야 한다."""
    trade = _trade("MID")
    holding = _holding(avg_buy_price=5_630.0)
    current_price = 5_200.0  # -7.64% — below MID -7%
    decision = evaluate_overnight_hold(holding, trade, current_price, _config())
    assert decision.action == "SELL"
    assert "-7.0%" in decision.reason or "-7%" in decision.reason


def test_evaluate_overnight_hold_short_horizon_still_sells_at_minus_three_percent():
    """SHORT 호라이즌은 기존처럼 -3% 손절 유지."""
    trade = _trade("SHORT")
    holding = _holding(avg_buy_price=10_000.0)
    current_price = 9_650.0  # -3.5%
    decision = evaluate_overnight_hold(holding, trade, current_price, _config())
    assert decision.action == "SELL"
