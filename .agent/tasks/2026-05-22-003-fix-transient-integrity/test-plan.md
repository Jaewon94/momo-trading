# Test Plan

Task: `2026-05-22-003-fix-transient-integrity`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python scripts/change_harness.py services/trade_lifecycle_integrity_service.py tests/services/test_trade_lifecycle_integrity_service.py
python -m pytest tests/services/test_trade_lifecycle_integrity_service.py -q
python -m pytest tests/scripts/test_check_runtime_integrity.py -q
python scripts/check_runtime_integrity.py --base-url http://127.0.0.1:9000 --days 7 --timeout-sec 30 --allow-status OK --allow-status WARN --json
```

## Manual Checks

- Confirm final runtime stays safe/read-only.
- Confirm scheduler is stopped after verification.
- Confirm account snapshot freshness after manual refresh.
- Confirm today trade list remains consistent: 307180 BUY confirmed, 487240 partial take-profit confirmed, 203400 confirm failed/cancelled.
