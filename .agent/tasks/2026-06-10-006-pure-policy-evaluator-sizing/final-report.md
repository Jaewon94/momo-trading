# Final Report

Phase 3a pure policy evaluator sizing 작업을 완료했다. 이번 변경은 수량 정책
판단 함수가 `TradeSignal`을 직접 바꾸는 부분을 줄이고, caller enforcement
지점에서 같은 최종 수량을 적용하도록 분리한 리팩터링이다.

## Changed

- `strategy/risk_manager.py`
  - guard-based quantity reduction에서 `signal.suggested_quantity` 직접 mutation 제거.
  - 기존처럼 `adjusted_quantity`, `previous_quantity`, `adjustments`,
    `policy_trace`를 반환한다.
- `agent/trading_agent.py`
  - aggressive exposure alignment helper는 decision/effect metadata를 반환한다.
  - buy path가 `exposure_decision.final_quantity`와
    `risk_result["adjusted_quantity"]`를 enforcement 지점에서 적용한다.
- `tests/strategy/test_risk_manager_enhancements.py`
  - risk manager가 signal을 직접 mutate하지 않는 계약으로 업데이트.
- `tests/agent/test_trading_agent_cycles.py`
  - risk adjusted quantity가 주문 직전 signal에 적용되는 parity regression 추가.
- `docs/architecture/trading-policy-engine-refactor-plan.md`
  - Phase 3a implementation status 업데이트.

## Behavior Impact

- Intended behavior change: none.
- Final enforced buy quantity is intended to remain the same.
- Risk/exposure thresholds are unchanged.
- Runtime settings are unchanged.
- Order request construction and broker submission path are unchanged.

## Verification

- `.venv313/bin/python -m py_compile strategy/risk_manager.py agent/trading_agent.py tests/agent/test_trading_agent_cycles.py tests/strategy/test_risk_manager_enhancements.py`: passed
- `.venv313/bin/python -m pytest tests/strategy/policy tests/api/test_admin_settings_validation.py tests/strategy/test_risk_manager_enhancements.py tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_trading_agent_risk_reservation.py tests/agent/test_order_reservation.py -q`: 166 passed
- `python scripts/change_harness.py ...`: high/protected as expected for order sizing paths
- `python scripts/check_runtime_integrity.py --days 7`: OK, pending orders 0, reconciliation OK
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-006-pure-policy-evaluator-sizing`: passed

## Remaining Work

- Runtime kill-switch side-effect extraction is still pending.
- Threshold policy and event-detector enforcement split is still pending.
- Policy registry/generated documentation remains Phase 4.
- Runtime server has not been restarted in this task.
