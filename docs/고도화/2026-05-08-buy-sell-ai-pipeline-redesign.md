# 매수/매도 AI 파이프라인 재설계 계획

작성일: 2026-05-08

## 배경

현재 자동매매는 후보 선별과 종목 분석 과정에서 Tier1/Tier2 LLM이 모두 개입한다. 운영 중 확인된 문제는 다음과 같다.

- Tier1 LLM도 CLI provider 직렬화와 timeout 영향을 받아 장중 판단 지연을 만든다.
- 이미 코드 기반 pre-gate, 후보 점수화, 비용/리스크 gate가 존재해 Tier1 LLM과 역할이 겹친다.
- 명백한 스킵 후보까지 AI 판단을 거치면 호출 수, DB 로그 쓰기, UI 대기 시간이 불필요하게 늘어난다.
- 매수와 매도는 의사결정 성격이 다르다. 매수는 후보 압축 문제이고, 매도는 이미 노출된 자본을 보호하는 문제다.

따라서 Tier1 LLM을 그대로 유지하기보다, 매수는 deterministic 필터와 점수화로 Tier1 역할을 대체하고 AI는 최종 후보에만 사용한다. 매도는 즉시 대응 룰과 AI 검토 룰을 분리한다.

## 외부 참고와 설계 근거

이 문서는 구현 전 다음 공식 문서의 원칙과 비교했다.

- SEC Rule 15c3-5 Market Access Rule: 주문 제출 전 자본/신용 한도, 오류 주문, 규제 요건을 통제해야 한다. 우리 설계의 주문 전 계좌/수량/금액/중복 주문 gate와 맞는다.  
  참고: https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access
- FINRA Market Access/Algorithmic Trading guidance: 알고리즘 매매는 사전 risk control, supervision, software development/testing, 운영 감시가 중요하다. shadow 검증, decision event, 테스트 선행 원칙과 맞는다.  
  참고: https://www.finra.org/rules-guidance/key-topics/algorithmic-trading
- QuantConnect Algorithm Framework: Universe Selection, Alpha, Portfolio Construction, Risk Management, Execution을 분리한다. 특히 Risk Management는 Execution 전에 portfolio target을 조정한다. 우리 설계의 `후보 선정/AI 판단/리스크/주문 실행` 분리와 같은 방향이다.  
  참고: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview  
  참고: https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/risk-management/key-concepts
- QuantConnect Trailing Stop Orders: trailing stop은 가격이 유리하게 움직일 때 stop price를 따라 올리고, stop price 도달 시 시장가 성격으로 체결된다. 우리 매도 설계의 `hard stop/trailing stop은 AI보다 우선` 원칙과 맞다.  
  참고: https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/trailing-stop-orders
- Freqtrade Stoploss: static stoploss, trailing stoploss, exchange/off-exchange stoploss를 분리하고, stoploss는 trade 보호 장치로 다룬다. 우리 설계의 `손절은 AI 판단 대상이 아니라 보호 룰`이라는 방향과 맞다.  
  참고: https://docs.freqtrade.io/en/latest/stoploss/
- KRX 코스닥 매매거래제도: 호가 단위와 매매수량 단위가 가격대/시장별로 정해져 있다. 주문 직전 호가 단위 보정과 1주 단위 제약 검증은 계속 유지해야 한다.  
  참고: https://regulation.krx.co.kr/contents/RGL/03/03020100/RGL03020100.jsp

비교 결과, 이 문서의 방향은 대체로 타당하다. 다만 구현 시 `AI 판단 단계`와 `주문 실행/리스크 단계`를 절대 섞지 않아야 한다. AI가 BUY/SELL 의견을 내더라도 주문 전 gate와 hard risk rule이 최종 통제권을 가져야 한다.

## 현재 코드와의 연결

새 구조는 완전히 새로 만드는 것이 아니라 기존 부품을 재배치하고 책임을 선명하게 만드는 방향이 적합하다.

