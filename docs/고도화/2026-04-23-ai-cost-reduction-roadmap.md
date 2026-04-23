# AI 보강 및 비용 절감 로드맵 (2026-04-23)

## 목표

AI를 없애는 것이 목표가 아니다. 현재 쓰는 Tier1/Tier2 AI는 유지하되, AI가 더 좋은 판단을 하도록 입력 품질을 높이고, 코드/규칙/통계로 명확히 처리 가능한 부분은 먼저 정리한다. 비용, 지연, 실패율을 줄이되 매매 안전성은 낮추지 않는다.

원칙:

- AI는 "가치가 높은 애매한 판단", "복합 맥락 해석", "서술형 리뷰"에 집중시킨다.
- 명확한 리스크, 가격/수량/세션/공시 규칙은 코드가 먼저 판단한다.
- deterministic 단계는 AI를 대체하기 위한 장치가 아니라 AI에 넣을 후보/맥락을 정제하는 장치다.
- 실거래 차단 로직은 TDD와 shadow 검증 후 승급한다.
- 관심사 분리: 수집, 분류, 스코어링, 게이트, 리포트, 주문 실행을 섞지 않는다.
- 기존 provider fallback은 유지하되, 호출 전 deterministic skip/caching을 먼저 적용한다.

## 현재 AI 사용 지도

| 기능 | 현재 AI 사용 | 위치 | 비AI 보강 가능성 | 우선순위 |
| --- | --- | --- | --- | --- |
| 시장 스캔/후보 선정 | Tier1 1회 호출 | `agent/market_scanner.py` | 높음 | P1 |
| 종목별 심층 분석 | 후보별 Tier1 호출 | `agent/trading_agent.py:_tier1_analysis` | 중간 | P1 |
| Tier2 최종 검토 | BUY/SELL 후보별 Tier2 호출 | `agent/trading_agent.py:_tier2_review` | 중간 | P1 |
| 뉴스 번역/감성 | 해외 뉴스별 NEWS_LLM 호출 | `services/news_translation_service.py` | 높음 | P0 일부 완료 |
| 뉴스 게이트 | 규칙 기반 | `services/news_signal_service.py` | 이미 비AI | 유지 |
| 보유종목 장중 재평가 | Tier1 일괄 호출 + 코드 폴백 | `scheduler/scheduler.py:_intraday_holdings_review` | 중간 | P2 |
| 스마트 청산 | Tier1 일괄 호출 + 코드 폴백 | `scheduler/scheduler.py:_smart_liquidation` | 중간 | P2 |
| 장마감 리뷰 | 수동 LLM 호출 | `agent/trading_agent.py` 장외 사이클 | 낮음 | P3 |
| 리뷰 기반 규칙 생성 | LLM 리뷰 결과 파싱 | `analysis/feedback/trading_rules.py` | 중간 | P3 |
| 수동 분석 | manual provider 호출 | `llm_factory.generate_manual` 경로 | 낮음 | P4 |

## 참고 근거

- OpenDART 주요사항보고서는 전환사채, 소송, 회생, 상장폐지 등 주요 경영/재무 이벤트를 구조화해 제공한다.
- KRX는 거래정지를 투자자 보호와 시장 관리를 위한 조치로 설명한다.
- KRX는 불성실공시 법인에 대해 매매거래정지, 관리종목 지정, 상장폐지 심사 가능성을 둔다.

따라서 공시/거래소 이벤트는 LLM 해석보다 결정론적 리스크 분류가 우선이다.

## 기능별 개선 계획

### 1. 뉴스 수집/번역/감성

현재:

- 수집 자체는 비AI다.
- 해외 번역/요약을 켜면 NEWS_LLM이 기사별로 호출된다.
- 번역을 끄면 감성도 대부분 중립으로 남아 뉴스 게이트 효과가 낮았다.
- 2026-04-23 1차 구현으로 `news_risk_classifier`, `news_topic_mapper`를 추가했다.
- 2026-04-23 2차 구현으로 기존 `news_items`에 deterministic enrichment를 재적용하는 backfill 서비스를 추가했다.

권장:

- 기본값은 `NEWS_TRANSLATE_FOREIGN_ENABLED=false`.
- 공시/시장공지 리스크는 deterministic classifier로 처리한다.
- 해외 뉴스는 번역 없이 영문 키워드로 국내 섹터를 매핑한다.
- 번역은 사람이 화면에서 읽을 필요가 있거나, 중요도가 높은 기사만 수동/오프피크 backfill로 처리한다.

운영 반영:

