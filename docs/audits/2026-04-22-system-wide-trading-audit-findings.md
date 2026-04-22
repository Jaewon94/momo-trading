# MOMO Trading 전체 시스템 감사 Findings

> 상태: Phase 0 기준선 문서입니다. 아직 실제 findings는 확정하지 않았습니다. 각 항목은 evidence가 확보된 뒤 P0-P3로 분류합니다.

## 심각도 기준

- `P0 Blocking`: 통제되지 않은 노출, 중복 주문, 거짓 손익, 위험한 운영 상태를 만들 수 있음
- `P1 Major`: 리스크 제어, 체결 품질, 성과 측정에 실질적 악영향
- `P2 Minor`: 비효율적이거나 시끄럽지만 즉시 위험하지는 않음
- `P3 Polish`: 편의성/정리 수준

## 분류 기준

- `제거`: 가치가 없고 의존성이 낮거나 위험/혼란만 만드는 기능
- `기본 비활성화`: 가능성은 있지만 안정성/가치가 증명되지 않은 기능
- `유지하되 harden`: 유용하지만 안전장치, 테스트, 관측성이 부족한 기능
- `실험`: A/B, shadow mode, forward return 분석이 필요한 기능

## Finding 템플릿

### F-000: 제목

- 심각도: `P?`
- 상태: `초안 | 검증 중 | 확정 | 해결됨`
- 영역: `주문 | 리스크 | PnL | 전략 | 백테스트 | LLM | 뉴스 | 운영 | 보안 | Admin`
- 현상:
- 영향:
- 증거:
- 재현/검증:
- 권고:
- 구현 전 테스트:
- Rollout:
- Rollback:
- 분류: `제거 | 기본 비활성화 | 유지하되 harden | 실험`

## Phase 0 Findings

- Phase 0에서는 감사 운영 기준, 산출물 경로, 검증 방식만 확정했습니다.
- Phase 1 시작 중 감사 운영 기준과 실제 runtime 설정이 불일치하는 것을 발견했고, 안전 조치로 `AUTONOMY_MODE=SEMI_AUTO`를 적용했습니다. 상세는 F-001에 기록합니다.

## Findings

### F-001: 감사 중 runtime이 AUTONOMOUS 상태로 운영 중이었음

- 심각도: `P1`
- 상태: `완화됨`
- 영역: `운영 | 주문`
- 현상: 감사 운영 기준은 `read-only / semi-auto`였지만, 실제 runtime은 `TRADING_ENABLED=true`, `AUTONOMY_MODE="AUTONOMOUS"`였습니다.
- 영향: 감사 중에도 자동 주문 경로가 계속 열려 있을 수 있어 증거 수집 중 상태가 변하고, 주문/PnL 분석이 흔들릴 수 있습니다.
- 증거: Admin settings API와 `runtime_settings`에서 `AUTONOMY_MODE="AUTONOMOUS"` 확인.
- 조치: `/api/v1/admin/settings/apply`로 `AUTONOMY_MODE="SEMI_AUTO"` 적용. 적용 결과 scheduler가 재시작되고 agent/scheduler idle이 확인됐습니다.
- 재검증: Admin settings API와 `runtime_settings`에서 `AUTONOMY_MODE="SEMI_AUTO"` 확인.
- 권고: 감사 기간에는 `SEMI_AUTO`를 유지하고, 자동 주문 재개는 findings/roadmap 승인 후 별도 체크리스트로 진행합니다.
- 구현 전 테스트: 해당 없음. 운영 설정 완화 조치입니다.
- Rollout: Admin settings apply 경로 사용.
- Rollback: 동일 경로로 `AUTONOMY_MODE="AUTONOMOUS"` 재적용 가능.
- 분류: `유지하되 harden`

### F-002: `orders` 테이블이 비어 있어 주문 source of truth가 불명확함

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `주문 | PnL | 운영`
- 현상: 운영 DB에서 `orders`는 0 rows인데 `trade_results`는 73 rows, `account_equity_snapshots`는 195 rows입니다.
- 영향: 주문 생명주기, 체결, 포지션, PnL이 어떤 테이블을 기준으로 대사되는지 불명확합니다. Admin/API/리포트가 서로 다른 source를 보면 성과 판단이 틀릴 수 있습니다.
- 증거: `data/app.db` read-only 쿼리 결과 `orders=0`, `trade_results=73`, `account_equity_snapshots=195`.
- 재현/검증: `sqlite3 -readonly data/app.db`로 row count 확인.
- 권고: Phase 2-4에서 canonical source of truth를 확정합니다. 최소한 `orders`, `trade_results`, 브로커 pending/fill, account snapshot의 책임을 문서화해야 합니다.
- 구현 전 테스트: `tests/services/test_performance_reporting_service.py`, `tests/agent/test_decision_maker.py`, `tests/scheduler/test_portfolio_sync_job.py`에 source mismatch 테스트 추가 후보.
- Rollout: 먼저 read-only report 추가, 이후 canonical PnL/service 분리.
- Rollback: report-only 변경은 제거 가능. 데이터 마이그레이션은 별도 백업 후 진행.
- 분류: `유지하되 harden`

### F-003: `PENDING_CONFIRM` BUY가 20건 존재하고 반복 종목이 있음

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `주문 | 리스크`
- 현상: Phase 1에서 `trade_results`에 `PENDING_CONFIRM BUY`가 20건 있었고, Phase 2 확인 시점에는 21건으로 늘었습니다. `KEC`, `GS글로벌`, `이브이첨단소재` 등 같은 종목 반복 pending이 보입니다.
- 영향: pending 상태가 실제 미체결인지, 체결 확인 누락인지, 중복 주문인지 판단되지 않으면 노출 계산과 신규 주문 차단이 틀릴 수 있습니다.
- 증거: `trade_results` 상태 집계와 pending 목록 read-only 쿼리. Phase 2 read-only 브로커 스냅샷에서 실제 미체결은 4건이지만 DB pending은 21건입니다.
- 재현/검증: Admin `/account/pending-orders`와 `sqlite3 -readonly data/app.db` pending 집계를 비교합니다.
- 권고: PENDING_CONFIRM stale detector를 먼저 report-only로 추가하고, 브로커 pending/holdings/DB pending을 하나의 reconciliation report로 노출해야 합니다.
- 구현 전 테스트: `tests/agent/test_decision_maker.py`, `tests/scheduler/test_portfolio_sync_job.py`에 stale/repeated pending reconciliation 테스트 추가 후보.
- Rollout: 먼저 report-only stale pending detector를 추가하고, 이후 자동 reconcile은 별도 승인.
- Rollback: detector는 제거 가능. 자동 reconcile은 DB 백업 후 진행해야 합니다.
- 분류: `유지하되 harden`

