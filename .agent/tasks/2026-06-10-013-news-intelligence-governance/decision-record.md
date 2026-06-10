# Decision Record

## Decision

뉴스 판단은 `strategy/news_intelligence_policy.py`를 canonical policy로 두고,
기존 뉴스 게이트, 뉴스 컨텍스트, 후보 뉴스 압력 계산이 이 정책을 참조하도록
통합한다. 장마감 후 LLM 뉴스 분석은 바로 활성화하지 않고, 비용 제한과
출처/근거/성과 검증 계약만 먼저 문서화한다.

## Rationale

- 지금 문제는 뉴스가 전혀 쓰이지 않는 것이 아니라, 기준과 목적이 여러 경로에
  흩어져 있어 품질을 높이기 어려운 점이다.
- 장마감 시간대의 뉴스/공시 정리는 중기/장기 판단에 도움이 될 수 있다. 다만
  LLM 비용은 모든 뉴스 item을 읽게 하면 빠르게 커지므로 deterministic
  grouping/filtering 후 하루 최대 1 batch 수준으로 제한해야 한다.
- 뉴스는 직접 주문 신호가 아니라 리서치 근거다. 주문은 기존 deterministic
  gate, risk manager, broker/session check를 계속 통과해야 한다.
- 뉴스 기능을 유료 기능 수준으로 만들려면 source quality, event taxonomy,
  match reason, item id citation, forward return/shadow metric이 먼저 남아야 한다.

## Deferred

- after-hours research memo 생성 job, 저장 테이블, admin preview, 비용 집계 UI.
- 외부 검색/외신 확장과 번역 pipeline 강화.
- 뉴스 이벤트 taxonomy를 실제 classifier/prompt output에 강제하는 단계.
- 뉴스 기반 성과 리포트와 A/B rollout.

## Risks

- 현재 변경은 정책 중앙화와 문서화가 중심이므로 뉴스 alpha 자체를 즉시 개선하지
  않는다.
- 향후 LLM research memo를 켤 때는 prompt injection, hallucination, cost drift,
  종목 매칭 오류를 별도 검증해야 한다.
- 실시간 주문 로직은 직접 변경하지 않았지만, 뉴스 서비스 import 경로가 바뀌므로
  기존 뉴스 테스트와 scanner 테스트로 회귀를 확인해야 한다.
