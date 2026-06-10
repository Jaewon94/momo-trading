# Test Plan

Task: `2026-06-10-001-aggressive-exposure-policy`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/test_exposure_policy.py tests/agent/test_trading_agent_cycles.py::test_aggressive_exposure_alignment_raises_buy_quantity_and_logs tests/agent/test_trading_agent_cycles.py::test_aggressive_exposure_alignment_does_not_raise_low_confidence tests/api/test_admin_settings_validation.py::test_admin_settings_accepts_aggressive_exposure_alignment_settings tests/api/test_admin_settings_validation.py::test_admin_settings_rejects_invalid_aggressive_exposure_confidence -q
.venv313/bin/python -m pytest tests/strategy/test_exposure_policy.py tests/strategy/test_risk_manager_enhancements.py tests/strategy/test_trading_guard.py tests/strategy/test_cash_ratio_units.py -q
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_risk_reservation.py tests/agent/test_trading_agent_market_data.py -q
.venv313/bin/python -m pytest tests/api/test_admin_settings_validation.py tests/api/test_admin_settings_routes.py tests/services/test_runtime_settings_service.py -q
python scripts/check_runtime_integrity.py --days 7
python scripts/task_harness.py verify 2026-06-10-001-aggressive-exposure-policy
```

## Results

- `git diff --check`: pass
- `python scripts/guard_git_command.py scan-secrets`: pass
- Focused pytest bundle: pass, `134 passed in 2.20s`
- `python scripts/check_task_harness.py --strict-current`: pass
- `python scripts/task_harness.py verify ...`: failed once because default Python 3.14 did not have `pytest`
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-001-aggressive-exposure-policy`: pass
- Live runtime integrity before restart: pass, pending broker/DB orders reconciled to zero
- Restart/live validation: pass
  - Server restarted in `tmux` session `momo-trading-server`.
  - Health endpoint returned healthy.
  - System status: `AUTONOMOUS`, effective order mode `FULL`, scheduler and agent running.
  - Runtime integrity after restart: pass, `broker_pending=0`, `db_pending=0`, `qty_mismatch=0`.
  - First post-restart cycle completed at `2026-06-10T11:32:38+09:00`.
  - Post-restart live BUY confirmed: `459550` 알트 2,500주 @ 2,100원.
  - New risk adjustment logging appeared live: Tier2 5,000주 -> trading guard `NEGATIVE_EXPECTANCY` multiplier 0.5 -> final 2,500주.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm AGGRESSIVE exposure alignment only raises already-approved BUY signals and does not bypass risk manager/broker checks.
- Confirm quantity changes are logged when exposure alignment, risk manager adjustment, or broker buying-power adjustment changes quantity.
- Confirm live runtime settings expose the new aggressive exposure alignment controls.
- Confirm trading-guard quantity multipliers appear as risk-manager adjustments instead of silent `TradeSignal` mutations.
