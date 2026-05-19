# Test Plan

Task: `2026-05-19-001-horizon-risk-rebalance`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m py_compile strategy/trading_guard.py agent/trading_agent.py strategy/trade_horizon.py services/candidate_scoring_service.py agent/market_scanner.py core/config.py
.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/strategy/test_trade_horizon.py tests/services/test_candidate_scoring_service.py -q
.venv313/bin/python -m pytest tests/strategy/test_risk_manager_enhancements.py tests/agent/test_trading_agent_cycles.py -q
git diff --check
python scripts/check_runtime_integrity.py --days 7
```

## Results

- `python -m py_compile ...`: passed.
- Focused strategy/service tests: `24 passed`.
- Risk manager and agent cycle regression tests: `37 passed`.
- `git diff --check`: passed.
- `python scripts/check_task_harness.py --strict-current`: passed.
- `python scripts/check_runtime_integrity.py --days 7`: passed after restart.
- Runtime settings check: `LOSS_STREAK_RECOVERY_MODE=PROBATION`.
- Runtime order reconciliation: broker pending 0, DB pending 0, broker-only 0, stale DB-only 0, quantity mismatch 0.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirmed no broker order placement, liquidation, DB reset, or production migration was run for this task.
- Confirmed app health endpoint responds after restart on `127.0.0.1:9000`.
- Noted off-hours `INVESTING` news source error as residual non-order-path observation.
