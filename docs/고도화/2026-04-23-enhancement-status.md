# 고도화 진행 현황 점검 (2026-04-23)

## 점검 기준

- 문서 체크박스가 아니라 현재 코드, 테스트, 라이브 서버 응답을 기준으로 판단했다.
- `구현 완료`는 저장소 코드와 테스트가 존재한다는 뜻이다.
- `운영 반영`은 현재 실행 중인 `http://127.0.0.1:9000` 프로세스가 해당 코드를 로드했다는 뜻이다.

## 현재 결론

어제/오늘 진행한 고도화 중 주문 안전, PnL 분리, 뉴스 deterministic enrichment, 뉴스 backfill API, LLM 지연 경고, canonical decision event, forward return labeling, decision benchmark, 장마감 청산 이후 자동 BUY 차단은 코드와 운영 서버에 반영되어 있다.

최근 추가된 AI 비용 절감 축인 `CandidateScoringService`, `PreAnalysisGate`, `DeterministicFinalGate`, `Tier1AnalysisCacheService`, `AI_SKIPPED` metric, `HoldingsPrecheckService`, `HoldingsReviewCacheService`는 코드와 테스트 기준으로 구현 완료 상태다. 다만 이 문서에서 `운영 반영`은 실제 9000 프로세스 재기동과 런타임 확인까지 끝난 항목만 뜻하므로, 최신 보유종목 precheck/review cache는 현재 기준 `코드 반영 완료`로 적는다.

2026-04-23 16:09 KST 기준 `POST /api/v1/admin/news/backfill-enrichment?limit=100&apply=false` dry-run은 정상 응답했고, 변경 후보 1건을 `apply=true`로 반영했다. 재확인 dry-run은 `changed_count=0`으로 같은 범위의 남은 deterministic enrichment 후보가 없었다.

2026-04-24 10:09 KST 기준 `POST /api/v1/admin/stocks/bootstrap-universe?rank_limit=50&apply=false` dry-run은 후보 128건, 생성 128건으로 정상 응답했다. 이후 `apply=true`로 128건을 생성했고, 랭킹 데이터가 호출 사이에 바뀌며 추가 관측된 6건도 2차 `apply=true`로 생성했다. 이 작업은 `stocks` universe upsert만 수행하며 주문은 제출하지 않는다.

## 구현 완료로 확인된 항목

### 주문/운영 안전

- `ORDER_SUBMISSION_MODE=READ_ONLY|SELL_ONLY|FULL` 명시 gate 구현.
- 자동매매 가능 세션 guard 통일.
- 브로커/DB pending reconciliation report 구현.
- stale `PENDING_CONFIRM` 수동 cleanup 구현. 기본은 dry-run.
- Kiwoom 미체결 취소주문 매핑 구현.
- cycle-local cash reservation ledger 구현. 기본은 `SHADOW`, `ENFORCE`에서 차단.
- 강제 청산 재시도 성공 기록 누락 수정.
- 스마트 청산 데이터 수집 실패를 `REVIEW_REQUIRED`/HOLD로 분리. 현재가 조회 실패, open BUY 누락, repository 예외는 즉시 SELL하지 않고 운영 로그에 확인 필요 사유를 남긴다.
- 실시간 구독 우선순위와 polling fallback watchlist 구현. 보유종목은 신규 후보보다 우선 구독되고, 41개 한도에서 밀린 종목은 polling fallback과 Admin observability 상태에 남는다.
- Admin 고위험 액션 confirmation token 서버 검증 구현. 기본값은 호환을 위해 `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED=false`이며, true일 때 reset/manual sell/cancel/cancel-and-sell/stale cleanup apply는 서버 생성 token 없이는 428로 거부된다.

### PnL/리스크

- `PnlTruthService`로 realized trade PnL, broker unrealized PnL, total asset delta를 분리.
- 성과 요약에 `pnl_truth`와 `metric_contract` 노출.
- AI risk tuner hard cap 추가: 일일 거래 수, 단일 주문금액, 단일 포지션 비중.
- `ACCOUNT_EQUITY_DRAWDOWN_GUARD_MODE=OFF|REPORT_ONLY|BLOCK_BUY|KILL_SWITCH` 추가. 기본값은 `REPORT_ONLY`이며, account equity baseline/latest snapshot 기준 총자산 drawdown을 BUY guard warning 또는 차단에 연결.

### 뉴스

