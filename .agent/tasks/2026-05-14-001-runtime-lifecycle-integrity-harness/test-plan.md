# Test Plan

Task: `2026-05-14-001-runtime-lifecycle-integrity-harness`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/scripts/test_check_runtime_integrity.py tests/scripts/test_change_harness.py -q
python scripts/check_runtime_integrity.py --days 7
python scripts/change_harness.py scheduler/scheduler.py
.venv313/bin/python scripts/task_harness.py verify 2026-05-14-001-runtime-lifecycle-integrity-harness
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm `check_runtime_integrity.py` is read-only and does not call apply,
  cancel, order placement, DB reset, or repair endpoints.
- If the live runtime integrity check fails, record it as expected evidence of
  the current broker/DB drift rather than masking it.

## Results

- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/scripts/test_check_runtime_integrity.py tests/scripts/test_change_harness.py -q` → passed, 135 tests.
- `python scripts/check_docs_consistency.py` → passed.
- `python scripts/check_task_harness.py --strict-current` → passed, 6 task artifact directories.
- `python scripts/change_harness.py scheduler/scheduler.py agent/decision_maker.py scripts/check_runtime_integrity.py` → high/protected with runtime integrity gate included.
- `.venv313/bin/python scripts/task_harness.py verify 2026-05-14-001-runtime-lifecycle-integrity-harness` → passed.
- `python scripts/check_runtime_integrity.py --days 7 --json` → expected fail on live data: status FAIL, pending 0, confirm_failed 50, unpaired_sells 14, broker_missing_open_buys 9, broker_mismatch_qty 8.
