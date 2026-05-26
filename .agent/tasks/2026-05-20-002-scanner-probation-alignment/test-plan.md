# Test Plan

Task: `2026-05-20-002-scanner-probation-alignment`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m pytest tests/services/test_candidate_scoring_service.py tests/agent/test_market_scanner.py -q
python -m pytest tests/strategy/test_trading_guard.py -q
python scripts/change_harness.py agent/market_scanner.py services/candidate_scoring_service.py analysis/llm/prompts/market_scan.py tests/services/test_candidate_scoring_service.py tests/agent/test_market_scanner.py
python -m pytest tests/trading tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/agent/test_market_scanner.py tests/services/test_candidate_scoring_service.py -q
python -m pytest tests/strategy tests/trading tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_order_reconciliation_service.py tests/agent/test_market_scanner.py tests/services/test_candidate_scoring_service.py -q
.venv313/bin/python scripts/task_harness.py verify 2026-05-20-002-scanner-probation-alignment
python scripts/check_runtime_integrity.py --days 7
python -m pytest tests/analysis/test_stock_analysis_prompt.py tests/services/test_deterministic_prompt_context_service.py -q
python -m py_compile analysis/llm/prompts/stock_analysis.py
python scripts/change_harness.py analysis/llm/prompts/stock_analysis.py tests/analysis/test_stock_analysis_prompt.py
python -m py_compile scheduler/scheduler.py
python -m pytest tests/scheduler/test_scheduler_runtime_paths.py::test_holdings_check_restores_persisted_ai_exit_thresholds_after_restart -q
python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
python scripts/change_harness.py scheduler/scheduler.py tests/scheduler/test_scheduler_runtime_paths.py
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm runtime DB entry-price reconciliation was only applied after explicit approval and only for order `0069525`.
- Confirm loss-streak PROBATION still blocks daily-cap, under-min-change, over-max-change, and compound weak intraday cases.
- Confirm loss-streak PROBATION now allows reduced-size recovery candidates while holding and with caution-only repeated-loss/single weak intraday signals.
- Confirm live persisted `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` remains `1` until an admin-confirmed protected runtime setting change is approved.
- Confirm live persisted `LOSS_STREAK_RECOVERY_MAX_DAILY_BUYS` is changed from `1` to `2` only through an admin-confirmed protected runtime setting update after user approval.
- Confirm post-restart activity logs show the Tier1 stock-analysis prompt uses mid/long wording and no longer says short-term trading specialist.
- Confirm intraday restart restores persisted AI stop/take/trailing thresholds for existing holdings before default stop/take fallback is used.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- After restart, confirm health/system status remains OK and no pending-order or holding mismatch appears.
