# Account Equity Session Metrics Design

**Date:** 2026-04-09

## Goal

Admin 우측 패널에서 `총자산 장시작 대비`, `보유 평가손익 당일/누적`을 명확히 보여주고, 그 기준선과 장중 변화를 DB에 남겨 다음날 판단과 사후 분석에 재사용할 수 있게 한다.

## In Scope

- 거래일 기준선(`장 시작 이후 첫 성공 계좌 스냅샷`)을 DB에 저장
- 장중 계좌 스냅샷 시계열을 DB에 저장
- `/api/v1/admin/account/balance` 응답에 세션 메트릭 추가
- Admin 우측 패널의 총자산/평가손익 표시 개선
- 장 마감 리포트가 저장된 시계열을 재사용할 수 있도록 구조 정리

## Out Of Scope

- 종목별 완전한 일중 시계열 정규화
- 입출금/출금 이벤트에 따른 기준선 자동 재정렬
- 별도 차트 페이지 신설
- 트레이딩 의사결정 로직 자체 변경

## Current State

- [trading_agent.py](/Users/jaewon/open-project/momo-trading/agent/trading_agent.py)는 `_daily_start_balance`를 메모리로만 보관한다.
- [scheduler.py](/Users/jaewon/open-project/momo-trading/scheduler/scheduler.py#L433)는 장 시작 전 이 메모리 값을 세팅한다.
- [admin.py](/Users/jaewon/open-project/momo-trading/api/routes/admin.py#L886)는 브로커 `get_balance()` 결과만 반환한다.
- [trade_state.js](/Users/jaewon/open-project/momo-trading/admin/static/js/trade_state.js)는 `balance.total_pnl`을 그대로 `보유 평가손익`으로 취급한다.
- [daily_report.py](/Users/jaewon/open-project/momo-trading/models/daily_report.py)는 장마감 요약만 저장하고, 장중 기준선/고저점/시계열은 저장하지 않는다.

## Design Principles

### 1. 관심사 분리

- 브로커 계좌 조회는 기존 adapter/account manager가 담당한다.
- 거래일 기준선 생성/복구/시계열 집계는 전용 계좌 세션 메트릭 서비스가 담당한다.
- Admin API는 현재 계좌와 세션 메트릭을 조합해서 응답만 만든다.
- 프론트는 계산 로직을 최소화하고 서버가 준 메트릭을 렌더링한다.

### 2. SOLID 적용

- Single Responsibility:
  - 새 모델은 `거래일 기준선`과 `계좌 스냅샷`만 표현한다.
  - 새 리포지토리는 조회/저장 쿼리만 담당한다.
  - 새 서비스는 baseline/snapshot/session metric 계산만 담당한다.
- Open/Closed:
  - 이후 종목별 기여도나 chart API를 추가하더라도 기존 baseline/snapshot 구조를 확장할 수 있다.
- Dependency Inversion:
  - API와 scheduler는 구체 쿼리 대신 서비스 인터페이스에 의존한다.

### 3. TDD 우선

다음 순서를 고정한다.

1. baseline/snapshot 서비스 단위 테스트
2. Admin balance API 응답 테스트
3. 프론트 quick stats 계산 테스트
4. 최소 구현
5. scheduler 연동 테스트

## Recommended Data Model

### `account_day_baselines`

거래일 기준선 1행.

- `id`
- `trading_date` unique index
- `baseline_at`
- `baseline_total_asset`
- `baseline_cash`
- `baseline_stock_value`
- `baseline_total_unrealized_pnl`
- `baseline_holding_count`
- `baseline_pending_order_count`
- `baseline_source`

### `account_equity_snapshots`

장중 계좌 스냅샷 시계열.

- `id`
- `trading_date` index
- `captured_at` index
- `session_phase`
- `total_asset`
- `cash`
- `stock_value`
- `total_unrealized_pnl`
- `total_unrealized_pnl_rate`
- `holding_count`
- `pending_order_count`
- `detail`

`detail`에는 JSON 문자열로 현재 보유 종목 요약, baseline 생성에 사용한 source 같은 부가정보를 넣는다. 초기 구현은 종목별 별도 테이블을 만들지 않는다.

## Session Metric Definitions

- `asset_delta = current_total_asset - baseline_total_asset`
- `asset_delta_rate = asset_delta / baseline_total_asset * 100`
- `realized_today_pnl = 오늘 청산 완료 pnl 합`
- `daily_unrealized_delta = asset_delta - realized_today_pnl`
- `total_unrealized_pnl = broker total_pnl`
- `intraday_high_asset = 오늘 저장된 snapshot.total_asset 최대값`
- `intraday_low_asset = 오늘 저장된 snapshot.total_asset 최소값`

UI 용어는 다음처럼 정리한다.

- `총자산`: 현재 총자산
- `장시작 대비`: 총자산 기준 일중 증감
- `당일 평가변동`: `daily_unrealized_delta`
- `누적 평가손익`: `total_unrealized_pnl`

`보유 평가손익(당일)`보다 `당일 평가변동`이 더 정확하다. 현재 데이터 구조로는 "오늘 열린 포지션만의 순수 미실현 손익"이 아니라 "오늘 총자산 변동에서 실현손익을 뺀 열린 포지션 기여분"이기 때문이다.

## Baseline Rules

- 기준선은 `09:00 이후 첫 성공 계좌 스냅샷`으로 생성한다.
- 장 시작 직후 조회 실패 시 baseline 생성은 보류한다.
- 같은 거래일에 baseline이 이미 있으면 재생성하지 않는다.
- 서버 재시작 시에도 baseline은 DB에서 복구된다.

## Snapshot Collection Rules

- 장중 5분 간격으로 snapshot 저장
- 장 시작 전 baseline 준비 시도 직후 snapshot 저장 가능
- holdings check 같은 기존 계좌 조회 지점에서 필요 시 추가 snapshot 저장 가능
- 장외에는 저장하지 않는다

초기 구현에서는 새 전용 interval job 하나로 책임을 분리한다.

## Backend Architecture

### New Service

예상 파일: `services/account_equity_service.py`

책임:

- 현재 계좌/보유/미체결을 읽어 persistence payload로 정규화
- baseline 생성/조회
- snapshot 저장
- today session metrics 계산
- API 응답용 enriched balance payload 생성

### New Repositories

- `repositories/account_day_baseline_repository.py`
- `repositories/account_equity_snapshot_repository.py`

### Scheduler Integration

- `pre_market` 단계에서 baseline 생성 시도
- 새 interval job에서 장중 snapshot 저장
- 기존 `trading_agent._daily_start_balance`는 새 baseline 값으로 동기화하거나 fallback 용도로만 유지

## API Shape

기존 `GET /api/v1/admin/account/balance` 응답을 확장한다.

```json
{
  "total_asset": 1000000,
  "cash": 250000,
  "stock_value": 750000,
  "total_pnl": 120000,
  "total_pnl_rate": 12.0,
  "session_metrics": {
    "trading_date": "2026-04-09",
    "baseline_at": "2026-04-09T09:01:15+09:00",
    "baseline_total_asset": 980000,
    "asset_delta": 20000,
    "asset_delta_rate": 2.04,
    "daily_unrealized_delta": -5000,
    "realized_today_pnl": 25000,
    "intraday_high_asset": 1015000,
    "intraday_low_asset": 972000,
    "is_stale": false
  }
}
```

baseline이 아직 없으면 `session_metrics`는 `null` 또는 필수 필드만 `0`으로 채운 payload 대신 `available: false`를 가진 구조를 반환한다.

## Frontend Shape

[trade_state.js](/Users/jaewon/open-project/momo-trading/admin/static/js/trade_state.js)

- `balance.session_metrics`를 읽어 quick stats 계산
- `당일 평가변동`과 `누적 평가손익`을 분리
- baseline 미존재 시 메타 문구를 안전하게 fallback

[app.js](/Users/jaewon/open-project/momo-trading/admin/static/js/app.js)

- 총자산 카드 메타를 `장시작 대비` 중심으로 교체
- 평가손익 카드를 `당일 평가변동 / 누적 평가손익` 2줄 구조로 변경

## Risks

- 장중 입출금이 있으면 `asset_delta` 해석이 왜곡될 수 있다.
- 브로커 응답 실패가 길어지면 baseline 생성이 늦어질 수 있다.
- snapshot을 너무 자주 저장하면 SQLite write 부하가 올라간다. 초기 구현은 5분 간격으로 제한한다.

## Final Decision

1. 거래일 baseline과 장중 snapshot을 별도 DB 테이블로 추가한다.
2. 총자산 일중 변동은 baseline 대비로 계산한다.
3. 평가손익은 `당일 평가변동`과 `누적 평가손익`으로 분리한다.
4. Admin API는 서버 계산 메트릭을 포함해 반환한다.
5. 구현은 TDD와 최소 책임 분리 원칙으로 진행한다.