- 2026-04-23 16:09 KST 기준 `POST /api/v1/admin/news/backfill-enrichment?limit=100&apply=false` dry-run 정상.
- dry-run 결과 변경 후보 1건을 `apply=true`로 반영했다.
- 반영 내용: Seeking Alpha의 TSM 애리조나 패키징 공장 기사에 `반도체` 토픽 metadata 추가.
- 적용 후 같은 범위 dry-run은 `changed_count=0`으로 재확인됐다.

추가 과제:

- DB 초기화 후 `stocks` 테이블이 비면 뉴스-종목 매핑이 사실상 불가능하므로 국내 종목 universe bootstrap을 별도 구현.
- KRX/YONHAP 국내 일반 뉴스의 리스크 키워드 확장.
- 정책/매크로 이벤트 source/type 추가.
- source별 precision/recall 대시보드: 몇 건이 실제 후보 종목과 연결됐는지, 차단 후보 수익률이 어땠는지.

TDD 후보:

- 거래정지/불성실공시/상장폐지/소송/전환사채 fixture.
- 영문 `AI chip export controls` -> 반도체 섹터 fixture.
- 기존 명시 sentiment는 덮어쓰지 않는 fixture.
- backfill은 dry-run과 실제 update를 분리.

### 2. 시장 스캔/후보 선정

현재:

- 거래량 상위, 급등락, 보유종목, 성과 요약을 모아 Tier1이 시장 국면과 후보를 한 번에 고른다.
- 기존 2단계 LLM을 1단계로 줄인 상태라 이미 비용 절감이 일부 되어 있다.

문제:

- 후보 선별은 데이터 랭킹/필터/점수화로 상당 부분 대체 가능하다.
- 매 사이클 AI가 후보를 고르면 시장 변동이 작아도 비용이 계속 발생한다.
- 후보 품질이 낮으면 Tier1/Tier2가 비싼 판단을 해도 결과가 좋아지기 어렵다.

현재 구현:

- `CandidateScoringService`를 추가했다.
- 현재 입력은 거래량 랭킹, 급등/급락, 보유종목, 현금이다.
- 출력은 후보 점수, source, 1주 매수 가능 여부, 보유 후보 여부, 근거 문구다.
- 시장 스캔 프롬프트에 deterministic 후보 top-N 요약을 함께 넣어 AI가 더 정제된 입력으로 시장 국면과 최종 종목을 판단하게 했다.

다음 확장:

- 최근 분석/매매 이력 cooldown 반영.
- 뉴스 압력/리스크 감점 반영.
- 전략 타입 추천과 제외 사유 코드 정교화.

대체 규칙 예:

- 1주 매수 불가 종목 제외.
- 스팩/ETN/런타임 매매불가 종목 제외.
- 거래량 상위 + 등락률 + 변동성 + 현금 제약으로 후보 3~8개 선정.
- 최근 분석한 종목은 cooldown.
- 뉴스 리스크가 큰 종목은 후보 점수 감점.

TDD 후보:

- 현금 부족 종목 제외.
- 최근 분석 cooldown 제외.
- 보유종목은 매도 검토 후보로 별도 유지.
- 거래량/등락률 점수로 deterministic top-N 선정.

### 3. 종목별 Tier1 분석

현재:

- 가격/일봉/분봉/차트 분석/피드백 컨텍스트를 넣고 종목별 Tier1 호출.
- 현금 부족, 데이터 부족은 이미 LLM 전에 스킵한다.
- LLM 응답 가격/신뢰도는 코드로 재검증한다.

문제:

- 모든 후보에 AI를 호출하면 후보 수에 비례해 비용이 증가한다.
- 단순 HOLD/스킵은 기술/리스크 규칙으로 먼저 걸러낼 수 있다.

현재 구현:

- `PreAnalysisGateService`를 추가했다.
- Tier1 직전에 `INSUFFICIENT_CASH`, `MISSING_CORE_MARKET_DATA`, `BEARISH_PRE_GATE`를 deterministic하게 차단한다.
- `BEARISH_PRE_GATE`는 비보유 종목에만 적용하며, 차트 종합 시그널이 `BEARISH`이고 confidence가 0.6 이상일 때 Tier1 호출을 생략한다.
- skip 사유는 activity log detail에 `pre_analysis_gate` 코드로 남긴다.

다음 확장:

- 거래량 부족, 손익비 계산 불가, 뉴스 리스크 과다, 비용 대비 edge 부족까지 확대.
- 차트/추세/리스크 점수와 뉴스/비용 맥락을 정리해 Tier1 프롬프트 입력 품질을 높인다.
- 명확한 제외 대상만 Tier1 전에 제거하고, 판단이 필요한 후보는 계속 Tier1로 보낸다.

