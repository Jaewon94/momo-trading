# MOMO Trading System-Wide Trading Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 감사 Findings F-001~F-036을 안전한 순서로 해결해 주문 안전성, PnL 신뢰도, 리스크 제어, 전략 검증 기반을 먼저 만들고 그 다음 매매 성능 개선 실험을 가능하게 한다.

**Architecture:** 먼저 live trading의 안전장치와 source of truth를 안정화하고, 이후 성과 측정/forward return dataset을 쌓는다. LLM, 뉴스, 전략 파라미터 변경은 측정 기반이 생긴 뒤 shadow/report-only 단계로만 rollout한다.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, SQLite local runtime DB, pytest/pytest-asyncio, Vitest, APScheduler, Kiwoom broker adapter.

---

## 운영 원칙

- 구현은 TDD 순서로만 진행한다: 실패 테스트 작성 -> 실패 확인 -> 최소 구현 -> 통과 확인 -> 관련 회귀 테스트 -> 문서 최신화 -> 커밋.
- live trading 영향이 있는 변경은 `report-only`, `shadow`, `dry-run`, runtime flag 중 하나를 먼저 둔다.
- 주문/리스크 변경은 기본적으로 더 보수적인 방향으로만 기본값을 둔다.
- `.env`와 runtime DB가 충돌할 수 있으므로 구현 중 실제 주문 상태는 항상 Admin settings API/runtime DB 기준으로 확인한다.
- 뉴스는 계속 기본 OFF로 유지한다. 뉴스/LLM은 성과 dataset 없이 BUY gate에 연결하지 않는다.
- 각 Track은 독립 커밋으로 진행한다. Track 안에서도 Task 단위 커밋을 만든다.

## 전체 우선순위

| 순서 | Track | 주요 Findings | 이유 |
|---:|---|---|---|
| 1 | Trading mode and order gate safety | F-001, F-005, F-010, F-031 | 운영자가 실주문 상태와 세션 경계를 오판하면 즉시 손실로 이어질 수 있음 |
| 2 | Order source of truth and reconciliation | F-002, F-003, F-006, F-011, F-012, F-032 | 중복 주문, stale pending, 기록 누락은 PnL/노출을 모두 망가뜨림 |
| 3 | PnL truth and kill switch | F-004, F-009, F-013, F-014, F-015 | 돈을 벌고 있는지 판단하려면 먼저 손익 계산이 맞아야 함 |
| 4 | Scheduler liquidation and realtime safety | F-033, F-036 | 의도치 않은 매도와 감시 누락을 줄임 |
| 5 | Observability and Admin safety | F-034, F-035 | 운영 데이터 삭제/실주문/장애 탐지를 안전하게 만듦 |
| 6 | Decision event and forward return dataset | F-016, F-019, F-026 | 전략/LLM/news 성과를 검증할 최소 데이터 기반 |
| 7 | Backtest hygiene | F-021, F-022, F-023, F-024, F-025 | 백테스트 과대평가를 막고 live와 분리 표기 |
| 8 | LLM/news simplification | F-007, F-027, F-028, F-029, F-030 | 장중 지연/오류를 줄이고 뉴스는 검증될 때까지 shadow로 제한 |
| 9 | Strategy taxonomy and cleanup | F-017, F-018, F-020 | legacy/이름 혼동 제거, 과최적화 방지 |

## 2026-04-23 현재 구현 검증 요약

- Track 1, Track 2, Track 3.1, Track 3.1a는 코드와 테스트 기준 완료 상태다.
- Track 5.1은 observability rollup key의 provider/model `NULL` 정규화와 maintenance failure preflight WARN 노출까지 구현됐다.
- Track 8 관련으로 LLM 지연 경고(`LLM_SLOW_CALL_WARN_SEC`)는 별도 커밋으로 구현됐다. 다만 cooldown incident dedupe는 아직 미구현이다.
- 뉴스 deterministic enrichment/backfill은 별도 커밋으로 구현됐다. 다만 현재 라이브 9000 서버는 최신 코드를 로드하지 않아 backfill endpoint가 아직 동작하지 않는다.
- Track 6.1 canonical decision event table/service와 Track 6.2 forward return labeling job은 구현됐다. 다만 benchmark/control report와 scanner/Tier 단계별 전체 연결은 아직 없어 뉴스/LLM/source별 실제 성과 검증은 report 수준에서 후속 구현이 필요하다.
- 전체 최신 현황은 `docs/고도화/2026-04-23-enhancement-status.md`에 별도 정리한다.

## Phase Gate

- Gate A: Track 1~5 완료 전에는 `AUTONOMY_MODE=AUTONOMOUS` 재개를 권장하지 않는다.
- Gate B: Track 1~6 완료 전에는 LLM/news/strategy 파라미터를 수익 개선 목적으로 변경하지 않는다.
- Gate C: Track 7 완료 전에는 백테스트 결과를 live 전략 성과 근거로 쓰지 않는다.
- Gate D: 뉴스 BUY 차단은 Track 6의 forward return 표본과 Track 8의 source별 report가 쌓인 뒤에만 검토한다.

## Track 1: Trading Mode and Order Gate Safety

### Task 1.1: 주문 제출 모드 명시화

**Files:**
- Modify: `core/config.py`
- Modify: `agent/decision_maker.py`
- Modify: `scheduler/scheduler.py`
- Modify: `services/manual_trade_service.py`
- Modify: `api/routes/admin.py`
- Modify: `admin/static/js/settings_action_state.js`
- Modify: `admin/static/js/settings_form_state.js`
- Test: `tests/agent/test_decision_maker.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`
- Test: `tests/services/test_manual_trade_service.py`
- Test: `tests/api/test_admin_settings_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - `ORDER_SUBMISSION_MODE=READ_ONLY`이면 신규 BUY, scheduler SELL, force liquidation, manual sell이 모두 broker `place_order`를 호출하지 않는 테스트를 추가한다.
  - `ORDER_SUBMISSION_MODE=SELL_ONLY`이면 BUY는 차단하고 SELL 계열만 허용하는 테스트를 추가한다.
  - 추가: Admin settings/status 노출 테스트와 frontend settings action binding 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/services/test_manual_trade_service.py tests/api/test_admin_settings_routes.py -q`
  - Expected: `ORDER_SUBMISSION_MODE` 설정/분기 부재로 실패.
  - Result: 7 failed, 111 passed, 6 errors. 실패 원인은 `ORDER_SUBMISSION_MODE` 설정과 주문 gate 부재.

