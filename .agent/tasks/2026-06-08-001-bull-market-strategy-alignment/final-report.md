# Final Report

## Summary

- 결정론 1차 스캐너 후보 폭을 8개에서 설정 기반 기본 30개로 확장했다.
- 인버스/레버리지/현금성/채권형 상품은 신규 BUY 후보에서 제외하고, 공격 성향에서 방어형 ETF를 감점하도록 했다.
- 공격적 리스크 성향에서는 상승률과 거래량이 함께 확인된 양의 모멘텀 후보만 `AGGRESSIVE_SHORT` 힌트를 넓히도록 했다.
- forward-return 라벨링은 최신 이벤트 우선 처리로 바꾸고, 일봉 종가가 없으면 장마감 이후 스냅샷으로 close 라벨을 남길 수 있게 했다.
- MID/LONG 포지션의 전략적 익절/리뷰 매도에는 최소 보유시간 가드를 추가했다. 손절, 브로커 대사, 청산 안전 경로는 유지했다.
- 체결확정 복구 과정에서 `TradeResult.notes`가 지워져 `trade_horizon`과 활성 손절/익절 메타데이터가 사라지는 문제를 수정했다.
- 장중 서버 재시작 시 열린 포지션의 DB 저장 손절/익절/트레일링 임계값을 `event_detector`에 즉시 복원하도록 했다.

## Verification

- Passed: `.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py tests/scheduler/test_portfolio_sync_job.py tests/services/test_candidate_scoring_service.py tests/scheduler/test_forward_return_label_job.py tests/agent/test_trading_agent_cycles.py tests/agent/test_market_scanner.py tests/strategy/test_trade_horizon.py -q`
- Result: `178 passed in 34.58s`
- Passed: `python scripts/check_task_harness.py --strict-current`
- Passed: `.venv313/bin/python scripts/task_harness.py verify 2026-06-08-001-bull-market-strategy-alignment`
- Passed after reconciliation/restart: `python scripts/check_runtime_integrity.py --days 7`
- Passed after restart: `curl -s http://127.0.0.1:9000/api/v1/health`

## Operational Notes

- During restart prep, `210120` had a BUY `PENDING_CONFIRM` and then SELL `PENDING_CONFIRM`. Both were recovered through the existing admin `RECOVER_PENDING_CONFIRMS` path after broker state confirmed the fills.
- A later `082800` BUY confirmation exposed the notes-loss bug. The live row was repaired to restore `trade_horizon=LONG`, then the position was closed by protective stop-loss at 09:52:53 for -162,500 KRW (-2.12%).
- Latest restart completed with the new code. A new `459550` BUY was confirmed, pending count is 0, and broker/DB reconciliation is clean. The position is marked `MID`.
- No destructive DB cleanup, broker reset, liquidation command, or manual broker order was run.
- Service is running in tmux session `momo-trading-server`; `start.sh -d` briefly started but did not persist in this execution environment.
- Current runtime integrity is OK. System status may still show a historical order WARN for the 09:30 `210120` sell confirmation failure, but current pending/order reconciliation is clean.
