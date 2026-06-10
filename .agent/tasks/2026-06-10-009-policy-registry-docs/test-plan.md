# Test Plan

Task: `2026-06-10-009-policy-registry-docs`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile strategy/policy/registry.py
.venv313/bin/python -m pytest tests/strategy/policy tests/scripts/test_docs_harness_checks.py -q
.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_risk_manager_enhancements.py tests/agent/test_trading_agent_cycles.py -q
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-009-policy-registry-docs
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm registry/docs changes are metadata-only.
