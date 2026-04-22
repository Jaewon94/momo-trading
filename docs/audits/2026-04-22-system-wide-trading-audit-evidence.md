# MOMO Trading 전체 시스템 감사 Evidence

> 상태: Phase 0 기준선 문서입니다. 이 문서는 읽기 전용 감사 증거를 누적합니다. 코드, 설정, 전략 파라미터, live trading 동작 변경은 별도 승인과 findings/roadmap 반영 전에는 하지 않습니다.

## Phase 0: 감사 안전선

### 감사 운영 기준

- 감사 중 live bot 운영 기준: `read-only / semi-auto` 우선. 실제 런타임 설정 변경은 별도 evidence와 함께 수행합니다.
- 브로커 read-only API 조회: 허용. 계좌, 보유, 미체결, quote 스냅샷 확인 목적에 한정합니다.
- 뉴스 기능: 감사 완료 전까지 `OFF 유지`를 기본값으로 둡니다. 재활성화는 뉴스 가치/부하/지연 평가 후 결정합니다.
- 개선 우선순위: 손실 방어, 주문 안전성, PnL 신뢰도, 리스크/노출 계산을 기대수익 실험보다 먼저 봅니다.
- 시크릿 스캔 범위: `tracked files + runtime logs`를 기본 범위로 둡니다. `.env`와 shell history는 필요 시 별도 확인 후 진행합니다.
- 구현 정책: findings와 improvement roadmap 승인 전에는 코드 구현을 시작하지 않습니다.

### 환경 기준점

- 기준 시각: `2026-04-22 10:53:17 KST`
- 작업 브랜치: `jaewon-ver`
- 기준 커밋: `8de637b8939427f265e5f2239bdf7e774ac135cd`
- 감사 범위 문서: `docs/audits/2026-04-22-system-wide-trading-audit-plan.md`
- 감사 TODO 문서: `docs/superpowers/plans/2026-04-22-system-wide-trading-audit-todo.md`

### Phase 0 검증 명령

```bash
git status --short
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
```

### Phase 0 관찰

- 현재까지 수행한 작업은 문서 생성과 문서 보정뿐입니다.
- 아직 DB read-only 쿼리, 브로커 read-only 스냅샷, 시크릿 스캔, 코드 분석 findings 작성은 시작하지 않았습니다.
- Phase 1부터 DB source of truth와 PnL 신뢰도 검증을 시작합니다.

### Phase 0 후속 안전 조치

- Phase 1 시작 시 runtime 설정을 확인한 결과 `AUTONOMY_MODE="AUTONOMOUS"`, `TRADING_ENABLED=true`였습니다.
- 감사 운영 기준과 맞추기 위해 Admin `/api/v1/admin/settings/apply` 경로로 `AUTONOMY_MODE="SEMI_AUTO"`를 적용했습니다.
- 적용 결과:
  - 변경: `AUTONOMY_MODE: AUTONOMOUS -> SEMI_AUTO`
  - scheduler was running: `true`
  - scheduler restarted: `true`
  - agent idle: `true`
  - scheduler idle: `true`
  - elapsed: `55814ms`
- 적용 후 API 확인:
  - `TRADING_ENABLED=true`
  - `AUTONOMY_MODE="SEMI_AUTO"`
  - `NEWS_POLL_ENABLED=false`
  - `NEWS_GATE_ENABLED=false`
  - `NEWS_LLM_ENABLED=false`
- 해석: 자동 주문 경로는 막고, 수동/반자동 검토와 기존 리스크 청산 가능성은 남긴 상태입니다. 단, `system/status`의 `market_session_auto_trading=true`는 시장 세션상 자동매매 가능 여부 표시로 보이며 실제 주문 분기는 `AUTONOMY_MODE`를 추가 확인해야 합니다.

## Phase 1: Source of Truth와 DB 무결성

### 설정과 DB 위치

- `core.config.Settings.DATABASE_URL` 기본값은 `runtime/data/app.db`입니다.
- 실제 `.env`에는 `DATABASE_URL=sqlite:///./data/app.db`가 설정되어 있습니다.
- `runtime/data/app.db`는 4KB이며 주요 테이블이 없거나 잠금 상태였습니다.
- 실제 운영 데이터는 `data/app.db`에서 확인되었습니다.
- Alembic 현재 버전: `d204f5a8b1c7`

### 테이블/모델/Repository 맵

| 테이블 | 모델 | Repository | 주요 역할 |
|---|---|---|---|
| `trade_results` | `models/trade_result.py` | `repositories/trade_result_repository.py` | 체결/포지션/PnL 유사 source |
| `orders` | `models/order.py` | `repositories/order_repository.py` | 일반 주문 엔티티. 현재 운영 DB rows 0 |
| `portfolio_holdings` | `models/portfolio.py` | `repositories/portfolio_repository.py` | DB 보유 종목. 현재 운영 DB rows 0 |
| `account_equity_snapshots` | `models/account_equity_snapshot.py` | `repositories/account_equity_snapshot_repository.py` | 계좌 자산/현금/평가손익 스냅샷 |
| `account_day_baselines` | `models/account_day_baseline.py` | `repositories/account_day_baseline_repository.py` | 일중 기준선 |
| `runtime_settings` | `models/runtime_setting.py` | `repositories/runtime_setting_repository.py` | Admin 런타임 설정 |
| `trading_rules` | `models/trading_rule.py` | 직접 repository 없음 | AI 일일 리뷰 기반 hard rule |
| `error_events` | `models/error_event.py` | `repositories/error_event_repository.py` | 개별 오류 이벤트 |
| `error_incidents` | `models/error_incident.py` | `repositories/error_incident_repository.py` | 오류 incident 집계 |
| `execution_metrics` | `models/execution_metric.py` | `repositories/execution_metric_repository.py` | 실행/LLM/운영 메트릭 |
| `resource_snapshots` | `models/resource_snapshot.py` | `repositories/resource_snapshot_repository.py` | 리소스 스냅샷 |
| `news_items` | `models/news_item.py` | `repositories/news_item_repository.py` | 뉴스/공시 저장소 |
| `market_data_daily` | `models/market_data.py` | `repositories/market_data_repository.py` | 일봉 데이터 |
| `market_snapshots` | `models/market_data.py` | `repositories/market_data_repository.py` | 현재가 스냅샷 |

### 운영 DB Row Count

| 테이블 | rows |
|---|---:|
| `trade_results` | 73 |
| `orders` | 0 |
| `portfolio_holdings` | 0 |
| `account_equity_snapshots` | 195 |
| `agent_activity_logs` | 3399 |
| `execution_metrics` | 2197 |
| `error_events` | 819 |
| `error_incidents` | 144 |
| `strategy_signals` | 0 |
| `recommendations` | 0 |
| `news_items` | 65 |
| `runtime_settings` | 32 |
| `trading_rules` | 7 |
| `market_data_daily` | 0 |
| `market_snapshots` | 0 |