### F-004: confirmed trade PnL이 0으로 유지되어 실현손익 신뢰도가 낮음

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `PnL | 성과 측정`
- 현상: `CONFIRMED BUY 48`, `CONFIRMED SELL 5`의 `pnl_sum`이 모두 `0.0`입니다. 반면 account equity snapshot의 평가손익은 수백만 원 단위로 변합니다.
- 영향: 리포트가 닫힌 거래 손익만 보면 실제 계좌 상태를 설명하지 못할 수 있습니다. 전략 평가와 자동 튜닝이 잘못된 목표를 최적화할 위험이 있습니다.
- 증거: `trade_results` PnL 집계와 `account_equity_snapshots.total_unrealized_pnl` 최신 스냅샷.
- 재현/검증: Phase 4에서 realized/unrealized/cash/asset delta를 분리해서 대사합니다.
- 권고: canonical PnL 모델을 정의하고, 리포트는 realized, unrealized, total asset delta를 분리 표시해야 합니다.
- 구현 전 테스트: `tests/services/test_performance_reporting_service.py`, `tests/services/test_account_equity_service.py`.
- Rollout: report-only 분리 표시부터 시작.
- Rollback: 기존 리포트 계산으로 되돌릴 수 있게 feature flag 또는 별도 필드로 도입.
- 분류: `유지하되 harden`

### F-005: `SEMI_AUTO`가 모든 실주문을 막는 설정이 아님

- 심각도: `P1`
- 상태: `확정`
- 영역: `주문 | 운영 | 리스크`
- 현상: `SEMI_AUTO`는 `DecisionMaker.execute`의 신규 AI 시그널을 추천 생성으로 돌리지만, 보유 점검 매도, 강제청산, 장중 보유 재평가, 갭 체크 매도, 수동 매도는 `TRADING_ENABLED=true`이면 실제 주문을 낼 수 있습니다.
- 영향: “감사 중 자동 주문 차단”이라고 이해하면 위험합니다. 신규 매수는 막혀도 안전매도/청산성 주문은 계속 실행될 수 있고, 감사 중 DB 상태가 계속 변할 수 있습니다.
- 증거: `agent/decision_maker.py:49-60`, `scheduler/scheduler.py:813-852`, `scheduler/scheduler.py:1011-1044`, `scheduler/scheduler.py:1413-1427`, `scheduler/scheduler.py:1674-1696`, `services/manual_trade_service.py:101-166`.
- 재현/검증: `AUTONOMY_MODE=SEMI_AUTO`, `TRADING_ENABLED=true`에서 scheduler sell path는 `TRADING_ENABLED`만 확인합니다.
- 권고: Admin UI와 운영 문서에 `SEMI_AUTO=신규 AI 시그널 승인 필요`, `TRADING_ENABLED=실주문 master switch`를 분리 표기합니다. 감사/동결 모드가 필요하면 `AUDIT_READ_ONLY` 또는 `ORDER_SUBMISSION_MODE=READ_ONLY|SELL_ONLY|FULL`처럼 명시적 gate를 별도 설계합니다.
- 구현 전 테스트: `tests/scheduler/test_scheduler_runtime_paths.py`, `tests/services/test_manual_trade_service.py`에 `SEMI_AUTO` 상태에서 어떤 주문 경로가 허용/차단되는지 명시 테스트 추가.
- Rollout: 먼저 문구/상태 배지 수정, 이후 주문 gate 리팩터링은 별도 feature flag로 진행.
- Rollback: 문구 변경은 즉시 되돌릴 수 있고, gate 변경은 기존 `TRADING_ENABLED` 동작으로 fallback 가능해야 합니다.
- 분류: `유지하되 harden`

### F-006: 브로커 pending 4건 대비 DB pending 21건으로 대사 불일치가 큼

- 심각도: `P1`
- 상태: `확정`
- 영역: `주문 | 리스크 | PnL`
- 현상: read-only 브로커 미체결은 4건인데 `trade_results.PENDING_CONFIRM BUY`는 21건입니다. `001250`, `008350`처럼 DB pending은 있으나 브로커 pending에는 없는 종목이 있습니다.
- 영향: DB pending을 그대로 노출/차단/성과 계산에 사용하면 실제 미체결보다 훨씬 큰 노출로 보거나, 반대로 체결됐지만 확정되지 않은 수량을 open lot/PnL에 누락할 수 있습니다.
- 증거: Admin `/account/pending-orders` 4건, `sqlite3` pending 집계 21건. `131400` 주문 `0088558`은 브로커 partial fill 2,565주/잔량 935주인데 DB pending은 주문 수량 3,500주 상태입니다.
- 재현/검증: `curl -s /api/v1/admin/account/pending-orders`와 `select ... from trade_results where status='PENDING_CONFIRM'` 비교.
- 권고: reconciliation report를 추가해 `broker_pending`, `db_pending`, `holdings`, `open_confirmed_buys`를 종목/주문번호 기준으로 대사합니다. 자동 수정은 report와 테스트가 쌓인 뒤에만 적용합니다.
- 구현 전 테스트: `tests/scheduler/test_portfolio_sync_job.py`에 브로커 4건/DB 21건 fixture, partial fill fixture, broker book missing but holdings increased fixture 추가.
- Rollout: report-only endpoint/Admin 표시 먼저. 이후 복구 job은 dry-run summary -> 승인 실행 순서로 분리.
- Rollback: report-only는 제거 가능. 자동 DB 보정은 적용 전 DB 백업과 변경 로그가 필요합니다.
- 분류: `유지하되 harden`

### F-007: LLM Codex timeout incident가 계속 누적되어 장중 판단 품질과 운영 안정성이 흔들림

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `LLM | 운영`
- 현상: 최신 `error_incidents`에 `llm_factory/generate` Codex timeout과 temporary disable 메시지가 계속 누적됩니다.
- 영향: 장중 분석이 지연/실패하면서 fallback rule이나 불완전한 판단으로 넘어갈 수 있습니다. 매매 성능 분석 시 “전략 실패”와 “LLM runtime 실패”를 분리하지 않으면 원인 분석이 틀립니다.
- 증거: `error_incidents` 최신 행들에서 `CODEX 최근 호출 실패로 비활성화 (...s 남음): Codex CLI timeout (120s)`가 반복됩니다.
- 재현/검증: `sqlite3 -readonly data/app.db`로 최신 `error_incidents` 조회.
- 권고: Phase 7에서 LLM provider별 timeout, fallback, concurrency, cost/latency를 별도 평가합니다. 지금은 매매 성능 결론을 내릴 때 LLM runtime 실패를 confounder로 표시합니다.
- 구현 전 테스트: `tests/analysis/test_llm_factory.py`, `tests/services/test_llm_usage_service.py`에 provider cooldown/fallback observability 테스트 후보.
- Rollout: 관측성/리포트 분리부터 시작.
- Rollback: report-only 변경은 제거 가능.
- 분류: `유지하되 harden`

