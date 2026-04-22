# System-Wide Trading Audit TODO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MOMO Trading의 주문, 리스크, 성과 측정, 전략, LLM, 뉴스, 스케줄러, 운영, 보안, Admin 기능을 증거 기반으로 감사하고, 승인 가능한 개선 로드맵을 만든다.

**Architecture:** 구현보다 먼저 read-only evidence pack을 만든다. 그 다음 P0/P1 안전 문제, PnL 신뢰도, 전략 기대값, 뉴스/LLM 가치, 운영/보안 리스크를 분리해 findings를 작성한다. 실제 코드 변경은 findings와 roadmap 승인 후 TDD로 작은 단위로 진행한다.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, SQLite, pytest, pytest-asyncio, Vitest, pandas/numpy, APScheduler, loguru

---

## 핵심 원칙

- 이 계획은 먼저 감사와 문서화를 수행한다. 코드, 전략 파라미터, live trading 설정은 별도 승인 전 변경하지 않는다.
- 모든 구현은 TDD로 진행한다. 먼저 실패하는 테스트를 만들고, 실패를 확인하고, 최소 구현으로 통과시킨다.
- SOLID와 관심사 분리를 지킨다. 주문, 리스크, PnL, 전략 평가, LLM/뉴스, 운영/보안 로직을 서로 섞지 않는다.
- 외부 라이브러리는 바로 추가하지 않는다. 기존 코드로 충분한지 먼저 판단하고, 라이브러리 추가는 장점/단점/락인/테스트 비용을 문서화한 뒤 승인받는다.
- 수익 보장은 하지 않는다. 목표는 손실 가능성 축소, 측정 신뢰도 향상, 기대값 있는 실험을 가능하게 만드는 것이다.

## 참고 기준

- SEC Rule 15c3-5: 사전 주문 리스크 제어, 자본/신용 한도, 오류/중복 주문 차단, 제한 종목 차단, 사후 체결 감시.
  https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access
- FINRA Algorithmic Trading / Market Access: 알고리즘 개발, 테스트, 배포 통제, 모니터링, 사전 주문 한도.
  https://www.finra.org/rules-guidance/key-topics/algorithmic-trading
  https://www.finra.org/rules-guidance/guidance/reports/2025-finra-annual-regulatory-oversight-report/market-access-rule
- KRX Market Surveillance: 조작, 규칙 위반, 계좌/패턴 기반 감시, market replay 관점.
  https://global.krx.co.kr/contents/GLB/04/0402/0402030000/GLB0402030000.jsp
- 대한민국 자본시장과 금융투자업에 관한 법률: 투자자 보호, 시장 공정성, 거래 질서, 불공정거래 방지.
  https://elaw.klri.re.kr/eng_mobile/ganadaDetail.do?hseq=73666&key=FINANCIAL+INVESTMENT+SERVICES+AND+CAPITAL+MARKETS+ACT&param=F&type=abc
- NIST SSDF / DevSecOps: 계획, 개발, 빌드, 테스트, 릴리즈, 배포, 운영 전 단계 보안과 검증.
  https://csrc.nist.gov/pubs/sp/800/218/final
  https://pages.nist.gov/nccoe-devsecops/
- OWASP Secrets Management: 시크릿 생성, 저장, 접근 제어, 회전, 폐기, 사고 대응.
  https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- Backtrader / QuantConnect: 백테스트에서 수수료, 슬리피지, 체결 모델이 필수라는 기준.
  https://www.backtrader.com/docu/slippage/slippage/
  https://www.backtrader.com/docu/commission-schemes/commission-schemes/
  https://www.quantconnect.com/docs/v1/algorithm-reference/trading-and-orders
- vectorbt: 벡터화 백테스트와 order fees/slippage, partial fill, stop price 설정 비교 기준.
  https://vectorbt.dev/api/portfolio/enums/
  https://vectorbt.dev/getting-started/features/
- ml4t-backtest: 최신 event-driven 백테스트 후보. 아직 베타/신규 라이브러리이므로 검증 주장, 제한사항, 의존성 안정성을 별도 확인해야 한다.
  https://pypi.org/project/ml4t-backtest/
- Bailey & López de Prado Deflated Sharpe Ratio: 다중 테스트, 선택 편향, 비정규 수익률, 백테스트 과최적화 보정.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

## 산출물