- [x] **Step 3: 최소 구현**
  - `ORDER_SUBMISSION_MODE=READ_ONLY|SELL_ONLY|FULL` runtime setting을 추가한다.
  - `TRADING_ENABLED=false`는 모든 실주문 차단, `READ_ONLY`는 모든 주문 차단, `SELL_ONLY`는 SELL만 허용, `FULL`은 기존 동작으로 정의한다.
  - Admin status에 `effective_order_submission_mode`와 `runtime_override_active`를 노출한다.
  - Result: `core/order_submission.py` 공통 gate, DecisionMaker/scheduler/manual trade 적용, Admin settings/status와 설정 UI 바인딩 추가.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_scheduler_runtime_paths.py tests/services/test_manual_trade_service.py tests/api/test_admin_settings_routes.py -q`
  - Expected: PASS.
  - Result: 118 passed.
  - UI check: `pnpm vitest run tests/frontend/test_settings_action_state.test.js` -> 1 file passed, 6 tests passed.

- [x] **Step 5: 문서/커밋**
  - Update: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`에서 F-001/F-005/F-010 상태 갱신.
  - Commit: `feat: add explicit order submission mode`
  - Result: 문서 갱신 완료. 커밋은 이 작업 검증 후 생성.

### Task 1.2: 자동매매 세션 guard 통일

**Files:**
- Modify: `scheduler/market_calendar.py`
- Modify: `scheduler/scheduler.py`
- Modify: `realtime/event_detector.py`
- Modify: `realtime/monitor.py`
- Test: `tests/scheduler/test_market_calendar.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`
- Test: `tests/realtime/test_event_detector.py`
- Test: `tests/realtime/test_monitor.py`

- [x] **Step 1: 실패 테스트 작성**
  - 15:25 KST `KRX_CLOSE` fixture에서 `supports_automated_trading=false`이고 주문 생성 path가 실행되지 않는 테스트를 추가한다.
  - 가격 모니터링은 가능하되 주문 트리거 이벤트는 publish되지 않거나 `order_allowed=false` metadata를 갖는지 테스트한다.
  - 추가: 신규 `tests/scheduler/test_market_calendar.py`, `tests/realtime/test_event_detector.py`를 만들고 scheduler holdings/review guard 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/scheduler/test_market_calendar.py tests/scheduler/test_scheduler_runtime_paths.py tests/realtime/test_event_detector.py tests/realtime/test_monitor.py -q`
  - Expected: 기존 `is_krx_trading_hours()` 기준 때문에 실패.
  - Result: 7 failed, 64 passed. 실패 원인은 `is_automated_trading_session` helper 부재와 guard 미적용.

- [x] **Step 3: 최소 구현**
  - `MarketCalendar.is_automated_trading_session()` helper를 추가한다.
  - 주문 생성 가능 경로는 이 helper를 사용한다.
  - 순수 가격 수집/표시는 기존 시장 시간 helper를 유지하되 이름을 명확히 한다.
  - Result: scheduler 주문 생성 경로는 자동매매 세션 guard를 사용하고, event detector는 가격 업데이트는 유지하되 close auction에서는 order-trigger 이벤트를 막는다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/scheduler/test_market_calendar.py tests/scheduler/test_scheduler_runtime_paths.py tests/realtime/test_event_detector.py tests/realtime/test_monitor.py -q`
  - Expected: PASS.
  - Result: 71 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-031 상태를 `해결됨` 또는 `완화됨`으로 변경.
  - Commit: `fix: align automated trading session guard`
  - Result: F-031을 `해결됨`으로 갱신. 커밋은 이 작업 검증 후 생성.

## Track 2: Order Source of Truth and Reconciliation

### Task 2.1: broker/DB pending reconciliation report 추가

**Files:**
- Create: `services/order_reconciliation_service.py`
- Modify: `api/routes/admin.py`
- Modify: `admin/static/js/activity_state.js`
- Test: `tests/services/test_order_reconciliation_service.py`
- Test: `tests/api/test_admin_trade_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - 브로커 pending 4건, DB `PENDING_CONFIRM` 21건, partial fill 1건 fixture를 만든다.
  - 결과가 `broker_only`, `db_only_stale`, `quantity_mismatch`, `partial_fill_pending`으로 분류되는지 테스트한다.
  - Result: `tests/services/test_order_reconciliation_service.py`와 `tests/api/test_admin_trade_routes.py`에 read-only 분류/API 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_order_reconciliation_service.py tests/api/test_admin_trade_routes.py -q`
  - Expected: 신규 서비스/endpoint 부재로 실패.
  - Result: `ModuleNotFoundError: No module named 'services.order_reconciliation_service'`로 실패 확인.

