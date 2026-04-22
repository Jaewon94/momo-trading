# 뉴스 인텔 실행 체크리스트 (2026-04-06)

## 목표
- 뉴스 수집, 해석, UI/UX, 리포트, 수익 검증 작업을 빠뜨리지 않고 순서대로 진행한다.

## 완료
- [x] `news_items` 저장 모델/중복 제거/조회 계층
- [x] `OpenDART` 수동 수집기
- [x] `KRX/KIND` 수동 수집기(RSS 우선 + HTML fallback)
- [x] `연합뉴스TV 경제 RSS` 수동 수집기
- [x] `Bloomberg` sitemap 수동 수집기
- [x] `CNBC` Markets RSS 수동 수집기
- [x] `Nasdaq` Markets RSS 수동 수집기
- [x] 장중/장외 자동 뉴스 폴링 구조
- [x] 서버 시작 직후 뉴스 자동 폴링 1회 실행
- [x] 신규 뉴스 이벤트 기반 증분 재검증
- [x] 이벤트 기반 타겟 뉴스 재수집(`AUTO_EVENT`)
- [x] 뉴스 게이트(부정 뉴스 압력 기반)
- [x] `NEWS_LLM_PROVIDER`, `NEWS_LLM_ENABLED`, `OLLAMA` 지원
- [x] 관리자 `뉴스` 탭 / 최근 뉴스 조회 / 수동 적재 API
- [x] `/admin` 내 `뉴스 아카이브` 뷰
  - 날짜 범위, 소스, 심볼, 감성, 검색어 기준 필터
  - 날짜별 그룹 카드와 원문 링크, 번역 제목/요약, 연관 심볼/섹터 배지
  - 소스별 건수 요약과 기사별 상세 보기 드로어
- [x] 해외 뉴스 한글 제목/요약 우선 표시(`display_title`, `display_summary`)
- [x] 해외 뉴스 번역 제한 병렬화
  - 일반 provider는 최대 3개 동시 번역
  - `OLLAMA`는 로컬 부하를 고려해 단일 in-flight 유지
- [x] 관리자 설정에서 뉴스 병렬도 조정 지원
  - `NEWS_FETCH_CONCURRENCY`로 소스 fetch 병렬도 조절
  - `NEWS_TRANSLATION_CONCURRENCY`로 해외 뉴스 번역 병렬도 조절
  - `NEWS_CLAUDE_SHARE_SESSION`으로 Claude Code 뉴스 번역 시 세션 공유 유지 여부 선택
- [x] 종목 상세 모달 타임라인 뉴스 이벤트
- [x] `오늘 안 산 이유` 카드의 뉴스 차단 집계
- [x] `오늘 리포트` 상단 접이식 `뉴스 인텔` 스트립
- [x] OpenDART `status=013` 빈 결과를 정상 처리
- [x] `NEWS_DOMESTIC_MEDIA_ENABLED` 설정 추가

## 이번 스프린트
- [x] 메인 화면 `뉴스 인텔` 영역의 운영 상태 노출
- [x] 마지막 수집 상태/시각/메시지 노출
- [x] 소스별 구현 여부/상태 노출
- [x] `오늘 리포트`에서 최근 뉴스/수집 버튼/소스 상태 바로 노출
- [x] `Bloomberg 수동 수집` 버튼 및 해외 뉴스 한글 우선 표시
- [x] 수동 수집 결과 UX 정리
  - 빈 결과, 신규 적재, 전량 중복을 구분해 운영 메시지 표시
  - `오늘 리포트` 뉴스 인텔 스트립에 뉴스 반영 거래/평균 부정 압력 노출
- [x] Shadow/롤아웃 운영 지표 추가
  - Shadow 후보 수, 뉴스 차단 건수, 실거래 샘플 기준 승급/유지/롤백 판정
  - 주간/월간 버킷에 뉴스 컨텍스트와 shadow 집계 포함

## 다음 우선순위
- [x] 해외 뉴스 실수집기 추가 확대 1차 (`Investing.com Stock Market News` RSS 추가)
- [x] 해외 뉴스 실수집기 추가 확대 2차 (`Seeking Alpha All News` RSS 추가)
- [x] 해외 뉴스 실수집기 추가 확대 판단(`Reuters` 대체 가능 소스 포함)
  - `Reuters` 직접 소스는 anti-bot/안정성 이슈로 현재 일반 피드 추가 보류
  - `Investing.com` 공식 RSS 카탈로그는 확인됐고, 현재는 `Stock Market News` 유지
  - `Seeking Alpha`는 `All News` 외 섹터별 feed가 존재하지만 US 의견성/편향이 강해 보조 테마 소스로 후순위 유지
