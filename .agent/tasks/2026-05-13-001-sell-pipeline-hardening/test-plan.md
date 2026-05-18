# Test Plan

Task: `2026-05-13-001-sell-pipeline-hardening`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python scripts/change_harness.py scheduler/scheduler.py tests/scheduler/test_scheduler_runtime_paths.py
python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
python scripts/task_harness.py verify 2026-05-13-001-sell-pipeline-hardening
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm no live broker order endpoint or DB reset command was run.
- Confirm existing duplicate sell lock and `DecisionMaker.confirm_and_record`
  path remain in use.
