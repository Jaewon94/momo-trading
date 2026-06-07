# Test Plan

Task: `2026-06-06-001-weekly-review-fixes`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m py_compile services/decision_event_service.py services/decision_event_quality.py services/decision_benchmark_service.py services/decision_forward_return_service.py api/routes/admin.py scheduler/jobs/calibration_review_job.py agent/decision_maker.py
.venv313/bin/python -m pytest tests/services/test_decision_event_service.py tests/services/test_decision_benchmark_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/jobs/test_calibration_review_job.py tests/api/test_admin_report_routes.py tests/agent/test_decision_maker.py -q
.venv313/bin/python -m pytest tests/services/test_performance_reporting_service.py tests/services/test_daily_report_service.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_trade_lifecycle_integrity_service.py tests/services/test_order_reconciliation_service.py -q
.venv313/bin/python -m pytest tests/agent tests/api tests/scheduler tests/services -q
python scripts/change_harness.py services/decision_event_service.py services/decision_event_quality.py services/decision_benchmark_service.py services/decision_forward_return_service.py api/routes/admin.py scheduler/jobs/calibration_review_job.py agent/decision_maker.py tests/services/test_decision_event_service.py tests/services/test_decision_benchmark_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/jobs/test_calibration_review_job.py tests/api/test_admin_report_routes.py tests/agent/test_decision_maker.py
python scripts/task_harness.py verify 2026-06-06-001-weekly-review-fixes
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm service health and admin report API after restart.
- Confirm no broker reset, DB deletion, migration, or order placement command was run.
