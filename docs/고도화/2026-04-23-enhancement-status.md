# 고도화 진행 현황 점검 (2026-04-23)

## 점검 기준

- 문서 체크박스가 아니라 현재 코드, 테스트, 라이브 서버 응답을 기준으로 판단했다.
- `구현 완료`는 저장소 코드와 테스트가 존재한다는 뜻이다.
- `운영 반영`은 현재 실행 중인 `http://127.0.0.1:9000` 프로세스가 해당 코드를 로드했다는 뜻이다.

## 현재 결론

어제/오늘 진행한 고도화 중 주문 안전, PnL 분리, 뉴스 deterministic enrichment, 뉴스 backfill API, LLM 지연 경고, canonical decision event, forward return labeling, decision benchmark, 장마감 청산 이후 자동 BUY 차단은 코드와 운영 서버에 반영되어 있다.

최근 추가된 AI 비용 절감 축인 `CandidateScoringService`, `PreAnalysisGate`, `DeterministicFinalGate`, `Tier1AnalysisCacheService`, `AI_SKIPPED` metric, `HoldingsPrecheckService`, `HoldingsReviewCacheService`는 코드와 테스트 기준으로 구현 완료 상태다. 다만 이 문서에서 `운영 반영`은 실제 9000 프로세스 재기동과 런타임 확인까지 끝난 항목만 뜻하므로, 최신 보유종목 precheck/review cache는 현재 기준 `코드 반영 완료`로 적는다.

2026-04-27 운영 확인 기준 서버는 `AUTONOMOUS/FULL` 상태에서 Kiwoom 연결, 뉴스 폴링, Admin API가 정상 응답했다. Tier1/Tier2/Manual LLM은 운영 의도대로 `CODEX/gpt-5.4` 단독이며 fallback은 비워둔다. 뉴스 번역은 `OLLAMA/qwen3:14b`를 유지하고, `qwen3:4b`는 반복된 지연/JSON 안정성 문제로 운영 후보에서 제외한다.

같은 확인에서 `010170`의 stale DB-only `PENDING_CONFIRM` 주문은 수동 cleanup으로 `CONFIRM_FAILED` 처리했다. `452190`은 broker 보유 3,800주와 DB open qty 3,800주가 일치했고 pending 주문은 0건이었다. 이 상태는 broker holdings delta 백필과 account snapshot 이후 백필 경로가 정상적으로 DB 보유 정합성을 회복했음을 보여준다.

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
- confirmed BUY 직후와 account equity snapshot 직후 broker holdings delta를 DB open BUY lot으로 백필한다. broker에는 보유가 있는데 DB open lot이 부족한 경우 `HOLDING_SYNC` source로 부족분을 채운다.
- broker 보유에서 사라졌지만 DB에는 open으로 남은 BUY lot은 `portfolio_sync_job`에서 기본 dry-run으로 보고한다. pending broker/DB 주문이 없을 때만 수동 apply 후보가 되며, apply 시 `BROKER_HOLDING_MISSING`으로 중립 종결한다.

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
- `NewsContextService` 구현. 최근 뉴스의 종목코드/종목명/source 매칭 결과를 Tier1/Tier2 prompt에 넣고, trade note와 report/benchmark에 `news_context_*` metadata로 남긴다.
- 뉴스 context는 BUY hard gate가 아니다. 현재 운영 의도는 "너무 강하지 않게, 판단에 도움이 되는 정도"의 보조 맥락이며, 차단/승급은 forward return 표본 확인 뒤에만 검토한다.

### LLM/관측성