- Create: `docs/audits/2026-04-22-system-wide-trading-audit-evidence.md`
  - 읽기 전용 증거, 명령, 쿼리 결과 요약, 파일/라인 근거를 기록한다.
- Create: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`
  - P0-P3 문제, 영향, 증거, 권고안, 제거/비활성화/유지/실험 분류를 기록한다.
- Create: `docs/superpowers/plans/2026-04-22-system-wide-trading-improvement-roadmap.md`
  - 감사 결과 기반 구현 계획이다. 이 문서 승인 후에만 실제 코드 변경을 시작한다.
- Existing spec: `docs/audits/2026-04-22-system-wide-trading-audit-plan.md`
  - 감사 범위와 기준선이다.

## 후보 라이브러리 검토 원칙

- 백테스트 엔진은 기존 `backtesting/`을 먼저 검증한다. 비용/슬리피지/체결 모델이 부족하면 Backtrader, vectorbt, QuantConnect LEAN, ml4t-backtest 중 비교표를 만든다.
- pandas/numpy는 이미 사용 중이므로 성과 분석과 forward return 계산에는 우선 기존 의존성을 사용한다.
- 시크릿 스캔은 먼저 `rg` 기반 read-only 점검으로 시작한다. 필요하면 gitleaks/trufflehog 같은 도구 도입을 별도 승인받는다.
- 관측성은 기존 `execution_metrics`, `error_events`, `error_incidents`, `resource_snapshots`를 먼저 활용한다. Prometheus 같은 외부 스택은 현재 단일 로컬 운영 구조에서는 후순위다.

## Phase 0: 감사 안전선 확정

**Files:**
- Read: `docs/audits/2026-04-22-system-wide-trading-audit-plan.md`
- Create: `docs/audits/2026-04-22-system-wide-trading-audit-evidence.md`
- Create: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`

- [x] **Step 1: 사용자 승인 조건 기록**
  - live bot을 계속 거래하게 둘지, read-only/semi-auto로 둘지 기록한다.
  - 브로커 read-only API 호출 허용 여부를 기록한다.
  - 뉴스 기능을 감사 중 계속 꺼둘지 기록한다.
  - 시크릿 스캔 범위를 `tracked only`, `runtime logs 포함`, `.env 포함`, `shell history 포함` 중 어디까지 볼지 기록한다.

- [x] **Step 2: 감사 evidence 문서 생성**
  - `docs/audits/2026-04-22-system-wide-trading-audit-evidence.md`를 생성한다.
  - 섹션은 `환경`, `Git 상태`, `런타임 상태`, `DB 스냅샷`, `브로커 스냅샷`, `파일/라인 근거`, `외부 기준`, `남은 질문`으로 나눈다.

- [x] **Step 3: findings 문서 생성**
  - `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`를 생성한다.
  - P0/P1/P2/P3 템플릿을 만든다.
  - 각 finding은 `현상`, `영향`, `증거`, `재현/검증`, `권고`, `구현 전 테스트`, `rollout/rollback`을 포함한다.

- [x] **Step 4: 초기 검증**
  - Run: `git status --short`
  - Expected: 감사 문서 변경 외에 의도치 않은 코드 변경이 없어야 한다.

## Phase 1: Source of Truth와 DB 무결성 감사

