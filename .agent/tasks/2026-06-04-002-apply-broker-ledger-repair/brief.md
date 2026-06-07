# Brief

## Metadata

- Task ID: `2026-06-04-002-apply-broker-ledger-repair`
- Created: `2026-06-04T10:30:11+09:00`
- Repo: `momo-trading`
- Title: Apply broker ledger repair

## Goal

Back up runtime DB, apply approved read-only-confirmed holdings reconciliation for broker-missing open BUY lots, restart service to load SELL confirmation fix, and verify runtime integrity without placing broker orders.

## Scope

In scope:

- 런타임 DB 백업 후 브로커 보유가 없는 open BUY 장부 1건을 중립 close로 대사.
- SELL 체결 확인 누락 수정 코드를 서비스에 반영.
- 로컬 SQLAlchemy/aiosqlite 디버그 로그 폭증 방지.
- 보유 종목 손절선 조정이 기존 보호 스탑보다 느슨해지지 않도록 보존 규칙 추가.
- 재시작 후 API, 주문 대사, 보유/잔고, 스타트업 사이클을 확인.

Out of scope:

- 신규 전략 방향 변경, 강제 청산 정책 변경.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Runtime DB `trade_results`, `decision_events`, `agent_activity_logs`
- Admin APIs: `/system/status`, `/account/balance`, `/account/holdings`, `/account/pending-orders`
- `scripts/check_runtime_integrity.py --days 7`

Plan implications:

- Adopt: 브로커 누락 open BUY는 백업 후 `BROKER_HOLDING_MISSING` 중립 close로 정리.
- Adopt: 본전/수익보호 스탑보다 낮은 `TIGHTEN_STOP`/HOLD stop 조정은 메모리와 DB 모두에서 보존.
- Adopt: `SQLALCHEMY_ECHO=false` 기본값으로 로컬 SQL 로그 폭증을 차단.
- Defer: 기존 `CONFIRM_FAILED` 과거 이력 8건은 현재 pending/order drift가 아니므로 별도 정리 과제로 분리.
- Reject: 브로커 주문 재실행, DB 삭제, 마이그레이션 실행.

## Completion Criteria

- SG세계물산 stale open BUY가 0손익 중립 close로 정리되고 lifecycle integrity가 OK.
- 서비스가 tmux `momo-trading-service`에서 실행 중이며 자동매매 설정이 정상.
- 대기 주문 0건, broker/db 주문 대사 OK.
- 손절선 보존 회귀 테스트와 기존 의사결정/스케줄러 테스트 통과.
- 오늘/이번 주 손익 및 이상 거래 분석이 최종 보고에 포함됨.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py -q`
- `python scripts/check_runtime_integrity.py --days 7`
- `curl -s http://127.0.0.1:9000/api/v1/admin/system/status`
- `curl -s http://127.0.0.1:9000/api/v1/admin/account/pending-orders`