- [x] **Step 3: 최소 구현**
  - read-only reconciliation service를 만든다.
  - Admin endpoint `GET /api/v1/admin/trades/reconciliation`를 추가한다.
  - 자동 수정은 하지 않는다.
  - Result: `OrderReconciliationService`와 read-only Admin endpoint를 추가했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_order_reconciliation_service.py tests/api/test_admin_trade_routes.py -q`
  - Expected: PASS.
  - Result: 7 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-002/F-003/F-006/F-012.
  - Commit: `feat: add order reconciliation report`
  - Result: findings 갱신 완료. 커밋은 이 작업 검증 후 생성.

### Task 2.1a: stale DB-only pending cleanup 수동 액션 추가

**Files:**
- Create: `services/stale_pending_cleanup_service.py`
- Modify: `api/routes/admin.py`
- Test: `tests/services/test_stale_pending_cleanup_service.py`
- Test: `tests/api/test_admin_trade_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - 오래된 DB-only `PENDING_CONFIRM BUY`와 브로커 pending에 남은 활성 주문 fixture를 만든다.
  - 기본 `DRY_RUN`은 DB를 바꾸지 않고, `apply`는 stale DB-only BUY만 `CONFIRM_FAILED`로 변경해야 한다.
  - Result: service/API 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_stale_pending_cleanup_service.py tests/api/test_admin_trade_routes.py::test_admin_trade_reconciliation_cleanup_defaults_to_dry_run -q`
  - Expected: 신규 서비스/endpoint 부재로 실패.
  - Result: `ModuleNotFoundError: No module named 'services.stale_pending_cleanup_service'`로 실패 확인.

- [x] **Step 3: 최소 구현**
  - `StalePendingCleanupService`를 추가해 기존 reconciliation 결과의 `db_only_stale`만 사용한다.
  - Admin endpoint `POST /api/v1/admin/trades/reconciliation/cleanup`을 추가한다.
  - 기본값은 `DRY_RUN`이며, `?apply=true`일 때만 `CONFIRM_FAILED`로 변경한다.
  - SELL pending은 보유수량 대사가 필요하므로 자동 변경하지 않고 skip한다.
  - Result: 서비스와 관리자 수동 cleanup endpoint를 추가했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_order_reconciliation_service.py tests/services/test_stale_pending_cleanup_service.py tests/api/test_admin_trade_routes.py -q`
  - Expected: PASS.
  - Result: 10 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-003/F-006에 수동 cleanup과 자동 정리 보류 상태를 반영한다.
  - Commit: `feat: add stale pending cleanup action`
  - Result: findings에 수동 cleanup endpoint, DRY_RUN 기본값, SELL pending skip 정책을 반영했다. 커밋은 이 작업 검증 후 생성.

### Task 2.1b: Kiwoom 미체결 취소주문 매핑 구현

**Files:**
- Modify: `trading/kiwoom_clients.py`
- Modify: `trading/adapters/kiwoom_adapter.py`
- Modify: `trading/adapters/base.py`
- Test: `tests/trading/test_kiwoom_clients.py`
- Test: `tests/trading/test_kiwoom_adapter.py`
- Test: `tests/trading/test_kiwoom_constraints.py`

- [x] **Step 1: 실패 테스트 작성**
  - `KiwoomOrderExecutor.cancel()`이 `kt10003`으로 `dmst_stex_tp`, `orig_ord_no`, `stk_cd`, `cncl_qty`를 보내는지 테스트한다.
  - `KiwoomBrokerAdapter.cancel_order()`가 미체결 목록에서 종목코드/잔량을 찾아 executor에 넘기는지 테스트한다.
  - 미체결 주문이 없으면 취소주문을 보내지 않고 실패하는지 테스트한다.
  - Result: Kiwoom 취소주문 테스트 3개를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/trading/test_kiwoom_clients.py::test_kiwoom_order_executor_cancels_order_with_original_order_mapping tests/trading/test_kiwoom_adapter.py::test_kiwoom_adapter_cancels_order_with_pending_order_context tests/trading/test_kiwoom_constraints.py::test_kiwoom_adapter_cancel_order_reports_missing_pending_order -q`
  - Expected: executor가 `symbol`을 받지 못하고 adapter가 미체결 컨텍스트 없이 취소를 호출해 실패.
  - Result: 3개 테스트 모두 실패 확인.

- [x] **Step 3: 최소 구현**
  - `OrderExecutorProtocol.cancel()`에 선택 인자 `symbol`, `quantity`를 추가한다.
  - `KiwoomBrokerAdapter.cancel_order()`는 현재 미체결 주문을 조회해 대상 주문의 종목/잔량을 확인한 뒤 취소 executor로 전달한다.
  - `KiwoomOrderExecutor.cancel()`은 `kt10003` + `/api/dostk/ordr`로 취소주문을 보낸다.
  - `supports_order_cancellation=True`로 capability를 실제 구현과 맞춘다.
  - Result: Kiwoom 미체결 취소주문 매핑을 구현했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/trading/test_kiwoom_clients.py tests/trading/test_kiwoom_adapter.py tests/trading/test_kiwoom_constraints.py tests/services/test_manual_trade_service.py tests/api/test_admin_account_routes.py -q`
  - Expected: PASS.
  - Result: 49 passed.

- [x] **Step 5: 문서/커밋**
  - 운영 적용 전 실제 취소 실행은 서버 재시작 후 사용자 확인을 거쳐 별도 수행한다.
  - Commit: `feat: implement kiwoom cancel order`
  - Result: 공식 Kiwoom REST 가이드의 `kt10003` 취소주문 TR과 생성 스펙의 payload 필드 계약을 기준으로 문서화했다.

### Task 2.2: cycle-local cash reservation ledger

**Files:**
- Create: `agent/order_reservation.py`
- Modify: `agent/trading_agent.py`
- Test: `tests/agent/test_order_reservation.py`
- Test: `tests/agent/test_trading_agent_risk_reservation.py`

- [x] **Step 1: 실패 테스트 작성**
  - 두 BUY 후보가 같은 cash snapshot을 동시에 통과하려는 fixture를 만든다.
  - 첫 후보가 70% 현금을 reserve하면 두 번째 후보는 남은 현금 기준으로 차단되는지 테스트한다.
  - Result: `tests/agent/test_order_reservation.py`와 `tests/agent/test_trading_agent_risk_reservation.py`에 cycle-local 현금 예약 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent/test_order_reservation.py tests/agent/test_trading_agent_risk_reservation.py -q`
  - Expected: reservation 부재로 두 후보가 모두 통과.
  - Result: `ModuleNotFoundError: No module named 'agent.order_reservation'`로 실패 확인.

- [x] **Step 3: 최소 구현**
  - cycle 단위 `OrderReservationLedger`를 추가한다.
  - 주문 접수 성공/실패/skip에서 reservation 상태를 명확히 해제하거나 확정한다.
  - 처음 rollout은 `ORDER_RESERVATION_ENFORCEMENT=shadow`로 mismatch 로그만 남긴다.
  - Result: `OrderReservationLedger`를 추가하고 TradingAgent BUY 직전 예약을 연결했다. 기본값은 `SHADOW`, 명시적으로 `ENFORCE`일 때만 cycle 현금 부족 BUY를 차단한다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent/test_order_reservation.py tests/agent/test_trading_agent_risk_reservation.py -q`
  - Expected: PASS.
  - Result: 3 passed.

