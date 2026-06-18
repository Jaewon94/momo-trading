"""MID/LONG 호라이즌 손절/익절 바운딩 회귀 테스트.

'중기/장기로 진입했는데 단기처럼 좁은 손절·가까운 익절로 관리되어
조기 손절/익절되는' 문제(예: 484870 MID인데 -3.7% 손절)를 막는지 검증한다.
"""
from agent.trading_agent import TradingAgent
from strategy.trade_horizon import TradeHorizon


def _agent() -> TradingAgent:
    # __init__(브로커/전략 로딩 등)을 건너뛰고 순수 메서드만 사용한다.
    return TradingAgent.__new__(TradingAgent)


def test_short_horizon_keeps_ai_levels():
    ta = _agent()
    entry = 91900.0
    assert ta._bound_stop_loss_to_horizon(88500, entry, TradeHorizon.SHORT) == 88500
    assert ta._bound_take_profit_to_horizon(98500, entry, TradeHorizon.SHORT) == 98500


def test_mid_widens_tight_stop_and_near_target():
    ta = _agent()
    entry = 91900.0
    # AI 손절 -3.7%(88500) → MID 기본 -7%까지 확대
    sl = ta._bound_stop_loss_to_horizon(88500, entry, TradeHorizon.MID)
    assert sl < 88500
    assert round((sl - entry) / entry * 100, 1) == -7.0
    # AI 익절 +7.2%(98500) → MID 기본 +12%까지 확대
    tp = ta._bound_take_profit_to_horizon(98500, entry, TradeHorizon.MID)
    assert tp > 98500
    assert round((tp - entry) / entry * 100, 1) == 12.0


def test_long_uses_long_defaults():
    ta = _agent()
    entry = 100000.0
    sl = ta._bound_stop_loss_to_horizon(98000, entry, TradeHorizon.LONG)
    tp = ta._bound_take_profit_to_horizon(103000, entry, TradeHorizon.LONG)
    assert round((sl - entry) / entry * 100, 1) == -10.0
    assert round((tp - entry) / entry * 100, 1) == 18.0


def test_already_wide_levels_are_not_narrowed():
    ta = _agent()
    entry = 100000.0
    # 이미 -12% 손절이면 MID 기본(-7%)으로 좁히지 않는다 (더 넓은 쪽 유지)
    sl = ta._bound_stop_loss_to_horizon(88000, entry, TradeHorizon.MID)
    assert sl == 88000
    # 이미 +20% 익절이면 MID 기본(+12%)으로 낮추지 않는다
    tp = ta._bound_take_profit_to_horizon(120000, entry, TradeHorizon.MID)
    assert tp == 120000


def test_none_or_zero_inputs_passthrough():
    ta = _agent()
    assert ta._bound_stop_loss_to_horizon(None, 100000, TradeHorizon.MID) is None
    assert ta._bound_stop_loss_to_horizon(95000, 0, TradeHorizon.MID) == 95000