### Runtime Settings Snapshot

| key | value |
|---|---|
| `AUTONOMY_MODE` | `"SEMI_AUTO"` |
| `TRADING_ENABLED` | `true` |
| `SCHEDULER_ENABLED` | `true` |
| `NEWS_POLL_ENABLED` | `false` |
| `NEWS_GATE_ENABLED` | `false` |
| `NEWS_LLM_ENABLED` | `false` |
| `NEWS_FETCH_CONCURRENCY` | `3` |
| `NEWS_TRANSLATION_CONCURRENCY` | `1` |
| `LLM_TIER1_CONCURRENCY` | `1` |
| `LLM_TIER2_CONCURRENCY` | `1` |

### Trade Result 상태

| status | side | count |
|---|---|---:|
| `CONFIRMED` | `BUY` | 48 |
| `CONFIRMED` | `SELL` | 5 |
| `PENDING_CONFIRM` | `BUY` | 20 |

추가 관찰:

- `PENDING_CONFIRM`은 2026-04-22 09:07:55부터 10:43:48까지 생성되어 있습니다.
- 반복 종목이 있습니다. 예: `092220 KEC`, `131400 이브이첨단소재`, `001250 GS글로벌`.
- `CONFIRMED` 거래의 `pnl_sum`은 BUY/SELL 모두 `0.0`입니다.
- `orders` 테이블은 0 rows입니다. 현재 주문/체결 source는 `orders`가 아니라 `trade_results`와 브로커/계좌 스냅샷에 치우쳐 있습니다.

### Account Equity 최신 스냅샷

| captured_at | total_asset | cash | stock_value | total_unrealized_pnl | pending_order_count |
|---|---:|---:|---:|---:|---:|
| 2026-04-22 10:55:00 | 530,664,894 | 103,143,773 | 427,521,121 | 6,016,099 | 4 |
| 2026-04-22 10:50:00 | 530,396,838 | 103,145,240 | 427,251,598 | 5,748,043 | 4 |
| 2026-04-22 10:45:00 | 532,236,973 | 107,672,256 | 424,564,717 | 7,588,178 | 4 |
| 2026-04-22 10:40:00 | 527,471,033 | 146,048,048 | 381,422,985 | 2,822,238 | 6 |
| 2026-04-22 10:35:00 | 525,614,627 | 146,058,324 | 379,556,303 | 965,832 | 5 |

### Error Incidents 최신 상태

- `error_incidents`는 144 rows입니다.
- 최신 20건은 모두 `component=llm_factory`, `operation=generate`, `severity=ERROR`, `status=OPEN`입니다.
- 최신 오류 시각은 `2026-04-22 10:51:37`입니다.

### Trading Rules

- 활성 rule:
  - `rr_floor=1.5`, active, expires `2026-04-23`
  - `require_stop_loss_logging=1.0`, active, expires `2027-04-02`
  - `revalidate_rr_ratio=1.0`, active, expires `2027-04-02`
- 비활성 rule:
  - 이전 `stop_loss_pct`, `min_confidence` override 다수

## Phase 2: 주문 생명주기와 브로커 Transport

### 주문 실행 경로 맵

| 경로 | 코드 위치 | 상태 변경 | 관찰 |
|---|---|---|---|
| AI 신규 시그널 | `agent/decision_maker.py:49-60` | `AUTONOMY_MODE` 분기 | `AUTONOMOUS`면 즉시 주문, `SEMI_AUTO`면 추천 생성 |
| AI 자동 주문 | `agent/decision_maker.py:62-213` | broker `place_order` 후 `PENDING_CONFIRM` 생성 | 주문번호가 있으면 즉시 `trade_results`에 pending 기록 |
| pending 생성 | `agent/decision_maker.py:391-438` | `PENDING_CONFIRM` | order_id 중복이면 기존 id 반환 |
| 체결 확인 | `agent/decision_maker.py:440-528` | `PENDING_CONFIRM -> CONFIRMED` 또는 실패 처리 | 3초 대기 후 broker `get_order_status` 조회 |
| 미체결 취소 | `agent/decision_maker.py:529-540` | broker cancel 호출 | 체결내역 미발견/체결수량 0이면 취소 시도 |
| pending 확정 | `agent/decision_maker.py:542-617` | `PENDING_CONFIRM -> CONFIRMED` | SELL이면 open BUY lot에 청산 반영 |
| pending 실패 | `agent/decision_maker.py:618-632` | `PENDING_CONFIRM -> CONFIRM_FAILED` | 예외 발생 시 reason 기록 |
| 수동 매도 | `services/manual_trade_service.py:101-166` | broker sell 후 `confirm_and_record` | `TRADING_ENABLED`와 정규장만 확인, `AUTONOMY_MODE`와 무관 |
| 보유 점검 매도 | `scheduler/scheduler.py:813-852` | broker sell 후 `confirm_and_record` | 손절/익절/시간 조건. `TRADING_ENABLED`만 확인 |
| 강제 청산 | `scheduler/scheduler.py:1011-1044` | broker sell 후 `confirm_and_record` | pending sell 차감 로직은 테스트 존재 |
| 장중 보유 재평가 | `scheduler/scheduler.py:1413-1427` | broker sell 후 `confirm_and_record` | `TRADING_ENABLED`만 확인 |
| 갭 체크 매도 | `scheduler/scheduler.py:1674-1696` | broker sell 후 `confirm_and_record` | `TRADING_ENABLED`만 확인 |
| 브로커 계약 | `trading/adapters/base.py:50-103` | 공통 adapter contract | balance, holdings, pending, order, cancel, status |
| 키움 상태 추론 | `trading/adapters/kiwoom_adapter.py:174-222` | pending/holding 기반 `OrderStatusInfo` 추론 | pending book에서 사라진 주문은 보유 수량 변화로 체결 추론 |
| MCP 주문 래퍼 | `trading/mcp_client.py:696-740` | KIS 주문 응답 정규화 | order_id/filled_quantity/filled_price 정규화 |
| legacy order executor | `trading/order_executor.py:12-40` | `TRADING_ENABLED` 확인 후 MCP 주문 | 현재 키움 직접 adapter보다 legacy MCP 경로 성격 |

### 주문 상태 전이표

| 상태 | 생성/변경 위치 | 의미 |
|---|---|---|
| `PENDING_CONFIRM` | `DecisionMaker._create_pending_record` | 주문 접수는 됐지만 체결 확인 미완료 |
| `CONFIRMED` | `DecisionMaker._confirm_pending_record`, `_record_trade_result`, `portfolio_sync_job._recover_pending_confirms` | 체결 또는 보유/미체결 대사로 확인됨 |
| `CONFIRM_FAILED` | `DecisionMaker._mark_pending_failed`, `portfolio_sync_job._recover_pending_confirms` | 체결 확인 실패 또는 매칭 실패 |
| open BUY | `TradeResultRepository.get_all_open_buys` | `side=BUY`, `status=CONFIRMED`, `exit_at IS NULL` |
| closed BUY | `_apply_sell_fill_to_open_buys` 호출 경로 | SELL 체결이 기존 BUY lot의 `exit_at`, `pnl`, `return_pct`를 채움 |
| independent SELL | `_record_trade_result` SELL branch | open BUY가 없으면 독립 SELL 기록 생성 |