- Codex 호출은 provider 단위 semaphore로 직렬화되어 동시 CLI 부하를 줄인다.
- `observability_service.record_llm_call`로 provider/model/latency/status 기록.
- `LLM_SLOW_CALL_WARN_SEC` 설정 추가. 기본 30초.
- LLM 호출이 임계 시간을 넘기면 `LLM_CALL / PROGRESS` 활동 로그와 SSE 경고를 남긴다.
- LLM 호출 실패/타임아웃은 `LLM_CALL / ERROR` 활동 로그를 남긴다.
- LLM provider cooldown 오류의 incident fingerprint에서 `(N초 남음)`처럼 매번 바뀌는 잔여 시간을 정규화해 같은 cooldown 장애를 하나의 incident로 누적한다.
- Observability maintenance rollup key의 provider/model `NULL`을 `UNKNOWN`으로 정규화한다.
- 최근 `OBSERVABILITY_MAINTENANCE` 실패는 system preflight의 `observability` WARN으로 노출한다.
- Tier1/Tier2/Manual runtime은 Codex-only 정책을 유지한다. fallback provider 추가는 운영자가 의도적으로 정책을 바꾸는 경우에만 한다.

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
- `candidate_path_comparison`을 추가해 scanner 후보, scanner-only, Tier1 도달, Tier1-only BUY, Tier2 BUY, 실제 BUY, random baseline을 같은 forward return 표본에서 비교한다.
- 이번 확장으로 source별 blocked candidate forward return과 actual buy 대비 평균 수익률 차이를 read-only로 볼 수 있게 됐다.
- 현재 `by_news_source_blocked`, `by_news_source_blocked_comparison`가 추가되어 source별 blocked 후보군과 source별 실제 BUY 후보군을 비교할 수 있다.
- `news_context_source_codes`와 `news_context_items`도 benchmark/report의 뉴스 enriched 판정에 포함한다. 기존 `news_negative_pressure`만으로는 prompt에 들어간 뉴스 보조 맥락을 집계하지 못했기 때문이다.
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
- review cache key의 `minutes_left`는 15분 버킷으로 정규화한다. 몇 분 차이만으로 cache hit가 깨지는 문제를 줄이되, 가격/손익/임계값/시장 문맥이 바뀌면 기존처럼 miss가 난다.
- 캐시 hit 종목은 `AI_SKIPPED`에 `HOLDINGS_REVIEW_CACHE/CACHE_HIT/TIER1`로 기록한다.
- 보유종목 precheck skip도 `AI_SKIPPED`에 `HOLDINGS_PRECHECK/{SELL|HOLD}/TIER1`로 기록한다.
- Admin observability overview에 `ai_skipped` 요약을 추가했다. stage/reason/tier/symbol/recent 표본을 API에서 확인할 수 있어 HOLD skip 플래그 활성화 전 운영 표본을 볼 수 있다.
- Admin 관측 화면에 `AI Skip` 섹션을 추가했다. 사유별 집계와 최근 표본을 화면에서 확인할 수 있다.
- Decision benchmark 응답에 `ai_skipped_observation`을 추가했다. 단, `AI_SKIPPED`는 forward return이 직접 붙은 표본이 아니므로 수익률 benchmark와 분리된 관측 섹션으로 노출한다.
- 장중 보유 재평가에서 precheck/cache로 LLM을 건너뛴 HOLD/SELL 판단도 `decision_events`에 기록한다. 이 경로는 `reference_price=current_price`를 남기므로 forward return labeling 대상이 된다.
- 스마트 청산에서 precheck로 LLM을 건너뛴 HOLD/SELL 판단도 `decision_events`에 `SMART_LIQUIDATION` stage로 기록한다.
- 일반 BUY 분석 파이프라인의 `PRE_ANALYSIS_GATE` 차단도 `decision_events`에 `PRE_ANALYSIS_GATE` stage로 기록한다. 강한 하락 추세 등 Tier1 전 차단 후보가 forward return labeling 대상이 된다.
- 일반 BUY 분석 파이프라인의 `DETERMINISTIC_FINAL_GATE`, `TIER1_COST_GATE` 차단도 `decision_events`에 기록한다. Tier1은 호출했지만 Tier2 전에 막은 후보도 이후 forward return 기준으로 판단 품질을 비교할 수 있다.
- 2026-04-24 14시 기준 운영 observability에서 `AI_SKIPPED/HOLDINGS_PRECHECK` 표본은 0건이다. 명확 HOLD skip 플래그는 근거 부족으로 계속 OFF 유지한다.
- 2026-04-26 재확인에서도 `AI_SKIPPED` metric은 0건이고, `decision_events`에는 HOLDINGS_PRECHECK/HOLDINGS_REVIEW_CACHE 표본이 없다. 원인은 Kiwoom 보유 심볼 `A010140`과 DB `trade_results.stock_symbol=010140` 형식 불일치로 보유 재평가가 `open BUY TradeResult 없음` REVIEW_REQUIRED에 머문 것이다. `TradeResultRepository` 조회 심볼 정규화를 보강했으므로 다음 장중 표본부터 precheck/cache metric 누적 여부를 다시 본다.
- 보유 재평가가 precheck/cache 전에 멈춘 경우를 `HOLDINGS_REVIEW/REVIEW_REQUIRED` execution metric으로 별도 기록한다. `AI_SKIPPED`와 분리해 `TRADE_RESULT_MISSING`, `PRICE_LOOKUP_FAILED`, `HOLDING_DATA_ERROR` 같은 데이터 확인 필요 사유를 Admin observability에서 바로 볼 수 있다.
- observability 추천이 과거에는 뉴스 번역 Ollama 모델을 `qwen3:4b`로 낮추라고 표시했지만, `qwen3:4b`는 운영 후보에서 제외한다. 설치와 샘플 검증은 완료됐으나 응답 지연과 JSON 형식 안정성 문제가 반복 확인되어 운영 `NEWS_LLM_MODEL`은 `qwen3:14b`를 유지하고, 추천 서비스도 뉴스 번역 모델을 8b 미만으로 낮추지 않는다.
- 뉴스 번역 추천 서비스는 이미 목표 모델을 쓰고 있을 때도 `DOWNGRADE`로 표시하던 상태 판정을 보정했다. 추천 모델과 현재 모델이 같으면 `KEEP`으로 표시한다.
- 해외 뉴스 번역이 비활성화된 상태에서는 observability가 뉴스 번역 모델 다운그레이드를 운영 액션으로 추천하지 않도록 보정했다.
- LLM 호출 metric detail에 `call_context`를 기록하고 Admin observability overview에 기능별 `llm.function_breakdown`을 추가했다. 기능별 호출 수/성공률/지연/prompt·response 문자 수를 분리해 볼 수 있다.
- SQLite 운영 DB 쓰기 경합 완화를 위해 `run_sqlite_write_with_retry`에 프로세스 내부 write 직렬화를 추가했다. 활동 로그 저장은 lock 재시도마다 새 ORM 엔트리를 생성하고, retry 기본을 최소 5회/250ms로 올려 기동 직후 뉴스 폴링과 observability/activity log 저장이 겹칠 때의 `database is locked` 실패를 줄인다.
- confirmed BUY 후 즉시 holdings backfill을 수행해 broker 체결은 됐지만 DB open BUY가 부족한 상태를 줄인다. account equity snapshot도 같은 백필을 수행해 장중 보유 재평가와 smart liquidation이 `TradeResult 없음`으로 멈추는 빈도를 낮춘다.
- DB open BUY가 broker holdings에서 사라진 경우는 자동 매도/매수로 보정하지 않는다. pending 여부를 확인한 뒤 DB 정합성 작업으로만 중립 종결하며, 실제 realized PnL truth는 broker execution history 연동 전까지 제한적으로 해석한다.