- `NewsRiskClassifier` 구현: 거래정지, 상장폐지, 불성실공시, 소송, 횡령/배임, 회생/부도, 전환사채/유상증자, 최대주주변경 등 고신호 리스크를 deterministic `NEGATIVE`로 분류.
- `NewsTopicMapper` 구현: 반도체, 2차전지, 자동차, 인터넷, 방산, 조선 섹터 키워드 매핑.
- `NewsIngestService` 저장 경로에 리스크/토픽 enrichment 반영.
- 기존 `news_items` 재분류용 `NewsEnrichmentBackfillService` 구현.
- 관리자 API `POST /api/v1/admin/news/backfill-enrichment` 구현.
- 뉴스 리포트에 `ingestion.enrichment_by_source` 추가.
- 해외 뉴스 번역 off 상태에서도 원문 저장과 키워드 기반 섹터 매핑은 가능하게 됨.

### LLM/관측성

- Codex 호출은 provider 단위 semaphore로 직렬화되어 동시 CLI 부하를 줄인다.
- `observability_service.record_llm_call`로 provider/model/latency/status 기록.
- `LLM_SLOW_CALL_WARN_SEC` 설정 추가. 기본 30초.
- LLM 호출이 임계 시간을 넘기면 `LLM_CALL / PROGRESS` 활동 로그와 SSE 경고를 남긴다.
- LLM 호출 실패/타임아웃은 `LLM_CALL / ERROR` 활동 로그를 남긴다.
- LLM provider cooldown 오류의 incident fingerprint에서 `(N초 남음)`처럼 매번 바뀌는 잔여 시간을 정규화해 같은 cooldown 장애를 하나의 incident로 누적한다.
- Observability maintenance rollup key의 provider/model `NULL`을 `UNKNOWN`으로 정규화한다.
- 최근 `OBSERVABILITY_MAINTENANCE` 실패는 system preflight의 `observability` WARN으로 노출한다.

## 부분 완료 또는 문서와 다른 항목

### 뉴스 rollout mode

- `NEWS_GATE_ROLLOUT_MODE`를 추가했다.
- 지원 mode는 `OFF`, `POLL_ONLY`, `SHADOW_ONLY`, `BUY_BLOCK_GATE`다.
- 값이 비어 있으면 기존 `NEWS_GATE_ENABLED`, `NEWS_SHADOW_ENABLED`, `NEWS_POLL_ENABLED` boolean 조합을 그대로 따른다.
- 명시적 `BUY_BLOCK_GATE`는 성과 rollout 상태가 `PROMOTE`일 때만 실제 BUY 차단으로 동작한다.
- rollout 조건이 부족하면 자동으로 `SHADOW_ONLY`로 낮춰 평가와 shadow 기록만 수행한다.

### 뉴스 source별 성과

- source별 수집 count, 실패/중복/스킵, enrichment 비율은 일부 볼 수 있다.
- decision event 기준 action/provider/stage/risk gate별 forward return benchmark API는 추가됐다.
- 현재 benchmark는 `event.source`, `strategy_type`, `tier1_decision`, `tier2_decision`, `metadata_json`의 `news_top_contributors.source_code`까지 read-only 집계한다.
- 동일 표본 수 기준 `random_same_count`, `scanner_top_same_count`, `tier1_buy_only`, `tier2_buy_only` control group도 read-only로 추가됐다.
- 이번 확장으로 source별 blocked candidate forward return과 actual buy 대비 평균 수익률 차이를 read-only로 볼 수 있게 됐다.
- 현재 `by_news_source_blocked`, `by_news_source_blocked_comparison`가 추가되어 source별 blocked 후보군과 source별 실제 BUY 후보군을 비교할 수 있다.
- 다만 gate contribution의 인과 추정과 동일 후보군 full attribution은 아직 없음.

### 뉴스 backfill 운영 반영

- `POST /api/v1/admin/news/backfill-enrichment?limit=100&apply=false` dry-run 정상.
- dry-run 결과: 후보 100건, 변경 1건, topic mapped 1건.
- `apply=true` 적용 결과: Seeking Alpha의 TSM 애리조나 패키징 공장 기사에 `반도체` 토픽 metadata 반영.
- 적용 후 재확인 dry-run 결과: 후보 100건, 변경 0건.
- 2026-04-23 당시 로컬 DB 기준 `news_items=1,481`, `stocks=0`, `portfolio_holdings=0`, `orders=0`, `market_snapshots=0`이었다.