### 중복 주문 차단 경로

- 신규 자동 BUY는 `DecisionMaker._find_existing_pending_buy`에서 브로커 미체결 매수 주문을 조회해 같은 종목 pending buy가 있으면 차단합니다.
- 수동 즉시 매도는 `ManualTradeService.sell_position`에서 같은 종목 pending sell이 있으면 차단합니다.
- 스케줄러 매도 계열은 `TradingAgent._acquire_sell`로 프로세스 내 같은 종목 중복 매도를 막습니다.
- 강제 청산은 pending sell 수량을 차감하는 테스트가 있습니다. 관련 테스트: `tests/scheduler/test_scheduler_runtime_paths.py::test_force_liquidation_subtracts_pending_sell_quantity`.
- 확인한 한계:
  - 신규 BUY 중복 차단은 브로커 pending book에 의존합니다. `trade_results.PENDING_CONFIRM`만 있고 브로커 pending book에 없거나 이미 partial fill된 경우, DB pending 자체가 신규 BUY 차단 기준으로 쓰이지 않습니다.
  - `SEMI_AUTO`는 `DecisionMaker.execute`의 신규 시그널 주문만 추천으로 돌립니다. 보유 점검/강제청산/갭 체크/수동 매도는 `TRADING_ENABLED=true`이면 실제 주문 경로가 열려 있습니다.

### 브로커 read-only 스냅샷

- 확인 시각: `2026-04-22 11:00 KST` 전후
- Admin system status:
  - `broker_provider=KIWOOM`
  - `trading_enabled=true`
  - `autonomy_mode=SEMI_AUTO`
  - `scheduler_running=true`
  - `agent_running=true`
  - `mcp_connected=false`
  - `market_open=true`
  - `market_session=KRX_NXT`
  - `market_session_auto_trading=true`
- Admin settings:
  - `AUTONOMY_MODE=SEMI_AUTO`
  - `NEWS_POLL_ENABLED=false`
  - `NEWS_GATE_ENABLED=false`
  - `NEWS_LLM_ENABLED=false`
  - `LLM_TIER1_CONCURRENCY=1`
  - `LLM_TIER2_CONCURRENCY=1`
- 브로커 미체결 주문:

| order_id | symbol | name | side | order_qty | filled_qty | remaining_qty | order_price | order_time |
|---|---|---|---|---:|---:|---:|---:|---|
| `0091483` | `010820` | 퍼스텍 | 매수 | 1,479 | 0 | 1,479 | 16,580 | 10:33:29 |
| `0088558` | `131400` | 이브이첨단소재 | 매수 | 3,500 | 2,565 | 935 | 2,080 | 10:28:30 |
| `0086997` | `092220` | KEC | 매수 | 7,552 | 0 | 7,552 | 1,660 | 10:25:53 |
| `0046549` | `018470` | 조일알미늄 | 매수 | 13,000 | 0 | 13,000 | 1,934 | 09:32:34 |

- 브로커 보유 종목:

| symbol | name | quantity | avg_buy_price | current_price | pnl | pnl_rate |
|---|---|---:|---:|---:|---:|---:|
| `001250` | GS글로벌 | 14,607 | 3,878 | 3,905 | -111,075 | -0.20% |
| `006110` | 삼아알미늄 | 40 | 74,400 | 75,800 | 28,916 | 0.97% |
| `008350` | 남선알미늄 | 23,969 | 2,644 | 2,660 | -191,094 | -0.30% |
| `010820` | 퍼스텍 | 170 | 17,270 | 16,760 | -112,637 | -3.84% |
| `101670` | 하이드로리튬 | 4,219 | 2,220 | 2,225 | -63,309 | -0.68% |
| `131400` | 이브이첨단소재 | 87,569 | 2,113 | 2,160 | 2,460,054 | 1.33% |

### DB와 브로커 pending 대사

- Phase 1 이후 `trade_results` 상태는 변했습니다.
  - Phase 1: `CONFIRMED BUY=48`, `CONFIRMED SELL=5`, `PENDING_CONFIRM BUY=20`
  - Phase 2 확인 시점: `CONFIRMED BUY=48`, `CONFIRMED SELL=6`, `PENDING_CONFIRM BUY=21`
- 브로커 미체결은 4건이지만 DB `PENDING_CONFIRM BUY`는 21건입니다.
- DB pending 종목별 집계:

| symbol | name | pending_count | pending_qty | oldest | newest |
|---|---|---:|---:|---|---|
| `092220` | KEC | 8 | 64,713 | 09:24:38 | 10:25:53 |
| `001250` | GS글로벌 | 5 | 17,807 | 10:02:29 | 10:58:06 |
| `131400` | 이브이첨단소재 | 4 | 33,000 | 09:07:55 | 10:28:30 |
| `008350` | 남선알미늄 | 2 | 9,048 | 09:49:09 | 10:38:45 |
| `010820` | 퍼스텍 | 1 | 1,479 | 10:33:29 | 10:33:29 |
| `018470` | 조일알미늄 | 1 | 13,000 | 09:32:34 | 09:32:34 |

- 대사 해석:
  - `010820`, `131400`, `092220`, `018470`은 DB pending과 브로커 pending이 직접 연결됩니다.
  - `001250`, `008350`은 DB pending이 있으나 브로커 pending에는 없습니다. 일부는 보유 수량에 반영됐거나 이미 취소/체결/복구 누락일 가능성이 있습니다.
  - `131400` order `0088558`은 브로커 기준 partial fill(`filled_qty=2565`, `remaining_qty=935`)인데 DB pending 수량은 주문 수량 3,500 그대로입니다. partial fill을 DB open lot에 즉시 반영하는지 추가 검증이 필요합니다.

### MCP/SSE 실패 복구 관찰

- `trading/mcp_client.py:500-566`은 미확인 주문 복구 시 KIS 주문내역을 종목코드와 주문유형으로 매칭하고, 체결수량이 있으면 `decision_maker.confirm_and_record`를 호출합니다.
- 현재 system status는 `mcp_connected=false`입니다. 키움 직접 adapter가 주 브로커라서 주문 자체가 MCP 필수는 아니지만, legacy MCP 복구 경로는 현재 연결 상태의 영향을 받습니다.
- 최신 `error_incidents`는 `llm_factory/generate`의 Codex timeout이 계속 쌓이고 있습니다. 예: `2026-04-22 11:01:46`, `CODEX 최근 호출 실패로 비활성화 (218s 남음): Codex CLI timeout (120s)`.