### F-008: AI risk tuner가 상한 없이 주문/포지션 한도를 완화할 수 있음

- 심각도: `P1`
- 상태: `확정`
- 영역: `리스크 | 자본 배분 | LLM`
- 현상: `AIRiskTuner._clamp_limits`는 최소값만 강제하고 상한선이 없습니다. `max_single_order_krw=0`은 무제한, `max_daily_trades=0`은 무제한, `max_position_pct`는 최소 5%만 있고 상한은 없습니다.
- 영향: LLM 또는 fallback 설정이 공격적으로 나오면 시스템 hard cap 없이 주문 금액/포지션 비중이 커질 수 있습니다. 이는 SEC/FINRA식 pre-trade credit/capital threshold 원칙과 맞지 않습니다.
- 증거: `strategy/ai_risk_tuner.py:112-131`, `core/config.py:144-146`, `.env`의 `MAX_SINGLE_ORDER_KRW=0`.
- 재현/검증: LLM risk tuning 결과가 큰 `max_single_order_krw`, `max_position_pct`를 반환해도 상한 clamp가 없습니다.
- 권고: LLM은 추천만 하게 두고, 시스템 hard cap은 별도 `ABS_MAX_SINGLE_ORDER_KRW`, `ABS_MAX_POSITION_PCT`, `ABS_MAX_DAILY_TRADES`로 항상 적용합니다.
- 구현 전 테스트: `tests/strategy/test_ai_risk_tuner.py` 또는 신규 테스트에 LLM이 과도한 한도를 반환해도 absolute cap으로 clamp되는 실패 테스트 추가.
- Rollout: 먼저 cap 설정과 로그만 추가하고, 기본 cap은 보수적으로 적용합니다.
- Rollback: cap 설정을 기존 0/무제한으로 되돌릴 수 있으나, 운영상 rollback은 별도 승인 필요.
- 분류: `유지하되 harden`

### F-009: kill switch가 실현손익만 보고 평가손실과 총자산 하락을 반영하지 않음

- 심각도: `P1`
- 상태: `확정`
- 영역: `리스크 | PnL`
- 현상: `TradingGuard`의 daily drawdown은 닫힌 BUY 거래의 `TradeResult.pnl`만 합산합니다. 열린 포지션 평가손익과 account equity delta는 반영하지 않습니다.
- 영향: 열린 포지션에서 큰 손실이 발생해도 청산 전에는 kill switch가 작동하지 않을 수 있습니다. 현재 DB의 confirmed PnL 신뢰도가 낮기 때문에 더 위험합니다.
- 증거: `strategy/trading_guard.py:16-79`, `strategy/trading_guard.py:59-79`, Phase 1/2의 `trade_results.pnl=0`, 최신 account equity snapshot의 평가손익 변동.
- 재현/검증: `account_equity_snapshots.total_unrealized_pnl`이 악화되어도 닫힌 BUY `pnl`이 0이면 daily drawdown은 0으로 계산됩니다.
- 권고: kill switch 입력을 `realized_pnl`, `unrealized_pnl`, `total_asset_delta`, `pending exposure`로 분리하고, 최소한 `account_equity_snapshots` 기준 intraday drawdown gate를 추가합니다.
- 구현 전 테스트: `tests/strategy/test_trading_guard.py`에 unrealized drawdown과 total asset drawdown이 BUY를 차단하는 실패 테스트 추가.
- Rollout: report-only 경고 -> BUY 차단 -> TRADING_ENABLED kill switch 순서로 단계 적용.
- Rollback: BUY 차단 gate만 feature flag로 끌 수 있게 분리.
- 분류: `유지하되 harden`

### F-010: `.env`와 runtime DB의 `TRADING_ENABLED`가 충돌해 운영자가 실주문 상태를 오판할 수 있음

- 심각도: `P1`
- 상태: `확정`
- 영역: `운영 | 리스크 | Admin`
- 현상: `.env`에는 `TRADING_ENABLED=false`가 설정되어 있지만 runtime DB/API는 `TRADING_ENABLED=true`입니다.
- 영향: 운영자가 파일 기준으로 “실주문 꺼짐”이라고 판단해도 실제 런타임은 주문 가능 상태일 수 있습니다. 특히 감사/장중 운영에서 위험합니다.
- 증거: `.env:78`, Admin settings API, `runtime_settings`의 `TRADING_ENABLED=true`.
- 재현/검증: `.env`와 `/api/v1/admin/settings` 비교.
- 권고: Admin에 “runtime override active” 배지를 표시하고, startup/evidence report에 config source priority를 명시합니다. 안전 모드에서는 `.env=false`와 runtime=true 충돌을 P1 경고로 띄웁니다.
- 구현 전 테스트: `tests/services/test_runtime_settings_service.py`, `tests/api/test_admin_settings_routes.py`에 source conflict 표시 테스트 후보.
- Rollout: read-only 설정 진단부터 추가.
- Rollback: 진단 표시 제거 가능.
- 분류: `유지하되 harden`

### F-011: 병렬 BUY 후보 간 현금 예약 ledger가 없어 주문 전 risk check가 같은 현금을 중복 사용할 수 있음

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `주문 | 리스크 | 자본 배분`
- 현상: 후보 종목 분석은 병렬로 수행되고 각 후보는 같은 cycle portfolio snapshot을 받아 risk check를 수행합니다. BUY 직전 buying power 재조회는 있지만, 주문 접수 후 체결/미체결 pending이 반영되기 전 다른 후보가 같은 현금을 기준으로 통과할 수 있습니다.
- 영향: 서로 다른 종목의 동시 BUY가 broker reject로 끝나거나, 의도보다 큰 주문 시도가 발생할 수 있습니다. 이는 중복 주문/과다 노출 방지 측면의 pre-trade control 공백입니다.
- 증거: `agent/trading_agent.py:295-344`, `agent/trading_agent.py:1075-1129`, `executed_count_ref`는 전달되지만 확인한 검색 범위에서 실제 cap 계산에 쓰이지 않습니다.
- 재현/검증: 여러 BUY 후보가 동시에 같은 `portfolio_cash`를 기준으로 risk check를 통과하는 fixture가 필요합니다.
- 권고: cycle-local reservation ledger를 두고, 주문 접수 성공 시 reserved cash/notional을 즉시 차감합니다. 브로커 pending과 DB pending reconciliation 결과도 주문 전 exposure에 포함합니다.
- 구현 전 테스트: `tests/agent/test_trading_agent_execution_policy.py` 또는 신규 `tests/agent/test_trading_agent_risk_reservation.py`에 병렬 BUY 현금 예약 테스트 추가.
- Rollout: 먼저 dry-run reservation log, 이후 실제 BUY gate에 적용.
- Rollback: reservation gate를 feature flag로 분리.
- 분류: `유지하되 harden`

