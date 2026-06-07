# Decision Record

## Decision

채택: runtime decision_events 오염을 DB 삭제로 처리하지 않고, 코드 경로에서 재발을 막고 분석/리포팅 경로에서 fixture성 행을 제외한다.

채택: admin daily report 응답은 저장된 report snapshot보다 trade ledger의 opened/completed/sell count 값을 우선한다.

채택: stale BUY pending-confirm은 신규 매수를 차단하기 전에 confirmation recovery를 한 번 실행하고 재조회한다.

채택: fast_gate_score 역방향 경고는 표본 30개 미만이면 ERROR가 아니라 watchlist성 PROGRESS 로그로 낮춘다.

## Rationale

- global `decision_event_service`가 import 시점의 `AsyncSessionLocal`을 잡고 있으면 테스트가 session factory를 patch해도 runtime DB로 기록될 수 있다. lazy session factory로 전환하면 테스트 격리와 런타임 경로가 분리된다.
- 주간 감사에서 fixture성 decision_event 행은 broker order/trade_result와 연결되지 않았다. 주문 실행 문제라기보다 데이터 품질/분석 오염 문제로 다루는 것이 안전하다.
- 2026-06-02 stored report의 PnL은 canonical completed trades 합계와 달랐다. API에서 ledger 기준으로 보정하면 DB snapshot을 직접 수정하지 않고 사용자-facing 수치를 맞출 수 있다.
- 오래된 BUY pending-confirm은 실제 체결/실패 확인 대상일 수 있으므로 즉시 무시하지 않고 기존 portfolio sync recovery 경로를 재사용한다.
- fast gate 역방향 신호는 n=13 수준에서는 전략 오류로 단정하기 어렵다.

## Deferred

- Runtime DB에 이미 존재하는 fixture성 decision_events 삭제 또는 별도 quarantine migration. DB mutation이므로 별도 승인 필요.
- 공격적 리스크 성향에서 현금 비중을 낮추기 위한 필터/LLM 임계치 조정. 수익성과 위험을 바꾸는 전략 변경이므로 별도 실험과 승인 필요.
- 스케줄러 테스트의 coroutine warning 정리. 이번 변경과 직접 관련된 실패는 아니다.

## Risks

- `agent/decision_maker.py`는 주문 판단 흐름에 가까운 protected surface다. 이번 변경은 stale pending 확인 복구를 추가하지만, 실거래 시간에는 복구 결과에 따라 매수 차단 여부가 달라질 수 있다.
- fixture decision_event 필터는 보수적인 조건(provider/model UNKNOWN, stock_name==symbol, cycle_id 패턴 등)을 사용한다. 조건을 넓히면 실제 이벤트를 제외할 수 있으므로 현재는 제한적으로 유지했다.
- 기존 contaminated rows는 삭제하지 않았으므로 raw DB 조회에는 여전히 보일 수 있다.
