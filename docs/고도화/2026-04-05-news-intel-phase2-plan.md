# 뉴스 인텔 2차 고도화 실행 계획 (2026-04-05)

## 목표
- 매수 전 정보 품질을 높여 손익비를 개선하고, 사후 검증 가능한 운영 체계 구축.

## 현재 반영 상태
- 완료:
  - `NEWS_LLM_ENABLED`, `NEWS_LLM_PROVIDER` 런타임 설정
  - `OLLAMA` 로컬 provider 추가 (`MANUAL_LLM_PROVIDER`, `NEWS_LLM_PROVIDER`에서 선택 가능)
  - `news_items` 저장 모델
  - `news_ingest_service` 정규화/중복제거/조회 계층
  - `open_dart_disclosure_service` 수동 수집기
  - `krx_kind_disclosure_service` 수동 수집기(RSS 우선 + HTML fallback)
  - `yonhap_news_service` 연합뉴스TV 경제 RSS 수집기
  - `bloomberg_news_service` sitemap 기반 해외 뉴스 수집기
  - `cnbc_news_service` Markets RSS 기반 해외 뉴스 수집기
  - `nasdaq_news_service` Markets RSS 기반 해외 뉴스 수집기
  - `news_translation_service` 해외 뉴스 한글 제목/요약 생성
  - `news_signal_service` 부정 뉴스 압력 기반 매수 게이트
  - `news_polling_service` 자동 폴링 + `NEW_NEWS_ITEM` 이벤트 발행
  - `trading_agent` 신규 뉴스 증분 재검증 핸들러
  - 성과 요약에 뉴스 게이트/재검증/뉴스 압력 메타데이터 반영
  - 관리자 API
    - `/api/v1/admin/news/sources`
    - `/api/v1/admin/news/items`
    - `/api/v1/admin/news/ingest`
    - `/api/v1/admin/news/fetch/dart`
    - `/api/v1/admin/news/fetch/krx`
    - `/api/v1/admin/news/fetch/yonhap`
    - `/api/v1/admin/news/fetch/bloomberg`
- 아직 미반영:
  - 수동 수집 실패 메시지 UX 정리
  - 해외 뉴스 실수집기 추가 확대(Reuters 대체 가능 소스 포함)
  - Shadow A/B 및 승급/롤백 자동화

## 2026-04-06 진행 메모
- 메인 `뉴스 인텔` 패널에 마지막 폴링 상태/수동 실행 결과/소스별 구현 상태를 노출하도록 확장
- `news_runtime_service`로 마지막 성공/실패/빈 결과 상태를 메모리 스냅샷으로 집계
- `오늘 리포트` 상단에 접이식 `뉴스 인텔` 스트립을 추가해 최근 뉴스/소스 상태/수동 수집 버튼을 메인 동선으로 이동
- `NEWS_DOMESTIC_MEDIA_ENABLED`를 추가해 연합뉴스TV 경제 RSS 자동 폴링을 옵트인으로 분리
- `NEWS_INCLUDE_FOREIGN`이 켜져 있으면 `Bloomberg`도 자동 폴링 대상으로 포함
- `NEWS_INCLUDE_FOREIGN`이 켜져 있으면 `CNBC`도 자동 폴링 대상으로 포함
- 해외 뉴스는 DB에 원문을 보존하고, 화면은 `display_title`/`display_summary`로 한글 우선 표시
- Reuters 공식 경로는 anti-bot 응답이 강해 1차 소스로는 Bloomberg sitemap을 우선 채택
- Reuters 대체 후보로 Investing.com 공식 RSS(`Stock Market News`) 추가
- `news_signal_service` 1차 정교화 적용
  - `SHORT/MID/LONG`별 임계치/신선도 차등
  - `회계 조사`, `investigation`, `공급 차질`, `profit warning` 등 위험 키워드 severity 반영
  - 동일 종목에 여러 소스가 동시 부정 보도하면 source diversity boost 반영
  - 게이트 결과에 상위 기여 뉴스 `contributors` 포함
- 종목 상세 모달에 `차트 / 비용 / 뉴스` 의사결정 카드 추가
  - `TradeResult.notes`에 비용·뉴스·차트 근거를 저장해 실거래 데이터에서도 재구성 가능하게 정리
- 수동 수집 결과는 `신규 적재 / 전량 중복 / 빈 결과`를 구분해 운영 메시지로 노출
- `오늘 리포트` 뉴스 인텔 스트립에 `뉴스 반영 거래 수 / 평균 부정 압력` 노출
- `Shadow A/B` 후보 집계와 `PROMOTE / KEEP / ROLLBACK / HOLDOUT` 롤아웃 판정 추가
- 주간/월간 버킷 요약에 뉴스 컨텍스트와 shadow 집계를 포함
- 뉴스 탭에서 `NEWS_SHADOW_ENABLED`, rollout 임계값을 런타임 조정 가능
- 뉴스 탭에 `Expectancy`, `PF`, `MDD`, `비용 차감 손익`, `Shadow 후보/차단율` KPI 카드 추가
- 성과 분석에서 `뉴스 반영 거래 vs 일반 거래` 실제 성과 비교 추가
  - `Expectancy`, `PF`, `비용 차감 손익` 차이를 별도 노출
  - 뉴스 반영 거래가 일반 거래보다 열위면 rollout 승급을 보류(`KEEP`)하도록 강화