TDD 후보:

- 현재가/일봉 없음 -> Tier1 미호출.
- 강한 하락 추세 + BUY 후보 -> Tier1 미호출 또는 HOLD.
- 최근 동일 종목 동일 조건 분석 캐시 hit -> Tier1 미호출.
- 기술 점수 중립/약함 -> Tier1 미호출.

### 4. Tier2 최종 검토

현재:

- Tier1이 BUY/보유 SELL 후보를 내면 Tier2가 최종 승인한다.
- 이후 비용 게이트와 뉴스 게이트도 수행된다.

문제:

- Tier2는 비싼 검토 단계인데, 코드로 이미 강하게 차단 가능한 후보까지 호출될 수 있다.
- Tier2가 수량/가격을 제안하지만 주문 수량은 계좌/리스크/호가 제약을 따라야 한다.

권장:

- Tier2 호출 전 `DeterministicFinalGate`를 둔다.
- 비용/손익비/최소 신뢰도/세션/매수가능수량/뉴스 리스크를 모두 먼저 통과해야 Tier2 호출.
- Tier2는 유지하되, 이미 코드상 불가능하거나 위험한 후보를 넘기지 않는다.
- Tier2에는 수량/가격 제약과 뉴스/비용/차트 근거를 구조화해서 넘겨 판단 품질을 높인다.

TDD 후보:

- 비용 게이트 실패 시 Tier2 미호출.
- 뉴스 리스크 차단 시 Tier2 미호출.
- Tier1 confidence 낮음 -> Tier2 미호출.
- Tier2 호출 전후 결정 차이와 성과를 기록.

### 5. 보유종목 장중 재평가

현재:

- 보유종목 전체를 Tier1 한 번에 넣어 HOLD/SELL/ADD_BUY를 판단한다.
- LLM 실패 시 `holding_policy.evaluate_overnight_hold` 코드 룰로 폴백한다.

문제:

- 30분 간격 호출은 누적 비용과 지연이 커질 수 있다.
- 대부분 보유종목은 가격/손절/목표/보유일 규칙으로 충분히 유지/청산이 가능하다.

권장:

- 코드 룰로 명확한 위험/정상 상태를 먼저 태깅하고, LLM은 이 태그와 함께 더 나은 HOLD/SELL/ADD_BUY 판단을 하게 한다.
- 예외 조건: 큰 갭, 뉴스 리스크 발생, 목표/손절 근처, 보유일 임계값 근처, 포트폴리오 현금 부족.
- 보유종목별 last-review cache를 둔다.

TDD 후보:

- 손절/목표/보유일 명확 -> LLM 미호출.
- 뉴스 리스크 신규 발생 -> LLM 또는 코드 SELL 권고 경로.
- 같은 종목 30분 내 조건 변화 없음 -> 재평가 스킵.

### 6. 스마트 청산

현재:

- 장마감/청산 쪽에서 보유종목 전체를 Tier1로 판단하고, 실패 시 코드 룰 폴백.

권장:

- `holding_policy` 결과를 LLM 입력의 구조화된 사전 판단으로 제공한다.
- 손실 과대, 목표 도달, 보유일 초과, TradeResult 없음처럼 명확한 상태는 별도 reason code로 표시한다.
- LLM은 이 reason code를 참고해 오버나이트 허용 여부와 예외 판단을 한다.

TDD 후보:

- 명확한 SELL 조건은 LLM 미호출.
- 명확한 HOLD 조건은 LLM 미호출 또는 shadow-only.
- 애매한 구간만 LLM 호출.

### 7. 장마감 리뷰와 규칙 생성

현재:

- 장마감 리뷰는 LLM이 서술형으로 생성한다.
- 리뷰 결과에서 트레이딩 규칙을 자동 생성한다.

문제:

- 장마감 리뷰는 실시간 매매 루프가 아니므로 비용은 덜 급하지만, 매일 호출된다.
- 규칙 생성은 LLM 출력에 의존하면 재현성이 떨어질 수 있다.

권장:

- 수치 리포트는 deterministic report generator가 생성한다.
- LLM은 "해설"과 "내일 주의사항"만 생성한다.
- 규칙 생성은 LLM 문장보다 정량 조건에서 생성한다.

TDD 후보:

- 거래 0건이면 LLM 리뷰 생략.
- 성과 지표 기반 규칙 생성.
- LLM 리뷰 실패해도 deterministic daily report 저장.

