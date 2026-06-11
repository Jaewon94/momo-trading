# 2026-06-11 서비스 개선 로드맵 (전체 시스템 감사 기반)

- 작성: Claude (Fable 5) 전체 시스템 감사, 태스크 `2026-06-10-014-improvement-roadmap`
- 입력: 4개 영역 병렬 감사 (아키텍처/트레이딩 도메인/테스트·품질/운영·보안) + Understand-Anything 지식 그래프 (`.understand-anything/knowledge-graph.json`)
- 이전 감사와의 관계: [2026-04-22 전체 감사](../audits/2026-04-22-system-wide-trading-audit-findings.md)의 후속. 당시 지적된 F-009(킬스위치), F-011(현금 예약)은 장치가 구현됐으나 아직 REPORT_ONLY/SHADOW 단계 — 이번 로드맵은 "졸업(enforce 전환)"을 핵심 주제로 다룬다.

## TL;DR

시스템의 매매 파이프라인(결정론 게이트 → LLM → 주문 생명주기 → 복구)은 성숙하다. 가장 큰 리스크는 코드 결함이 아니라 **(1) 무인증 admin API가 LAN에 노출된 것, (2) 리스크 가드가 추정 체결가·실현손익에만 의존하는 것, (3) 보호 장치 다수가 SHADOW/REPORT_ONLY로 잠들어 있는 것**이다. 우선순위는 "보안 차단 → PnL 데이터 신뢰성 → 가드 졸업 → 구조 개선" 순서.

## 1. 고쳐야 할 점 (심각도순)

### P0 — 보안 (즉시, 코드 변경 최소)

| # | 이슈 | 근거 | 조치 |
|---|------|------|------|
| S1 | admin/orders API 전체 무인증. 매도·설정변경·DB 초기화·LLM 키 등록이 모두 열려 있음 | `api/routes/admin.py:90,1679,2252,2317`, `api/routes/orders.py:24,36` | FastAPI dependency 한 개로 전 라우터에 API 키 헤더 검증 적용 |
| S2 | 기본 바인딩 0.0.0.0 → 같은 네트워크 누구나 실거래 주문 가능 | `scripts/dev/start.sh:24`, `Dockerfile:22` | 기본 HOST를 `127.0.0.1`로 변경 |
| S3 | kis-mcp 사이드카(KIS 키 보유 프록시)가 무인증으로 전 인터페이스 노출 | `docker-compose.yml:7-8`, `docker/kis-mcp/entrypoint.py:22-27` | 포트 바인딩을 `127.0.0.1:3100:3000`으로 제한 |
| S4 | LLM API 키가 runtime_settings 테이블에 평문 저장, 백업 DB(권한 644)에 복제됨 | `api/routes/admin.py:241-254` | 환경변수/키체인 격리 또는 저장 시 암호화, 백업 파일 권한 600 |

### P1 — 돈을 잃을 수 있는 결함 (트레이딩 도메인)

| # | 이슈 | 근거 | 조치 |
|---|------|------|------|
| T1 | SELL 체결가가 추정값(주문가/평단 역산, expected_price 폴백) → 실현손익 왜곡 → 일손실 한도·기대값 가드·연속손실 카운트가 부정확한 입력으로 작동 | `trading/adapters/kiwoom_adapter.py:231-287`, `agent/decision_maker.py:971-975,1183-1185` | 키움 체결내역 TR 연동으로 실측 체결가/체결시각 확보. **모든 피드백 루프의 전제** |
| T2 | 일일 손실 한도가 실현손익 기준뿐. 보유 포지션 일중 급락 시에도 신규 매수 지속. 계좌자산 DD 가드는 기본 REPORT_ONLY | `strategy/trading_guard.py:31-37,304-327` | equity DD 가드를 BLOCK_BUY 기본화, 미실현 평가손 기준 디리스킹 추가 |
| T3 | 손절 감시가 사실상 폴링(키움 실시간 시세 미지원): 폴백 5분 + fast guard 3분 → 급락 시 수 분간 미반응 | `realtime/monitor.py:25`, `scheduler/scheduler.py:904-912` | 보유종목 한정 10~30초 폴링으로 단축 |
| T4 | 사이클 내 현금 예약이 SHADOW → 병렬 매수 태스크가 같은 현금으로 동시 주문 가능 (4/22 F-011의 미완 후속) | `core/config.py:205`, `agent/trading_agent.py:2021-2024` | ORDER_RESERVATION_ENFORCEMENT를 ENFORCE로 전환 |
| T5 | 스캔 파이프라인 SELL이 `_selling` 락 미사용 → 손절 이벤트와 동시 발생 시 이중 매도 제출 가능 | `agent/trading_agent.py:1693-1721` (락은 3626,3737에만) | 사이클 경로 SELL에도 `_acquire_sell` 적용 |
| T6 | 일손실 계산에 naive `datetime.now()` 사용 (기록은 `now_kst()`) → 서버 TZ가 KST 아니면 일자 윈도우 어긋남 | `strategy/trading_guard.py:307` | `now_kst()`로 통일 (유사 9곳 일괄: `services/performance_reporting_service.py:63,132` 등) |
| T7 | VI/거래정지/서킷브레이커 대응 코드 부재. 청산 불가 포지션의 상태 관리 없음 | 전체 grep 0건, 재시도는 `scheduler/scheduler.py:2033-2055` 1회뿐 | 거래정지/VI 상태 머신 + 해제 시 자동 재시도 + 운영자 알림 |
| T8 | 뉴스 게이트 조회 윈도우가 호라이즌 정책의 `lookback_hours`를 무시하고 전역 설정 사용 | `services/news_signal_service.py:38` vs `strategy/news_intelligence_policy.py` | 호라이즌별 lookback 적용 |
| T9 | 매매불가 블록리스트 `_untradeable_symbols`가 리셋 없이 영구 누적 | `agent/market_scanner.py:39-44` | 일일 리셋 (pre_market에서 clear) |

