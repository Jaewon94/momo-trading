# Final Report

## Outcome

계획 수립 완료. 런타임 매매 로직, 브로커 액션, 런타임 DB, 주문 실행 경로는 변경하지 않았다.

생성 문서:

- `architecture-plan.md`: 단/중/장기별 LLM/데이터 컨텍스트 분리 설계안
- `decision-record.md`: 채택/보류/거절 판단
- `brief.md`, `test-plan.md`, `quality-scorecard.md`: 검토 범위와 검증 결과 갱신

## Recommendation

중장기 판단을 현재처럼 차트 중심 단일 LLM 경로에 맡기는 구조는 부족하다. 단기, 중기, 장기는 같은 LLM을 단순히 다른 문구로 부르는 방식이 아니라, 입력 데이터와 출력 계약을 분리해야 한다.

권장 방향:

- 공통 `DecisionContext` 스키마 도입
- SHORT/MID/LONG별 context builder 분리
- SHORT/MID/LONG별 prompt/schema contract 분리
- live path에서는 먼저 deterministic horizon routing을 하고, 해당 horizon analyst만 호출
- 모든 신규 horizon analyst는 shadow mode로 검증 후 활성화
- 리스크, 사이징, 매도, 실행 정책은 계속 중앙 policy registry가 소유

## Verification

Passed:

```bash
.venv313/bin/python scripts/task_harness.py verify 2026-06-10-010-horizon-llm-architecture-plan
python scripts/check_task_harness.py --strict-current
```

Failed / separate operational issue:

```bash
python scripts/check_runtime_integrity.py --days 7
```

Result:

- `order_reconciliation=FAIL`
- `db_pending=1`
- `db_only_stale=1`
- `pending_confirms=1`
- `broker_missing_open_buys=1`

이 런타임 정합성 문제는 horizon LLM 설계와 별개이며, 별도 승인된 운영 복구 작업으로 처리해야 한다.

## Commit Status

커밋하지 않음. 사용자는 이번 메시지에서 "바로 구현이 아니라 계획"이라고 명시했고, 런타임 무결성 검증도 아직 실패 상태이므로 "이상 없이 다 되고 테스트도 다 통과" 조건을 만족하지 않는다.