### F-012: DB open BUY 노출이 실제 브로커 보유 평가액보다 크게 부풀어 있음

- 심각도: `P1`
- 상태: `확정`
- 영역: `리스크 | PnL | 주문`
- 현상: DB `CONFIRMED BUY AND exit_at IS NULL`은 48건, entry notional 약 981,916,149원입니다. 브로커 보유 종목은 6개, account snapshot 주식평가액은 약 430,159,408원입니다.
- 영향: DB open BUY를 노출/PnL/성과 학습에 쓰면 실제보다 큰 포지션으로 판단할 수 있고, 반대로 브로커 snapshot만 쓰면 stale DB lot이 계속 학습 데이터에 남습니다.
- 증거: `sqlite3 -readonly data/app.db` open BUY 집계, Admin holdings/account snapshot.
- 재현/검증: `trade_results` open BUY 집계와 `/api/v1/admin/account/holdings` 비교.
- 권고: Phase 4에서 canonical PnL/source를 확정하고, Phase 2의 pending reconciliation과 묶어 stale open lot report를 추가합니다.
- 구현 전 테스트: `tests/services/test_performance_reporting_service.py`, `tests/scheduler/test_portfolio_sync_job.py`에 stale open BUY 대사 테스트 후보.
- Rollout: report-only stale lot detector부터 시작.
- Rollback: report-only 제거 가능.
- 분류: `유지하되 harden`

### F-013: closed trade 표본이 0건이라 기대값/승률/PF 기반 성과 판단이 불가능함

- 심각도: `P1`
- 상태: `확정`
- 영역: `PnL | 성과 측정 | 전략`
- 현상: 운영 DB에서 `side=BUY`, `status=CONFIRMED`, `exit_at IS NOT NULL`인 closed trade가 0건입니다. PerformanceReportingService와 PerformanceTracker는 이 closed BUY만 기대값/승률/PF/연속손실의 기준으로 사용합니다.
- 영향: 현재 “전략이 돈을 잘 버는지”를 closed-trade 지표로 판단할 수 없습니다. LLM risk tuning과 trading guard의 성과 입력도 사실상 비어 있어 전략 개선 판단이 왜곡됩니다.
- 증거: `services/performance_reporting_service.py:170-183`, `analysis/feedback/performance_tracker.py:35-40`, read-only DB 집계 `closed BUY=0`.
- 재현/검증: `select count(*) from trade_results where side='BUY' and status='CONFIRMED' and exit_at is not null`.
- 권고: closed trade 표본이 부족하면 UI/API/LLM prompt에 `INSUFFICIENT_CLOSED_TRADE_SAMPLE`을 명시하고, 전략 성과 판단은 account equity delta와 별도 표시합니다.
- 구현 전 테스트: `tests/services/test_performance_reporting_service.py`에 closed trade 0건이면 “평가 불가” 상태를 반환하는 테스트 추가.
- Rollout: report-only 상태 필드부터 추가.
- Rollback: 상태 필드 제거 가능.
- 분류: `유지하되 harden`

### F-014: account equity는 기록되지만 전략 성과/kill switch와 충분히 연결되지 않음

- 심각도: `P1`
- 상태: `확정`
- 영역: `PnL | 리스크 | 성과 측정`
- 현상: `account_equity_snapshots`는 총자산, 현금, 주식평가, 평가손익을 잘 저장하고 session metrics도 계산합니다. 그러나 PerformanceTracker와 TradingGuard의 핵심 성과/손실 판단은 closed `TradeResult`에 치우쳐 있습니다.
- 영향: 계좌 총자산이 장중 크게 흔들려도 전략 기대값, 연속 손실, kill switch에는 즉시 반영되지 않습니다. 현재 같은 장중에는 total_asset 517,447,795~533,288,675 범위까지 움직였습니다.
- 증거: `services/account_equity_service.py:182-239`, `strategy/trading_guard.py:59-79`, 최신 account snapshots.
- 재현/검증: account equity snapshot asset range와 closed trade PnL 집계를 비교합니다.
- 권고: 성과 모델을 `realized_trade_pnl`, `unrealized_pnl`, `total_asset_delta`, `cash_delta`, `pending_exposure`로 분리하고, risk gate는 최소 `total_asset_delta`와 intraday drawdown을 사용해야 합니다.
- 구현 전 테스트: `tests/services/test_account_equity_service.py`, `tests/strategy/test_trading_guard.py`에 account equity 기반 drawdown 테스트 추가.
- Rollout: 먼저 리포트 경고와 chart, 이후 BUY gate/kill switch에 연결.
- Rollback: gate 적용 전 report-only 단계는 제거 가능.
- 분류: `유지하되 harden`

### F-015: daily report의 주문 count와 TradeResult count가 섞여 리포트 해석이 혼란스러움

- 심각도: `P2`
- 상태: `검증 중`
- 영역: `성과 측정 | 리포트`
- 현상: 저장된 2026-04-21 daily report는 `total_orders=2`인데 `buy_count=0`, `sell_count=0`입니다. daily report는 activity count와 TradeResult count를 함께 사용합니다.
- 영향: 리포트 사용자가 “주문 2건이 있었는데 매수/매도는 0건”으로 보게 되어 실제 주문/추천/체결/확인대기 구분이 흐려집니다.
- 증거: `services/daily_report_service.py:119-137`, `daily_reports` read-only DB 조회.
- 재현/검증: `select report_date,total_orders,buy_count,sell_count from daily_reports`.
- 권고: report schema를 `recommendations`, `submitted_orders`, `broker_pending_orders`, `confirmed_entries`, `confirmed_exits`, `closed_positions`로 분리합니다.
- 구현 전 테스트: daily report 서비스 테스트 파일을 추가하거나 기존 테스트에 count source별 분리 테스트 추가.
- Rollout: 새 필드 추가 후 기존 total은 deprecated 표시.
- Rollback: 기존 필드 유지 가능.
- 분류: `유지하되 harden`