### 구현 후보 테스트

- `tests/agent/test_decision_maker.py`
  - 브로커 pending book에는 없지만 DB `PENDING_CONFIRM`이 있는 같은 종목 BUY를 차단하거나 reconcile하도록 실패 테스트 추가 후보.
  - partial fill pending order가 들어왔을 때 filled_qty만 open exposure에 반영되는지 테스트 추가 후보.
- `tests/scheduler/test_portfolio_sync_job.py`
  - 브로커 pending 4건, DB pending 21건 같은 불일치 fixture에서 stale pending report가 생성되는지 테스트 후보.
  - partial fill이 남은 pending으로 유지되면서 체결분이 DB open lot/PnL source에 반영되는지 테스트 후보.
- `tests/services/test_manual_trade_service.py`
  - manual sell은 `AUTONOMY_MODE=SEMI_AUTO`와 무관하게 `TRADING_ENABLED=true`면 동작한다는 명시 테스트 후보.
- `tests/trading/test_kiwoom_adapter.py`
  - pending book에서 사라진 주문과 보유 수량 변화로 체결 추론하는 현재 테스트를 partial fill/repeated pending case로 확장 후보.

## Phase 3: 리스크 제어와 자본 배분

### 외부 기준 요약

감사 기준은 다음 1차/공식 자료의 공통 원칙을 코드 수준으로 축약했습니다.

| 출처 | 감사에 반영한 기준 |
|---|---|
| SEC Rule 15c3-5 Market Access Risk Management Controls, https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access | 주문 전 credit/capital threshold, 오류 주문, 중복 주문, 가격/수량 parameter 차단 |
| e-CFR 17 CFR § 240.15c3-5, https://www.law.cornell.edu/cfr/text/17/240.15c3-5 | pre-trade financial/regulatory controls, direct control, regular effectiveness review |
| FINRA Algorithmic Trading, https://www.finra.org/rules-guidance/key-topics/algorithmic-trading | 알고리즘 거래의 일반 risk assessment, 개발/테스트/감독 통제 |
| KRX 주문유형 설명, https://global.krx.co.kr/contents/GLB/06/0602/0602020202/GLB0602020202T5.jsp | 시장가 주문은 빠르지만 불리한 가격/급격한 체결가 변동 위험이 있어 지정가/가격 guard 필요 |

### 리스크 Gate 순서

| 순서 | 위치 | 적용 대상 | 관찰 |
|---|---|---|---|
| 1 | `TradingAgent._run_trading_cycle` | cycle 전체 | 포트폴리오 스냅샷, 현금 부족 시 신규 매수 차단 |
| 2 | `AIRiskTuner.compute_limits` | cycle 전체 | LLM이 일일 거래수/주문한도/포지션/현금비중을 제안 |
| 3 | `TradingAgent._analyze_and_trade` 초반 | 후보 종목 | 연속 손실 5회 hard rule. BUY만 차단, 보유/SELL 분석은 허용 |
| 4 | `TradingAgent._analyze_and_trade` | 후보 종목 | 현재가/일봉/분봉 조회와 현금으로 1주 또는 최소수량 매수 가능 여부 확인 |
| 5 | Tier1 분석 후 trading rules | BUY 후보 | `min_confidence`, `revalidate_rr_ratio`, `require_stop_loss_logging` 적용 |
| 6 | Tier2 최종 검토 | BUY/SELL 후보 | LLM 최종 승인 필요 |
| 7 | cost gate/news gate | BUY 후보 | 기대 edge 대비 비용, 뉴스 부정압 차단 |
| 8 | SELL 보유 확인 | SELL 후보 | 보유 종목/수량 없으면 SELL 차단, 수량은 보유 스냅샷으로 보정 |
| 9 | `RiskManager.check` | 주문 직전 | BUY는 trading guard, 일일 거래수, 가격/수량, RR, 변동성 사이징, 단일 주문 한도, 현금, 현금비중, 포지션 비중 확인. SELL은 기본 허용 |
| 10 | BUY 주문 직전 buying power 재조회 | BUY | 병렬 주문으로 변한 가용금액을 반영하려는 최종 조회 |
| 11 | `DecisionMaker.execute` | 주문/추천 분기 | `AUTONOMY_MODE=SEMI_AUTO`면 추천 생성, `AUTONOMOUS`면 broker order |

### Runtime Risk Settings

API 기준 현재 설정:

| key | value |
|---|---|
| `TRADING_ENABLED` | `true` |
| `AUTONOMY_MODE` | `SEMI_AUTO` |
| `RISK_APPETITE` | `MODERATE` |
| `BUY_ORDER_EXECUTION_MODE` | `LIMIT_GUARD` |
| `BUY_SLIPPAGE_GUARD_BPS` | `20` |
| `AUTO_RISK_KILL_SWITCH_ENABLED` | `true` |
| `MAX_DAILY_DRAWDOWN_PCT` | `2.5` |
| `MAX_CONSECUTIVE_LOSSES` | `4` |
| `MIN_STRATEGY_EXPECTANCY` | `0.0` |
| `EXPECTANCY_SAMPLE_SIZE` | `12` |
| `VOLATILITY_POSITION_SIZING_ENABLED` | `true` |
| `RISK_PER_TRADE_PCT` | `0.5` |
| `RISK_MULTIPLIER_SHORT` | `0.7` |
| `RISK_MULTIPLIER_MID` | `1.0` |
| `RISK_MULTIPLIER_LONG` | `1.2` |
| `COST_GATE_ENABLED` | `true` |

`.env` 기준과 runtime 기준의 차이:

- `.env`는 `TRADING_ENABLED=false`입니다.
- runtime DB/API는 `TRADING_ENABLED=true`입니다.
- `runtime_settings`에는 `TRADING_ENABLED=true`만 저장되어 있고, 나머지 risk key는 대부분 config default/API settings 값으로 보입니다.
- 운영자는 `.env`만 보고는 현재 실주문 master switch 상태를 판단할 수 없습니다.

### AIRiskTuner 한도 처리

- `strategy/ai_risk_tuner.py:112-131`의 `_clamp_limits`는 “최소 안전값만 적용, 상한선 없음”으로 구현되어 있습니다.
- `max_daily_trades`: 0 이상이면 허용, 0은 무제한입니다.
- `max_single_order_krw`: 0 이상이면 허용, 0은 무제한입니다.
- `max_position_pct`: 최소 5%만 강제하고 상한선은 없습니다.
- `min_cash_ratio`: 0이면 제한 없음입니다.
- LLM 실패 시 default는 `MAX_SINGLE_ORDER_KRW` 설정을 따르는데, 기본값/`.env` 모두 0이면 시스템 hard cap이 없습니다.

### TradingGuard와 Kill Switch

