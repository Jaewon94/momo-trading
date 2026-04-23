# 고도화 진행 현황 점검 (2026-04-23)

## 점검 기준

- 문서 체크박스가 아니라 현재 코드, 테스트, 라이브 서버 응답을 기준으로 판단했다.
- `구현 완료`는 저장소 코드와 테스트가 존재한다는 뜻이다.
- `운영 반영`은 현재 실행 중인 `http://127.0.0.1:9000` 프로세스가 해당 코드를 로드했다는 뜻이다.

## 현재 결론

어제/오늘 진행한 고도화 중 주문 안전, PnL 분리, 뉴스 deterministic enrichment, 뉴스 backfill API, LLM 지연 경고, canonical decision event, forward return labeling, decision benchmark, 장마감 청산 이후 자동 BUY 차단은 코드와 운영 서버에 반영되어 있다.

2026-04-23 16:09 KST 기준 `POST /api/v1/admin/news/backfill-enrichment?limit=100&apply=false` dry-run은 정상 응답했고, 변경 후보 1건을 `apply=true`로 반영했다. 재확인 dry-run은 `changed_count=0`으로 같은 범위의 남은 deterministic enrichment 후보가 없었다.

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
- 현재 로컬 DB 기준 `news_items=1,481`, `stocks=0`, `portfolio_holdings=0`, `orders=0`, `market_snapshots=0`이다. 뉴스는 쌓이고 있지만 국내 종목 universe가 비어 있어 종목 attach와 source별 attribution 품질은 제한적이다.

### Observability maintenance

- raw metric, hourly rollup, reporting service는 구현되어 있다.
- rollup 저장 단계에서 provider/model `NULL`은 `UNKNOWN`으로 정규화된다.
- maintenance 실행 기록이 없으면 새 DB 호환을 위해 preflight는 OK 정보성 상태로 두고, 최근 실패가 있으면 WARN으로 노출한다.

## 아직 미구현으로 확인된 핵심 항목

### P0/P1 성격

- intraday forward return 정밀도 개선용 분봉/틱 snapshot history.

### AI 비용/지연 절감

- 국내 종목 universe bootstrap 구현. `POST /api/v1/admin/stocks/bootstrap-universe`로 보유/미체결/거래량/등락률 랭킹 기반 최소 universe를 dry-run/apply 할 수 있다.
- `CandidateScoringService` 구현. 거래량/급등/급락/보유/현금 기반 deterministic top-N 후보 점수를 만들고 시장 스캔 프롬프트에 함께 넣는다.
- `PreAnalysisGate` 구현. 현재는 Tier1 직전에 `INSUFFICIENT_CASH`, `MISSING_CORE_MARKET_DATA`, `BEARISH_PRE_GATE`를 코드로 차단하고 activity log detail에 gate code를 남긴다.
- `DeterministicFinalGate` 구현. 현재는 Tier2 직전에 `CONFIDENCE_GATE`, `RR_RATIO_GATE`, `RR_UNDEFINED_GATE`, `STOP_LOSS_REQUIRED_GATE`, `BUYING_POWER_GATE`를 코드로 차단하고 activity log detail에 gate code를 남긴다.
- 동일 종목/동일 조건 분석 캐시 구현. 같은 종목/전략/현재가/시장국면/보유여부/차트 신호/피드백 컨텍스트 조건이면 짧은 TTL 동안 Tier1 결과를 재사용하며, 수동 provider/model override 호출은 캐시를 우회한다.
- Tier1 비용 pre-gate 구현. Tier1 BUY 분석의 target/current price만으로 edge가 비용 대비 명백히 부족하면 Tier2 호출 전에 차단한다.
- `AI_SKIPPED` metric 구현. `PRE_ANALYSIS_GATE`, `TIER1_CACHE`, `DETERMINISTIC_FINAL_GATE`, `TIER1_COST_GATE`에서 절감된 Tier와 reason code를 execution metric으로 남긴다.
- Tier1/Tier2 deterministic prompt context 구현. 프롬프트에 `Deterministic 사전 판단` 섹션을 추가해 차트 신호, 현금/최소수량, RR 비율, 손절 필수 여부, 매수가능수량을 구조화해 전달한다.
- LLM cooldown incident dedupe.

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

1. `POST /api/v1/admin/stocks/bootstrap-universe?rank_limit=50&apply=false` dry-run 후 `apply=true`로 최소 국내 종목 universe를 채운다. 현재 로컬 DB 기준 `stocks=0`이라 먼저 운영 적용 확인이 필요하다.
2. 보유종목 재평가 비용 절감 설계를 진행한다.
3. 뉴스 gate의 Tier2 전 차단 이동은 shadow/rollout 표본을 더 확인한 뒤 재검토한다.

## 당장 바꾸지 말 것

- 뉴스 gate를 더 공격적으로 켜기.
- Nasdaq을 핵심 판단 소스로 승격.
- Tier1/Tier2를 제거.
- LLM 실패 시 주문을 더 쉽게 통과시키기.
- 청산 이후 장마감 직전 자동 재매수를 허용하기.