- [x] **Step 5: 관련 회귀/커밋**
  - Run: `./.venv313/bin/python -m pytest tests/agent tests/strategy tests/trading -q`
  - Commit: `feat: add cycle cash reservation ledger`
  - Result: 134 passed. 커밋은 이 작업 검증 후 생성.

### Task 2.3: liquidation retry 기록 누락 수정

**Files:**
- Modify: `scheduler/scheduler.py`
- Test: `tests/scheduler/test_scheduler_force_liquidation.py`

- [x] **Step 1: 실패 테스트 작성**
  - 첫 매도 실패, retry 성공 fake adapter fixture에서 `decision_maker.confirm_and_record`가 retry 성공에도 1회 호출되는지 테스트한다.
  - Result: 기존 `tests/scheduler/test_scheduler_runtime_paths.py::test_force_liquidation_retries_failed_orders_once`에 retry success 기록 기대값을 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/scheduler/test_scheduler_force_liquidation.py -q`
  - Expected: retry success 기록 누락으로 실패.
  - Result: `confirmed_orders == []`로 실패 확인. 실제 테스트 파일은 기존 구조상 `tests/scheduler/test_scheduler_runtime_paths.py`를 사용했다.

- [x] **Step 3: 최소 구현**
  - `_record_liquidation_sell()` helper를 만들고 1차 성공/재시도 성공이 같은 기록 경로를 쓰게 한다.
  - `order_id`가 없으면 기록하지 않고 error log를 남긴다.
  - Result: `_record_liquidation_sell()`를 추가하고 1차 성공/재시도 성공 모두 같은 기록 경로를 사용하게 했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/scheduler/test_scheduler_force_liquidation.py tests/scheduler/test_scheduler_runtime_paths.py -q`
  - Expected: PASS.
  - Result: `tests/scheduler/test_scheduler_runtime_paths.py` 63 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-032.
  - Commit: `fix: record successful liquidation retries`
  - Result: F-032 갱신 완료. 커밋은 이 작업 검증 후 생성.

## Track 3: PnL Truth and Kill Switch

### Task 3.1: canonical account PnL summary 서비스

**Files:**
- Create: `services/pnl_truth_service.py`
- Modify: `services/performance_reporting_service.py`
- Modify: `api/routes/admin.py`
- Test: `tests/services/test_pnl_truth_service.py`
- Test: `tests/services/test_performance_reporting_service.py`

- [x] **Step 1: 실패 테스트 작성**
  - closed BUY 0건, open DB lot stale, account equity snapshot 존재 fixture를 만든다.
  - 결과가 `realized_trade_pnl`, `unrealized_broker_pnl`, `total_asset_delta`, `sample_status=INSUFFICIENT_CLOSED_TRADE_SAMPLE`로 분리되는지 테스트한다.
  - Result: `tests/services/test_pnl_truth_service.py`와 `tests/services/test_performance_reporting_service.py`에 canonical PnL 분리와 metric contract 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_pnl_truth_service.py tests/services/test_performance_reporting_service.py -q`
  - Expected: 신규 canonical summary 부재로 실패.
  - Result: `ModuleNotFoundError: No module named 'services.pnl_truth_service'`로 실패 확인. 추가로 `metric_contract` 부재 실패도 확인했다.

- [x] **Step 3: 최소 구현**
  - PnL truth service를 추가해 closed trade, broker/account snapshot, daily baseline을 분리 계산한다.
  - 기존 performance report에는 새 필드를 추가하고 기존 필드는 deprecated 표시만 한다.
  - Result: `PnlTruthService`를 추가하고 performance summary에 `pnl_truth`와 `metric_contract`를 연결했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_pnl_truth_service.py tests/services/test_performance_reporting_service.py -q`
  - Expected: PASS.
  - Result: 13 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-004/F-013/F-014/F-015.
  - Commit: `feat: add canonical pnl truth summary`
  - Result: findings 갱신 완료. 커밋은 이 작업 검증 후 생성.

### Task 3.1a: AI risk tuner absolute hard cap 추가

**Files:**
- Modify: `core/config.py`
- Modify: `strategy/ai_risk_tuner.py`
- Modify: `analysis/llm/prompts/risk_tuning.py`
- Test: `tests/strategy/test_cash_ratio_units.py`

- [x] **Step 1: 실패 테스트 작성**
  - LLM이 과도한 `max_daily_trades`, `max_single_order_krw`, `max_position_pct`를 반환해도 절대 상한으로 내려가는 fixture를 만든다.
  - `0 = 무제한` 입력도 절대 상한이 있으면 상한값으로 대체되는지 테스트한다.
  - Result: `tests/strategy/test_cash_ratio_units.py`에 hard cap 테스트 2개를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy/test_cash_ratio_units.py::test_ai_risk_tuner_applies_absolute_hard_caps tests/strategy/test_cash_ratio_units.py::test_ai_risk_tuner_replaces_unlimited_values_with_absolute_caps -q`
  - Expected: 절대 상한 설정/로직 부재로 실패.
  - Result: `Settings`에 `ABS_MAX_DAILY_TRADES`가 없어 실패 확인.

- [x] **Step 3: 최소 구현**
  - `ABS_MAX_DAILY_TRADES`, `ABS_MAX_SINGLE_ORDER_KRW`, `ABS_MAX_POSITION_PCT` 설정을 추가한다.
  - `_clamp_limits()`와 `_default_limits()`에 절대 상한을 적용한다.
  - LLM 프롬프트에 시스템 절대 상한과 적용 의미를 명시한다.
  - Result: 기본값은 일일 8회, 단일 주문 50,000,000원, 단일 포지션 15%로 설정했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy -q`
  - Expected: PASS.
  - Result: 12 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-008.
  - Commit: `feat: cap ai risk tuner limits`
  - Result: F-008을 `해결됨`으로 갱신했다. 커밋은 이 작업 검증 후 생성.

