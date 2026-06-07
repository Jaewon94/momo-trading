# Brief

## Metadata

- Task ID: `2026-06-06-001-weekly-review-fixes`
- Created: `2026-06-06T12:28:39+09:00`
- Repo: `momo-trading`
- Title: Stabilize weekly trading review fixes

## Goal

Implement recommended fixes from the weekly trading review: prevent decision event contamination, align PnL reporting, improve stale confirmation handling, and document fast gate follow-up without broker or DB mutation

## Scope

In scope:

- 테스트/런타임 세션 팩토리 오염으로 decision_events에 들어간 fixture성 행이 성과/벤치마크에 섞이지 않도록 방지한다.
- 저장된 일간 리포트 값이 오래된 경우 API 응답에서 canonical trade ledger 기준으로 PnL/승패/주문 수를 보정한다.
- 오래된 BUY pending-confirm 행이 신규 매수를 계속 막는 경우 확인 복구를 먼저 시도하도록 한다.
- pre-LLM fast gate의 소표본 역방향 경고를 오류가 아닌 관찰 대상으로 낮춘다.
- 위 내용을 테스트와 하네스 산출물에 기록한다.

Out of scope:

- Unrelated trading behavior changes.
- Runtime DB cleanup, reset, migration, broker-affecting command unless separately approved.
- 기존 contaminated decision_event 행 삭제. 이번 작업은 추가 오염 방지와 리포팅/분석 제외만 수행한다.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- 2026-06-03 weekly trading review artifacts
- runtime API/DB read-only checks from the weekly audit
- related service/API/scheduler/agent tests

Plan implications:

- Adopt: 코드 차원에서 fixture성 decision_event 유입 경로와 분석 혼입을 막고, admin report API는 canonical trade ledger 값을 우선한다.
- Adopt: stale BUY pending-confirm은 차단 결론 전에 portfolio sync recovery를 한 번 시도한다.
- Adopt: fast_gate_score 역방향 신호는 표본 30개 미만이면 error가 아닌 watchlist로 기록한다.
- Defer: 이미 쌓인 runtime decision_events 정리는 DB mutation이므로 별도 명시 승인 후 수행한다.
- Reject: 공격적 리스크 모드에서 필터/LLM 임계치를 임의 완화하지 않는다. 현재 현금 비중 문제는 필터/LLM/시장 휴장/후보 부족을 운영 리포트로 확인하고 조정해야 한다.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/services/test_decision_event_service.py tests/services/test_decision_benchmark_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/jobs/test_calibration_review_job.py tests/api/test_admin_report_routes.py tests/agent/test_decision_maker.py -q`
- `.venv313/bin/python -m pytest tests/services/test_performance_reporting_service.py tests/services/test_daily_report_service.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_trade_lifecycle_integrity_service.py tests/services/test_order_reconciliation_service.py -q`
- `.venv313/bin/python -m pytest tests/agent tests/api tests/scheduler tests/services -q`
- `.venv313/bin/python -m py_compile services/decision_event_service.py services/decision_event_quality.py services/decision_benchmark_service.py services/decision_forward_return_service.py api/routes/admin.py scheduler/jobs/calibration_review_job.py agent/decision_maker.py`
- `python scripts/change_harness.py <changed paths>`
- `python scripts/task_harness.py verify 2026-06-06-001-weekly-review-fixes`
