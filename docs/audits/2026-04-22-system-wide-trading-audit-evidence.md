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

> 아직 시작하지 않았습니다.

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
