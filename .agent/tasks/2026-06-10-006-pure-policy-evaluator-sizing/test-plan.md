# Test Plan

Task: `2026-06-10-006-pure-policy-evaluator-sizing`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile strategy/risk_manager.py agent/trading_agent.py strategy/policy/engine.py
.venv313/bin/python -m pytest tests/strategy/test_risk_manager_enhancements.py tests/agent/test_trading_agent_cycles.py tests/strategy/policy -q
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_order_reservation.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-006-pure-policy-evaluator-sizing
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm final enforced quantities remain identical to previous adjusted
  quantities before order submission.