현재 재사용 가능한 코드:

- `services/candidate_scoring_service.py`: 시장 스캔 후보 점수화. 현재는 거래량/급등/급락/보유/현금/뉴스 압력 중심이다.
- `services/pre_analysis_gate_service.py`: 종목별 Tier1 전 deterministic gate. 현금 부족, 데이터 부족, 강한 하락 추세를 막는다.
- `services/deterministic_final_gate_service.py`: Tier2 전 confidence/RR/손절/매수가능수량 gate.
- `services/deterministic_prompt_context_service.py`: AI prompt에 deterministic context를 넣는 역할.
- `services/tier1_analysis_cache_service.py`: 동일 조건 Tier1 결과 cache. Tier1 LLM 제거 후에는 최종 AI 판단 cache로 역할 변경 가능하다.
- `services/holdings_precheck_service.py`: 보유 종목 LLM 전 precheck. 현재는 `holding_policy` 기반 SELL/HOLD skip을 판단한다.
- `services/holdings_review_cache_service.py`: 보유 재평가 LLM 결과 cache.
- `strategy/holding_policy.py`: 보유일, 손실, 목표가, 신뢰도 등 보유/청산 fallback 판단.
- `agent/trading_agent.py`: `_analyze_and_trade`, `_tier1_analysis`, `_tier2_review`가 현재 매수/종목 분석 핵심 경로다.
- `scheduler/scheduler.py`: `_intraday_holdings_review`, `_smart_liquidation`이 보유종목 재평가/청산 경로다.
- `agent/decision_maker.py`: 실제 주문, 체결 확인, SELL 보유수량 감소 추론, BUY lot 청산 손익 연결 경로다.

구현 방향:

- 매수는 `CandidateScoringService`와 `PreAnalysisGateService`를 확장해 Tier1 LLM 역할을 대체한다.
- 기존 `_tier2_review`는 이름과 prompt를 정리해 `final_ai_review` 역할로 유지한다.
- `DeterministicFinalGateService`는 AI 이후 주문 전 gate로 계속 유지한다.
- 매도는 `HoldingsPrecheckService`를 확장해 hard sell rule과 상태 점수화를 분리한다.
- `DecisionMaker`의 체결/청산 기록 경로는 건드리지 않고, 매도 신호 생성부와 UI event 표시만 정리한다.

## 목표

1. 매수 후보의 LLM 호출 수를 줄이고 장중 의사결정 지연을 낮춘다.
2. AI는 명확한 스킵 판단이 아니라 가치가 높은 최종 판단에 집중시킨다.
3. 매도는 AI 대기 때문에 손절/청산이 지연되지 않게 한다.
4. 매수와 매도 각각의 decision event, skip reason, AI 사용 사유를 관측 가능하게 남긴다.
5. 첫 구현은 shadow/관측 중심으로 시작하고, 실주문 차단/실행 정책은 테스트와 운영 표본 확인 후 승급한다.

## 핵심 원칙

- deterministic 단계는 BUY를 직접 만들지 않는다. 매수에서는 `SKIP`, `HOLD`, `AI_REVIEW_CANDIDATE`까지만 만든다.
- hard risk는 AI보다 우선한다. 손절, 장 마감 강제청산, 브로커 보유 불일치 같은 매도 사유는 AI가 뒤집지 않는다.
- AI는 단일 최종 판단으로 축소한다. 기존 Tier2급 분석을 최종 AI 판단으로 사용한다.
- 매수 AI와 매도 AI의 prompt와 판단 기준은 분리한다.
- 리스크 성향은 필터 임계값, 점수 가중치, 손절/익절 허용 폭에 반영한다.
- 주문 실행은 별도 책임이다. AI/점수화 단계는 주문을 직접 내지 않고 `TradeSignal` 후보만 만든다.
- 주문 직전에는 항상 계좌, 주문 가능 수량, 호가 단위, 중복 주문, 일일 손실/거래 제한을 재검증한다.

