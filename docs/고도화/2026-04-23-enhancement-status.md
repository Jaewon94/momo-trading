# 고도화 진행 현황 점검 (2026-04-23)

## 점검 기준

- 문서 체크박스가 아니라 현재 코드, 테스트, 라이브 서버 응답을 기준으로 판단했다.
- `구현 완료`는 저장소 코드와 테스트가 존재한다는 뜻이다.
- `운영 반영`은 현재 실행 중인 `http://127.0.0.1:9000` 프로세스가 해당 코드를 로드했다는 뜻이다.

## 현재 결론

어제/오늘 진행한 고도화 중 주문 안전, PnL 분리, 뉴스 deterministic enrichment, 뉴스 backfill API, LLM 지연 경고는 코드에 반영되어 있다. 다만 현재 떠 있는 9000 서버는 최신 커밋을 아직 로드하지 않아 신규 뉴스 backfill endpoint가 `404`로 확인됐다. 운영 반영에는 안전한 재시작이 필요하다.

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

### 뉴스 backfill 운영 반영

- 코드와 테스트는 있다.
- 현재 9000 서버에서 `POST /api/v1/admin/news/backfill-enrichment?limit=1&apply=false`는 `404`로 확인됐다.
- 원인: 실행 중인 서버가 최신 커밋을 아직 로드하지 않음.
- 필요한 조치: 장중 영향을 피해서 서버 재시작 후 dry-run부터 실행.

### 뉴스 rollout mode

- 현재는 `NEWS_GATE_ENABLED`, `NEWS_SHADOW_ENABLED`, `NEWS_POLL_ENABLED` 같은 boolean 조합이다.
- 문서에 제안한 `OFF|POLL_ONLY|SHADOW_ONLY|SEMI_AUTO_GATE_RECOMMENDATION|BUY_BLOCK_GATE` enum mode는 아직 없다.
- 표본 수/forward return 조건을 만족해야 `BUY_BLOCK_GATE`를 허용하는 guard도 아직 없다.

### 뉴스 source별 성과

- source별 수집 count, 실패/중복/스킵, enrichment 비율은 일부 볼 수 있다.
- source별 blocked candidate forward return, gate contribution, 실제 성과 기여도는 아직 없다.
- 이유: canonical decision event 기반은 추가됐지만 forward return dataset과 source별 benchmark가 아직 없음.

### Observability maintenance

- raw metric, hourly rollup, reporting service는 구현되어 있다.
- rollup 저장 단계에서 provider/model `NULL`은 `UNKNOWN`으로 정규화된다.
- maintenance 실행 기록이 없으면 새 DB 호환을 위해 preflight는 OK 정보성 상태로 두고, 최근 실패가 있으면 WARN으로 노출한다.

## 아직 미구현으로 확인된 핵심 항목

### P0/P1 성격

- forward return labeling job.

### AI 비용/지연 절감

- 국내 종목 universe bootstrap.
- `CandidateScoringService`.
- `PreAnalysisGate`.
- `DeterministicFinalGate`.
- 동일 종목/동일 조건 분석 캐시.
- `AI_SKIPPED` metric.
- LLM cooldown incident dedupe.

### Admin UX 후속

- 고위험 액션 confirmation UI flow.
- confirmation 기본값 true 전환 여부 결정.

### 실험/성과 검증

- candidate scanner/Tier/risk 단계별 decision event 세부 연결.
- benchmark/control group report.
- source별 뉴스 성과와 차단 후보 사후 수익률.
- backtest same-bar execution 제거.
- fee/fill/report metadata 분리.
- `STABLE_SHORT`/`AGGRESSIVE_SHORT`를 alpha source와 execution profile로 분리.

## 권장 실행 순서

1. 최신 서버 재시작 후 신규 endpoint와 LLM 지연 경고가 운영에 반영되는지 확인.
2. `POST /api/v1/admin/news/backfill-enrichment?limit=100&apply=false` dry-run 실행.
3. dry-run 결과가 타당하면 `apply=true`로 기존 뉴스 deterministic enrichment 적용.
4. DB 초기화 이후 비어 있을 수 있는 `stocks` universe bootstrap 구현.
5. forward return labeling을 붙여 새로 추가된 canonical decision event를 LLM/뉴스/전략 성과 검증 dataset으로 완성한다.
6. 그 다음 `CandidateScoringService`, `PreAnalysisGate`, `DeterministicFinalGate`를 순서대로 붙인다.
7. 뉴스 gate는 enum rollout mode로 바꾸고, `BUY_BLOCK_GATE`는 forward return 표본이 쌓인 뒤에만 허용한다.

## 당장 바꾸지 말 것

- 뉴스 gate를 더 공격적으로 켜기.
- Nasdaq을 핵심 판단 소스로 승격.
- Tier1/Tier2를 제거.
- LLM 실패 시 주문을 더 쉽게 통과시키기.
- forward return dataset 없이 전략/뉴스/LLM 파라미터를 수익 개선 목적으로 조정하기.