### Task 3.2: account equity 기반 drawdown guard

**Files:**
- Modify: `strategy/trading_guard.py`
- Modify: `core/config.py`
- Modify: `core/runtime_settings.py`
- Test: `tests/strategy/test_trading_guard.py`
- Test: `tests/services/test_account_equity_service.py`
- Test: `tests/api/test_admin_settings_routes.py`
- Test: `tests/api/test_admin_settings_validation.py`

- [x] **Step 1: 실패 테스트 작성**
  - closed trade PnL은 0이지만 account equity delta가 일중 -3%인 fixture에서 BUY가 차단되는지 테스트한다.
  - 첫 rollout은 `ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE=report_only`에서 차단하지 않고 warning만 반환하는 테스트도 추가한다.
  - Result: `TradingGuard` 단위 테스트에 report-only warning, kill-switch 차단, 실제 snapshot 기반 drawdown 계산 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/services/test_account_equity_service.py -q`
  - Expected: closed trade only 계산 때문에 실패.
  - Result: `_get_account_equity_drawdown` 부재로 신규 테스트 2건 실패를 확인했다.

- [x] **Step 3: 최소 구현**
  - `TradingGuard`에 account equity drawdown input을 받는 별도 method를 추가한다.
  - `report_only|block_buy|kill_switch` mode를 runtime setting으로 둔다.
  - Result: `ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE=OFF|REPORT_ONLY|BLOCK_BUY|KILL_SWITCH`를 추가했다. `TradingGuard`는 `PnlTruthService`의 baseline/latest snapshot summary를 읽어 총자산 drawdown을 계산한다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy/test_trading_guard.py tests/services/test_account_equity_service.py -q`
  - Expected: PASS.
  - Result: 관련 설정 API 테스트 포함 `36 passed`.

- [x] **Step 5: 문서/커밋**
  - Update: F-009/F-014.
  - Commit: `feat: add account equity drawdown guard`
  - Result: findings와 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

## Track 4: Scheduler Liquidation and Realtime Safety

### Task 4.1: smart liquidation data failure action 분리

**Files:**
- Modify: `scheduler/scheduler.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`

- [x] **Step 1: 실패 테스트 작성**
  - quote failure 또는 open BUY missing fixture에서 해당 종목이 즉시 `to_sell`에 들어가지 않는지 테스트한다.
  - 기본값은 자동 SELL이 아니라 `REVIEW_REQUIRED`/HOLD로 검증한다.
  - Result: 현재가 조회 실패, open BUY `TradeResult` 없음, repository 예외, 수집 결과 없음 path의 회귀 테스트를 추가/수정했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py::test_smart_liquidation_holds_for_review_when_no_holdings_data tests/scheduler/test_scheduler_runtime_paths.py::test_collect_holdings_data_marks_symbol_for_review_when_price_lookup_fails tests/scheduler/test_scheduler_runtime_paths.py::test_collect_holdings_data_marks_symbol_for_review_when_trade_result_is_missing tests/scheduler/test_scheduler_runtime_paths.py::test_collect_holdings_data_marks_symbol_for_review_on_repository_error -q`
  - Expected: 현재는 fallback sell이라 실패.
  - Result: 기존 구현은 데이터 실패 종목을 `to_sell`로 보내 실패했다.

- [x] **Step 3: 최소 구현**
  - `_collect_holdings_data()`가 데이터 실패를 `fallback_sell`이 아니라 `review_required`로 반환하게 한다.
  - `_smart_liquidation()`과 장중 보유 재평가는 `review_required` 종목을 HOLD로 유지하고 운영 로그에 남긴다.
  - alert에는 symbol, reason, missing data type을 남긴다.
  - Result: 즉시 SELL 모드를 추가하지 않고 안전 기본값을 코드 기본 동작으로 고정했다. 설정 기반 SELL rollback은 의도치 않은 청산 위험을 되살리므로 이번 구현 범위에서 제외했다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q`
  - Expected: PASS.
  - Result: 63 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-033.
  - Commit: `fix: avoid selling on smart liquidation data failure`
  - Result: F-033과 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

### Task 4.2: realtime subscription priority와 fallback watchlist

**Files:**
- Modify: `realtime/stream_manager.py`
- Modify: `realtime/monitor.py`
- Modify: `api/routes/admin.py`
- Test: `tests/realtime/test_stream_manager.py`
- Test: `tests/realtime/test_monitor.py`
- Test: `tests/api/test_admin_observability_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - 42개 이상 symbol에서 held position이 new candidate보다 우선 구독되는지 테스트한다.
  - 구독되지 못한 종목이 polling fallback watchlist에 포함되는지 테스트한다.
  - Result: `tests/realtime/test_stream_manager.py`, `tests/realtime/test_monitor.py`, `tests/api/test_admin_observability_routes.py`에 우선순위/fallback/운영 노출 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/realtime/test_stream_manager.py tests/realtime/test_monitor.py tests/api/test_admin_observability_routes.py -q`
  - Expected: 우선순위/폴백 부재로 실패.
  - Result: `SubscriptionPriority`/fallback 상태와 Admin realtime payload 부재로 실패 확인.

