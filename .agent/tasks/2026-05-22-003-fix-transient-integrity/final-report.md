# Final Report

## Outcome

- Fixed the transient lifecycle integrity false-fail path.
- Runtime is back up with the new code loaded.
- Final runtime state is safe/read-only and integrity is `OK`.

## Root Cause

The lifecycle check allowed broker/DB mismatch only when both broker pending orders and DB `PENDING_CONFIRM` rows existed for the same symbol.

In real broker timing, a filled or cancelled order can disappear from broker pending orders before the DB confirmation task finalizes. During that short window:

- fresh BUY pending can make broker holdings appear higher than DB confirmed open quantity.
- fresh SELL pending can make broker holdings appear lower than DB confirmed open quantity.

That should be a bounded `WARN`, not an immediate `FAIL`.

## Code Change

- `services/trade_lifecycle_integrity_service.py`
  - Fetches pending-confirm rows with side, quantity, order id, and event time.
  - Applies a freshness window based on configured order-confirm wait settings plus status timeout and buffer.
  - Allows fresh BUY pending to cover temporary broker-extra holdings.
  - Allows fresh SELL pending to cover temporary broker-missing holdings.
  - Keeps stale pending mismatches as `FAIL`.
- `tests/services/test_trade_lifecycle_integrity_service.py`
  - Added regression tests for fresh BUY pending after broker pending disappears.
  - Added regression test that stale BUY pending still fails.
  - Added fresh SELL pending coverage.

## Verification

- `python scripts/change_harness.py services/trade_lifecycle_integrity_service.py tests/services/test_trade_lifecycle_integrity_service.py`
  - risk: medium
  - protected: no
- `python -m pytest tests/services/test_trade_lifecycle_integrity_service.py -q`
  - 10 passed
- `python -m pytest tests/scripts/test_check_runtime_integrity.py -q`
  - 9 passed
- Runtime restart:
  - health OK
  - server running at `http://127.0.0.1:9000/admin`
- Final runtime integrity:
  - status `OK`
  - trading disabled
  - effective order mode disabled
  - scheduler stopped
  - broker pending 0
  - DB pending 0
  - broker-only 0
  - stale DB-only 0
  - quantity mismatch 0
  - broker untracked holdings 0
- Account snapshot refreshed at 2026-05-22 13:30 KST:
  - total asset 479,559,080 KRW
  - cash 466,791,500 KRW
  - stock value 12,767,580 KRW
  - unrealized PnL 245,238 KRW
  - holding count 4
  - pending order count 0

## Additional Observation

After server restart, `scheduler_running` briefly became true because `NEWS_POLL_ENABLED=true` starts the scheduler for news-only jobs even while `SCHEDULER_ENABLED=false` and order submission is disabled. This is not an order placement issue, but the status wording can confuse trading scheduler state with news polling state.

Follow-up: consider separating `trading_scheduler_running` from `news_scheduler_running`, or make the scheduler stop route persist a full scheduler stop including news polling when that is the operator intent.