## 전체 구조

```text
시장/실시간 이벤트
→ 데이터 수집
→ 매수 후보와 보유 포지션 분리

매수 후보:
  1차 deterministic 대량 필터
  → 2차 deterministic 점수화/top-N
  → 3차 AI 최종 판단
  → 주문 전 리스크/호가/계좌 gate
  → 주문

보유 포지션:
  1차 hard sell rule
  → 2차 상태 점수화/분류
  → 3차 AI 보유/청산 판단
  → 주문 전 리스크/호가/체결 gate
  → 주문 또는 유지
```

## 매수 파이프라인

현재 코드 기준으로는 `CandidateScoringService → PreAnalysisGateService → final AI review → DeterministicFinalGateService → DecisionMaker` 흐름으로 정리하는 것이 가장 자연스럽다.

### 1차: 대량 필터

목적은 명백히 볼 필요 없는 후보를 빠르게 제거하는 것이다.

대표 필터:

- 매수 가능 현금 부족
- 최소 주문 수량/금액 미달
- 거래대금 부족
- 호가/가격 데이터 부족
- 장 마감 임박 신규 매수 제한
- 이미 보유 중이거나 pending 주문 존재
- 최근 분석 cooldown
- 강한 하락 추세
- 과열 추격 매수 위험
- 비용 대비 기대 edge 부족
- 뉴스/공시 고위험 이벤트
- 리스크 성향과 맞지 않는 변동성

초기 구현에서는 이미 있는 `PreAnalysisGateService`를 확장한다. 신규 필터를 한 번에 많이 켜기보다 다음 순서로 승급한다.

1. 이미 운영 표본이 있는 현금 부족/데이터 부족/강한 하락 추세.
2. 비용 대비 edge 부족과 RR 계산 불가.
3. 마감 임박 추격 매수/과열.
4. 뉴스 고위험 차단. 단, 뉴스 hard block은 rollout 표본이 충분할 때만 실제 차단한다.

출력:

- `SKIP`: AI 호출 없이 종료
- `HOLD`: 관심은 있으나 현재 진입하지 않음
- `CONTINUE`: 2차 점수화로 전달

### 2차: deterministic 점수화

목적은 AI가 볼 후보를 상위 일부로 압축하는 것이다.

현재 `CandidateScoringService`는 시장 스캔 후보 점수화에 이미 존재한다. 다만 지금은 후보 생성/요약 성격이 강하므로, Tier1 LLM 대체용으로 쓰려면 다음 보강이 필요하다.

점수 요소:

- 거래대금/유동성
- 당일 등락률과 과열도
- 일봉 추세
- 분봉 추세
- VWAP 위치
- RSI 구간
- MACD histogram 방향
- 거래량 증가율
- 손익비
- 뉴스 긍정/부정 압력
- 시장 국면 적합도
- 리스크 성향 적합도
- 최근 실패/중복 분석 cooldown

추가 필요 항목:

- 점수 breakdown을 구조화해 저장한다.
- 점수 기준으로 `AI_REVIEW_CANDIDATE`, `WATCH`, `SKIP_LOW_SCORE`를 명확히 나눈다.
- 보유 종목은 매수 후보 점수화에서 제외하고 매도/보유 파이프라인으로 보낸다.
- top-N은 리스크 성향과 cycle 상황에 따라 동적으로 계산한다.

출력:

- `AI_REVIEW_CANDIDATE`: AI 최종 판단 대상으로 선정
- `WATCH`: 후보는 좋지만 AI 호출 우선순위 미달
- `SKIP_LOW_SCORE`: 점수 부족

top-N 정책 예:

- 안정형: 상위 1~2개, 점수 기준 높게
- 중립형: 상위 2~3개, 표준 기준
- 공격형: 상위 3~5개, 모멘텀 가중치 확대

### 3차: AI 최종 판단

기존 Tier2급 분석을 매수 최종 판단으로 사용한다.