### F-016: 후보별 forward return 데이터가 없어 전략 기대값을 검증할 수 없음

- 심각도: `P1`
- 상태: `확정`
- 영역: `전략 | 성과 측정 | 백테스트`
- 현상: `analysis_results`, `recommendations`, `strategy_signals`, `market_data_daily`, `market_snapshots`가 모두 0 rows입니다. `agent_activity_logs`에는 단계별 로그가 있지만, 후보별 decision event와 이후 5분/15분/30분/1시간/종가 수익률이 구조화되어 저장되지 않습니다.
- 영향: 어떤 후보를 샀어야 했는지, HOLD/SKIP이 맞았는지, Tier1/Tier2/risk gate가 기대값을 높였는지 판단할 수 없습니다. 현재 상태에서 “돈을 더 잘 벌게” 하는 전략 개선은 근거 없이 파라미터를 만지는 과최적화가 될 수 있습니다.
- 증거: 운영 DB row count `analysis_results=0`, `recommendations=0`, `strategy_signals=0`, `market_data_daily=0`, `market_snapshots=0`; activity log는 존재하지만 forward return label이 없음.
- 재현/검증: `sqlite3 -readonly data/app.db` row count와 `agent_activity_logs` 단계별 count 비교.
- 권고: 구현 1순위로 `decision_events`와 `decision_forward_returns` 또는 동등한 canonical dataset을 추가합니다. 모든 scan/Tier1/Tier2/risk/recommend/order/fill 후보에 대해 기준가와 future return을 저장해야 합니다.
- 구현 전 테스트: 신규 `tests/services/test_decision_event_service.py`에 후보 이벤트 생성, 중복 방지, 5m/15m/30m/60m/close label 업데이트 테스트를 먼저 작성합니다.
- Rollout: shadow/write-only로 시작해 최소 1~2주 데이터 수집 후 리포트와 gate에 연결합니다.
- Rollback: 수집 테이블 write를 feature flag로 끄고 기존 매매 경로는 유지합니다.
- 분류: `유지하되 harden`

### F-017: `StockScreener`가 현재 funnel에서 사용되지 않는 legacy 단계로 보임

- 심각도: `P2`
- 상태: `검증 중`
- 영역: `전략 | LLM | 운영`
- 현상: `agent/stock_screener.py`는 별도 `SCREENING` activity를 남기는 LLM 후보 필터링 단계지만, 운영 DB에는 `SCREENING` 로그가 0건입니다. 현재 `MarketScanner.scan`이 시장 데이터 수집과 LLM selection을 한 번에 수행합니다.
- 영향: 문서/README상 funnel과 실제 운영 funnel이 달라지고, LLM 호출 단계가 중복으로 남아 있으면 유지보수와 성능 튜닝 기준이 흐려집니다.
- 증거: `rg StockScreener` 결과 현재 코드 호출은 전역 인스턴스 정의와 문서 중심이며, DB activity count에서 `SCREENING=0`.
- 재현/검증: `rg -n "stock_screener|StockScreener|SCREENING"`와 activity log count 확인.
- 권고: 사용 계획이 없으면 제거 후보로 두고, 유지하려면 scanner와 screener의 책임을 분리해 `scan -> screen` 단계와 성과 attribution을 명확히 합니다.
- 구현 전 테스트: 제거 전 `tests/agent/test_market_scanner.py`와 cycle 테스트에서 현재 scanner-only funnel이 유지되는지 확인합니다.
- Rollout: 먼저 README/Admin 문구에서 legacy 표시, 이후 미사용 코드 제거.
- Rollback: 제거 전 커밋으로 되돌릴 수 있으나, 삭제보다 deprecation 주석부터 적용하는 편이 안전합니다.
- 분류: `제거`

### F-018: `StableShort`/`AggressiveShort`는 독립 전략 alpha가 아니라 LLM 판단의 실행 프로필에 가까움

- 심각도: `P1`
- 상태: `확정`
- 영역: `전략 | 성과 측정`
- 현상: 두 전략 클래스는 `recommendation=BUY/SELL/HOLD`와 confidence를 LLM 분석에서 받아 손절/익절/긴급도와 reason text를 붙입니다. RSI/MACD/trend 조건은 대체로 설명 보강이며 BUY 진입의 독립 hard edge 조건이 아닙니다.
- 영향: 리포트가 `STABLE_SHORT` 또는 `AGGRESSIVE_SHORT`의 성과처럼 표시되면 실제로는 LLM decision pipeline 성과를 전략 성과로 오해할 수 있습니다. 어떤 전략이 돈을 버는지 attribution이 틀어집니다.
- 증거: `strategy/stable_short.py`, `strategy/aggressive_short.py` 파일 주석과 `evaluate` 구현.
- 재현/검증: LLM recommendation이 BUY이고 confidence만 통과하면 전략은 BUY signal을 생성합니다.
- 권고: 이름과 리포트 분류를 `execution_profile` 또는 `strategy_profile`로 재정의하고, 독립 technical strategy는 별도 benchmark로 분리합니다.
- 구현 전 테스트: strategy evaluate 테스트에 “LLM recommendation이 같은 경우 technical reason은 signal 생성 여부를 바꾸지 않는다”는 현재 동작 고정 테스트를 추가합니다.
- Rollout: 리포트 문구/모델 필드부터 바꾸고, 기존 DB 값은 migration 없이 alias로 유지합니다.
- Rollback: 표시명만 되돌리면 됩니다.
- 분류: `유지하되 harden`

### F-019: 단계별 benchmark/control group이 없어 LLM, 기술분석, risk gate의 기여도를 분리할 수 없음

