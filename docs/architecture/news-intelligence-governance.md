# News Intelligence Governance

뉴스/공시는 momo-trading에서 독립 매수 신호가 아니라 차트, 수급, 리스크,
보유 기간 판단을 보조하는 근거 계층이다. 뉴스 기능을 돈 받고 팔아도 될
수준으로 만들려면 가중치를 먼저 키우는 것이 아니라 출처, 종목 매칭, 이벤트
분류, 검증 가능한 효과 측정이 먼저 갖춰져야 한다.

중앙 정책 파일:

- `strategy/news_intelligence_policy.py`

연결 경로:

- 수집: `services/news_polling_service.py`
- 저장/정규화: `services/news_ingest_service.py`
- 후보 뉴스 압력: `agent/market_scanner.py`
- 매수 뉴스 게이트: `services/news_signal_service.py`
- Tier1/Tier2 프롬프트 컨텍스트: `services/news_context_service.py`
- 뉴스 유입 후 재검증: `agent/trading_agent.py`

## Operating Principles

- 뉴스는 주문을 직접 만들지 않는다.
- LLM 뉴스 요약은 다음 장 분석을 돕는 리서치 메모이며, 매수/매도는 기존
  deterministic gate, risk manager, broker/session check를 계속 통과해야 한다.
- 공식 공시와 거래소 데이터는 높은 신뢰도를 주되, 단순 가격제한폭 확대,
  형식적 소유 변동, 중립 행정 공시는 매매 영향이 낮은 이벤트로 분류한다.
- 외부 뉴스 본문은 untrusted content로 취급한다. 프롬프트에 넣을 때는 출처,
  제목, 요약, 시각, 종목 매칭 이유만 넣고 명령문처럼 해석하지 않는다.
- 효과가 검증되기 전에는 뉴스 차단을 강화하지 않는다. Shadow/A/B와 forward
  return으로 개선 효과를 확인한 뒤 rollout한다.

## After-Hours Research

장마감 후에는 실시간 주문 압력이 없으므로 뉴스와 공시를 정리하기 좋은
시간이다. 다만 LLM 비용이 수익으로 이어지려면 매번 긴 뉴스를 읽는 방식이
아니라 다음 장에서 재사용 가능한 구조화 결과를 만들어야 한다.

권장 1단계:

- 장마감 이후 수집된 DART/KRX/YONHAP를 종목/섹터/이벤트 유형별로 묶는다.
- 보유 종목, 오늘 스캔 후보, 중기/장기 후보와 매칭되는 이벤트를 우선한다.
- LLM 호출은 하루 1회 이하, 최대 1 batch로 제한한다.
- 결과는 `actionable`, `watch`, `ignore/noise`, `risk` 같은 label과 근거 item id를
  포함해야 한다.
- 결과는 다음 날 Tier1 프롬프트에 "전일 리서치 메모"로 들어가며, 주문 신호나
  quantity를 직접 만들지 않는다.

비용 대비 판단:

- 유리한 경우: 중기/장기 보유, 공시/수주/실적/가이던스처럼 며칠 이상 의미가
  남는 이벤트가 많을 때.
- 불리한 경우: 단순 장중 급등락, 가격제한폭 공지, 종목 연결 없는 시장 잡음,
  이미 가격에 반영된 언론 반복 보도가 대부분일 때.
- 기본값은 LLM off다. 운영 데이터에서 뉴스 컨텍스트가 forward return, 손절
  회피, 과매매 감소에 기여하는지 먼저 봐야 한다.

## Event Taxonomy

중앙 이벤트 분류는 `strategy/news_intelligence_policy.py`의
`NEWS_EVENT_POLICIES`를 기준으로 관리한다.

중요도가 높은 이벤트:

- 실적/잠정실적
- 가이던스/전망 변경
- 공급계약/수주
- 규제/거래정지/제재
- 소송/조사/회계 이슈