- [x] 거래 상태 표현 정리
  - 3단 UI 배지를 `매수/매도` 단일 문구에서 `접수중/대기중/부분 매도/완료`까지 드러나는 상태 체계로 개편
  - 이벤트 레이더/3단 카드/종목 상세가 동일 상태 모델을 재사용하도록 정리
  - 종목 상세 타임라인에서 부분 매도 후 닫힌 BUY lot가 보유처럼 보이지 않게 라벨 수정
- [x] 관리자 설정 영속화
  - 재시작 후 `TRADING_ENABLED`, `AUTONOMY_MODE`, `SCHEDULER_ENABLED`, 뉴스 토글 유지
- [x] `start.sh -d` PID 추적/상태 표시 안정화
- [x] 뉴스 폴링/브로커/주문 오류 운영 상태 노출
- [x] 기준선 리셋 이후 데이터 안내 노출
  - 뉴스 인텔 / 성과 분석 화면에 `기준선 리셋 이후 데이터` 배지 표시
- [x] 운영 DB 초기화 및 기준선 재생성 지원
  - 시스템 설정 탭의 `DB 초기화` 버튼
  - `POST /api/v1/admin/system/reset-operational-baseline`
- [x] 운영 DB 백업 지원
  - 시스템 설정 탭의 `DB 백업` 버튼
  - `POST /api/v1/admin/system/backup-operational-db`
  - `DB 초기화` 실행 전 자동 백업
- [x] 뉴스 소스 fetch 병렬화
  - `DART`, `KRX`, `YONHAP`, `BLOOMBERG`, `CNBC`, `NASDAQ`, `INVESTING`, `SEEKING_ALPHA`를 task 단위로 병렬 조회
  - 소스별 런타임 상태 기록과 DB ingest/save 순서는 기존 의미 유지
- [x] 뉴스 소스 런타임 집계 정합성 보강
  - source pill의 `received / created / duplicates / skipped`를 실제 ingest 결과 기준으로 집계
  - overall 상태를 마지막 성공 소스가 덮지 않도록 `SUCCESS / EMPTY / PARTIAL_ERROR`로 별도 계산
- [x] 반복 실패 소스 cooldown
  - `NEWS_SOURCE_FAILURE_THRESHOLD`, `NEWS_SOURCE_FAILURE_COOLDOWN_MIN` 추가
  - 같은 소스가 연속 실패하면 잠시 polling을 쉬고 `cooldown` 상태를 운영 UI에 노출
- [x] 해외 뉴스 소스 방어적 파싱/요청 보강
  - `Investing.com` RSS가 일부 malformed XML로 내려와도 정리 후 파싱
  - `Yonhap` 요청은 브라우저형 header를 사용해 403 가능성 완화
- [x] 뉴스 감성/영향도 점수 정교화
  - 장중/장외 세션 가중치 반영
  - `pressure_base`와 세션/다중소스 보정 후 최종 압력 분리 집계
- [x] 메타데이터 기반 종목/섹터 연관도 가중치 반영
  - `symbol_relevance`, `sector_relevance`가 있으면 뉴스 게이트 압력 계산에 반영
- [x] 수집기 단계의 연관 심볼/섹터 메타데이터 자동 보강
  - 종목명 매칭 결과를 `matched_stock_names`, `related_symbols`, `primary_symbol`로 저장
  - `Stock.category`를 이용해 `sector_label`, `sector_symbols`, `sector_relevance` 자동 채움
- [x] 업종 키워드만 있는 기사도 섹터 종목군으로 추론
  - 직접 종목명이 없어도 기사 제목/요약에 `반도체`, `인터넷` 같은 카테고리명이 있으면 `matched_sector_labels`, `sector_symbols`를 자동 보강
- [x] 복수 업종 기사에 대한 섹터 가중치 분리
  - `AI반도체와 플랫폼인터넷`처럼 여러 업종이 같이 나오면 `matched_sector_labels`, `sector_weights`를 함께 저장해 게이트가 업종별로 다른 가중치를 쓸 수 있게 정리
- [x] 뉴스 게이트 정교화 1차
  - 호라이즌별 임계치/신선도 민감도 차등
  - 헤드라인 위험 키워드 severity boost
  - 다중 소스 동시 부정 보도 시 source diversity boost
  - 상위 기여 뉴스(contributors) 반환
- [x] 뉴스 기반 의사결정 카드(`차트 / 비용 / 뉴스`) 통합
  - 종목 상세 모달에 의사결정 카드 추가
  - `TradeResult.notes`에 비용/뉴스/차트 근거 저장