### P2 — 운영 견고성

| # | 이슈 | 근거 | 조치 |
|---|------|------|------|
| O1 | 외부 알림 채널 전무 (체결/오류/kill-switch가 브라우저 SSE와 로그뿐) → 무인 운영 시 장애 인지 불가. **실증: [6/12 인시던트](2026-06-12-server-downtime-incident.md) — 서버가 1.5거래일 꺼져 있어도 아무도 몰랐음** | 전수 grep 0건 | Telegram/Slack 웹훅 최소 구현 |
| O2 | DB 백업이 수동뿐 (마지막 백업 6/6, 운영 DB는 6/10) | `scheduler/scheduler.py:752-1005`에 백업 잡 없음 | 기존 `runtime_backup_service`를 일일 잡으로 등록 + 보존정책 |
| O3 | 프로세스 자동 재시작 없음 (nohup+PID뿐) → 장중 크래시 시 손절 가드 통째로 정지 | `scripts/dev/start.sh:462-468` | launchd KeepAlive plist |
| O4 | 기동 시 PENDING_CONFIRM 자동 reconcile 없음 (서비스는 존재, 배선만 안 됨) | `scheduler/scheduler.py:1010-1034`, `services/order_reconciliation_service.py` | `_on_startup`에서 자동 reconcile 배선 |
| O5 | 로그 로테이션 없음 + `diagnose=True`로 예외 시 변수값(시크릿 잠재) 덤프 | `core/logging.py:27-48`, `scripts/dev/start.sh:465` | loguru 파일 싱크 rotation/retention, 프로덕션 diagnose=False |
| O6 | venv 파손: `venv/bin/python`(3.14.5)으로는 import 불가, `venv/bin/python3.13`만 동작 | venv/lib 구조 확인 | venv 재생성 |
| O7 | compose 헬스체크 `|| exit 0`으로 무력화, `.dockerignore` 부재(+`COPY . .`로 .env/DB가 이미지에 포함) | `docker-compose.yml:25`, `Dockerfile:15` | 헬스체크 수정, .dockerignore 추가 (Docker 경로 유지 시) |

### P3 — 코드 구조/품질

| # | 이슈 | 근거 | 조치 |
|---|------|------|------|
| C1 | `api/routes/admin.py` 갓파일 (3,079줄, 65 엔드포인트). 라우트에서 직접 ORM 삭제·스케줄러 private 함수 호출 | `admin.py:25-38,1440-1453,2503` | 도메인별 패키지 분할 + ORM 로직 서비스로 이동 |
| C2 | 에러 처리 3원화: ServiceException 봉투 vs bare HTTPException vs `{"error":...}` dict | `exceptions/common.py`, `admin.py:182` 외 11곳, 서비스 12곳 | ErrorCode 기반 단일 체계로 통일 |
| C3 | 런타임 설정 키가 3곳 수동 동기화 (config 기본값 ↔ MUTABLE_SETTINGS 215키 ↔ 검증 if 체인). enum 위반은 조용히 무시(`_SKIP`) | `core/runtime_settings.py:10-508` | 단일 레지스트리에서 파생 생성, 검증 실패는 400 반환 |
| C4 | 레이어 위반: core→scheduler, core→fastapi, services→admin(표현 계층) | `core/post_liquidation_guard.py:6`, `core/runtime_settings.py:5`, `services/activity_logger.py:9` | market_calendar를 core/domain으로 이동, 도메인 예외 분리 |
| C5 | 죽은 코드: `core/database.py:62-63` 도달 불가, 동기 BaseRepository 미사용, stale `/dashboard/system/status`, 미사용 Deps, 유령 DB 파일 4개(0바이트) | 각 파일 확인 | 일괄 정리 (C3과 같은 PR 권장) |
| C6 | LLM JSON 파싱 5곳 독립 구현, 뉴스 수집 서비스 6종 패턴 복제, naive datetime 9곳 | `core/json_utils.py:15` 외 | `parse_llm_json`으로 수렴, 뉴스 수집 공통 베이스 추출 |

### P2-T — 테스트/CI

2026-06-11 전체 실행 결과: **pytest 1009 passed / 8 failed (37분 53초)**, **vitest 143 passed / 1 failed**. 실패 9건은 모두 이번 태스크에서 수정 완료 — 단, 실패 원인 자체가 구조적 문제를 드러냄:

| # | 이슈 | 조치 |
|---|------|------|
| Q1 | **단위 테스트가 실제 외부 호출을 함**: llm_factory 테스트는 모델 override 경로에서 실제 LLM CLI를 실행했고, news_polling 테스트 5건은 모킹 누락된 소스(investing, seeking_alpha)가 실제 HTTP를 호출해 실데이터 18건이 검증에 섞임 | (수정 완료) 구조 대책: conftest에서 외부 네트워크/CLI 차단 가드 추가, 새 뉴스 소스 추가 시 테스트 픽스처 갱신을 체크리스트화 |
| Q2 | **시한폭탄 테스트**: holding_policy 픽스처가 `entry_at=2026-05-27` 고정 → 15일 경과한 6/11에 MAX_HOLD_DAYS_MID에 걸려 깨짐. holdings_precheck는 mid-long 정책 전환(-3% → 추론 MID -7%) 이전 기대값을 유지한 stale test | (수정 완료) 구조 대책: 날짜 의존 테스트는 상대 시간 또는 freezegun 사용 규칙화 |
| Q3 | CI 부재 (`.github/workflows` 없음) — 위 9건이 수일간 조용히 깨져 있어도 아무도 모름. vitest 실패도 UI 변경 커밋(`ad0eb6e`)이 테스트 갱신 없이 들어간 것 | GitHub Actions에 pytest+vitest+harness check 등록. 37분 스위트는 분할/병렬화(-n auto) 검토 |

## 2. 추가해야 할 점 (기능 공백)

1. **실체결 데이터 파이프라인** (T1과 동일 — 최우선)
2. **포트폴리오 수준 리스크**: 섹터/테마 집중도 한도, 상관 노출 한도 (현재는 종목 단위 사이징뿐)
3. **LLM 비용 하드 캡**: 일일 호출/토큰 예산 초과 시 deterministic-only 모드 강등 (현재는 관측만)
4. **외부 알림** (O1)
5. **VI/거래정지 상태 머신** (T7)
6. **CI 파이프라인** (Q2)

## 3. 나아갈 방향 (전략적 진화)

1. **"PnL truth" 우선**: 실측 체결 데이터 → 가드/expectancy/캘리브레이션 신뢰성 확보가 모든 피드백 루프의 전제.
2. **SHADOW → ENFORCE 졸업 절차 정립**: order reservation, news gate, fast gate, equity DD 가드 등 잠들어 있는 보호 장치들을, 이미 쌓이는 decision_event/forward-return 데이터로 "차단했더라면 손실이 줄었는가"를 측정해 단계적으로 전환. 졸업 기준을 `docs/architecture/trading-policy-governance.md`에 명문화.
3. **백테스트를 '게이트 리플레이'로 진화**: 현재 백테스트는 LLM 대신 RSI/MACD 프록시 + 갭 무시 체결(`backtesting/engine.py:226-232`)이라 실전 전략 검증 불가. decision_event 기록이 풍부하므로 과거 사이클 재생 방식이 더 현실적.
4. **호라이즌 중심 청산 체계 고도화**: staged stop/min-hold/hold extension 설계는 좋음 — 다음 단계는 호라이즌별 성과 분해(IC/expectancy by horizon)로 파라미터를 데이터 기반 튜닝.
5. **지식 그래프 상시화**: `.understand-anything/` 그래프를 커밋해 팀 공유, `/understand-diff`를 정책 변경 체크리스트에 편입.

## 4. 실행 순서 제안

| 단계 | 내용 | 규모 |
|------|------|------|
| Phase 0 (이번 주) | S1–S4 보안 차단, O6 venv (테스트 9건은 이번 태스크에서 수정 완료) | 작음 — 대부분 설정/한 줄 |
| Phase 1 | T1 실체결가, T2 미실현 차단, T6 TZ 통일, O1 알림, O2 백업 잡, O4 기동 reconcile | 중간 |
| Phase 2 | T3 손절 주기, T4 예약 ENFORCE, T5 매도 락, T9 블록리스트 리셋, O3 재시작, Q2 CI | 중간 |
| Phase 3 | C1–C6 구조 개선, T7 상태 머신, T8 뉴스 lookback, 백테스트 개선 | 큼 — 분할 진행 |

각 Phase는 `scripts/task_harness.py start`로 개별 태스크 등록 후 진행. 매매 임계값/청산/브로커 동작에 닿는 항목(T2–T5, T7)은 `docs/workflows/trading-policy-change-checklist.md` 절차를 먼저 따른다.

## 5. 도구 연동 (Understand-Anything)

- 산출물 위치: `momo-trading/.understand-anything/` (`knowledge-graph.json`, `config.json`)
- 시각화: `/understand-dashboard` (대화형 웹 대시보드)
- 변경 영향도: 보호 영역 수정 전 `/understand-diff` 실행을 commit harness 체크리스트에 추가 권장
- 온보딩: `/understand-onboard`로 신규 참여자 가이드 생성 가능