- 심각도: `P1`
- 상태: `확정`
- 영역: `전략 | LLM | 성과 측정`
- 현상: no-trade, random same candidates, scanner-only, technical-only, Tier1-only, Tier2-only, risk/cost-gated, actual recommendation/order 간 비교 결과가 저장되지 않습니다.
- 영향: 특정 단계가 수익을 높이는지, 지연과 비용만 늘리는지 알 수 없습니다. 특히 LLM 호출 비용/지연과 뉴스/기술분석 단계의 가치를 평가할 수 없습니다.
- 증거: Phase 5 funnel과 DB row count. Benchmark를 산출하는 service/test가 확인되지 않음.
- 재현/검증: 저장된 후보 이벤트와 future return dataset이 없어서 benchmark query 자체를 구성할 수 없습니다.
- 권고: forward return dataset 위에 benchmark report를 먼저 read-only로 추가합니다. 각 benchmark는 같은 시간, 같은 후보군, 같은 비용 가정으로 비교해야 합니다.
- 구현 전 테스트: 신규 `tests/services/test_strategy_benchmark_service.py`에 동일 후보군 랜덤 baseline, scanner-only baseline, Tier1/Tier2 filter 비교 fixture 추가.
- Rollout: 최소 표본 수 미달 시 `INSUFFICIENT_SAMPLE`만 반환하고, gate에는 연결하지 않습니다.
- Rollback: report-only service 제거 가능.
- 분류: `실험`

### F-020: 현재 상태에서 전략/뉴스/LLM 파라미터를 바로 조정하면 과최적화 위험이 큼

- 심각도: `P1`
- 상태: `확정`
- 영역: `전략 | 백테스트 | LLM`
- 현상: closed trade 표본 0건, 후보별 forward return 0건, benchmark 0건인 상태입니다. 그런데 risk, confidence, cost, LLM provider, 뉴스 gate 등 조정 가능한 파라미터는 많습니다.
- 영향: 장중 몇 개 사례만 보고 threshold를 바꾸면 실제 기대값 개선이 아니라 noise에 맞춘 튜닝이 될 가능성이 큽니다.
- 증거: F-013, F-016, F-019와 연결. 외부 기준도 multiple testing/overfitting 방지를 요구합니다.
- 재현/검증: 현재 DB만으로 parameter trial별 out-of-sample 성과를 계산할 수 없습니다.
- 권고: 파라미터 변경은 `experiment_id`, 기간, 표본 수, benchmark, 비용 가정, out-of-sample 기준을 문서화한 뒤 shadow/SEMI_AUTO에서 검증합니다.
- 구현 전 테스트: experiment registry 또는 benchmark report에 `min_sample_size`, `in_sample/out_of_sample` 구분 테스트 추가.
- Rollout: 문서화된 실험 단위로만 변경하고, 각 Phase 완료 후 문서 최신화와 커밋을 유지합니다.
- Rollback: 실험 flag를 끄고 이전 runtime setting snapshot으로 복구합니다.
- 분류: `실험`

### F-021: 백테스트가 현재 봉 정보를 보고 같은 봉 종가에 진입하는 look-ahead/동시체결 가정을 가짐

- 심각도: `P1`
- 상태: `확정`
- 영역: `백테스트 | 전략`
- 현상: `BacktestEngine.run`은 `lookback_df = df.iloc[:i + 1]`로 현재 봉 close/high/low까지 포함해 지표를 계산한 뒤, 같은 `current_price=close`로 즉시 매수합니다.
- 영향: 실제로는 종가가 확정된 뒤 같은 종가로 체결할 수 없거나, 다음 봉 open/limit 조건을 써야 합니다. 이 구조는 성과를 낙관적으로 만들 수 있습니다.
- 증거: `backtesting/engine.py:86-124`, `_buy(symbol, current_date, current_price)`.
- 재현/검증: 현재 봉 close로 BUY 신호가 생기는 fixture에서 같은 봉 close 체결이 발생합니다.
- 권고: 신호 생성 봉과 체결 봉을 분리합니다. 기본값은 `signal_on_close -> execute_next_open` 또는 명시적 `execute_next_close`로 두고, 리포트에 체결 정책을 표시합니다.
- 구현 전 테스트: 신규 `tests/backtesting/test_engine_execution_model.py`에 “i봉 신호는 i+1봉 이전에 체결되지 않는다”는 실패 테스트 추가.
- Rollout: 기존 API에는 `execution_timing` 기본값을 보수적으로 추가하고, 기존 방식은 `LEGACY_SAME_CLOSE`로 명시합니다.
- Rollback: feature flag로 legacy 체결 정책을 유지할 수 있게 합니다.
- 분류: `유지하되 harden`

### F-022: 백테스트가 live LLM pipeline이 아니라 rule-based RSI/MACD 대체 모델을 검증함

- 심각도: `P1`
- 상태: `확정`
- 영역: `백테스트 | 전략 | LLM`
- 현상: live trading은 scanner, chart, Tier1 LLM, Tier2 LLM, strategy profile, risk/cost gate를 거치지만, backtest는 `_build_rule_based_analysis`에서 RSI/MACD/cross 점수로 recommendation을 만듭니다.
- 영향: backtest 결과가 좋아도 live LLM 전략이 좋다는 증거가 아닙니다. 반대로 backtest가 나빠도 LLM pipeline을 부정할 수 없습니다.
- 증거: `backtesting/engine.py:150-190`, `agent/trading_agent.py`의 Tier1/Tier2 경로.
- 재현/검증: backtest 실행 시 LLM provider나 실제 prompt path를 사용하지 않습니다.
- 권고: 백테스트 리포트에 `model_family=RULE_BASED_TECHNICAL_PROXY`를 표시하고, live pipeline 검증은 Phase 5의 decision event/forward return dataset으로 분리합니다.
- 구현 전 테스트: backtest report schema에 model_family/execution_policy가 포함되는 테스트 추가.
- Rollout: 표시 필드부터 추가하고, LLM replay backtest는 별도 실험으로 둡니다.
- Rollback: 표시 필드 제거 가능.
- 분류: `유지하되 harden`

### F-023: 백테스트 체결 모델이 미체결/부분체결/호가/상하한가/세금을 반영하지 않음

- 심각도: `P1`
- 상태: `확정`
- 영역: `백테스트 | 주문 | 성과 측정`
- 현상: `_buy`와 `_close_position`은 고정 percentage slippage와 commission만 반영하고 전량 체결로 처리합니다. KRX 호가단위, 가격제한폭, 거래정지, 거래세/제세금, 부분체결, 주문 거부가 없습니다.
- 영향: 특히 단기/급등주 전략에서는 체결 가능성과 비용이 성과 대부분을 좌우할 수 있어 실제보다 성과가 과대평가될 수 있습니다.
- 증거: `backtesting/engine.py:205-274`, `BacktestConfig`의 `commission_rate`, `slippage_rate`.
- 재현/검증: 유동성이 낮거나 gap이 큰 fixture에서도 계산상 수량이 있으면 전량 체결됩니다.
- 권고: `FeeModel`, `SlippageModel`, `FillModel`을 분리하고, 최소 `KoreaStockFeeModel`, `NextBarOHLCFillModel`, `LimitGuardFillModel`을 테스트로 고정합니다.
- 구현 전 테스트: 수수료/세금/슬리피지/부분체결/상하한가 fixture를 추가합니다.
- Rollout: report-only로 비용 breakdown을 먼저 출력하고, 이후 기존 결과와 새 결과를 나란히 표시합니다.
- Rollback: legacy cost model을 별도 옵션으로 유지합니다.
- 분류: `유지하되 harden`

