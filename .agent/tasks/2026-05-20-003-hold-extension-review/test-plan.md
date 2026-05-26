# Test Plan

Task: `2026-05-20-003-hold-extension-review`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m py_compile strategy/holding_policy.py analysis/llm/prompts/overnight_hold.py scheduler/scheduler.py core/config.py
.venv313/bin/python -m pytest tests/services/test_holdings_precheck_service.py tests/analysis/test_overnight_hold_prompt.py tests/scheduler/test_scheduler_runtime_paths.py::test_smart_liquidation_treats_llm_extend_as_hold_and_updates_notes tests/scheduler/test_scheduler_runtime_paths.py::test_smart_liquidation_rejects_extend_when_hard_exit_condition_exists -q
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
python scripts/change_harness.py strategy/holding_policy.py analysis/llm/prompts/overnight_hold.py scheduler/scheduler.py core/config.py .env.example
.venv313/bin/python scripts/task_harness.py verify 2026-05-20-003-hold-extension-review
python scripts/check_runtime_integrity.py --days 7
```

## Results

- `python -m py_compile ...`: passed.
- Focused extension/precheck/prompt tests: 11 passed.
- `tests/scheduler/test_scheduler_runtime_paths.py`: 84 passed.
- `python scripts/change_harness.py ...`: risk `blocked` because this changes protected hold/liquidation/config/LLM surfaces and touches `.env.example`.
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-20-003-hold-extension-review`: passed.
- `python scripts/check_runtime_integrity.py --days 7`: passed with `system=OK`, order reconciliation `OK`, lifecycle status `OK`.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- After restart, confirm read-only health/status/runtime integrity where available.
- Restarted runtime in persistent `tmux` session `momo-runtime`; `/api/v1/health` returned healthy and system status showed scheduler/agent running.