- [x] **Step 3: 최소 구현**
  - priority enum을 `HELD_POSITION > PENDING_ORDER > ACTIVE_THRESHOLD > NEW_CANDIDATE`로 둔다.
  - 한도 초과 시 낮은 priority를 skip하고 watchlist에 넣는다.
  - Admin observability status에 skipped subscription count를 노출한다.
  - Result: `SubscriptionRequest`/`SubscriptionPriority`를 추가하고, scheduler는 보유종목을 `HELD_POSITION`, 신규 후보를 `NEW_CANDIDATE`로 넘긴다. `RealtimeMonitor`는 stream 한도에서 밀린 종목을 polling fallback으로 조회한다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv/bin/python -m pytest tests/realtime/test_stream_manager.py tests/realtime/test_monitor.py tests/api/test_admin_observability_routes.py -q`
  - Expected: PASS.
  - Result: 관련 realtime/API 테스트 묶음 16 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-036.
  - Commit: `feat: prioritize realtime subscriptions`
  - Result: F-036과 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

## Track 5: Observability and Admin Safety

### Task 5.1: observability maintenance NULL provider/model 수정

**Files:**
- Modify: `services/observability_maintenance_service.py`
- Modify: `services/system_preflight_service.py`
- Test: `tests/services/test_observability_maintenance_service.py`
- Test: `tests/api/test_admin_system_preflight_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - provider/model이 NULL인 error metric과 문자열 provider/model success metric이 섞인 fixture를 만든다.
  - maintenance가 rollup을 생성하고 preflight가 최근 maintenance 실패를 WARN으로 노출하는지 테스트한다.
  - Result: `tests/services/test_observability_maintenance_service.py`와 `tests/services/test_system_preflight_service.py`에 회귀 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/services/test_observability_maintenance_service.py::test_observability_maintenance_service_normalizes_missing_provider_model tests/services/test_system_preflight_service.py::test_system_preflight_service_warns_on_recent_observability_maintenance_failure -q`
  - Expected: tuple sort 실패 또는 preflight 미노출로 실패.
  - Result: tuple sort TypeError와 preflight OK 오판 실패를 확인했다.

- [x] **Step 3: 최소 구현**
  - rollup key에서 provider/model을 `UNKNOWN`으로 normalize한다.
  - maintenance failure summary를 preflight에 추가한다.
  - Result: rollup dimension 정규화 helper를 추가하고, 최근 `JOB/OBSERVABILITY_MAINTENANCE` 실패를 preflight `observability` WARN으로 노출했다. 실행 기록 없음은 새 DB 호환을 위해 OK 정보성 상태로 둔다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv/bin/python -m pytest tests/services/test_observability_maintenance_service.py tests/services/test_system_preflight_service.py tests/api/test_admin_system_preflight_routes.py -q`
  - Expected: PASS.
  - Result: 6 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-035.
  - Commit: `fix: harden observability maintenance rollups`
  - Result: F-035와 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

### Task 5.2: Admin dangerous action confirmation

**Files:**
- Create: `services/admin_action_confirmation_service.py`
- Modify: `api/routes/admin.py`
- Test: `tests/services/test_admin_action_confirmation_service.py`
- Test: `tests/api/test_admin_account_routes.py`
- Test: `tests/api/test_admin_trade_routes.py`

- [x] **Step 1: 실패 테스트 작성**
  - confirmation token 없이 reset/sell/cancel-and-sell 요청 시 `428 Precondition Required` 또는 `409 Conflict`가 반환되는지 테스트한다.
  - confirmation token은 action type, symbol/order_id, quantity, TTL, nonce에 묶여야 한다.
  - Result: confirmation service 단위 테스트와 reset/sell/cancel-and-sell/cleanup apply API 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/services/test_admin_action_confirmation_service.py tests/api/test_admin_account_routes.py::test_admin_manual_sell_route_requires_confirmation_when_enabled tests/api/test_admin_account_routes.py::test_admin_manual_sell_route_accepts_confirmation_token_when_enabled tests/api/test_admin_account_routes.py::test_admin_pending_sell_replace_route_requires_confirmation_when_enabled tests/api/test_admin_trade_routes.py::test_admin_trade_reconciliation_cleanup_apply_requires_confirmation_when_enabled tests/api/test_admin_trade_routes.py::test_admin_reset_operational_baseline_requires_confirmation_when_enabled -q`
  - Expected: 현재 route가 바로 실행되어 실패.
  - Result: 신규 service/endpoint 부재로 실패 확인.

- [x] **Step 3: 최소 구현**
  - `POST /api/v1/admin/actions/confirmations`로 challenge를 생성한다.
  - 위험 endpoint는 `confirmation_token`을 요구한다.
  - 기본 rollout은 `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false` compatibility flag로 시작하고, 테스트에서는 true로 검증한다.
  - Result: HMAC 서명 token을 action/resource/quantity/TTL/nonce에 묶고, token 재사용을 차단했다. reset, manual sell, cancel-buy, cancel-and-sell, cleanup apply에 적용했다.

- [x] **Step 4: 호환성 확인**
  - 기본값 `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false`에서는 기존 Admin UI 호출이 그대로 동작한다.
  - UI confirmation flow는 플래그를 true로 전환하기 전 별도 후속 작업으로 둔다.

- [x] **Step 5: 전체 통과/커밋**
  - Run: `./.venv/bin/python -m pytest tests/api/test_admin_account_routes.py tests/api/test_admin_trade_routes.py tests/services/test_admin_action_confirmation_service.py -q`
  - Result: 25 passed. Settings route/validation 회귀 27 passed.
  - Commit: `feat: require confirmation for dangerous admin actions`
  - Result: F-034와 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

## Track 6: Decision Event and Forward Return Dataset

### Task 6.1: canonical decision event table/service

**Files:**
- Create: `models/decision_event.py`
- Create: `repositories/decision_event_repository.py`
- Create: `services/decision_event_service.py`
- Add: `alembic/versions/<revision>_add_decision_events.py`
- Modify: `agent/decision_maker.py`
- Test: `tests/services/test_decision_event_service.py`
- Test: `tests/agent/test_decision_maker.py`

- [x] **Step 1: 실패 테스트 작성**
  - 후보 symbol별 scanner score, Tier1/Tier2 decision, risk gate result, final action이 하나의 decision event로 저장되는지 테스트한다.
  - LLM provider/model/latency/status가 함께 저장되는지 테스트한다.
  - Result: canonical event 저장/정규화 service 테스트와 order gate blocked path에서 decision event가 기록되는 DecisionMaker 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/services/test_decision_event_service.py tests/agent/test_decision_maker.py::test_decision_maker_records_decision_event_when_order_submission_is_blocked -q`
  - Expected: 모델/서비스 부재로 실패.
  - Result: `models.decision_event` 부재로 실패 확인.