구현 시 이름은 `Tier2`를 그대로 둘 수 있지만, 의미는 `final_ai_review`에 가깝다. 새 구조에서는 Tier1 LLM이 없으므로 prompt에 들어가는 `tier1_analysis` 입력은 deterministic summary로 대체해야 한다.

AI 입력:

- 종목 기본 정보
- 현재가/등락률/거래량
- 일봉/분봉 요약
- deterministic 필터 통과 사유
- deterministic 점수와 항목별 breakdown
- 뉴스 context
- 계좌/현금/보유 종목 수
- 리스크 성향
- 주문 가능 수량 범위
- 비용/호가 제약

AI 출력:

- `BUY`
- `HOLD`
- `SKIP`
- confidence
- entry price
- stop loss
- take profit
- trailing stop
- position sizing hint
- 핵심 근거
- 주요 리스크

AI 출력 후에도 주문 전 gate는 유지한다.

- 수량/금액 cap
- 일일 거래 수 cap
- 포지션 비중 cap
- 호가 단위 보정
- 손절가/목표가 유효성
- 중복 주문 방지
- provider timeout/cooldown guard

## 매도 파이프라인

매도는 매수보다 보수적으로 설계한다. 이미 자본이 노출되어 있으므로 AI 호출을 줄이는 것보다 위험 대응 지연을 막는 것이 우선이다.

현재 코드 기준으로는 `scheduler._intraday_holdings_review`, `scheduler._smart_liquidation`, `HoldingsPrecheckService`, `strategy.holding_policy`, `DecisionMaker` 경로를 정리하는 작업이다. 매도는 `TradingAgent._analyze_and_trade`의 매수 후보 경로와 섞지 않는 것이 좋다.

### 1차: hard sell rule

AI 없이 즉시 처리하는 영역이다.

대표 사유:

- hard stop loss 이탈
- trailing stop 이탈
- 장 마감 강제청산 조건
- 최대 보유일 초과
- 브로커 보유에서 사라졌지만 DB open lot이 남은 경우
- pending sell/order 불일치 보정
- 현재가 조회 실패로 인한 review required
- 주문 체결 상태와 보유 수량 불일치
- 거래정지/상장폐지/회생/부도 등 고위험 공시

초기 적용에서 `현재가 조회 실패`는 hard sell이 아니라 `REVIEW_REQUIRED`로 둔다. 데이터가 불확실한 상태에서 시장가 매도를 자동 실행하는 것은 운영 리스크가 크다.

출력:

- `SELL_NOW`: AI 없이 매도 주문 진행
- `RECONCILE_ONLY`: 실제 주문이 아니라 DB/브로커 정합성 보정
- `REVIEW_REQUIRED`: 데이터 부족으로 자동 매도하지 않고 확인 필요
- `CONTINUE`: 2차 상태 점수화로 전달

중요 정책:

- hard stop 이탈은 AI가 뒤집지 않는다.
- 데이터가 부족하면 즉시 매도하지 않는다. `REVIEW_REQUIRED`로 남기고 운영자가 볼 수 있게 한다.
- 브로커 보유 불일치는 매매 신호가 아니라 정합성 작업으로 처리한다.

### 2차: 보유 상태 점수화

목적은 보유 포지션을 상태별로 분류하고 AI 검토 대상을 제한하는 것이다.

이 단계는 현재 `HoldingsPrecheckService`를 확장하는 것이 맞다. 다만 기존 precheck는 skip 여부 중심이므로, 새 구현에서는 `PositionReviewDecision` 같은 구조체로 상태/점수/사유를 분리하는 편이 낫다.

분류:

- `CLEAR_HOLD`: 명확한 보유
- `WATCH`: 감시 필요
- `AI_REVIEW`: AI 판단 필요
- `SELL_CANDIDATE`: 매도 후보
- `PARTIAL_TAKE_PROFIT_CANDIDATE`: 부분 익절 후보