**Files:**
- Read: `models/`
- Read: `repositories/`
- Read: `alembic/versions/`
- Read: `core/database.py`
- Read: `api/routes/admin.py`
- Update: `docs/audits/2026-04-22-system-wide-trading-audit-evidence.md`
- Update: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`

- [x] **Step 1: 테이블/모델/마이그레이션 맵 작성**
  - `trade_results`, `orders`, `portfolio_holdings`, `account_equity_snapshots`, `runtime_settings`, `trading_rules`, `error_events`, `error_incidents`, `market_data_daily`, `market_snapshots`, `news_items`의 모델과 repository를 연결해 기록한다.

- [x] **Step 2: read-only DB 스냅샷 수집**
  - 주문 상태별 수량, pending age, 체결/미체결, 계좌 snapshot, error incident, runtime setting, trading rules를 수집한다.
  - DB 파일 위치는 먼저 `core/config.py`, `core/database.py`, `runtime/`에서 확인한다.

- [x] **Step 3: PnL source of truth 후보 정리**
  - `trade_results.pnl`, `orders`, `account_equity_snapshots.total_unrealized_pnl`, 브로커 스냅샷 중 무엇이 어느 상황에서 기준인지 정리한다.

- [x] **Step 4: findings 기록**
  - PnL이 닫힌 거래 기준인지, 열린 포지션 평가손익까지 포함하는지 불명확하면 P1 후보로 기록한다.
  - DB와 브로커 포지션 불일치 가능성이 있으면 P0/P1 후보로 기록한다.

## Phase 2: 주문 생명주기와 브로커 transport 감사

**Files:**
- Read: `agent/decision_maker.py`
- Read: `trading/order_executor.py`
- Read: `trading/account_manager.py`
- Read: `trading/adapters/base.py`
- Read: `trading/adapters/kiwoom_adapter.py`
- Read: `trading/adapters/kis_adapter.py`
- Read: `trading/mcp_client.py`
- Read: `trading/kis_websocket.py`
- Read: `scheduler/jobs/portfolio_sync_job.py`
- Read: `services/manual_trade_service.py`
- Read: `services/broker_smoke_service.py`
- Read: `tests/agent/test_decision_maker.py`
- Read: `tests/trading/`
- Update: audit evidence/findings docs

- [x] **Step 1: 주문 상태 전이표 작성**
  - `PENDING_CONFIRM`, `CONFIRMED`, `CONFIRM_FAILED`, open/closed sell 상태가 어디서 생성/변경되는지 파일/라인으로 기록한다.

- [x] **Step 2: 중복 주문 차단 경로 확인**
  - pending buy, pending sell, manual trade, scheduler liquidation, holdings review가 같은 종목을 동시에 건드릴 수 있는지 확인한다.

- [x] **Step 3: MCP/SSE 실패 복구 확인**
  - `trading/mcp_client.py`의 pending future, `_unconfirmed_orders`, reconnect, rate limit, timeout 처리 흐름을 기록한다.

- [x] **Step 4: 브로커 read-only smoke 기준 정의**
  - 승인된 경우에만 `tools/broker_smoke.py` 또는 service 경로로 잔고/보유/미체결/quote를 조회한다.
  - 승인 없으면 코드와 테스트만 근거로 감사한다.

- [x] **Step 5: 구현 후보 테스트 정의**
  - 문제가 발견되면 먼저 `tests/agent/test_decision_maker.py`, `tests/scheduler/test_portfolio_sync_job.py`, `tests/services/test_manual_trade_service.py`, `tests/trading/test_mcp_client.py`에 실패 테스트를 추가하는 계획으로 기록한다.

## Phase 3: 리스크 제어와 자본 배분 감사

**Files:**
- Read: `strategy/risk_manager.py`
- Read: `strategy/trading_guard.py`
- Read: `strategy/ai_risk_tuner.py`
- Read: `strategy/holding_policy.py`
- Read: `models/trading_rule.py`
- Read: `services/runtime_settings_service.py`
- Read: `services/runtime_reconfiguration_service.py`
- Read: `tests/strategy/`
- Read: `tests/agent/test_trading_agent_cost_gate.py`
- Update: audit evidence/findings docs

- [x] **Step 1: 리스크 gate 순서 맵 작성**
  - LLM decision, strategy signal, cost gate, risk manager, trading guard, broker submit 순서를 그린다.

- [x] **Step 2: 노출 계산 기준 확인**
  - 현금, 보유 수량, 미체결 주문, 종목별 노출, 일일 손실, 평가손익이 모두 주문 전 계산에 들어가는지 확인한다.

- [x] **Step 3: trading rules 우선순위 확인**
  - `trading_rules`와 runtime settings가 LLM 판단보다 먼저/강하게 적용되는지 확인한다.

- [x] **Step 4: P0/P1 후보 기록**
  - 미체결 주문이 노출에서 빠지면 P0/P1.
  - 평가손실이 kill switch에서 빠지면 P1.
  - 손절/청산 로직이 진입보다 약하면 P1.

## Phase 4: 성과 측정과 PnL 신뢰도 감사

**Files:**
- Read: `services/performance_reporting_service.py`
- Read: `services/account_equity_service.py`
- Read: `analysis/feedback/performance_tracker.py`
- Read: `models/trade_result.py`
- Read: `models/account_equity_snapshot.py`
- Read: `tests/services/test_performance_reporting_service.py`
- Read: `tests/services/test_account_equity_service.py`
- Update: audit evidence/findings docs

- [x] **Step 1: realized/unrealized PnL 정의 분리**
  - 닫힌 거래 손익, 열린 포지션 평가손익, 총자산 변화, 현금 변화의 정의를 분리한다.

- [x] **Step 2: 성과 지표 신뢰도 점검**
  - expectancy, profit factor, max drawdown, win rate, trade count가 어떤 source에서 계산되는지 기록한다.

- [x] **Step 3: canonical PnL 모델 초안 작성**
  - 구현하지 말고 먼저 어떤 테이블/필드가 canonical인지 findings에 제안한다.

- [x] **Step 4: 구현 후보 테스트 정의**
  - 문제 발견 시 `tests/services/test_performance_reporting_service.py`에 “닫힌 거래만”, “열린 평가손익 포함”, “브로커 snapshot과 대사” 테스트를 먼저 추가하도록 계획한다.

## Phase 5: 전략 가치와 매매 기대값 감사

**Files:**
- Read: `agent/market_scanner.py`
- Read: `agent/stock_screener.py`
- Read: `agent/trading_agent.py`
- Read: `analysis/chart_analyzer.py`
- Read: `analysis/technical/`
- Read: `strategy/stable_short.py`
- Read: `strategy/aggressive_short.py`
- Read: `strategy/signal.py`
- Read: `repositories/analysis_repository.py`
- Read: `repositories/recommendation_repository.py`
- Read: `tests/agent/`
- Update: audit evidence/findings docs

- [ ] **Step 1: funnel 정의**
  - `scan -> screen -> chart/LLM -> final review -> strategy -> risk -> order -> fill -> PnL` 단계별 count를 정의한다.

- [ ] **Step 2: forward return 기준 정의**
  - BUY/HOLD/SKIP 이후 5분, 15분, 30분, 1시간, 장마감 수익률을 어떤 market data로 계산할지 정한다.

- [ ] **Step 3: 벤치마크 정의**
  - 거래 안 함, 같은 후보군 랜덤, 스캐너만, 기술 분석만, LLM만, LLM+리스크를 비교 대상으로 둔다.

- [ ] **Step 4: 전략 제거/유지 기준 적용**
  - 기준선보다 못하거나 비용/리스크만 증가시키는 단계는 `기본 비활성화` 또는 `실험` 후보로 기록한다.

## Phase 6: 백테스트와 실험 위생 감사

**Files:**
- Read: `backtesting/engine.py`
- Read: `backtesting/metrics.py`
- Read: `backtesting/report.py`
- Read: `backtesting/data_loader.py`
- Read: `tests/backtesting/test_data_loader.py`
- Update: audit evidence/findings docs

- [ ] **Step 1: 현재 백테스트 가정 기록**
  - 체결 시점, 수수료, 세금, 슬리피지, 상하한가, 미체결, survivorship bias, look-ahead 가능성을 기록한다.

- [ ] **Step 2: 외부 라이브러리 비교표 작성**
  - Backtrader: 성숙한 event-driven 엔진, 수수료/슬리피지 모델 문서가 좋다.
  - vectorbt: 벡터화 성능 장점, event/order lifecycle 세밀성은 별도 검토 필요.
  - QuantConnect LEAN: 현실 모델이 좋지만 로컬 통합 비용이 크다.
  - ml4t-backtest: 최신 라이브러리라 검증 주장과 의존성 안정성을 별도 검토해야 한다.

- [ ] **Step 3: 도입 여부 결정 게이트**
  - 현재 `backtesting/`을 고치는 편이 나은지, 외부 라이브러리 검증 계층을 붙일지 findings에 기록한다.
  - 라이브러리 추가가 필요하면 별도 계획과 사용자 승인을 받는다.

- [ ] **Step 4: 과최적화 방지 기준 작성**
  - walk-forward, out-of-sample, parameter trial log, Deflated Sharpe Ratio 또는 최소한의 multiple-testing 보정 계획을 roadmap에 넣는다.

## Phase 7: LLM, 뉴스, 비용/지연 가치 감사

**Files:**
- Read: `analysis/llm/`
- Read: `analysis/llm/prompts/`
- Read: `services/llm_usage_service.py`
- Read: `services/llm_runtime_recommendation_service.py`
- Read: `services/news_*`
- Read: `services/open_dart_disclosure_service.py`
- Read: `services/krx_kind_disclosure_service.py`
- Read: `services/yonhap_news_service.py`
- Read: `services/bloomberg_news_service.py`
- Read: `services/cnbc_news_service.py`
- Read: `services/nasdaq_news_service.py`
- Read: `services/investing_news_service.py`
- Read: `services/seeking_alpha_news_service.py`
- Read: `tests/analysis/`
- Read: `tests/services/test_news_*`
- Update: audit evidence/findings docs

- [ ] **Step 1: LLM 단계별 가치 측정 기준 정의**
  - latency, timeout, fallback, provider, model, prompt version, confidence, forward return을 연결할 기준을 정한다.

- [ ] **Step 2: Codex/Claude/Ollama 병렬도 정책 검토**
  - Codex 번역 병렬도 1 고정과 news fetch 병렬도의 차이를 문서화한다.
  - CLI timeout cascade와 rate limit이 거래 판단을 막는지 확인한다.

- [ ] **Step 3: 뉴스 소스별 비용/가치 평가**
  - DART, KRX, YONHAP, BLOOMBERG, CNBC, NASDAQ, INVESTING, SEEKING_ALPHA별 성공률, 중복률, stale rate, trade gate 기여도를 평가한다.

- [ ] **Step 4: 제거/비활성화 후보 기록**
  - 기여도 미확인인데 latency/cost/failure만 늘리면 `기본 비활성화`.
  - noisy source는 `active set 제거` 또는 `cooldown 강화`.

## Phase 8: 스케줄러, 실시간 이벤트, 운영/보안/Admin 감사

**Files:**
- Read: `scheduler/scheduler.py`
- Read: `scheduler/market_calendar.py`
- Read: `realtime/`
- Read: `services/observability_*`
- Read: `services/error_*`
- Read: `services/system_preflight_service.py`
- Read: `services/runtime_backup_service.py`
- Read: `api/routes/admin.py`
- Read: `admin/static/index.html`
- Read: `admin/static/js/`
- Read: `tests/scheduler/`
- Read: `tests/realtime/`
- Read: `tests/frontend/`
- Read: `tests/api/test_admin_*`
- Update: audit evidence/findings docs

- [ ] **Step 1: scheduler job timeline 작성**
  - 정기 스캔, 이벤트 기반 분석, 뉴스 수집, 번역 backfill, 포트폴리오 sync, daily report가 겹치는지 기록한다.

- [ ] **Step 2: 운영 상태 신뢰도 점검**
  - PID, logs, incidents, health, broker runtime, Admin dashboard가 같은 사실을 보여주는지 확인한다.

- [ ] **Step 3: 보안/시크릿 점검**
  - 승인된 범위 안에서 `.env.example`, tracked files, runtime logs의 secret-like pattern을 확인한다.
  - 토큰/계좌번호가 발견되면 값은 문서에 쓰지 않고 위치와 조치만 기록한다.

- [ ] **Step 4: Admin 수동 제어 안전성 점검**
  - 읽기 전용 action과 위험 action이 분리되는지, pending 주문 취소/대체/매도 action이 중복을 막는지 확인한다.

## Phase 9: Findings 리뷰와 구현 로드맵 작성

**Files:**
- Update: `docs/audits/2026-04-22-system-wide-trading-audit-findings.md`
- Create: `docs/superpowers/plans/2026-04-22-system-wide-trading-improvement-roadmap.md`

- [ ] **Step 1: P0/P1 먼저 정렬**
  - 기준: 통제되지 않은 노출, 중복 주문, 거짓 PnL, 브로커/DB 불일치, 위험한 운영 상태.

- [ ] **Step 2: 구현 묶음 분리**
  - `Order safety`
  - `PnL truth`
  - `Risk and exposure`
  - `Strategy evaluation`
  - `Backtest hygiene`
  - `LLM/news simplification`
  - `Observability/security/Admin safety`

- [ ] **Step 3: 각 묶음에 TDD 태스크 작성**
  - 각 태스크는 `실패 테스트 -> 실패 확인 -> 최소 구현 -> 통과 확인 -> 관련 테스트 -> 커밋` 순서로 쓴다.

- [ ] **Step 4: rollout/rollback 작성**
  - live trading 영향이 있는 변경은 feature flag 또는 runtime setting으로 끌 수 있어야 한다.
  - 주문/리스크 변경은 shadow mode 또는 read-only validation 단계가 먼저 있어야 한다.

- [ ] **Step 5: 사용자 승인 요청**
  - 이 단계까지 완료되면 구현을 시작하지 말고 roadmap 승인 요청을 한다.

## 예상 구현 계획 템플릿

실제 구현은 감사 결과가 나온 뒤 아래 형식을 따른다.

### Template A: 주문 안전성 수정

**Files:**
- Modify: `agent/decision_maker.py`
- Modify: `scheduler/jobs/portfolio_sync_job.py`
- Test: `tests/agent/test_decision_maker.py`
- Test: `tests/scheduler/test_portfolio_sync_job.py`

- [ ] **Step 1: 실패 테스트 작성**
  - 중복 pending buy, 오래된 PENDING_CONFIRM, 부분체결/부분청산 케이스 중 하나를 재현한다.
- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/scheduler/test_portfolio_sync_job.py -q`
  - Expected: 새 테스트가 의도한 이유로 실패한다.
