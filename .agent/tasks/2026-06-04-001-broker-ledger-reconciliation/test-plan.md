# Test Plan

Task: `2026-06-04-001-broker-ledger-reconciliation`

## Commands

```bash
python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py -q
python scripts/check_runtime_integrity.py --days 7
python scripts/check_task_harness.py --strict-current
python scripts/task_harness.py verify 2026-06-04-001-broker-ledger-reconciliation
```

## Results

- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py -q`
  - Result: passed
  - Output summary: `136 passed, 3 warnings`
  - Notes: warnings are existing scheduler coroutine warnings in `test_scheduler_start_registers_trading_jobs_when_enabled_after_news_only_start`.
- `python scripts/check_runtime_integrity.py --days 7`
  - Result: failed
  - Output summary: system/settings/order reconciliation OK; lifecycle FAIL with `broker_missing_open_buys=1`.
  - Notes: this is the pre-existing live `004060` broker-vs-DB mismatch. No runtime DB repair was applied.
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-04-001-broker-ledger-reconciliation`
  - Result: passed
  - Output summary: `diff_check`, `py_compile`, `secret_scan`, `task_harness`, `markdown_links`, `docs_consistency`, and `harness_tests` passed.
- `python scripts/task_harness.py verify 2026-06-04-001-broker-ledger-reconciliation`
  - Result: failed
  - Reason: default Homebrew Python 3.14 lacks `pytest`; rerun with `.venv313` passed.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm no broker order, runtime DB repair, reset, migration, or liquidation command was executed during verification.
- If runtime integrity still reports existing SG Global mismatch, record it as pre-existing live data requiring explicit repair approval.

Manual check result: no broker order, runtime DB repair, reset, migration, liquidation, or service restart was performed.
