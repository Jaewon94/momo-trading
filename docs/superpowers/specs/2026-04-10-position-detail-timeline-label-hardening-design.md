# Position Detail Timeline Label Hardening Design

**Date:** 2026-04-10

## Goal

종목 상세 타임라인에서 `closed BUY lot`가 다시 `매수 완료`처럼 보이는 회귀를 막고, 운영자가 부분 청산 이력과 최종 청산 이력을 즉시 구분할 수 있게 한다.

## Scope

- [api/routes/admin.py](/Users/jaewon/open-project/momo-trading/api/routes/admin.py)의 포지션 상세 타임라인 거래 라벨 정규화
- [tests/api/test_admin_position_detail_routes.py](/Users/jaewon/open-project/momo-trading/tests/api/test_admin_position_detail_routes.py)의 회귀 테스트 추가
- 프론트는 기존 [admin/static/js/position_detail_state.js](/Users/jaewon/open-project/momo-trading/admin/static/js/position_detail_state.js) 규칙을 유지하고, 백엔드가 내려준 `trade_state_*` 메타를 우선 사용한다

## Out Of Scope

- 거래 히스토리 카드 전체 문구 재설계
- 이벤트 레이더와 3단 카드 상태 체계 통합
- 새로운 상태 모델 도입

## Current State

- 백엔드 [api/routes/admin.py](/Users/jaewon/open-project/momo-trading/api/routes/admin.py)의 `_build_position_timeline()`는 `has_exit`, `fill_type`, `remaining_open_quantity`를 기준으로 `부분 매도 후 정리` / `최종 청산 lot`를 내려주도록 되어 있다.
- 프론트 [admin/static/js/position_detail_state.js](/Users/jaewon/open-project/momo-trading/admin/static/js/position_detail_state.js)는 `detail.trade_state_kind_label`, `detail.trade_state_badge`, `detail.trade_state_tone`, `detail.trade_state_icon`가 있으면 그 값을 우선 사용한다.
- 현재 프론트 단위 테스트는 이 문구를 기대하지만, API 라우트 테스트는 기본 BUY 체결 케이스만 확인하고 있어 백엔드 회귀가 생겨도 바로 잡히지 않을 수 있다.

## Problem

운영 혼동의 핵심은 실제 보유가 없는 `closed BUY lot`가 타임라인에서 진입 체결처럼 보일 수 있다는 점이다. 이 문제는 프론트 렌더링보다 API 응답 계약을 회귀 테스트로 고정하는 쪽이 더 직접적이다.

## Decision

- 포지션 상세 타임라인의 거래 상태 라벨 소스 오브 트루스는 백엔드 API로 둔다.
- `BUY + has_exit + PARTIAL_EXIT 또는 remaining_open_quantity > 0`는 항상:
  - `title = "부분 매도 후 정리"`
  - `trade_state_kind_label = "부분 매도 후 정리"`
  - `trade_state_badge = "PARTIAL_EXIT"`
  - `trade_state_detail_label = "잔량 n주 보유 중"` 또는 빈 문자열
- `BUY + has_exit`이지만 부분 청산이 아니면 항상:
  - `title = "최종 청산 lot"`
  - `trade_state_kind_label = "최종 청산 lot"`
  - `trade_state_badge = "FINAL_EXIT"`
  - `trade_state_detail_label = "전체 수량 청산 완료"`

## Testing Strategy

- API 회귀 테스트 2개를 추가한다.
  - `closed BUY lot`가 부분 청산 이력일 때 `부분 매도 후 정리`와 잔량 문구를 내리는지
  - `closed BUY lot`가 완전 청산 이력일 때 `최종 청산 lot`와 완료 문구를 내리는지
- 필요하면 프론트 포지션 상세 테스트는 기존 기대값 유지 여부만 재실행한다.

## Residual Risk

- 거래 히스토리 카드나 다른 화면이 별도 상태 추론을 쓰면 문구 드리프트는 여전히 남을 수 있다.
- 이번 단계는 `position detail timeline`만 하드닝하며, 나머지 거래 상태 체계 통합은 다음 작업이다.
