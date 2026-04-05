# 거래 코어 수익방어 고도화 (2026-04-05)

## 목적
- 방향 적중률보다 손익비/손실제어를 먼저 개선해 순손익 안정화.
- 장중 급변/품질저하 구간에서 자동으로 매수 리스크를 줄이기.

## 반영 내용
1. 매수 실행 정책 분리
- 설정: `BUY_ORDER_EXECUTION_MODE` (`LIMIT_GUARD` | `MARKET`)
- 설정: `BUY_SLIPPAGE_GUARD_BPS`
- `LIMIT_GUARD` 모드에서 매수 지정가가 없으면 `현재가 + 슬리피지 가드(bp)`로 제한가 자동 생성.

2. 자동 리스크 킬스위치
- 신규 모듈: `strategy/trading_guard.py`
- 차단 기준:
  - 일손실률 한도 (`MAX_DAILY_DRAWDOWN_PCT`)
  - 연속 손실 횟수 (`MAX_CONSECUTIVE_LOSSES`)
  - 전략 기대값 하한 (`MIN_STRATEGY_EXPECTANCY`, 샘플 `EXPECTANCY_SAMPLE_SIZE`)
- 차단 시 `TRADING_ENABLED=false` 자동 전환(설정 ON 시).

3. 변동성 기반 포지션 사이징
- 설정: `VOLATILITY_POSITION_SIZING_ENABLED`, `RISK_PER_TRADE_PCT`
- 손절폭(`entry-stop`) 기준으로 허용 손실 예산 내 수량 재계산.
- 과대 수량 제안 시 자동 감축.

4. 운영 설정 노출 확장
- `/api/v1/admin/settings` mutable 항목에 신규 리스크/실행 설정 추가.

## 기대 효과
- 급락일 손실 꼬리 위험 감소.
- 체결 품질 편차(슬리피지) 완화.
- 전략 성능 저하 국면에서 자동 방어.

## 테스트
- `tests/strategy/test_trading_guard.py`
- `tests/strategy/test_risk_manager_enhancements.py`
- `tests/agent/test_trading_agent_execution_policy.py`