점수 요소:

- 현재 손익률
- entry 대비 stop/target 위치
- 목표가 도달률
- trailing high 대비 하락률
- 보유 기간
- AI 최초 confidence
- 최근 분봉 추세
- 일봉 추세 훼손 여부
- 거래량 약화
- 시장 국면 악화
- 뉴스 부정 압력
- 같은 섹터 동반 약세
- 장 마감까지 남은 시간
- 리스크 성향

예시 정책:

- 안정형: 손실 확대 전 `AI_REVIEW`를 빨리 올리고, 부분 익절 기준을 낮춘다.
- 중립형: stop/target과 추세 훼손을 균형 있게 반영한다.
- 공격형: 수익 포지션은 더 길게 가져가되 hard stop은 유지한다.

### 3차: AI 보유/청산 판단

AI는 모든 보유 종목을 매번 보지 않는다. `AI_REVIEW`, `SELL_CANDIDATE`, `PARTIAL_TAKE_PROFIT_CANDIDATE`만 본다.

매도 AI prompt는 매수 최종 판단 prompt와 분리한다. 같은 `FINAL_REVIEW_PROMPT`를 계속 쓰면 BUY/SELL 기준이 섞여 설명과 UI 표시가 흐려질 수 있다.

AI 입력:

- 매입가/현재가/수량/손익률
- active stop loss / take profit / trailing stop
- 목표가 도달률
- 보유 기간과 남은 허용 기간
- 최근 일봉/분봉 추세
- 뉴스 context
- 시장/섹터 상태
- 기존 매수 근거
- deterministic 상태 점수와 분류 사유
- 리스크 성향

AI 출력:

- `HOLD`
- `SELL`
- `PARTIAL_SELL`
- `TIGHTEN_STOP`
- `RAISE_TRAILING_STOP`
- confidence
- 매도 비율
- 새 stop loss
- 새 take profit
- 근거
- 반대 시나리오

AI 출력 제한:

- hard stop 이탈 종목은 AI 판단 대상이 아니다.
- AI가 stop loss를 entry와 너무 가깝게 만들면 리스크 성향별 최소/최대 손절폭으로 보정한다.
- AI가 `HOLD`를 내도 주문/체결/보유 정합성 문제는 별도 보정한다.

## 리스크 성향 반영

### 안정형

- 매수 top-N 축소
- 거래대금/추세/손익비 기준 강화
- 손절폭 상대적으로 좁게
- 부분 익절 기준 낮게
- 뉴스 부정 압력 가중치 높게
- `WATCH`에서 `AI_REVIEW`로 승급하는 기준 낮게

### 중립형

- 표준 top-N
- 표준 손절/익절 범위
- 추세와 손익비 균형
- 부분 익절은 목표가 근처 또는 탄력 둔화 시 검토

### 공격형

- 매수 top-N 확대
- 모멘텀/거래량 가중치 확대
- 손절폭 상대적으로 넓게
- 수익 포지션은 trailing 기반으로 더 길게 보유
- 단, hard stop과 일일 손실 한도는 유지

## 관측성

각 단계는 decision event와 activity log에 사유를 남긴다.

매수 기록 필드:

- `buy_stage`: `FILTER`, `SCORING`, `AI_FINAL`, `ORDER_GATE`
- `filter_reason`
- `score_total`
- `score_breakdown`
- `rank`
- `top_n_limit`
- `ai_review_selected`
- `ai_provider`
- `ai_latency_ms`

매도 기록 필드:

- `sell_stage`: `HARD_RULE`, `POSITION_SCORING`, `AI_REVIEW`, `ORDER_GATE`, `RECONCILIATION`
- `sell_reason`
- `position_state`
- `position_score`
- `hard_stop_triggered`
- `partial_sell_ratio`
- `active_stop_loss`
- `active_take_profit`
- `trailing_stop_pct`
- `ai_provider`
- `ai_latency_ms`

