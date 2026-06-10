# Test Plan

Task: `2026-06-10-005-policy-engine-wrapper`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile strategy/policy/engine.py agent/trading_agent.py agent/decision_maker.py
.venv313/bin/python -m pytest tests/strategy/policy tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_news_gate.py tests/agent/test_trading_agent_cost_gate.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-005-policy-engine-wrapper
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm facade methods preserve existing result payloads and trace reason codes.