- `TradingGuard.evaluate_buy_guard`는 BUY 전용입니다.
- 일중 손실 한도는 `TradeResult.side=BUY`, `status=CONFIRMED`, `exit_at IS NOT NULL`인 닫힌 거래의 `pnl` 합계를 `portfolio_budget`으로 나눠 계산합니다.
- 연속 손실과 전략 기대값도 `TradeResult` 기반입니다.
- Phase 1/2에서 확인한 것처럼 confirmed trade PnL이 0에 가깝고 DB pending/open lot 정합성이 낮으면 kill switch의 입력값 신뢰도가 낮습니다.
- 평가손익(`account_equity_snapshots.total_unrealized_pnl`)과 총자산 변화는 kill switch에 직접 반영되지 않습니다.

### Trading Rules 우선순위

- pre-market에서 `trading_rule_engine.load_active_rules()`를 호출하고, strategy/risk manager/trading agent에 적용합니다.
- 활성 rules:

| rule_type | scope | param | value | source | priority | active | expires_at | applied_count |
|---|---|---|---:|---|---|---:|---|---:|
| `PARAM_OVERRIDE` | `ALL` | `rr_floor` | 1.5 | `DAILY_REVIEW` | `MEDIUM` | 1 | 2026-04-23 15:40:40 | 1 |
| `VALIDATION_TOGGLE` | `ALL` | `require_stop_loss_logging` | 1.0 | `BOOTSTRAP` | `HIGH` | 1 | 2027-04-02 08:50:00 | 3 |
| `VALIDATION_TOGGLE` | `ALL` | `revalidate_rr_ratio` | 1.0 | `BOOTSTRAP` | `HIGH` | 1 | 2027-04-02 08:50:00 | 3 |

- trading rules는 Tier2 전에 일부 hard gate로 적용됩니다.
- 한계: pre-market 로드/적용 구조라 장중 새 rule 생성 또는 runtime 변경과의 동기화는 추가 확인이 필요합니다.

### 노출 계산과 실제 계좌 비교

- 브로커 보유 종목은 6개, stock_value 약 430,159,408원입니다.
- DB `CONFIRMED BUY AND exit_at IS NULL`은 48건, 수량 합계 411,263주, entry notional 합계 약 981,916,149원입니다.
- DB open BUY 명목금액이 최신 계좌 주식평가액의 약 2.28배입니다.
- 이 차이는 Phase 2의 pending/confirmed 대사 불일치와 연결됩니다.
- RiskManager의 주문 전 `portfolio_budget`, `portfolio_cash`, `holding_count`, `today_trade_count`는 portfolio snapshot에서 오며, DB open BUY notional과 DB pending notional은 직접 차감하지 않습니다.
- BUY 직전 buying power 재조회가 있지만, 병렬 후보들이 같은 cycle snapshot으로 동시에 risk check를 통과할 수 있습니다. 서로 다른 종목 간 현금 예약 ledger는 확인되지 않았습니다.

### 가격/수량 오류 주문 방지

- `RiskManager.check`는 가격과 수량이 0 이하이면 차단합니다.
- `MAX_SINGLE_ORDER_KRW`가 0이면 단일 주문 금액 hard cap은 없습니다.
- `BUY_ORDER_EXECUTION_MODE=LIMIT_GUARD`이면 BUY 시장가 대신 현재가 + `BUY_SLIPPAGE_GUARD_BPS` 지정가를 만들 수 있습니다.
- `BUY_ORDER_EXECUTION_MODE=MARKET`이면 BUY도 시장가가 가능하며, KRX 자료상 시장가는 빠르지만 불리한 가격 변동 위험이 있습니다.
- SELL 안전매도/청산은 시장가 매도가 기본입니다. 이는 청산 목적상 타당할 수 있지만, 중복 매도와 수량 보정이 더 중요합니다.

### Phase 3 Verification

```bash
.venv313/bin/python -m pytest tests/strategy/test_risk_manager_enhancements.py tests/strategy/test_trading_guard.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_execution_policy.py
```

결과:

- 10 tests passed.
- 확인 범위: 변동성 사이징, short horizon multiplier, trading guard 차단, daily drawdown/negative expectancy, cost gate, BUY execution policy.
- 미확인 범위: DB pending/open lot과 브로커 pending/holdings 대사 기반 노출 차감, 병렬 BUY 현금 예약, runtime/.env 불일치 경고.

## Phase 4: 성과 측정과 PnL 신뢰도

### 성과 Source 구분

| 지표 | 코드 위치 | Source | 관찰 |
|---|---|---|---|
| closed trade metrics | `services/performance_reporting_service.py:57-95`, `170-183` | `TradeResult` 중 `side=BUY`, `status=CONFIRMED`, `exit_at IS NOT NULL` | 기대값, PF, 승률, max drawdown은 닫힌 BUY만 사용 |
| live account snapshot | `services/performance_reporting_service.py:124-154` | broker adapter balance/holdings/pending | current account는 live 값으로 별도 포함 |
| account equity snapshot | `services/account_equity_service.py:46-67`, `98-155` | broker adapter balance/holdings/pending -> `account_equity_snapshots` | 총자산, 현금, 주식평가, 평가손익, pending count 기록 |
| session metrics | `services/account_equity_service.py:182-239` | day baseline + latest snapshot + completed trades | `asset_delta`, `realized_today_pnl`, `daily_unrealized_delta` 계산 |
| strategy feedback stats | `analysis/feedback/performance_tracker.py:35-40`, `164-190` | closed BUY only | AI feedback/expectancy/연속손실은 닫힌 BUY만 기준 |
| daily report | `services/daily_report_service.py:124-163` | opened/completed/sell count + broker unrealized | 실현손익과 미실현손익을 모두 prompt/report에 넣음 |

### 운영 DB PnL 집계

- `trade_results` closed BUY: `0`
- `trade_results` open confirmed BUY: `48`
- `trade_results` pending BUY: `21`
- confirmed BUY 전체 `pnl_sum=0.0`, `return_pct_sum=0.0`, `is_win_count=0`
- 의미:
  - closed-trade 기반 기대값, PF, 승률, max drawdown은 현재 운영 DB에서 학습/평가에 쓸 표본이 없습니다.
  - open/pending 상태가 많은데 닫힌 거래가 0건이라 “돈을 벌고 있는지”는 trade outcome 기반으로 판단할 수 없습니다.
  - 현재 판단 가능한 것은 broker/account equity 기준 총자산 변화와 평가손익뿐입니다.

### Account Equity Snapshot

최신 계좌 API 응답:

| key | value |
|---|---:|
| `total_asset` | 529,528,690 |
| `cash` | 183,654,660 |
| `stock_value` | 345,874,030 |
| `total_pnl` | -2,047,365 |
| `total_pnl_rate` | -0.59% |
| `session_metrics.asset_delta` | +3,528,292 |
| `session_metrics.asset_delta_rate` | +0.67% |
| `session_metrics.realized_today_pnl` | 0 |
| `session_metrics.daily_unrealized_delta` | +3,528,292 |
| `session_metrics.intraday_high_asset` | 533,288,675 |
| `session_metrics.intraday_low_asset` | 517,447,795 |