### F-024: 백테스트 data loader가 날짜 범위와 trading day를 엄밀하게 보장하지 않음

- 심각도: `P2`
- 상태: `확정`
- 영역: `백테스트 | 데이터`
- 현상: `load_from_broker`는 calendar day 차이로 candle count를 요청하고, 반환된 candle을 start/end로 다시 필터링하지 않습니다. 로컬 `market_data_daily`도 0 rows라 재현 가능한 백테스트 dataset이 없습니다.
- 영향: 사용자가 지정한 기간과 실제 테스트 기간이 달라질 수 있고, 동일한 테스트를 나중에 재현하기 어렵습니다.
- 증거: `backtesting/data_loader.py:17-45`, Phase 5 DB row count `market_data_daily=0`.
- 재현/검증: broker가 요청 기간 밖 candle을 반환하는 fake adapter fixture에서 그대로 리포트에 포함됩니다.
- 권고: 반환 후 날짜 필터링, trading day count 로깅, 데이터 source/version/hash를 리포트에 포함합니다.
- 구현 전 테스트: `tests/backtesting/test_data_loader.py`에 기간 밖 candle 제거 테스트 추가.
- Rollout: 필터링과 metadata는 backward-compatible하게 추가 가능합니다.
- Rollback: 필터링 flag를 끌 수 있게 두되 기본은 엄격 모드로 둡니다.
- 분류: `유지하되 harden`

### F-025: 백테스트 엔진/metrics 테스트가 없어 성과 지표를 신뢰하기 어려움

- 심각도: `P1`
- 상태: `확정`
- 영역: `백테스트 | 테스트`
- 현상: 현재 `tests/backtesting/`에는 data loader 테스트 2개만 있고, engine/metrics/report 테스트가 없습니다.
- 영향: 성과 지표나 체결 정책을 바꿔도 회귀를 잡기 어렵고, 백테스트 리포트를 운영 판단에 쓰기 위험합니다.
- 증거: `rg --files tests/backtesting backtesting` 결과 `tests/backtesting/test_data_loader.py`만 존재.
- 재현/검증: `BacktestEngine`, `calculate_metrics`, `BacktestReport` 직접 테스트가 없습니다.
- 권고: Phase 6 이후 실제 구현 첫 단계는 TDD로 engine execution model 테스트를 추가하는 것입니다.
- 구현 전 테스트: 동일 항목이 곧 구현 전 테스트입니다. look-ahead, fees/slippage, stop/take/gap, final liquidation, metrics edge case를 fixture로 고정합니다.
- Rollout: 테스트 추가 후 엔진 리팩터링. 외부 라이브러리 도입은 테스트 baseline이 생긴 뒤 판단합니다.
- Rollback: 테스트는 제거하지 않고, legacy behavior는 별도 옵션으로 고정합니다.
- 분류: `유지하되 harden`

### F-026: LLM 단계의 latency/cost가 forward return과 연결되지 않아 가치 판단이 불가능함

- 심각도: `P1`
- 상태: `확정`
- 영역: `LLM | 전략 | 성과 측정`
- 현상: `execution_metrics`에는 provider/model/latency/status가 저장되지만, 후보별 이후 수익률이나 stage별 benchmark와 연결되지 않습니다.
- 영향: Codex, Claude, Ollama 중 무엇이 돈을 더 벌게 하는지, 또는 지연만 늘리는지 판단할 수 없습니다. Tier1+Tier2 지연이 50~80초인 후보도 있어 단기 전략에서는 latency 자체가 edge를 없앨 수 있습니다.
- 증거: Phase 7 `LLM_CALL` 집계, F-016의 forward return dataset 부재.
- 재현/검증: 특정 `cycle_id/symbol`의 LLM latency는 조회 가능하지만, 같은 decision event의 5m/15m/30m/close return은 조회할 수 없습니다.
- 권고: decision event에 `provider`, `model`, `prompt_version`, `elapsed_ms`, `fallback_used`, `decision_action`, `forward_returns`를 함께 저장합니다.
- 구현 전 테스트: `tests/services/test_decision_event_service.py`에 LLM metadata와 forward return label 저장 테스트 추가.
- Rollout: write-only metric enrichment부터 시작하고 gate에는 연결하지 않습니다.
- Rollback: enrichment feature flag를 끄면 기존 LLM 라우팅은 유지됩니다.
- 분류: `유지하되 harden`

### F-027: Codex timeout cooldown이 후보별 오류로 증폭되어 incident 수가 과대 집계될 수 있음

- 심각도: `P1`
- 상태: `확정`
- 영역: `LLM | 운영`
- 현상: `CodexProvider`는 timeout 후 300초 cooldown을 적용하지만, cooldown 중인 provider를 여러 후보가 다시 확인하면서 `llm_factory/generate` error event와 incident가 반복 생성됩니다.
- 영향: 실제 root cause는 1개의 Codex timeout이어도 운영 UI에는 다수 LLM 장애처럼 보일 수 있습니다. 장중에는 후보 분석 실패가 연쇄적으로 발생해 decision coverage가 떨어집니다.
- 증거: 최신 `error_events`의 `CODEX 최근 호출 실패로 비활성화 (...s 남음): Codex CLI timeout (120s)` 반복, `error_incidents`의 `llm_factory/generate` open 119건.
- 재현/검증: Codex timeout 후 cooldown 중 여러 symbol 분석이 들어오면 provider unavailable 오류가 반복 기록됩니다.
- 권고: provider cooldown 상태는 per-call exception이 아니라 provider health 상태로 집계하고, 같은 cooldown window에서는 incident dedupe/circuit-open event 1건으로 제한합니다.
- 구현 전 테스트: `tests/analysis/test_llm_factory.py`에 cooldown 중 동일 provider 반복 호출 시 incident가 증폭되지 않는 테스트 추가.
- Rollout: observability 집계 변경부터 적용하고 LLM 라우팅은 유지합니다.
- Rollback: 기존 error_capture 호출 방식으로 되돌릴 수 있습니다.
- 분류: `유지하되 harden`