- 일일 리포트에 `매수/보류 근거 태그` 섹션 추가
  - 뉴스 위험 낮음, 다중 소스 확인, 차트 패턴, 게이트 차단 사유를 카드로 요약
- `/admin` 메인 내 `성과 분석` 뷰 추가
  - 호라이즌/전략별 성과, Shadow / Rollout, 주간/월간 버킷을 전용 화면으로 분리
- `news_signal_service` 2차 정교화 적용
  - 장중/장외 세션 가중치 반영
  - `pressure_base`와 세션/다중소스 보정 후 최종 압력 분리
- 실행 체크리스트는 `2026-04-06-news-intel-checklist.md`에서 관리

## 범위
- 뉴스/공시 수집 파이프라인
- 뉴스 감성/영향도 스코어링
- 이벤트 기반 재검증
- 리포트/대시보드 확장

## 구현 순서

### 1) 데이터 계층
- `news_items` 저장 모델 추가
  - 필드: source, published_at, title, url, summary, symbols, sentiment_score, impact_score, trust_score, dedupe_hash
- `news_source_policies` 설정
  - source tier(A/B/C), 활성 여부, 기본 신뢰도

### 2) 수집 계층
- `news_ingest_service` 추가
  - 폴링 기반 수집(장중/장외 주기 분리)
  - 중복 제거 + 정규화 + 심볼 매핑
- 브로커/시장과 무관한 독립 서비스로 구현
- 1차 소스 카탈로그
  - Tier A: `DART`, `KRX`
  - Tier B: `YONHAP`, `REUTERS`, `BLOOMBERG`
- 운영 설정:
  - `NEWS_LLM_ENABLED` (뉴스 AI on/off)
  - `NEWS_LLM_PROVIDER` (`AUTOMATIC|CLAUDE_CODE|CODEX`)
  - 비용/속도 우선 시 CODEX, 품질 우선 시 CLAUDE_CODE 권장

### 2-1) 로컬 LLM 확장 계획
- `LLMProvider.OLLAMA` 추가
- 설정:
  - `OLLAMA_BASE_URL`
  - `OLLAMA_MODEL`
  - `OLLAMA_MODEL_TIER1`
  - `OLLAMA_MODEL_TIER2`
- 적용 순서:
  - 뉴스 요약/감성 분석부터 우선 적용 완료
  - 실거래 판단 Tier1/Tier2는 Shadow 검증 후 확대

### 3) 분석 계층
- `news_signal_service` 추가
  - sentiment/impact/freshness/trust 종합 점수
  - 종목별 `news_pressure` 계산
- `trading_agent`의 BUY 경로에 뉴스 게이트 결합 완료
  - 강한 부정 뉴스만 차단하는 보수적 임계값으로 시작

### 4) 이벤트/재검증
- `EventType.NEW_NEWS_ITEM` 추가
- 새 뉴스 수신 시 재검증 큐에 적재 완료
  - 대상: 보유종목 + 현재 감시 종목
  - 종목 쿨다운 적용 (`NEWS_RECHECK_COOLDOWN_SEC`)

### 5) 리포트/검증
- 기존 성과 API 확장
  - 뉴스 차단 건수, 뉴스 재검증 횟수, 거래별 뉴스 압력 메타데이터 반영 완료
- 주간/월간 리포트에 뉴스 섹션 추가
- 비용 차감 후 순손익(`net_pnl_after_cost`) 집계 추가 완료
- 승급/롤백 기준값을 관리자 뉴스 탭에서 즉시 조정 가능

### 6) UI/UX
- 의사결정 카드에 `뉴스` 추가
  - 차트/비용/뉴스 점수 + 최종 판정
- 종목 상세 타임라인에 뉴스 이벤트 삽입
- 뉴스 탭에 KPI 카드 / Rollout 정책 요약 추가
- `/admin/performance`에 실거래 vs Shadow(A/B) 비교 패널 추가

## 성공 기준
- 비용 차감 후 순손익 개선
- Max Drawdown 악화 없이 Expectancy 개선
- 뉴스 차단 거래의 사후 손실 회피율 확인

## 리스크
- 저품질 소스 과적용으로 과차단 가능
- 심볼 매핑 오탐으로 잘못된 차단 가능
- 해결: 소스 가중치, 쿨다운, 최소 샘플 기반 승급/롤백
