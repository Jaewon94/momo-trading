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

## Open Questions

- 감사 기간에 `TRADING_ENABLED=true`를 유지할지, 아니면 `SELL_ONLY`/`READ_ONLY`에 가까운 별도 운영 모드를 만들지 결정해야 합니다.
- DB pending과 브로커 pending이 불일치할 때 어떤 값을 신규 BUY 차단과 노출 계산의 기준으로 삼을지 결정해야 합니다.
- LLM risk tuning이 제안할 수 있는 absolute cap을 계좌 규모별로 얼마로 둘지 결정해야 합니다.
- `.env`와 shell history까지 시크릿 스캔 범위를 확장할지는 tracked files + runtime logs 점검 후 결정합니다.
