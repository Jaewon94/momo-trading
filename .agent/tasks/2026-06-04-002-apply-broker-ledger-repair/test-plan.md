# Test Plan

Task: `2026-06-04-002-apply-broker-ledger-repair`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py -q
python scripts/check_runtime_integrity.py --days 7
curl -s http://127.0.0.1:9000/api/v1/admin/system/status
curl -s http://127.0.0.1:9000/api/v1/admin/account/pending-orders
```

## Results

- Task harness strict check: passed.
- Focused regression suite: `173 passed, 3 warnings in 33.97s`.
- Runtime integrity after final restart: OK; broker pending 0, DB pending 0, stale DB-only 0, qty mismatch 0, lifecycle pending 0.
- Service health: healthy on `http://127.0.0.1:9000`.
- Runtime mode: `TRADING_ENABLED=true`, `AUTONOMY_MODE=AUTONOMOUS`, effective order mode `FULL`, scheduler and agent running.
- Startup scan after final restart: `scanned=5`, `analyzed=5`, `signals=0`, `executed=0`.
- Pending orders API: empty list.

## Manual Checks

- Runtime DB backup created before reconciliation: `runtime/backups/db/app-manual-20260604-103021.db`.
- SG세계물산 stale open BUY closed neutral with `BROKER_HOLDING_MISSING`; no broker order placed for this repair.
- Open holdings after final restart: 센서뷰 1005주, 원텍 400주.
- 보유 stop 보존 확인: 원텍은 낮은 stop 제안 후 DB 기준 7,985원으로 메모리가 되돌아갔고, 센서뷰/원텍 open BUY stop 값은 DB에 보호 방향으로 반영됨.