### F-028: 뉴스 기능은 현재 꺼져 있고 저장 표본도 stale/neutral이라 매매 가치가 검증되지 않음

- 심각도: `P1`
- 상태: `확정`
- 영역: `뉴스 | 전략 | 성과 측정`
- 현상: runtime 기준 `NEWS_POLL_ENABLED=false`, `NEWS_GATE_ENABLED=false`, `NEWS_LLM_ENABLED=false`, `NEWS_SHADOW_ENABLED=false`입니다. 저장된 `news_items`는 65건이며 최신 published_at은 2026-04-21이고 negative_count는 0입니다.
- 영향: 지금 뉴스는 매매 판단에 영향이 없으므로 안전하지만, 다시 켜도 돈을 더 벌게 하는지 판단할 데이터가 없습니다.
- 증거: runtime settings와 `news_items` source 집계.
- 재현/검증: `sqlite3 -readonly data/app.db`로 runtime/news_items 집계 확인.
- 권고: 뉴스는 계속 OFF 유지합니다. 재개 시에는 poll-only 또는 shadow-only로 시작하고, 실제 `NEWS_GATE_ENABLED=true`는 blocked-vs-baseline forward return 표본이 쌓인 뒤 적용합니다.
- 구현 전 테스트: `tests/services/test_news_signal_service.py`, `tests/services/test_news_reporting_service.py`에 sample-size 부족 시 rollout 불가 테스트 추가.
- Rollout: `POLL_ONLY -> SHADOW_ONLY -> SEMI_AUTO_GATE_RECOMMENDATION -> BUY_BLOCK_GATE` 순서.
- Rollback: runtime settings에서 `NEWS_POLL_ENABLED=false`, `NEWS_GATE_ENABLED=false`, `NEWS_LLM_ENABLED=false`로 즉시 비활성화.
- 분류: `기본 비활성화`

### F-029: 뉴스 fetch 병렬도와 번역 병렬도가 다른 개념인데 Admin/운영 문서에서 혼동될 수 있음

- 심각도: `P2`
- 상태: `확정`
- 영역: `뉴스 | 운영`
- 현상: `NEWS_FETCH_CONCURRENCY`는 여러 뉴스 소스 HTTP fetch 병렬도이고, `NEWS_TRANSLATION_CONCURRENCY`는 LLM 번역 병렬도입니다. 코드상 `CODEX`/`OLLAMA` 번역은 항상 1로 강제됩니다.
- 영향: fetch 병렬도를 Codex 병렬도처럼 이해하면 불필요하게 낮추거나, 반대로 번역 병렬도를 높이면 Codex timeout을 악화시킬 수 있습니다.
- 증거: `services/news_polling_service.py:_poll_enabled_sources`, `services/news_translation_service.py:_translation_concurrency_limit`, `analysis/llm/llm_factory.py:_provider_concurrency_limit`.
- 재현/검증: `NEWS_FETCH_CONCURRENCY=3`, `NEWS_TRANSLATION_CONCURRENCY=1`, news provider CODEX일 때 fetch는 최대 3 source, translation은 1 LLM 호출로 제한됩니다.
- 권고: Admin 설정 설명을 `source fetch concurrency`와 `LLM translation concurrency`로 분리 표기합니다. 현재 값은 `fetch=3`, `translation=1` 유지가 적절합니다.
- 구현 전 테스트: admin/settings schema 또는 runtime settings service 테스트에 설명/분류 필드 추가 후보.
- Rollout: UI/문서 변경부터 적용.
- Rollback: 설명 문구 제거 가능.
- 분류: `유지하되 harden`

### F-030: 뉴스 source별 성과 기여도와 중복/stale/실패율이 rollout gate와 연결되지 않음

- 심각도: `P1`
- 상태: `검증 중`
- 영역: `뉴스 | 성과 측정`
- 현상: source catalog에는 trust score와 official flag가 있지만, source별 created/duplicate/stale/error와 trade outcome이 연결되지 않습니다.
- 영향: 어떤 뉴스 소스를 유지/제거할지 판단할 수 없습니다. foreign source를 켜면 번역 비용과 latency가 늘지만 성과 기여가 불명확합니다.
- 증거: `news_items`는 DART/KRX/YONHAP 65건만 있고, `NEWS_POLL` execution metric은 확인되지 않았으며, news gate/shadow도 꺼져 있습니다.
- 재현/검증: source별 뉴스 count는 가능하지만 source별 blocked trade forward return은 계산 불가입니다.
- 권고: source별 `received/created/duplicate/skipped/error`, `translation_failed`, `gate_contribution`, `blocked_forward_return` 리포트를 추가한 뒤 source active set을 조정합니다.
- 구현 전 테스트: `tests/services/test_news_reporting_service.py`에 source별 stale/duplicate/translation failure/rollout summary fixture 추가.
- Rollout: report-only 후 source disable/enable 결정.
- Rollback: source별 runtime flag를 기존 값으로 복구.
- 분류: `실험`

## Open Questions

- 감사 기간에 `TRADING_ENABLED=true`를 유지할지, 아니면 `SELL_ONLY`/`READ_ONLY`에 가까운 별도 운영 모드를 만들지 결정해야 합니다.
- DB pending과 브로커 pending이 불일치할 때 어떤 값을 신규 BUY 차단과 노출 계산의 기준으로 삼을지 결정해야 합니다.
- LLM risk tuning이 제안할 수 있는 absolute cap을 계좌 규모별로 얼마로 둘지 결정해야 합니다.
- closed trade 0건인 현 상태에서 전략 성과 판단은 account equity forward return 중심으로 임시 전환할지 결정해야 합니다.
- strategy 이름을 실제 alpha 전략으로 유지할지, execution profile로 바꿀지 결정해야 합니다.
- 후보별 forward return을 기존 `analysis_results`/`recommendations`에 넣을지, 신규 canonical table로 분리할지 결정해야 합니다.
- 백테스트 기본 체결 정책을 `next_open`, `next_close`, `limit_guard` 중 무엇으로 둘지 결정해야 합니다.
- 뉴스 재개 시 첫 단계는 `POLL_ONLY`로 할지 `SHADOW_ONLY`까지 같이 켤지 결정해야 합니다.
- Tier1 LLM을 계속 Codex `gpt-5.4`로 둘지, latency-sensitive 모델/Claude/Ollama 후보를 실험할지 결정해야 합니다.
- `.env`와 shell history까지 시크릿 스캔 범위를 확장할지는 tracked files + runtime logs 점검 후 결정합니다.
