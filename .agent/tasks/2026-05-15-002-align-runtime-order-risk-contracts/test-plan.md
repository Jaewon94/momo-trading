# Test Plan

Task: `2026-05-15-002-align-runtime-order-risk-contracts`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/agent/test_trading_agent_market_data.py tests/strategy/test_cash_ratio_units.py
python scripts/task_harness.py verify 2026-05-15-002-align-runtime-order-risk-contracts
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- After restart, confirm the API is healthy and the read-only integrity report reflects the expected state.