운영 화면에는 다음을 분리해서 보여준다.

- AI 없이 스킵한 매수 후보
- 점수화 후 AI로 보낸 후보
- AI가 최종 BUY/HOLD/SKIP한 후보
- hard rule로 매도된 포지션
- AI 검토 후 매도/보유/부분익절된 포지션
- 데이터 부족으로 `REVIEW_REQUIRED`가 된 포지션

## 구현 단계 제안

### Phase 1: 문서/테스트 설계

- 매수/매도 파이프라인 책임 경계 확정
- 기존 서비스 재사용 범위 정리
- 신규 테스트 fixture 설계
- 운영 metric 이름 확정
- 이 단계에서는 운영 코드 변경 없음.

### Phase 2: 매수 Tier1 LLM 제거 shadow

- 기존 Tier1 LLM 호출 전 deterministic filter/scoring 결과를 기록
- 기존 Tier1/Tier2 결과와 shadow 비교
- false negative 후보의 forward return 확인
- 실주문 흐름은 변경하지 않음
- 이 단계의 목표는 `Tier1 LLM을 제거해도 놓치는 후보가 어느 정도인지`를 먼저 확인하는 것이다.

2026-05-08 1차 구현:

- `DETERMINISTIC_TIER1_FAST_GATE_MODE` 설정을 추가했다.
- 값은 `OFF`, `SHADOW`, `ENFORCE`를 지원한다.
- 빈 값은 기존 `DETERMINISTIC_TIER1_FAST_GATE_ENABLED` boolean을 따르는 legacy mode다.
- `SHADOW`에서는 deterministic fast gate가 `HOLD`를 내도 Tier1 LLM을 건너뛰지 않는다.
- 대신 `DETERMINISTIC_TIER1_FAST_GATE_SHADOW` decision event를 남긴다.
- 이 event에는 `would_skip_tier1`, `score`, `reason_code`, gate detail이 들어간다.
- 이 단계는 주문 판단을 변경하지 않고 비교 표본을 쌓기 위한 것이다.

### Phase 3: 매수 Tier1 LLM 대체 적용

- Tier1 LLM 호출 제거
- deterministic score top-N만 AI 최종 판단으로 전달
- AI 최종 판단은 기존 Tier2 provider 정책 사용
- `AI_SKIPPED`와 decision event로 절감량 기록
- `FINAL_REVIEW_PROMPT`의 `tier1_analysis` 필드는 deterministic summary 입력을 받을 수 있게 변경한다.

### Phase 4: 매도 hard rule/상태 점수화 분리

- hard sell rule을 AI 검토보다 앞에 고정
- `REVIEW_REQUIRED`와 `RECONCILE_ONLY`를 매도 신호와 분리
- 보유 상태 점수화 결과를 decision event에 기록
- 명확 HOLD skip은 기본 OFF로 시작
- 손절/트레일링/강제청산은 AI provider timeout과 무관하게 실행되어야 한다.

### Phase 5: 매도 AI 최종 판단 적용

- `AI_REVIEW`, `SELL_CANDIDATE`, `PARTIAL_TAKE_PROFIT_CANDIDATE`만 AI 호출
- 매도 전용 prompt 적용
- 부분 익절/stop 조정 출력 검증
- 운영 표본 확인 후 자동 실행 범위 확대

## 구현 전 확인해야 할 코드 쟁점

