# Test Plan

Task: `2026-06-10-007-pure-threshold-policy-split`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile agent/trading_agent.py tests/agent/test_trading_agent_cycles.py
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py -q
.venv313/bin/python -m pytest tests/strategy/policy tests/strategy/test_risk_manager_enhancements.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-007-pure-threshold-policy-split
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm calculated threshold values are unchanged.
- Confirm pure threshold calculation does not call event detector.
