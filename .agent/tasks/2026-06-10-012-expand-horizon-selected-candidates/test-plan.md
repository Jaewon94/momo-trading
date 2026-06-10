# Test Plan

Task: `2026-06-10-012-expand-horizon-selected-candidates`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/test_horizon_scan_policy.py tests/agent/test_market_scanner.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py tests/services/test_runtime_settings_service.py -q
.venv313/bin/python -m py_compile core/config.py strategy/horizon_scan_policy.py agent/market_scanner.py agent/trading_agent.py
python scripts/check_runtime_integrity.py --days 7
```

## Results

- Pass: `python scripts/check_task_harness.py --strict-current`
  - `checked 36 task artifact directories`
- Pass: `.venv313/bin/python scripts/task_harness.py verify 2026-06-10-012-expand-horizon-selected-candidates`
  - `diff_check`, `py_compile`, `secret_scan`, `task_harness`, `markdown_links`, `docs_consistency`, `harness_tests` all passed.
  - Note: The same command with system `python` first failed because `/opt/homebrew/opt/python@3.14/bin/python3.14` did not have `pytest` installed; this was an environment issue, not a project test failure.
- Pass: `.venv313/bin/python -m pytest tests/strategy/test_horizon_scan_policy.py tests/agent/test_market_scanner.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py tests/services/test_runtime_settings_service.py -q`
  - `74 passed in 1.47s`
- Pass: `.venv313/bin/python -m py_compile core/config.py strategy/horizon_scan_policy.py agent/market_scanner.py agent/trading_agent.py`
- Pass: `python scripts/check_runtime_integrity.py --days 7`
  - `system=OK`, `order_reconciliation=OK`, `status=OK`, `db_pending=0`, `broker_pending=0`, `confirm_failed=19`.
- Pass: `git diff --check`
- Runtime settings confirmed through admin settings API:
  - `HORIZON_SHORT_MAX_CANDIDATES=30`, `HORIZON_MID_MAX_CANDIDATES=60`, `HORIZON_LONG_MAX_CANDIDATES=100`
  - `HORIZON_SHORT_SELECTED_MAX=10`, `HORIZON_MID_SELECTED_MAX=12`, `HORIZON_LONG_SELECTED_MAX=12`
- Health confirmed through `/api/v1/health`: `healthy`.
- System status confirmed scheduler/agent are running; current session is `NXT_AFTER`, so automatic regular-session trading is disabled by broker/session policy.
- Post-restart check confirmed `/api/v1/health` is `healthy`, scheduler/agent are running, selected caps remain `SHORT=10 MID=12 LONG=12`, and runtime integrity remains `OK`.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- No DB deletion, migration, broker reset, liquidation, or credential changes were run.
