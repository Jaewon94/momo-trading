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

5. 호라이즌(단기/중기/장기) 기반 운영
- 신규 유틸: `strategy/trade_horizon.py`
- 판정 기준:
  - 단기: 이벤트 급등락/고변동/공격 전략
  - 장기: 강세/테마 국면 + 고신뢰도
  - 그 외 중기
- 적용:
  - 호라이즌별 리스크 배수 (`RISK_MULTIPLIER_SHORT/MID/LONG`)
  - 호라이즌별 비용 게이트(예상 비용 대비 기대엣지)
  - 호라이즌별 손절/익절/트레일링 기본값 보정

6. 수익 검증 리포트 API
- `GET /api/v1/admin/performance/summary?days=30`
  - overall KPI, 전략별/호라이즌별 KPI, 리스크 차단 횟수
- `GET /api/v1/admin/performance/periodic?period=weekly|monthly&size=8`
  - 주간/월간 버킷 기반 성과 추이
- KPI: trade_count, win_rate, expectancy, profit_factor, total_pnl, avg_return_pct, max_drawdown

## 기대 효과
- 급락일 손실 꼬리 위험 감소.
- 체결 품질 편차(슬리피지) 완화.
- 전략 성능 저하 국면에서 자동 방어.

## 테스트
- `tests/strategy/test_trading_guard.py`
- `tests/strategy/test_risk_manager_enhancements.py`
- `tests/agent/test_trading_agent_execution_policy.py`
- `tests/strategy/test_trade_horizon.py`
- `tests/agent/test_trading_agent_cost_gate.py`