- [x] **Step 3: 최소 구현**
  - append-only decision event 저장 경로를 추가한다.
  - 거래 실행에는 연결하지 않고 write-only 관측으로 시작한다.
  - Result: `decision_events` 모델, repository, service, Alembic revision을 추가했다. `DecisionMaker`의 order validation/gate/submission/recommendation path에서 best-effort write-only event를 남긴다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv/bin/python -m pytest tests/agent/test_decision_maker.py tests/services/test_decision_event_service.py -q`
  - Expected: PASS.
  - Result: 38 passed.

- [x] **Step 5: 문서/커밋**
  - Update: F-016/F-019/F-026.
  - Commit: `feat: record canonical decision events`
  - Result: F-016/F-019/F-026과 고도화 현황 문서를 갱신했다. 커밋은 이 작업 검증 후 생성.

### Task 6.2: forward return labeling job

**Files:**
- Create: `scheduler/jobs/forward_return_label_job.py`
- Create: `models/decision_forward_return.py`
- Create: `repositories/decision_forward_return_repository.py`
- Create: `services/decision_forward_return_service.py`
- Add: `alembic/versions/<revision>_add_decision_forward_returns_table.py`
- Modify: `scheduler/scheduler.py`
- Modify: `core/config.py`
- Test: `tests/scheduler/test_forward_return_label_job.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`

- [x] **Step 1: 실패 테스트 작성**
  - decision event 이후 5m/15m/30m/close 가격이 들어왔을 때 forward return labels가 채워지는지 테스트한다.
  - 가격 데이터가 없으면 `label_status=WAITING_DATA`로 남는지 테스트한다.
  - Result: intraday snapshot, daily close, missing data WAITING_DATA 테스트를 추가했다.

- [x] **Step 2: 실패 확인**
  - Run: `./.venv/bin/python -m pytest tests/scheduler/test_forward_return_label_job.py -q`
  - Expected: labeling job 부재로 실패.
  - Result: `models.decision_forward_return` 부재로 실패 확인.

- [x] **Step 3: 최소 구현**
  - scheduler interval job으로 labels를 backfill한다.
  - BUY/HOLD/SKIP별 counterfactual return을 모두 저장한다.
  - Result: `decision_forward_returns` 테이블, service, scheduler interval job, observability job metric을 추가했다. 현재 intraday label은 사용 가능한 최신 `market_snapshots`의 `updated_at`이 target 이후일 때 라벨링하고, close label은 `market_data_daily.close`를 사용한다.

- [x] **Step 4: 통과 확인**
  - Run: `./.venv/bin/python -m pytest tests/scheduler/test_forward_return_label_job.py tests/scheduler/test_scheduler_runtime_paths.py::test_scheduler_forward_return_label_records_success_metric tests/scheduler/test_scheduler_runtime_paths.py::test_scheduler_forward_return_label_records_error_metric -q`
  - Expected: PASS.
  - Result: 부분 검증 8 passed. 전체 관련 테스트는 커밋 전 재실행한다.

- [x] **Step 5: 문서/커밋**
  - Update: F-016/F-019.
  - Commit: `feat: label decision forward returns`
  - Result: F-016/F-019/F-026과 고도화 현황 문서를 갱신했다. 커밋은 최종 검증 후 생성.

## Track 7: Backtest Hygiene

### Task 7.1: execution timing과 look-ahead 제거

**Files:**
- Modify: `backtesting/engine.py`
- Modify: `backtesting/report.py`
- Test: `tests/backtesting/test_engine_execution_model.py`

- [ ] **Step 1: 실패 테스트 작성**
  - i봉 close로 생긴 신호가 i봉 close에 즉시 체결되지 않고 i+1 open 또는 설정된 execution policy로 체결되는지 테스트한다.

- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/backtesting/test_engine_execution_model.py -q`
  - Expected: 현재 same-close 체결로 실패.

- [ ] **Step 3: 최소 구현**
  - `execution_timing=NEXT_OPEN|NEXT_CLOSE|LEGACY_SAME_CLOSE`를 추가한다.
  - 기본값은 `NEXT_OPEN`으로 두고 legacy는 명시 옵션으로만 사용한다.

- [ ] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/backtesting/test_engine_execution_model.py tests/backtesting/test_data_loader.py -q`
  - Expected: PASS.

- [ ] **Step 5: 커밋**
  - Commit: `fix: remove default same-bar backtest execution`

### Task 7.2: fee/fill/report metadata 분리

**Files:**
- Create: `backtesting/fill_models.py`
- Create: `backtesting/fee_models.py`
- Modify: `backtesting/engine.py`
- Modify: `backtesting/report.py`
- Test: `tests/backtesting/test_fill_models.py`
- Test: `tests/backtesting/test_fee_models.py`
- Test: `tests/backtesting/test_report_metadata.py`

- [ ] **Step 1: 실패 테스트 작성**
  - KRX fee/tax, slippage, partial fill, 상하한가/거래정지 guard fixture를 만든다.
  - report에 `model_family`, `execution_policy`, `fee_model`, `fill_model`이 표시되는지 테스트한다.

- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/backtesting/test_fill_models.py tests/backtesting/test_fee_models.py tests/backtesting/test_report_metadata.py -q`
  - Expected: 모델/metadata 부재로 실패.

- [ ] **Step 3: 최소 구현**
  - `KoreaStockFeeModel`, `NextBarOHLCFillModel`, `LimitGuardFillModel`을 추가한다.
  - backtest가 live LLM pipeline이 아니라 `RULE_BASED_TECHNICAL_PROXY`임을 report에 표시한다.

