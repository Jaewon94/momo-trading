# Test Plan

Task: `2026-06-10-008-runtime-kill-switch-effect-split`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile strategy/trading_guard.py tests/strategy/test_trading_guard.py
.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_risk_manager_enhancements.py -q
.venv313/bin/python -m pytest tests/strategy/policy tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-008-runtime-kill-switch-effect-split
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm live runtime settings are not manually toggled by verification.
