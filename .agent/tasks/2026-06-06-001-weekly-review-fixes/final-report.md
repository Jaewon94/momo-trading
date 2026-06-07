# Final Report

## Summary

- decision_event 세션 팩토리 오염을 막기 위해 global service가 현재 `core.database.AsyncSessionLocal`을 lazy resolution하도록 수정했다.
- fixture성 decision_events가 benchmark/forward-return label에 섞이지 않도록 보수적인 quality filter를 추가했다.
- admin daily report API가 trade ledger의 opened/completed/sell count 기준으로 PnL과 승패를 보정하도록 변경했다.
- stale BUY pending-confirm은 매수 차단 전에 recovery를 한 번 실행하고 재조회하도록 했다.
- fast_gate_score 역방향 신호는 표본 30개 미만일 때 ERROR가 아니라 watchlist성 PROGRESS 로그로 기록하도록 바꿨다.

## Verification

- `.venv313/bin/python -m py_compile services/decision_event_service.py services/decision_event_quality.py services/decision_benchmark_service.py services/decision_forward_return_service.py api/routes/admin.py scheduler/jobs/calibration_review_job.py agent/decision_maker.py` passed.
- Focused tests passed: 79 passed.
- Related reporting/sync/integrity tests passed: 59 passed.
- Broad tests passed: 641 passed, 3 existing scheduler coroutine warnings.
- `python scripts/check_task_harness.py --strict-current` passed after task status correction.
- `.venv313/bin/python scripts/task_harness.py verify 2026-06-06-001-weekly-review-fixes` passed.
- Service restarted in tmux foreground session `momo-trading-service`; health API returned healthy.
- Admin system status returned OK broker/orders/news/ollama/account_snapshot states. Market is closed on 2026-06-06 because of 현충일; next market open is 2026-06-08 09:00.
- Trade lifecycle integrity API returned `status=OK`: pending confirms 0, unpaired sells 0, broker missing open BUY 0, broker untracked holdings 0.
- `scripts/check_runtime_integrity.py --days 7` returned system/order/lifecycle status OK.
- 2026-06-02 admin report now overlays canonical trade ledger metrics: `total_pnl=-212170`, `sell_count=3`, `open_position_count=0`.
- Weekly 2026-06-01..2026-06-05 canonical closed BUY result: 14 closed trades, 8 wins, 6 losses, realized PnL `+290900`.
- Latest report date 2026-06-05: realized PnL `-198000`, open positions 0.
- Candidate scoring runtime sample since 2026-06-01: 219 cycles, 1752 candidate scoring events, exactly 8 candidates per cycle.
- AI skip metrics since 2026-06-01: fast gate 237, pre-analysis gate 24, deterministic final gate 14.

## Operational Safety

- Broker reset, DB deletion, migration, liquidation, or order placement command was not run.
- Existing runtime contaminated decision_events were not deleted. Cleanup remains deferred until explicit DB mutation approval.
- Service startup ran normal scheduler startup paths and news polling; no order placement occurred because the market session is closed/holiday.

## Remaining Watch Items

- Scheduler coroutine warning cleanup is unrelated but should be handled separately.
- Runtime raw DB still contains historical fixture-like decision_events. Current code prevents new contamination and excludes probable fixtures from benchmark/forward labels, but DB cleanup remains a separate protected operation.