### 8. 수동 분석

현재:

- 사용자가 수동 분석을 트리거하면 manual provider를 호출한다.

권장:

- 수동 분석은 사용자가 의도적으로 비용을 쓰는 경로라 유지한다.
- 다만 결과 캐시와 provider/model 선택 UI를 명확히 한다.
- 동일 입력 재분석 시 캐시 사용 여부를 물어볼 수 있다.

### 9. 관측성과 비용 추적

현재:

- `observability_service.record_llm_call`로 LLM 호출 기록이 있다.
- Admin에 provider 상태와 일부 사용량이 노출된다.

권장:

- 기능별 LLM 호출 수/평균 시간/실패율/토큰 또는 비용 추정치를 별도 집계한다.
- "AI 호출 전 deterministic skip 수"를 같이 기록한다.
- 비용 절감 작업은 호출 수 감소와 성과 악화 여부를 같이 봐야 한다.

TDD 후보:

- 각 skip gate가 `AI_SKIPPED` metric을 남기는지.
- 기능별 LLM 호출 예산 초과 시 degrade mode로 전환하는지.

## 단계별 실행 순서

## 2026-04-23 코드 검증 업데이트

- 뉴스 deterministic enrichment와 backfill 서비스/API는 코드 구현, 테스트, 운영 API 확인까지 완료됐다.
- `POST /api/v1/admin/news/backfill-enrichment`는 운영 서버에서 정상 동작한다.
- `LLM_SLOW_CALL_WARN_SEC` 기반 지연 경고도 코드/테스트/커밋 및 운영 서버 재시작 반영이 완료됐다.
- canonical decision event, forward return labeling job, decision benchmark read-only API는 구현 완료됐다.
- 장마감 청산 이후 자동 BUY 차단과 청산 후 자동 재스캔 비활성화도 구현 및 운영 설정 확인이 완료됐다.
- `POST /api/v1/admin/stocks/bootstrap-universe` 기반 최소 종목 universe bootstrap도 구현됐다. 보유/미체결/거래량·등락률 랭킹에서 관측된 국내 종목을 `stocks`에 dry-run/apply 할 수 있다.
- `CandidateScoringService`는 구현 완료됐다.
- `PreAnalysisGate`는 구현 완료됐다.
- `DeterministicFinalGate`, `AI_SKIPPED` metric은 아직 구현되지 않았다.
- 세부 진행 현황은 `docs/고도화/2026-04-23-enhancement-status.md`를 기준 문서로 둔다.

### Phase 1: 뉴스와 후보 선정 입력 보강

1. 뉴스 리스크 분류/테마 매핑 backfill. 코드/테스트/운영 적용 완료.
2. 국내 종목 universe bootstrap. 코드/테스트는 완료됐고, 운영 DB에 dry-run/apply 확인이 다음 순서다.
3. 시장 스캔 deterministic 후보 점수에 cooldown/뉴스 감점을 붙이고, AI 시장 해설 optional 분리를 검토.
4. `DeterministicFinalGate` 설계 및 연결.

### Phase 2: Tier1/Tier2 입력 품질과 호출 전 gate 강화

1. `DeterministicFinalGate` 추가.
2. 동일 종목/동일 조건 분석 캐시.
3. Tier1/Tier2 프롬프트에 deterministic reason code와 점수 입력.
4. `AI_SKIPPED` metric 추가.

### Phase 3: 보유종목 재평가 비용 절감

1. `holding_policy` primary 전환.
2. 예외 조건에서만 LLM 호출.
3. 보유종목 review cooldown/cache.

### Phase 4: 장마감 리뷰 구조화

1. deterministic daily report 생성.
2. LLM 해설 optional.
3. 규칙 생성은 정량 지표 기반으로 분리.

## 지금 당장 바꾸지 말아야 할 것

- Tier1/Tier2를 완전히 제거.
- AI가 잘하는 복합 판단을 단순 점수식으로 대체.
- 뉴스 게이트를 검증 없이 강하게 조정.
- LLM 실패 시 주문을 더 공격적으로 실행.
- 한 번에 시장 스캔, 종목 분석, 보유 재평가를 모두 리팩터링.

## 완료 판정 기준

- 기능별 LLM 호출 수가 감소한다.
- 장중 지연이 줄어든다.
- LLM 실패가 매매 루프 실패로 전파되지 않는다.
- deterministic skip/allow 이유가 activity log와 리포트에 남는다.
- shadow 비교에서 수익률/손실 회피가 악화되지 않는다.