중요도 중간 이벤트:

- 증자/자사주/배당/소각
- 최대주주/임원 지분 변동
- 공급망/수요 변화
- 섹터/테마 뉴스

낮은 이벤트:

- 가격제한폭 확대 같은 단순 시장공지
- 종목 직접 연결이 없는 반복 언론 기사
- LLM이 출처 없이 추론한 내용

## Product-Grade Requirements

뉴스 기능을 유료 기능 수준으로 만들기 위한 최소 기준:

- Match quality: 뉴스가 어떤 종목에 왜 연결됐는지 `symbol`, `name`, `sector`,
  `theme` 중 하나로 설명 가능해야 한다.
- Source quality: DART/KRX 같은 공식 출처와 언론/외신을 분리해 표시해야 한다.
- Event quality: 뉴스 item이 이벤트 taxonomy 중 어디에 속하는지 표시해야 한다.
- Evidence quality: LLM 요약은 item id/source/title/time을 보존해야 한다.
- Outcome quality: 뉴스가 반영된 결정과 미반영 기준선의 forward return을 비교해야 한다.
- Cost quality: LLM 호출 수, latency, cost estimate가 남아야 한다.
- Safety quality: 외부 본문은 prompt injection 방어 지침을 거쳐야 하며,
  LLM output은 주문 도구를 직접 호출하지 않는다.

## Agent And Skill Alignment

미래 작업자는 뉴스 관련 변경 시 다음 파일을 함께 확인해야 한다.

- `strategy/news_intelligence_policy.py`: horizon별 뉴스 정책과 장마감 리서치 계약.
- `strategy/policy/registry.py`: `news_intel` 정책 owner, 관련 설정, 필수 테스트.
- `docs/architecture/trading-policy-governance.md`: 정책 owner와 변경 절차.
- `AGENTS.md`: 자동화 agent가 뉴스/웹/LLM 리서치 변경 시 따라야 할 repo 지침.
- `.agent/project-card.md`: 프로젝트 컨텍스트에서 뉴스 정책 위치를 찾는 진입점.

뉴스 기능은 별도 skill로 분리하지 않고, trading-policy governance 문서와 agent
가이드에 묶어 관리한다. 별도 skill이 필요해지는 시점은 외부 검색/RAG/LLM
research memo가 실제 운영 기능으로 켜지고, prompt contract와 평가 harness가
독립 실행 단위가 될 때다.

## Evidence Base

- Tetlock (2007), `Giving Content to Investor Sentiment`: 금융 뉴스/언론의
  부정적 톤이 시장 움직임과 연결될 수 있음을 보여준다.
- MacKinlay (1997), `Event Studies in Economics and Finance`: 뉴스/공시 같은
  이벤트 효과는 정상 수익 대비 초과수익으로 검증해야 한다.
- Goldsmith-Pinkham and Lyu (2025), `Causal Inference in Financial Event Studies`:
  긴 기간/변동성 구간에서는 이벤트 효과 추정이 편향될 수 있으므로 신중한
  검증이 필요하다.
- Lumer et al. (2025), financial RAG 비교 연구: 금융 문서 RAG는 검색 정확도,
  answer quality, latency, cost의 tradeoff를 같이 봐야 한다.
- Yin et al. (2026), financial RAG hallucination 연구: 금융 RAG도 검색 문서와
  모순되는 환각이 생길 수 있어 세부 claim 검증이 필요하다.
- OWASP LLM01:2025 Prompt Injection: 외부 웹/문서/뉴스는 indirect prompt
  injection 위험이 있으므로 외부 content를 분리하고 출력 형식을 검증해야 한다.

Sources:

- https://doi.org/10.1111/j.1540-6261.2007.01232.x
- https://www.jstor.org/stable/2729691
- https://arxiv.org/abs/2511.15123
- https://arxiv.org/abs/2511.18177
- https://arxiv.org/abs/2602.05723
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/