### 종목 universe bootstrap 운영 반영

- 2026-04-24 10:09 KST 기준 `POST /api/v1/admin/stocks/bootstrap-universe?rank_limit=50&apply=false` dry-run 정상.
- dry-run 결과: 후보 128건, 생성 128건, 갱신 0건. 소스는 보유 1건, 미체결 0건, 거래량 50건, 등락 상위 50건, 등락 하위 50건이다.
- 1차 `apply=true` 적용 결과: 128건 생성.
- 적용 직후 재확인 dry-run에서 랭킹 데이터 변동으로 추가 생성 후보 4건이 보였고, 2차 `apply=true`에서 추가 관측 후보 6건을 생성했다.
- 거래량/등락 랭킹은 실시간성이 있어 호출 시점마다 후보가 조금 달라질 수 있다. 운영 목적은 비어 있던 `stocks` universe를 최소 관측 universe로 복구하는 것이다.

### Observability maintenance

- raw metric, hourly rollup, reporting service는 구현되어 있다.
- rollup 저장 단계에서 provider/model `NULL`은 `UNKNOWN`으로 정규화된다.
- maintenance 실행 기록이 없으면 새 DB 호환을 위해 preflight는 OK 정보성 상태로 두고, 최근 실패가 있으면 WARN으로 노출한다.

## 최근 구현 완료 항목

### AI 비용/지연 절감

- 국내 종목 universe bootstrap 구현. `POST /api/v1/admin/stocks/bootstrap-universe`로 보유/미체결/거래량/등락률 랭킹 기반 최소 universe를 dry-run/apply 할 수 있다.
- `CandidateScoringService` 구현. 거래량/급등/급락/보유/현금 기반 deterministic top-N 후보 점수를 만들고 시장 스캔 프롬프트에 함께 넣는다.
- `PreAnalysisGate` 구현. 현재는 Tier1 직전에 `INSUFFICIENT_CASH`, `MISSING_CORE_MARKET_DATA`, `BEARISH_PRE_GATE`를 코드로 차단하고 activity log detail에 gate code를 남긴다.
- `DeterministicFinalGate` 구현. 현재는 Tier2 직전에 `CONFIDENCE_GATE`, `RR_RATIO_GATE`, `RR_UNDEFINED_GATE`, `STOP_LOSS_REQUIRED_GATE`, `BUYING_POWER_GATE`를 코드로 차단하고 activity log detail에 gate code를 남긴다.
- 동일 종목/동일 조건 분석 캐시 구현. 같은 종목/전략/현재가/시장국면/보유여부/차트 신호/피드백 컨텍스트 조건이면 짧은 TTL 동안 Tier1 결과를 재사용하며, 수동 provider/model override 호출은 캐시를 우회한다.
- Tier1 비용 pre-gate 구현. Tier1 BUY 분석의 target/current price만으로 edge가 비용 대비 명백히 부족하면 Tier2 호출 전에 차단한다.
- `AI_SKIPPED` metric 구현. `PRE_ANALYSIS_GATE`, `TIER1_CACHE`, `DETERMINISTIC_FINAL_GATE`, `TIER1_COST_GATE`에서 절감된 Tier와 reason code를 execution metric으로 남긴다.
- Tier1/Tier2 deterministic prompt context 구현. 프롬프트에 `Deterministic 사전 판단` 섹션을 추가해 차트 신호, 현금/최소수량, RR 비율, 손절 필수 여부, 매수가능수량을 구조화해 전달한다.
- `HoldingsPrecheckService` 구현. 장중 보유 재평가와 스마트 청산에서 `holding_policy`가 명확한 SELL 사유를 내는 종목은 LLM 전에 걸러 즉시 코드 판단을 사용한다.
- 현재 precheck가 바로 차단하는 사유는 `TradeResult 없음`, `매입가 정보 없음`, `손실 과대`, `보유일 초과`, `AI 신뢰도 저하`, `목표가 도달` 계열이다.
- `HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED=false` 기본값으로 명확한 HOLD skip 경로를 추가했다. 기본값은 보수적으로 꺼두며, 활성화 시 수익권, 신뢰도 0.65 이상, 목표가까지 1% 이상 여유, 최대 보유일 임박 아님 조건을 모두 만족해야 HOLD를 LLM 없이 통과시킨다.
- precheck 평가 자체가 불가능하면 예외를 삼키고 기존 LLM 경로를 그대로 유지해 회귀를 막는다.
- `HoldingsReviewCacheService` 구현. 장중 보유 재평가에서 동일 종목/가격/손익/보유일/활성 임계값/시장 국면/남은 시간 조건이면 짧은 TTL 동안 이전 LLM 결정을 재사용한다.
- 캐시 hit 종목은 `AI_SKIPPED`에 `HOLDINGS_REVIEW_CACHE/CACHE_HIT/TIER1`로 기록한다.
- 보유종목 precheck skip도 `AI_SKIPPED`에 `HOLDINGS_PRECHECK/{SELL|HOLD}/TIER1`로 기록한다.
- Admin observability overview에 `ai_skipped` 요약을 추가했다. stage/reason/tier/symbol/recent 표본을 API에서 확인할 수 있어 HOLD skip 플래그 활성화 전 운영 표본을 볼 수 있다.
- Admin 관측 화면에 `AI Skip` 섹션을 추가했다. 사유별 집계와 최근 표본을 화면에서 확인할 수 있다.
- Decision benchmark 응답에 `ai_skipped_observation`을 추가했다. 단, `AI_SKIPPED`는 forward return이 직접 붙은 표본이 아니므로 수익률 benchmark와 분리된 관측 섹션으로 노출한다.
- 장중 보유 재평가에서 precheck/cache로 LLM을 건너뛴 HOLD/SELL 판단도 `decision_events`에 기록한다. 이 경로는 `reference_price=current_price`를 남기므로 forward return labeling 대상이 된다.