- `_tier2_review`가 `tier1_analysis` JSON을 필수 전제로 삼는 부분을 deterministic summary로 바꿔도 prompt 품질이 유지되는지 확인한다.
- 현재 매수 후보와 보유 종목이 같은 `CandidateScoringService` 결과에 섞일 수 있다. 새 구조에서는 보유 종목은 매도 파이프라인으로 명확히 분리한다.
- `HoldingsPrecheckService`의 기존 SELL skip 사유 중 `TradeResult 없음`, `매입가 정보 없음`은 실제 매도 신호가 아니라 데이터 정합성 문제다. 새 구조에서는 `SELL_NOW`가 아니라 `REVIEW_REQUIRED` 또는 `RECONCILE_ONLY`로 분리해야 한다.
- SELL 체결 기록과 BUY lot 청산 손익 연결은 `DecisionMaker`가 담당한다. 매도 신호 고도화에서 이 경로를 우회하면 안 된다.
- UI 실시간 이벤트는 `BUY`, `BUY_CONFIRMED`, `SELL`, `SELL_CONFIRMED`, `REVIEW_REQUIRED`, `RECONCILE_ONLY`를 구분해서 표시해야 한다.
- SQLite write lock 이력이 있으므로, shadow 기록을 과도하게 늘릴 경우 activity log보다 metric/decision event 중심으로 압축 저장한다.

## 테스트 계획

### 매수 단위 테스트

- 현금 부족 후보는 AI 호출 없이 `SKIP`.
- 데이터 부족 후보는 AI 호출 없이 `SKIP`.
- 강한 하락 추세 후보는 AI 호출 없이 `HOLD`.
- 과열 추격 후보는 리스크 성향별로 다르게 처리.
- 점수 상위 top-N만 AI 최종 판단 대상으로 선정.
- 안정형/중립형/공격형에서 top-N과 score threshold가 달라짐.
- AI BUY 출력 후 손절/목표가/수량 gate가 실패하면 주문하지 않음.

### 매도 단위 테스트

- hard stop 이탈은 AI 호출 없이 `SELL_NOW`.
- trailing stop 이탈은 AI 호출 없이 `SELL_NOW`.
- 브로커 보유 불일치는 `RECONCILE_ONLY`로 분리.
- 현재가 조회 실패는 `REVIEW_REQUIRED`이며 즉시 매도하지 않음.
- 수익 중 목표가 근처 후보는 `PARTIAL_TAKE_PROFIT_CANDIDATE`.
- 손실 중이나 hard stop 전 후보는 `AI_REVIEW`.
- 명확 HOLD 후보는 flag가 꺼져 있으면 기존 경로 유지.
- AI가 너무 타이트한 stop을 주면 리스크 성향별 bound로 보정.

### 통합 테스트

- 매수 후보 20개 중 1차 필터/2차 점수화 후 3개만 AI 호출.
- AI timeout이 발생해도 매수 주문은 보수적으로 중단.
- hard sell rule은 AI provider timeout 상태와 무관하게 동작.
- 동일 종목 pending sell이 있으면 중복 매도 주문을 만들지 않음.
- decision event에 stage/reason/score/provider/latency가 남음.

### 운영 검증

- Tier1 LLM 호출 수 감소율
- 평균 cycle 시간 감소
- AI timeout 건수 감소
- deterministic skip 후보의 forward return
- AI 최종 후보의 실제 체결률/수익률
- hard sell rule 매도 후 손실 확대 회피 여부
- `REVIEW_REQUIRED` 발생 빈도와 원인

## 보류할 내용

다음 항목은 첫 적용 범위에서 제외한다.

- AI 여러 개의 consensus 투표
- 동일 prompt를 모든 provider에 동시에 던지는 race 방식
- AI가 hard stop을 취소하는 기능
- deterministic score만으로 즉시 BUY하는 기능
- 데이터 부족 상태에서 보수적 시장가 매도하는 기능

## 결론

매수는 `대량 필터 → 점수화/top-N → AI 최종 판단`으로 단순화한다. 기존 Tier1 LLM의 역할은 deterministic filter/scoring으로 대체하고, AI는 기존 Tier2급 최종 판단만 수행한다.

매도는 같은 방식으로 단순화하면 안 된다. 매도는 `hard rule 즉시 대응 → 보유 상태 점수화 → 필요한 경우 AI 판단`으로 분리한다. 손절/정합성/강제청산은 AI보다 우선하고, AI는 애매한 보유/부분익절/청산 판단에만 사용한다.
