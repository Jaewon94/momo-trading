# MOMO Trading 전체 시스템 감사 Evidence

> 상태: Phase 0 기준선 문서입니다. 이 문서는 읽기 전용 감사 증거를 누적합니다. 코드, 설정, 전략 파라미터, live trading 동작 변경은 별도 승인과 findings/roadmap 반영 전에는 하지 않습니다.

## Phase 0: 감사 안전선

### 감사 운영 기준

- 감사 중 live bot 운영 기준: `read-only / semi-auto` 우선. 실제 런타임 설정 변경은 별도 evidence와 함께 수행합니다.
- 브로커 read-only API 조회: 허용. 계좌, 보유, 미체결, quote 스냅샷 확인 목적에 한정합니다.
- 뉴스 기능: 감사 완료 전까지 `OFF 유지`를 기본값으로 둡니다. 재활성화는 뉴스 가치/부하/지연 평가 후 결정합니다.
- 개선 우선순위: 손실 방어, 주문 안전성, PnL 신뢰도, 리스크/노출 계산을 기대수익 실험보다 먼저 봅니다.
- 시크릿 스캔 범위: `tracked files + runtime logs`를 기본 범위로 둡니다. `.env`와 shell history는 필요 시 별도 확인 후 진행합니다.
- 구현 정책: findings와 improvement roadmap 승인 전에는 코드 구현을 시작하지 않습니다.

### 환경 기준점

- 기준 시각: `2026-04-22 10:53:17 KST`
- 작업 브랜치: `jaewon-ver`
- 기준 커밋: `8de637b8939427f265e5f2239bdf7e774ac135cd`
- 감사 범위 문서: `docs/audits/2026-04-22-system-wide-trading-audit-plan.md`
- 감사 TODO 문서: `docs/superpowers/plans/2026-04-22-system-wide-trading-audit-todo.md`

### Phase 0 검증 명령

```bash
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
```

### Phase 0 관찰

- 현재까지 수행한 작업은 문서 생성과 문서 보정뿐입니다.
- 아직 DB read-only 쿼리, 브로커 read-only 스냅샷, 시크릿 스캔, 코드 분석 findings 작성은 시작하지 않았습니다.
- Phase 1부터 DB source of truth와 PnL 신뢰도 검증을 시작합니다.

## Phase 1: Source of Truth와 DB 무결성

> 아직 시작하지 않았습니다.

## Phase 2: 주문 생명주기와 브로커 Transport

> 아직 시작하지 않았습니다.

## Phase 3: 리스크 제어와 자본 배분

> 아직 시작하지 않았습니다.

## Phase 4: 성과 측정과 PnL 신뢰도

> 아직 시작하지 않았습니다.

## Phase 5: 전략 가치와 매매 기대값

> 아직 시작하지 않았습니다.

## Phase 6: 백테스트와 실험 위생

> 아직 시작하지 않았습니다.

## Phase 7: LLM, 뉴스, 비용/지연 가치

> 아직 시작하지 않았습니다.

## Phase 8: 스케줄러, 실시간 이벤트, 운영/보안/Admin

> 아직 시작하지 않았습니다.