최신 DB snapshots:

| captured_at | total_asset | cash | stock_value | total_unrealized_pnl | pnl_rate | holding_count | pending_count |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-04-22 11:10 | 528,195,291 | 183,662,041 | 344,533,250 | -3,380,764 | -0.98% | 6 | 3 |
| 2026-04-22 11:05 | 529,261,473 | 208,395,433 | 320,866,040 | -2,314,582 | -0.72% | 6 | 4 |
| 2026-04-22 11:00 | 533,288,675 | 103,129,267 | 430,159,408 | 8,639,880 | 2.07% | 7 | 5 |
| 2026-04-22 10:55 | 530,664,894 | 103,143,773 | 427,521,121 | 6,016,099 | 1.44% | 7 | 4 |
| 2026-04-22 10:50 | 530,396,838 | 103,145,240 | 427,251,598 | 5,748,043 | 1.38% | 7 | 4 |

기준선:

- 2026-04-22 baseline: total_asset 526,000,398, cash 525,983,658, stock_value 16,740, unrealized -113, holding_count 2, pending_count 0.
- 이후 11:00에는 stock_value가 430,159,408까지 증가했습니다.
- 총자산 기준 baseline은 유용하지만, baseline stock/cash/holding 상태는 장 시작 직후 동기화 전 상태일 가능성이 있어 포지션/노출 기준으로 쓰기 어렵습니다.

### Daily Reports

최신 저장 리포트:

| report_date | cycles | analyses | recommendations | total_orders | buy_count | sell_count | win/loss | total_pnl | unrealized_pnl | open_positions |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|
| 2026-04-21 | 15 | 280 | 180 | 2 | 0 | 0 | 0/0 | 0 | 0 | 8 |
| 2026-04-10 | 2 | 166 | 20 | 13 | 13 | 0 | 0/0 | 0 | 0 | 8 |

관찰:

- daily report는 broker unrealized를 포함하도록 구현되어 있지만 저장된 과거 리포트의 `unrealized_pnl`은 0입니다.
- 2026-04-22 리포트는 아직 저장되지 않았습니다.
- `total_orders=2`인데 `buy_count=0`, `sell_count=0`인 2026-04-21 row는 activity count 기반 total과 TradeResult 기반 count가 섞인 결과일 가능성이 있습니다.

### Rollout/전략 평가 영향

- `PerformanceReportingService._calc_metrics`는 trade_count가 0이면 expectancy, PF, drawdown을 모두 0으로 반환합니다.
- PF는 loss가 없으면 999로 cap되지만, 현재는 closed trade가 0이라 PF 0입니다.
- rollout 판단은 min sample size를 보지만, closed trade가 0이면 promote는 되지 않습니다.
- 문제는 “나쁘다”보다 “평가 불가”입니다. 이 상태에서 전략/뉴스/LLM 성능 결론을 내리면 안 됩니다.

### Phase 4 Verification

```bash
.venv313/bin/python -m pytest tests/services/test_performance_reporting_service.py tests/services/test_account_equity_service.py tests/strategy/test_trading_guard.py
```

결과:

- 17 tests passed.
- 확인 범위: performance metric 계산, rollout 판단, account baseline/session metrics, trading guard.
- 미확인 범위: closed trade 0건일 때 UI/API가 “평가 불가”로 표시되는지, activity count와 TradeResult count 불일치 경고, stale open lot/pending이 성과 리포트에 경고로 노출되는지.

## Phase 5: 전략 가치와 매매 기대값

### 외부 기준

| 출처 | 감사에 반영한 기준 |
|---|---|
| A. Craig MacKinlay, Event Studies in Economics and Finance, https://www.jstor.org/stable/2729691 | 매수/보류/스킵 같은 의사결정 이벤트 이후 일정 시간 수익률과 초과수익률을 측정해야 함 |
| Bailey et al., The Probability of Backtest Overfitting, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253 | 여러 전략/파라미터를 비교할수록 과최적화 가능성이 커지므로 out-of-sample과 benchmark가 필요함 |
| Bailey and Lopez de Prado, The Deflated Sharpe Ratio, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551 | 선택 편향과 non-normal return을 고려하지 않은 성과 지표는 과대평가될 수 있음 |

### 현재 의사결정 Funnel

운영 로그와 코드 기준 현재 funnel은 다음처럼 볼 수 있습니다.

| 단계 | 코드/데이터 위치 | 현재 기록 | 관찰 |
|---|---|---|---|
| 시장 scan | `agent/market_scanner.py` | `agent_activity_logs.activity_type=SCAN` | 거래량/급등/급락/보유/계좌/성과 요약을 LLM에 넣고 `selected`를 받음 |
| screen | `agent/stock_screener.py` | `SCREENING` 로그 없음 | `StockScreener`는 존재하지만 현재 주요 cycle에서는 별도 단계로 쓰이지 않는 것으로 보임 |
| chart/technical | `analysis/chart_analyzer.py`, `analysis/technical/` | `TIER1_ANALYSIS` detail 일부 | RSI, MACD, MA, BB, 패턴, 추세 분석은 있으나 구조화된 forward label은 없음 |
| Tier1 LLM | `TradingAgent._tier1_analysis` | `TIER1_ANALYSIS`, `LLM_CALL` | BUY/HOLD/SELL과 confidence를 생성 |
| Tier2 LLM | `TradingAgent._tier2_review` | `TIER2_REVIEW`, `LLM_CALL` | 최종 승인/거절, 수량, 근거를 생성 |
| strategy eval | `strategy/stable_short.py`, `strategy/aggressive_short.py` | `STRATEGY_EVAL` | 전략은 독립 alpha 모델이라기보다 LLM 판단을 손절/익절/긴급도 파라미터로 변환 |
| risk/cost/news gate | `RiskManager`, `_evaluate_cost_gate`, `_evaluate_news_gate` | `RISK_CHECK`, `REPORT` shadow 일부 | 비용 gate는 켜져 있고 뉴스 gate는 현재 꺼짐 |
| order/recommendation | `agent/decision_maker.py` | `DECISION`, `ORDER`, `TRADE_RESULT` | `SEMI_AUTO`에서는 추천 생성. 실주문 source는 Phase 2 findings와 같이 불명확 |
| fill/PnL | `trade_results`, `account_equity_snapshots` | `TRADE_RESULT`, equity snapshot | closed BUY 0건이라 trade outcome 기반 기대값은 계산 불가 |

### 운영 로그 Count

전체 `agent_activity_logs` 집계:

