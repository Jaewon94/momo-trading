# Test Plan

Task: `2026-05-14-003-additional-consistency-restart-validation`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python scripts/change_harness.py api/routes/admin.py admin/static/js/app.js admin/static/index.html docs/workflows/code-commit-harness.md tests/api/test_admin_settings_routes.py tests/api/test_admin_settings_validation.py tests/api/test_admin_scheduler_routes.py tests/api/test_admin_manual_actions.py
.venv313/bin/python -m pytest tests/api -q
.venv313/bin/python -m pytest tests/scripts/test_check_runtime_integrity.py tests/scripts/test_change_harness.py -q
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/scheduler/test_portfolio_sync_job.py -q
pnpm test:ui
python scripts/check_docs_consistency.py
python scripts/task_harness.py verify 2026-05-14-003-additional-consistency-restart-validation
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- After restart, use only safe GET/openapi/static checks plus the read-only runtime integrity gate.
- Do not probe live manual sell/cancel endpoints without a token because an old server would execute them.
