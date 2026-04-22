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

> 아직 시작하지 않았습니다.

## Phase 4: 성과 측정과 PnL 신뢰도

> 아직 시작하지 않았습니다.

## Phase 5: 전략 가치와 매매 기대값

> 아직 시작하지 않았습니다.

## Phase 6: 백테스트와 실험 위생

> 아직 시작하지 않았습니다.

## Phase 7: LLM, 뉴스, 비용/지연 가치

> 아직 시작하지 않았습니다.

## Phase 8: 스케줄러, 실시간 이벤트, 운영/보안/Admin

> 아직 시작하지 않았습니다.