| activity_type | phase | count |
|---|---|---:|
| `SCAN` | `START/COMPLETE/ERROR` | 23 / 12 / 11 |
| `TIER1_ANALYSIS` | `START/COMPLETE` | 372 / 372 |
| `TIER2_REVIEW` | `START/COMPLETE` | 200 / 201 |
| `STRATEGY_EVAL` | `COMPLETE` | 197 |
| `RISK_CHECK` | `COMPLETE/SKIP` | 197 / 12 |
| `DECISION` | `START/COMPLETE/SKIP/ERROR` | 165 / 67 / 102 / 3 |
| `ORDER` | `COMPLETE` | 10 |
| `TRADE_RESULT` | `COMPLETE` | 34 |
| `SCREENING` | 전체 | 0 |

2026-04-22 당일 집계:

| activity_type | count |
|---|---:|
| `SCAN` | 14 |
| `TIER1_ANALYSIS` | 298 |
| `TIER2_REVIEW` | 146 |
| `STRATEGY_EVAL` | 73 |
| `RISK_CHECK` | 73 |
| `DECISION` | 137 |
| `ORDER` | 7 |
| `TRADE_RESULT` | 29 |
| `LLM_CALL` | 294 |

해석:

- funnel 자체는 로그로 추적 가능하지만, 각 후보가 어떤 단계에서 탈락했고 이후 수익률이 어땠는지 계산할 canonical table은 없습니다.
- `analysis_results`, `recommendations`, `strategy_signals`, `market_data_daily`, `market_snapshots`는 모두 0 rows입니다.
- 따라서 현재는 activity log JSON을 역파싱해야만 funnel 분석이 가능하고, 이는 감사/성과 모델의 source of truth로 쓰기 어렵습니다.

### 전략 코드의 실제 역할

- `StableShortStrategy`와 `AggressiveShortStrategy`는 파일 주석처럼 “판단은 AI 분석 결과를 신뢰하고, 전략은 실행 파라미터와 이유 텍스트를 제공”하는 구조입니다.
- `recommendation=BUY`이고 confidence가 기준 이상이면 BUY 신호를 만들고, target/stop/urgency를 붙입니다.
- 일부 RSI, MACD, cross, trend 정보는 reason text에 추가되지만 BUY의 독립 hard edge 조건은 아닙니다.
- 따라서 현재 성과 attribution은 “전략 alpha”라기보다 `scanner + chart features + Tier1 LLM + Tier2 LLM + risk/cost gate + execution parameter` 조합으로 봐야 합니다.

### Forward Return 평가 기준

Phase 5 결론상 구현 후보는 다음 dataset을 먼저 쌓아야 합니다.

| 필드 | 이유 |
|---|---|
| `decision_event_id`, `cycle_id`, `symbol`, `timestamp` | 후보별 이벤트 추적 |
| `stage` | `SCAN_SELECTED`, `TIER1_BUY`, `TIER1_HOLD`, `TIER2_APPROVED`, `RISK_BLOCKED`, `RECOMMENDED`, `ORDER_SUBMITTED`, `FILLED` 등 funnel 단계 |
| `candidate_source` | volume/surge/drop/event/holding 등 scanner source |
| `price_at_decision` | forward return 기준가 |
| `decision_action`, `confidence`, `provider`, `strategy_type`, `horizon` | LLM/전략 attribution |
| `target_price`, `stop_loss_price`, `cost_bps`, `edge_bps` | 비용 대비 기대 edge 검증 |
| `ret_5m`, `ret_15m`, `ret_30m`, `ret_60m`, `ret_close` | 이벤트 이후 수익률 |
| `market_ret_same_window`, `sector_ret_same_window` | 초과수익률 또는 상대성과 |
| `actual_order_id`, `fill_price`, `fill_qty`, `realized_pnl`, `unrealized_pnl_at_close` | 실제 실행 결과와 signal 품질 분리 |

시장 데이터 source는 우선순위가 필요합니다.

1. 장중 broker quote snapshot을 `market_snapshots` 또는 신규 `decision_forward_returns`에 저장합니다.
2. 체결/추천이 없어도 모든 후보의 decision price와 future price를 남깁니다.
3. 일봉 `market_data_daily`는 close 기준 평가용으로 쓰고, 5~60분 평가는 분봉/quote snapshot 기반으로 분리합니다.

### Benchmark 정의

전략/LLM/리스크 단계별 가치는 아래 benchmark와 비교해야 합니다.

| Benchmark | 설명 |
|---|---|
| no-trade | 같은 시간 현금 보유 |
| random same candidates | 같은 scan 후보군에서 무작위 선택 |
| scanner only | volume/surge/drop 상위 후보를 그대로 선택 |
| technical only | `ChartAnalyzer.signal_summary` 방향/강도만 사용 |
| Tier1 only | Tier1 BUY/HOLD/SELL만 사용 |
| Tier2 only | Tier2 승인까지 사용 |
| risk/cost gated | Tier2 승인 후 risk/cost gate 통과만 사용 |
| actual recommendation/order | 현재 운영 정책이 실제 추천/주문한 결과 |

### 제거/유지 기준

- `StockScreener`: 별도 `SCREENING` 로그가 0이고 현재 scanner가 selection을 통합한다면 `제거` 또는 `기본 비활성화` 후보입니다. 다만 README/과거 계획 문서와 연결되어 있어 삭제 전 호출 경로와 UI 설명을 정리해야 합니다.
- `StableShortStrategy`, `AggressiveShortStrategy`: 제거 대상은 아닙니다. 다만 “전략 alpha”로 표현하면 안 되고, `LLM decision -> execution profile`로 이름/문서/리포트를 바꾸는 것이 정확합니다.
- `analysis_results`, `recommendations`, `strategy_signals`: 현재 비어 있지만 개념은 필요합니다. 제거보다 `decision_events/forward_returns` 계층으로 대체하거나 역할을 명확히 해야 합니다.
- 뉴스/LLM/기술분석 단계는 forward return dataset이 최소 표본을 채우기 전에는 돈을 더 벌게 하는 기능이라고 결론내리면 안 됩니다.

### Phase 5 Verification

```bash
.venv313/bin/python -m pytest tests/agent/test_market_scanner.py tests/agent/test_trading_agent_cost_gate.py tests/agent/test_trading_agent_execution_policy.py tests/strategy/test_trade_horizon.py
```

결과:

- 9 tests passed.
- 확인 범위: market scanner adapter 사용, cost gate, execution policy, trade horizon.
- 미확인 범위: 후보별 forward return 저장, benchmark 산출, 전략 stage별 attribution. 이들은 아직 구현되어 있지 않습니다.

## Phase 6: 백테스트와 실험 위생

### 외부 기준