- [ ] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/backtesting -q`
  - Expected: PASS.

- [ ] **Step 5: 문서/커밋**
  - Update: F-021~F-025.
  - Commit: `feat: add explicit backtest fill and fee models`

## Track 8: LLM and News Simplification

### Task 8.1: LLM cooldown incident dedupe

**Files:**
- Modify: `analysis/llm/llm_factory.py`
- Modify: `analysis/llm/codex_provider.py`
- Modify: `services/error_incident_service.py`
- Test: `tests/analysis/test_llm_factory.py`
- Test: `tests/services/test_error_incident_service.py`

- [ ] **Step 1: 실패 테스트 작성**
  - Codex timeout 후 cooldown 중 10개 후보가 들어와도 incident는 cooldown window당 1건만 생성되는지 테스트한다.

- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/analysis/test_llm_factory.py tests/services/test_error_incident_service.py -q`
  - Expected: incident 증폭으로 실패.

- [ ] **Step 3: 최소 구현**
  - provider health/circuit-open event와 per-call failure를 분리한다.
  - cooldown 중에는 동일 provider/model/root cause incident를 dedupe한다.

- [ ] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/analysis/test_llm_factory.py tests/services/test_error_incident_service.py -q`
  - Expected: PASS.

- [ ] **Step 5: 문서/커밋**
  - Update: F-007/F-027.
  - Commit: `fix: dedupe llm cooldown incidents`

### Task 8.2: 뉴스는 shadow/report-only rollout으로 고정

**Files:**
- Modify: `services/news_runtime_service.py`
- Modify: `services/news_signal_service.py`
- Modify: `services/news_reporting_service.py`
- Modify: `api/routes/admin.py`
- Modify: `admin/static/js/settings_action_state.js`
- Modify: `admin/static/js/settings_form_state.js`
- Test: `tests/services/test_news_runtime_service.py`
- Test: `tests/services/test_news_signal_service.py`
- Test: `tests/services/test_news_reporting_service.py`
- Test: `tests/frontend/test_settings_action_state.test.js`

- [ ] **Step 1: 실패 테스트 작성**
  - sample size가 부족하면 `NEWS_GATE_ENABLED=true` 적용 요청이 거부되거나 warning required 상태가 되는지 테스트한다.
  - fetch concurrency와 translation concurrency 설명/분류가 분리되어 반환되는지 테스트한다.

- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_news_runtime_service.py tests/services/test_news_signal_service.py tests/services/test_news_reporting_service.py -q`
  - Expected: rollout gate/report 부재로 실패.

- [ ] **Step 3: 최소 구현**
  - news mode를 `OFF|POLL_ONLY|SHADOW_ONLY|SEMI_AUTO_GATE_RECOMMENDATION|BUY_BLOCK_GATE`로 정의한다.
  - 기본값은 현재처럼 OFF.
  - BUY_BLOCK_GATE는 forward return 표본과 source report 조건을 통과해야만 허용한다.

- [ ] **Step 4: UI 테스트**
  - Run: `pnpm vitest run tests/frontend/test_settings_action_state.test.js`
  - Expected: PASS.

- [ ] **Step 5: 문서/커밋**
  - Update: F-028/F-029/F-030.
  - Commit: `feat: constrain news rollout modes`

## Track 9: Strategy Taxonomy and Cleanup

### Task 9.1: strategy profile와 alpha source 명명 분리

**Files:**
- Modify: `strategy/stable_short.py`
- Modify: `strategy/aggressive_short.py`
- Modify: `strategy/base.py`
- Modify: `agent/trading_agent.py`
- Modify: `analysis/llm/prompts/`
- Test: `tests/strategy/test_strategy_profiles.py`
- Test: `tests/agent/test_trading_agent_market_data.py`

- [ ] **Step 1: 실패 테스트 작성**
  - `STABLE_SHORT`/`AGGRESSIVE_SHORT`가 alpha strategy가 아니라 execution/risk profile로 report되는지 테스트한다.

- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy/test_strategy_profiles.py tests/agent/test_trading_agent_market_data.py -q`
  - Expected: 현재 명명 혼합으로 실패.

- [ ] **Step 3: 최소 구현**
  - `alpha_source`, `execution_profile`, `risk_profile` 필드를 분리한다.
  - legacy `StockScreener` 사용 여부를 명시하고, 미사용이면 deprecated 표시한다.

- [ ] **Step 4: 통과 확인**
  - Run: `./.venv313/bin/python -m pytest tests/strategy/test_strategy_profiles.py tests/agent/test_trading_agent_market_data.py -q`
  - Expected: PASS.

- [ ] **Step 5: 문서/커밋**
  - Update: F-017/F-018/F-020.
  - Commit: `refactor: separate alpha source and execution profile`

## 최종 검증 게이트

- [ ] Backend targeted tests
  - Run: `./.venv313/bin/python -m pytest tests/agent tests/trading tests/strategy tests/services tests/scheduler tests/realtime tests/backtesting -q`
- [ ] API/Admin targeted tests
  - Run: `./.venv313/bin/python -m pytest tests/api -q`
- [ ] Frontend state tests
  - Run: `pnpm vitest run tests/frontend/test_event_radar_state.test.js tests/frontend/test_performance_page_state.test.js tests/frontend/test_manual_trade_action_state.test.js tests/frontend/test_observability_state.test.js tests/frontend/test_settings_action_state.test.js`
- [ ] Full backend suite
  - Run: `./.venv313/bin/python -m pytest -q`
- [ ] Git safety
  - Run: `git status --short --untracked-files=all`

## 승인 전 중단점

이 문서는 구현 계획입니다. 다음 조건 전에는 코드/설정/전략 파라미터를 바꾸지 않습니다.

- [ ] 사용자가 Track 1~5를 먼저 진행하는 우선순위에 승인했다.
- [ ] 사용자가 implementation mode를 선택했다: subagent-driven 또는 inline execution.
- [ ] live trading 운영 모드가 확인됐다: 권장값은 `ORDER_SUBMISSION_MODE=READ_ONLY` 또는 최소 `SELL_ONLY`.
- [ ] 각 Task별 첫 커밋 전 현재 runtime order state를 다시 확인한다.
