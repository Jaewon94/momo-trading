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
- 현상: `trade_results`에 `PENDING_CONFIRM BUY`가 20건 있습니다. `KEC`, `이브이첨단소재`, `GS글로벌` 등 같은 종목 반복 pending이 보입니다.
- 영향: pending 상태가 실제 미체결인지, 체결 확인 누락인지, 중복 주문인지 판단되지 않으면 노출 계산과 신규 주문 차단이 틀릴 수 있습니다.
- 증거: `trade_results` 상태 집계와 pending 목록 read-only 쿼리.
- 재현/검증: Phase 2에서 브로커 read-only pending orders와 `scheduler/jobs/portfolio_sync_job.py`의 recovery 로직을 대사해야 합니다.
- 권고: Phase 2에서 PENDING_CONFIRM age, broker pending, holdings, trade_results를 대사하고 stale pending 처리 기준을 확정합니다.
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

## Open Questions

- 실제 runtime settings가 감사 운영 기준과 일치하는지 확인해야 합니다.
- 브로커 read-only 스냅샷을 언제 캡처할지 Phase 1 시작 시 결정해야 합니다.
- `.env`와 shell history까지 시크릿 스캔 범위를 확장할지는 tracked files + runtime logs 점검 후 결정합니다.