| 출처 | 감사에 반영한 기준 |
|---|---|
| Backtrader Slippage, https://www.backtrader.com/docu/slippage/slippage/ | market/limit/stop 주문별 슬리피지 적용과 high/low cap, 다음 봉 open 체결 같은 현실 모델이 필요함 |
| Backtrader Commission Schemes, https://www.backtrader.com/docu/commission-schemes/commission-schemes/ | 주식/선물별 commission scheme, percentage/fixed commission을 명확히 분리해야 함 |
| vectorbt Portfolio enums/orders, https://vectorbt.dev/api/portfolio/enums/ | fees, fixed_fees, slippage, min/max size, partial fill, reject probability 같은 주문 파라미터를 모델링 가능 |
| QuantConnect LEAN Slippage Models, https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models | null/constant/volume share/market impact slippage처럼 모델 선택이 필요함 |
| QuantConnect LEAN Trading and Orders, https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/trading-and-orders | backtest fill/fee/slippage/margin은 플러그인 모델로 제어하고, live order는 비동기 상태 전이를 가진다는 기준 |

### 현재 Backtest Engine 가정

| 항목 | 코드 위치 | 현재 가정 | 감사 판단 |
|---|---|---|---|
| 데이터 단위 | `BacktestEngine.run` | 일봉 OHLCV | 장중 전략/실시간 이벤트 성능 검증에는 부족 |
| 시작 lookback | `for i in range(30, len(df))` | 30봉 이후부터 평가 | 최소 indicator lookback 목적은 타당 |
| 신호 생성 | `lookback_df = df.iloc[:i + 1]` | 현재 봉 close/high/low까지 포함해 지표 계산 | 현재 봉 종가를 보고 같은 봉 종가에 매수하는 look-ahead/동시체결 가정 |
| 진입 가격 | `_buy(... current_price)` | 신호 봉 close에 즉시 매수, 매수 슬리피지 가산 | 다음 봉 open/limit fill이 아니라 낙관적일 수 있음 |
| 청산 가격 | `_check_positions` | 손절은 low, 익절은 high, max hold는 close | 같은 봉 high/low 순서를 모르지만 stop-loss를 먼저 보는 보수적 순서 |
| 진입 당일 stop/TP | `run` 순서 | 포지션 체크 후 신규 매수 | 진입 당일 손절/익절은 평가하지 않음 |
| 수수료 | `commission_rate` | 매수/매도 각각 percentage | 세금/거래세/최소 수수료/브로커별 fee 없음 |
| 슬리피지 | `slippage_rate` | 매수는 +, 매도는 - 고정 percentage | 호가/거래량/시장가/지정가/상하한가 미반영 |
| 포지션 | `_has_position(symbol)` | 단일 종목 1포지션 | 포트폴리오 동시 후보, 현금 경쟁, 상관 노출 미검증 |
| 주문 실패 | 없음 | 계산 가능하면 전량 체결 | 미체결/부분체결/거부/reject probability 없음 |
| 상하한가/유동성 | 없음 | OHLC 안이면 체결 | KRX 가격제한폭, 호가단위, 거래정지, 저유동성 미반영 |
| 지표 기반 전략 | `_build_rule_based_analysis` | AI 대신 RSI/MACD/cross 규칙 | 실제 live LLM pipeline과 다른 전략을 테스트 |
| 성과 지표 | `calculate_metrics` | trade return과 equity curve 기반 | benchmark, out-of-sample, parameter trial log 없음 |

### Data Loader 관찰

- `BacktestDataLoader.load_from_broker`는 `count=(end_date - start_date).days`로 broker daily candles를 요청합니다.
- 반환 candle을 날짜순으로 정렬하지만, 요청 결과가 실제 `start_date/end_date` 안에 있는지 재필터링하지 않습니다.
- calendar day와 trading day 차이를 그대로 count로 사용합니다.
- DB source인 `market_data_daily`는 Phase 5 기준 0 rows라 현재 로컬 deterministic backtest dataset은 없습니다.
- 테스트는 broker adapter 호출과 실패 시 empty frame 반환만 검증합니다.

### 현재 테스트 범위

확인한 backtesting test:

- `tests/backtesting/test_data_loader.py::test_backtest_data_loader_uses_broker_adapter_candles`
- `tests/backtesting/test_data_loader.py::test_backtest_data_loader_returns_empty_frame_when_broker_raises`

미확인:

- 엔진이 다음 봉 체결을 하는지
- 수수료/슬리피지가 PnL에 정확히 반영되는지
- stop-loss/take-profit 순서와 gap 처리
- 같은 봉 high/low 양쪽 터치 시 정책
- `max_hold_days` off-by-one
- final liquidation이 equity curve에 반영되는지
- 데이터 기간 필터링
- benchmark/out-of-sample/parameter trial log

### 외부 라이브러리 검토

| 후보 | 장점 | 단점/주의 | 추천 |
|---|---|---|---|
| Backtrader | event-driven, commission/slippage/order model 문서가 성숙 | 프로젝트가 오래됐고 async/live pipeline과 직접 맞추려면 adapter 필요 | 현실 체결 모델의 reference 또는 독립 검증 엔진 후보 |
| vectorbt | 빠른 벡터화, fees/slippage/order records/partial reject 등 풍부 | event-driven order lifecycle과 live broker reconciliation은 별도 설계 필요 | benchmark/parameter sweep 보조 도구 후보 |
| QuantConnect LEAN | fill/fee/slippage/margin/reality modeling 개념이 강함 | 로컬 Python 서비스에 통합 비용이 큼 | 당장 도입보다 설계 기준/장기 후보 |

### Phase 6 결론

- 지금 백테스트 결과로 운영 전략의 수익성을 판단하면 안 됩니다.
- 이유는 live pipeline이 LLM 기반인데 backtest는 rule-based RSI/MACD 대체 모델이고, 체결도 현재 봉 close 동시체결에 가깝기 때문입니다.
- 즉시 외부 라이브러리로 교체하기보다, 현재 엔진에 아래 안전 기준을 먼저 추가하는 것이 비용 대비 낫습니다.

우선순위:

1. 엔진 테스트 추가: look-ahead 방지, 다음 봉 open/close 체결 정책, 수수료/슬리피지, stop/TP/gap.
2. 데이터 검증 추가: start/end 필터, trading day count, corporate action/adjusted price 여부 표시.
3. 실행 모델 분리: `SignalModel`, `FillModel`, `FeeModel`, `SlippageModel`, `PortfolioModel`.
4. benchmark report 추가: buy-and-hold, no-trade, random, scanner-only, technical-only.
5. 외부 라이브러리는 현재 엔진 결과와 독립 비교하는 verification layer로 먼저 사용.

### Phase 6 Verification

```bash
.venv313/bin/python -m pytest tests/backtesting/test_data_loader.py
```

결과:

- 2 tests passed.
- 확인 범위: broker candle 로딩, broker 실패 시 empty frame.
- 미확인 범위: backtest engine 체결/PnL/metrics. 테스트가 아직 없습니다.

## Phase 7: LLM, 뉴스, 비용/지연 가치

> 아직 시작하지 않았습니다.

## Phase 8: 스케줄러, 실시간 이벤트, 운영/보안/Admin

> 아직 시작하지 않았습니다.