## 아직 미구현 또는 추가 검증이 필요한 핵심 항목

### P0/P1 성격

- intraday forward return 정밀도 개선용 분봉/틱 snapshot history.

### AI 비용/지연 절감 후속

- 보유종목 명확 HOLD skip은 플래그 기반 코드 경로까지 구현 완료. 운영 기본값은 OFF이므로, `AI_SKIPPED/HOLDINGS_PRECHECK` 표본을 본 뒤 활성화 여부를 결정한다.
- 스마트 청산 review cache는 현재 보류한다. `_force_liquidation()`에서 청산 시각에 단발 호출되는 경로라 반복 호출 절감 효과가 작고, 캐시가 청산 직전 최신 판단을 흐릴 수 있다.
- review cache TTL/key 조건 운영 데이터 기준 조정.
- 장중 보유 재평가 precheck/cache 판단은 `decision_events`에 연결 완료. 스마트 청산 단발 판단과 다른 skip gate의 직접 수익률 attribution은 아직 아님.

### Admin UX 후속

- 고위험 액션 confirmation UI flow.
- confirmation 기본값 true 전환 여부 결정.

### 장마감 리스크 관리

- 청산 시각 이후 자동 BUY는 `POST_LIQUIDATION_BUY_BLOCK_ENABLED=true` 기본값으로 주문 직전 차단한다.
- 스마트/강제 청산 완료 후 자동 재스캔은 실행하지 않는다.
- 청산 이후 좋아 보이는 신호는 분석/로그/decision event로 남길 수 있지만, 실제 자동 BUY 주문은 다음 거래일 전까지 막는다.

### 실험/성과 검증

- candidate scanner/Tier/risk 단계별 decision event 세부 연결.
- source별 뉴스 attribution benchmark.
- 동일 후보군 random/scanner-only/Tier-only benchmark.
- source별 뉴스 성과와 차단 후보 사후 수익률.
- backtest same-bar execution 제거.
- fee/fill/report metadata 분리.
- `STABLE_SHORT`/`AGGRESSIVE_SHORT`를 alpha source와 execution profile로 분리.

## 권장 실행 순서

1. `AI_SKIPPED/HOLDINGS_PRECHECK` 표본을 확인한 뒤 `HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED` 활성화 여부를 결정한다.
2. 장중 보유 재평가 review cache TTL/key 조건을 운영 데이터 기준으로 조정한다.
3. 뉴스 gate의 Tier2 전 차단 이동은 shadow/rollout 표본을 더 확인한 뒤 재검토한다.

## 당장 바꾸지 말 것

- 뉴스 gate를 더 공격적으로 켜기.
- Nasdaq을 핵심 판단 소스로 승격.
- Tier1/Tier2를 제거.
- LLM 실패 시 주문을 더 쉽게 통과시키기.
- 청산 이후 장마감 직전 자동 재매수를 허용하기.