- [ ] **Step 3: 최소 구현**
  - 주문 intent 단위 idempotency 또는 stale pending reconciliation을 최소 범위로 구현한다.
- [ ] **Step 4: 통과 확인**
  - 같은 pytest 명령을 다시 실행한다.
- [ ] **Step 5: 회귀 확인**
  - Run: `./.venv313/bin/python -m pytest tests/agent tests/trading tests/scheduler -q`

### Template B: PnL 신뢰도 수정

**Files:**
- Modify: `services/performance_reporting_service.py`
- Modify: `services/account_equity_service.py`
- Test: `tests/services/test_performance_reporting_service.py`
- Test: `tests/services/test_account_equity_service.py`

- [ ] **Step 1: 실패 테스트 작성**
  - 닫힌 거래 실현손익과 열린 포지션 평가손익이 섞이지 않도록 테스트한다.
- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_performance_reporting_service.py tests/services/test_account_equity_service.py -q`
- [ ] **Step 3: 최소 구현**
  - canonical PnL 계산을 service 단위로 분리한다.
- [ ] **Step 4: 통과 확인**
  - 같은 pytest 명령을 다시 실행한다.

### Template C: 뉴스/LLM 단순화 또는 gating

**Files:**
- Modify: `services/news_runtime_service.py`
- Modify: `services/news_signal_service.py`
- Modify: `analysis/llm/selection_policy.py`
- Test: `tests/services/test_news_runtime_service.py`
- Test: `tests/services/test_news_signal_service.py`
- Test: `tests/analysis/test_llm_factory.py`

- [ ] **Step 1: 실패 테스트 작성**
  - noisy source cooldown, stale news reject, provider fallback 의미 보존 중 하나를 재현한다.
- [ ] **Step 2: 실패 확인**
  - Run: `./.venv313/bin/python -m pytest tests/services/test_news_runtime_service.py tests/services/test_news_signal_service.py tests/analysis/test_llm_factory.py -q`
- [ ] **Step 3: 최소 구현**
  - 뉴스/LLM 단계는 deterministic guardrail을 우선하고 LLM은 판단 보조로 제한한다.
- [ ] **Step 4: 통과 확인**
  - 같은 pytest 명령을 다시 실행한다.

## 최종 검증 게이트

- [ ] Backend targeted tests
  - Run: `./.venv313/bin/python -m pytest tests/agent tests/trading tests/strategy tests/services tests/scheduler tests/realtime tests/backtesting -q`
- [ ] API/Admin targeted tests
  - Run: `./.venv313/bin/python -m pytest tests/api -q`
- [ ] Frontend state tests
  - Run: `pnpm test:ui`
- [ ] Full backend suite
  - Run: `./.venv313/bin/python -m pytest -q`
- [ ] Git safety
  - Run: `git status --short`
  - Expected: 의도한 문서/코드 변경만 있어야 한다.

## 구현 시작 전 확인

- [ ] 사용자가 Phase 0의 운영 안전선에 답했다.
- [ ] evidence 문서가 생성됐다.
- [ ] findings 문서에 P0/P1/P2/P3가 정리됐다.
- [ ] improvement roadmap이 작성됐다.
- [ ] 사용자가 roadmap 구현을 명시적으로 승인했다.

이 조건이 충족되기 전에는 코드, 설정, 전략 파라미터, live trading 동작을 변경하지 않는다.
