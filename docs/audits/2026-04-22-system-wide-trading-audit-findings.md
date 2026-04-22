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

## Open Questions

- 감사 기간에 `TRADING_ENABLED=true`를 유지할지, 아니면 `SELL_ONLY`/`READ_ONLY`에 가까운 별도 운영 모드를 만들지 결정해야 합니다.
- DB pending과 브로커 pending이 불일치할 때 어떤 값을 신규 BUY 차단과 노출 계산의 기준으로 삼을지 결정해야 합니다.
- `.env`와 shell history까지 시크릿 스캔 범위를 확장할지는 tracked files + runtime logs 점검 후 결정합니다.
