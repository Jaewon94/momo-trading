# Test Plan

Task: `2026-06-10-011-horizon-scheduled-news-analysis`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/test_horizon_scan_policy.py tests/services/test_candidate_scoring_service.py tests/services/test_news_context_service.py tests/services/test_deterministic_prompt_context_service.py tests/agent/test_market_scanner.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/policy/test_settings_catalog.py tests/services/test_runtime_settings_service.py -q
.venv313/bin/python -m pytest tests/strategy/test_horizon_scan_policy.py tests/services/test_candidate_scoring_service.py tests/services/test_news_context_service.py tests/services/test_deterministic_prompt_context_service.py tests/agent/test_market_scanner.py tests/agent/test_trading_agent_market_data.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py tests/strategy/policy/test_settings_catalog.py tests/services/test_runtime_settings_service.py tests/analysis/test_stock_analysis_prompt.py -q
.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/api/test_admin_manual_actions.py -q
python scripts/task_harness.py verify 2026-06-10-011-horizon-scheduled-news-analysis
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-011-horizon-scheduled-news-analysis
python scripts/check_runtime_integrity.py --days 7
.venv313/bin/python -m pytest tests/analysis/test_stock_analysis_prompt.py tests/services/test_deterministic_prompt_context_service.py tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py -q
```

## Results

- Focused pytest: `189 passed in 34.78s`
- Admin settings/manual API pytest: `18 passed in 1.34s`
- Policy registry pytest: `4 passed in 0.65s`
- Task harness with `.venv313`: passed
- Task harness with default/`uv` Python: failed because the selected environment did not have `pytest`; this was an environment issue, not a code test failure.
- Runtime integrity: failed. `trading_enabled=True`, `autonomy=AUTONOMOUS`, `effective_order_mode=FULL`, `order_reconciliation=FAIL`, `db_pending=1`, `db_only_stale=1`, `broker_missing_open_buys=1`.
- Post-restart prompt revalidation: found and fixed the Tier1 system prompt still being MID/LONG-centric for all candidates.
- Prompt-focused retest: `65 passed in 1.25s`
- Final focused pytest after prompt fix: `190 passed in 24.32s`
- Final admin/settings/policy pytest: `22 passed in 1.18s`

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Restart was performed after explicit user request. The service is running, but stale pending-order reconciliation remains a separate operational issue.
