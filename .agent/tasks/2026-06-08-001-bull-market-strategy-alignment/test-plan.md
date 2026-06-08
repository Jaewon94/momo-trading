# Test Plan

Task: `2026-06-08-001-bull-market-strategy-alignment`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m pytest tests/services/test_candidate_scoring_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/test_trade_horizon.py -q
python -m pytest tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/test_trade_horizon.py -q
python -m pytest tests/api/test_admin_settings_validation.py::test_admin_settings_accepts_loss_streak_recovery_mode tests/strategy/test_trading_guard.py -q
python scripts/task_harness.py verify 2026-06-08-001-bull-market-strategy-alignment
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm profit-guard stops above average buy price do not bypass MID/LONG minimum holding windows unless the horizon default loss stop is breached.
- Confirm tight loss stops below average buy price but above the horizon default loss stop are held through the configured soft-stop minimum window, and hard default stop breaches still sell.
- Confirm `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS=50` is accepted and the consecutive-loss guard stays in warning/reduced-size `PROBATION` mode instead of fully disabling recovery controls.
- Confirm service health/status if runtime restart is performed.
- Confirm no broker reset, DB deletion, migration, or forced liquidation was performed.
