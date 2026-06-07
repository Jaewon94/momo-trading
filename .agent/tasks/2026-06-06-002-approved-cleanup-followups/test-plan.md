# Test Plan

Task: `2026-06-06-002-approved-cleanup-followups`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py::test_scheduler_start_registers_trading_jobs_when_enabled_after_news_only_start -q -W error::RuntimeWarning
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q -W error::RuntimeWarning
.venv313/bin/python -m pytest tests/services/test_decision_event_service.py tests/services/test_decision_benchmark_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/jobs/test_calibration_review_job.py tests/api/test_admin_report_routes.py tests/agent/test_decision_maker.py -q
.venv313/bin/python -m pytest tests/agent tests/api tests/scheduler tests/services -q
.venv313/bin/python scripts/task_harness.py verify 2026-06-06-002-approved-cleanup-followups
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm runtime DB backup exists before cleanup.
- Confirm cleanup target count and post-cleanup count.
- Confirm service health/status after restart.
