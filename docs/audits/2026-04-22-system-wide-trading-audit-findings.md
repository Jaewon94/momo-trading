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

- 현재 확정된 P0/P1/P2/P3 finding은 없습니다.
- Phase 0에서는 감사 운영 기준, 산출물 경로, 검증 방식만 확정했습니다.

## Open Questions

- 실제 runtime settings가 감사 운영 기준과 일치하는지 확인해야 합니다.
- 브로커 read-only 스냅샷을 언제 캡처할지 Phase 1 시작 시 결정해야 합니다.
- `.env`와 shell history까지 시크릿 스캔 범위를 확장할지는 tracked files + runtime logs 점검 후 결정합니다.