## 수익 검증
- [x] `Shadow Portfolio` A/B 비교
  - 뉴스ON 실제 결정 vs 뉴스OFF 기준 후보 집계
- [x] 뉴스 반영 vs 미반영 전략 성과 비교
  - Shadow 후보/실거래 샘플/차단 건수로 운영 비교
- [x] 뉴스 반영 거래 vs 일반 거래 실제 성과 비교
  - `Expectancy`, `PF`, `비용 차감 손익` 기준 비교 패널 추가
  - 뉴스 반영 거래가 일반 거래보다 열위면 `PROMOTE` 대신 `KEEP` 유지
- [x] KPI: `Expectancy`, `Profit Factor`, `MDD`, 비용 차감 후 순손익
- [x] 승급/롤백 자동화
  - 실거래 샘플, PF, 기대값, MDD 기준으로 `PROMOTE/KEEP/ROLLBACK/HOLDOUT` 판정

## 리포트
- [x] 일간 리포트에 뉴스 영향 섹션 추가
- [x] 일간 리포트에 뉴스 반영 거래 vs 일반 거래 비교 스냅샷 추가
  - `뉴스 반영 거래` / `일반 거래`의 `Expectancy`, `PF`, `총 손익`, `비용 차감 손익 차이`를 같은 카드에서 비교
- [x] 주간/월간 리포트에 뉴스 기여도/오판 사례 추가
- [x] “왜 샀고 왜 안 샀는지” 뉴스 근거 태깅
  - 일일 리포트에 `매수/보류 근거 태그` 섹션 추가
  - 뉴스 위험 낮음, 다중 소스 확인, 차트 패턴, 게이트 차단 사유를 카드로 요약

## 운영 UI
- [x] 뉴스 탭에서 Shadow/롤아웃 기준 직접 조정
- [x] 뉴스 탭에 KPI 카드 / Rollout 정책 상태 노출
- [x] 전용 성과 페이지에서 주간/월간 비교 분리
  - `/admin` 내 `성과 분석` 뷰 추가
  - 호라이즌/전략별 성과, 주간/월간 버킷, 뉴스 운영 수치 한 화면 노출

## 운영 체크
- [ ] 뉴스 인텔 고도화 메모 반영 여부 확인
  - `docs/고도화/2026-04-22-news-intel-upgrade-notes.md`
  - 기본 방향: Nasdaq 기본 off, 해외 번역 off, 뉴스는 성과 검증 전 shadow/report-only 중심
- [ ] AI 비용 절감 로드맵 반영 여부 확인
  - `docs/고도화/2026-04-23-ai-cost-reduction-roadmap.md`
  - 기본 방향: Tier1/Tier2는 유지하되 명확한 공시/가격/세션/비용 판단은 deterministic reason code로 선처리해 AI 입력 품질과 비용 효율을 개선
- [ ] 운영 재시작 후 뉴스 enrichment backfill 실행
  - `POST /api/v1/admin/news/backfill-enrichment?limit=1000&apply=false`로 dry-run
  - 결과 확인 후 `apply=true`
  - `risk_classified`, `topic_mapped`, `symbols_attached` 변화 확인
- [ ] DB 초기화 후 국내 종목 universe 복구
  - 2026-04-23 점검 기준 `stocks=0`, 보유/미체결/스냅샷 0건
  - `stocks`가 비어 있으면 해외/국내 매체 뉴스가 종목으로 연결되지 않음
  - KRX/Kiwoom/KIS 종목 마스터 또는 거래량 상위 기반 bootstrap 설계 필요
- [ ] `OPEN_DART_API_KEY` 실제 운영키 유지
- [ ] `NEWS_DOMESTIC_MEDIA_ENABLED` 켜기 전 소스 이용조건 확인
- [ ] `Bloomberg`/해외 소스 이용조건 및 호출 안정성 확인
- [ ] 장중/장외 자동 폴링 로그 확인
- [ ] `news_items` 적재 건수와 UI 노출 동기화 확인
- [ ] 소스별 마지막 성공/실패 원인 확인
  - 1차 반영: 뉴스 overview/source pill에 마지막 상태 메시지 + `24h 적재 건수` 표시
  - 2차 반영: `마지막 성공 시각`, `연속 실패 횟수`, `최근 실행 시각`, `신규/중복/스킵`, `마지막 실패 시각` 표시
  - 3차 반영: `cooldown 남은 시간` 표시 및 일부 소스 실패 시 overall `PARTIAL_ERROR` 유지
  - 운영 점검 명령: `bash start.sh check-news`
