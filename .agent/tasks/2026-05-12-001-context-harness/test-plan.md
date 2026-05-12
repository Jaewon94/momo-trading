# Test Plan

Task: `2026-05-12-001-context-harness`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m pytest tests/scripts/test_check_task_harness.py tests/scripts/test_task_harness.py -q
```

## Coverage Targets

- Missing required task files fail validation.
- Current task pointer must reference an existing task.
- Invalid task id format fails validation.
- Strict current mode turns warnings into failures.
- Task CLI can create a new task, append logs, and print status in a temp repo.

## Manual Checks

- Added docs do not include secrets.
- Trading runtime code is not changed by this task.
- Protected operations are documented clearly.

## Verification Loop

- Run the commands above after implementation.
- Fix failures and rerun until both checks pass.
- Record final result in `run-log.json` and `quality-scorecard.md`.
