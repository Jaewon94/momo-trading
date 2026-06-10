# Final Report

Phase 3b threshold policy split을 완료했다. 이번 변경은 손절/익절/트레일링
스탑 값을 계산하는 부분과 `event_detector`에 적용하는 부분을 분리한
행동 보존 리팩터링이다.

## Changed

- `agent/trading_agent.py`
  - `_resolve_trade_thresholds` 추가: threshold 값을 계산하지만
    `event_detector`에 쓰지 않는다.
  - `_enforce_trade_thresholds` 추가: 계산된 threshold를 event detector에
    적용한다.
  - `_apply_trade_thresholds`는 기존 호출 호환 wrapper로 유지.
- `tests/agent/test_trading_agent_cycles.py`
  - pure resolver가 `event_detector.set_thresholds`를 호출하지 않는 테스트 추가.
- `docs/architecture/trading-policy-engine-refactor-plan.md`
  - Phase 3b implementation status 업데이트.

## Behavior Impact

- Intended behavior change: none.
- Stop-loss/take-profit/trailing-stop formulas are unchanged.
- Existing `_apply_trade_thresholds` callers keep the same side effect.
- Event-driven sell execution behavior is unchanged.

## Verification

- `.venv313/bin/python -m py_compile agent/trading_agent.py tests/agent/test_trading_agent_cycles.py`: passed
- `.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py -q`: 45 passed
- `.venv313/bin/python -m pytest tests/strategy/policy tests/api/test_admin_settings_validation.py tests/strategy/test_risk_manager_enhancements.py tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_trading_agent_risk_reservation.py tests/agent/test_order_reservation.py -q`: 167 passed
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-007-pure-threshold-policy-split`: passed
- `python scripts/check_runtime_integrity.py --days 7`: initially found one live DB pending confirm, then passed after pending-confirm recovery.

## Runtime Reconciliation

- Initial issue: `244920` BUY remained `PENDING_CONFIRM` while broker pending
  orders were 0 and broker holdings showed the position.
- Action: ran `_recover_pending_confirms()`.
- Result: recovered 1, failed 0, skipped 0; runtime integrity then passed with
  pending 0 and reconciliation OK.

## Remaining Work

- Runtime kill-switch side-effect extraction remains pending.
- Policy registry/generated documentation remains Phase 4.
- Runtime server has not been restarted in this task.