## 아직 미구현 또는 추가 검증이 필요한 핵심 항목

### P0/P1 성격

- intraday forward return 정밀도 개선용 분봉/틱 snapshot history.

### AI 비용/지연 절감 후속

- 보유종목 명확 HOLD skip은 플래그 기반 코드 경로까지 구현 완료. 운영 기본값은 OFF이며, 최근 표본이 0건이라 아직 활성화하지 않는다.
- 스마트 청산 review cache는 현재 보류한다. `_force_liquidation()`에서 청산 시각에 단발 호출되는 경로라 반복 호출 절감 효과가 작고, 캐시가 청산 직전 최신 판단을 흐릴 수 있다.
- review cache key의 잔여시간 조건은 15분 버킷으로 조정 완료. TTL 자체는 30분 기본값을 유지한다.
- 장중 보유 재평가 precheck/cache, 스마트 청산 precheck, 일반 분석 `PRE_ANALYSIS_GATE`, `DETERMINISTIC_FINAL_GATE`, `TIER1_COST_GATE` 판단은 `decision_events`에 연결 완료.
- 시장 스캔 deterministic 후보 점수 top-N은 `CANDIDATE_SCORING` decision event로 기록한다. scanner score, buyable 여부, source/reason metadata를 남겨 scanner-only 후보의 사후 수익률을 비교할 수 있다.
- 시장 스캔 후보 점수에 최근 6시간 후보/분석 decision event cooldown 감점을 반영했다. 비보유 반복 후보만 감점하고 보유종목은 매도 검토 후보로 유지한다.
- 시장 스캔 후보 top-N에 뉴스 게이트의 부정 뉴스 압력을 반영했다. 비보유 후보만 감점하고 `news_negative_pressure`를 후보/decision event metadata에 남긴다.
- 시장 스캔 deterministic 후보에 `strategy_type_hint`와 `reason_codes`를 추가했다. 프롬프트와 `CANDIDATE_SCORING` decision event metadata에 같은 값을 남겨 전략별/사유별 scanner-only 성과 비교가 가능하다.
- 기능별 LLM 호출 집계는 overview API와 Admin 관측 화면 노출까지 구현 완료.
- 뉴스 번역 `qwen3:4b` 다운그레이드는 운영 후보에서 제외한다. JSON-only 프롬프트와 qwen 응답 정규화(`<think>` 제거, 프롬프트 echo 이후 JSON 후보 재추출, 감성 라벨/점수 보정, 번역 필드 검증`)를 보강했지만, 2026-04-26 재측정 중 첫 샘플은 161초 후 프롬프트 echo로 파싱 실패했고, 45초 timeout 재측정도 retry 포함 92초 후 `ReadTimeout`으로 실패했다. 추가 실험은 가능하지만 운영 추천/기본값에는 반영하지 않는다.

### Admin UX 후속

- 고위험 액션 confirmation UI flow는 1차 구현 완료. 설정 화면에서 `ADMIN_DANGEROUS_ACTION_CONFIRMATION_REQUIRED`를 켤 수 있고, DB 초기화/즉시 매도/미체결 취소/취소 후 재매도는 실행 직전에 서버 확인 토큰을 발급받아 요청 본문에 붙인다.
- confirmation 기본값 true 전환 여부는 운영 표본 확인 후 결정한다.

### 장마감 리스크 관리

- 청산 시각 이후 자동 BUY는 `POST_LIQUIDATION_BUY_BLOCK_ENABLED=true` 기본값으로 주문 직전 차단한다.
- 스마트/강제 청산 완료 후 자동 재스캔은 실행하지 않는다.
- 청산 이후 좋아 보이는 신호는 분석/로그/decision event로 남길 수 있지만, 실제 자동 BUY 주문은 다음 거래일 전까지 막는다.
- Daily report의 `strategy_stats`에 `metric_contract`를 추가해 `total_orders`, `buy_count`, `sell_count`, 승패, 보유 종목 수의 source/filter/formula를 분리 기록한다.
- Daily report API 응답에 `metric_contract`를 별도 필드로 승격하고, Admin 리포트 카드에서 집계 기준을 접이식으로 확인할 수 있게 했다.

### 실험/성과 검증

- candidate scanner/Tier/risk 단계별 decision event 세부 연결.
- source별 뉴스 attribution benchmark. `news_context_*`가 붙은 거래와 없는 거래의 forward return 비교는 실제 운영 표본이 더 필요하다.
- 동일 후보군 random/scanner-only/Tier-only benchmark는 `candidate_path_comparison` read-only 응답까지 구현 완료. 다음은 운영 표본 누적 후 UI 노출/임계값 조정.
- source별 뉴스 성과와 차단 후보 사후 수익률.
- backtest same-bar execution 제거.
- Backtest 기본 체결 정책을 `NEXT_OPEN`으로 바꾸고, 과거 같은 봉 종가 체결은 `LEGACY_SAME_CLOSE`를 명시한 경우에만 사용하도록 1차 수정했다. API 요청/리포트 config에는 `execution_timing`과 `RULE_BASED_TECHNICAL_PROXY` model family를 표시한다.
- fee/fill/report metadata 분리.
- `STABLE_SHORT`/`AGGRESSIVE_SHORT`를 alpha source와 execution profile로 분리.
- SQLite는 단일 파일 DB라 외부 프로세스 간 lock 가능성은 남는다. 다음 운영 재기동 후 `database is locked`가 반복되면 뉴스 폴링 완료 로그와 observability metric 저장 순서를 더 분리하거나 startup 뉴스 폴링을 지연 실행으로 바꾼다.

## 권장 실행 순서

1. `qwen3:4b` 뉴스 번역은 운영 전환 후보에서 제외한다. 뉴스 번역 Ollama 경량화가 필요하면 8b 이상 모델을 별도 후보로 검증한다.
2. Tier1/Tier2/Manual은 Codex-only 정책을 유지한다. fallback provider는 장애 회피 목적이라도 운영 의도와 충돌할 수 있으므로 임의로 추가하지 않는다.
3. broker holdings와 DB open qty mismatch를 계속 확인한다. `HOLDING_SYNC` 백필은 정합성 복구이고, `BROKER_HOLDING_MISSING` 중립 종결은 realized PnL truth가 아니다.
4. `AI_SKIPPED/HOLDINGS_PRECHECK` 표본이 쌓이면 `HOLDINGS_PRECHECK_SKIP_CLEAR_HOLD_ENABLED` 활성화 여부를 결정한다.
5. 장중 보유 재평가 review cache hit율/오판율을 운영 표본으로 확인한다.
6. 뉴스 gate의 Tier2 전 차단 이동은 shadow/rollout 표본을 더 확인한 뒤 재검토한다.

## 당장 바꾸지 말 것

- 뉴스 gate를 더 공격적으로 켜기.
- Nasdaq을 핵심 판단 소스로 승격.
- Tier1/Tier2를 제거.
- LLM 실패 시 주문을 더 쉽게 통과시키기.
- 청산 이후 장마감 직전 자동 재매수를 허용하기.
- `qwen3:4b`를 뉴스 번역 운영 모델로 다시 추천하기.
- Codex-only Tier runtime에 fallback을 묵시적으로 추가하기.
