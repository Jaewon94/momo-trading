# Test Plan

Task: `2026-06-10-003-policy-trace-phase-zero`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/policy -q
.venv313/bin/python -m pytest tests/strategy/test_risk_manager_enhancements.py tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py -q
.venv313/bin/python -m pytest tests/strategy/policy tests/strategy/test_risk_manager_enhancements.py tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_trading_agent_risk_reservation.py tests/agent/test_order_reservation.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-003-policy-trace-phase-zero
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm no buy/sell threshold, quantity calculation, broker order call, runtime
  setting mutation, DB schema, or liquidation behavior changed.
- Confirm added trace keys are additive metadata only.
