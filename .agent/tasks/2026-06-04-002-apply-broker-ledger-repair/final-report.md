# Final Report

## 운영 결과

- 서비스는 `tmux` 세션 `momo-trading-service`에서 실행 중이다.
- API health는 정상이며, `TRADING_ENABLED=true`, `AUTONOMY_MODE=AUTONOMOUS`, effective order mode `FULL`이다.
- 스케줄러와 에이전트는 실행 중이고, 최종 스타트업 사이클은 `scanned=5`, `analyzed=5`, `signals=0`, `executed=0`으로 신규 주문 없이 종료됐다.
- 최종 pending orders API 결과는 빈 목록이다.
- 최종 runtime integrity는 OK이며 broker/db pending, stale DB-only, 수량 mismatch, broker-missing open BUY가 모두 0이다.

## 장부 복구

- 런타임 DB 백업: `runtime/backups/db/app-manual-20260604-103021.db`
- SG세계물산 `004060` open BUY 1500주는 브로커 보유가 없어 `BROKER_HOLDING_MISSING` 중립 close로 정리했다.
- 이 복구는 브로커 주문을 새로 내지 않고 DB 장부만 브로커 상태에 맞춘 작업이다.

## 매매 분석

- 이번 주 확정 closed BUY 기준 실현손익은 +337,270원이다.
- 오늘 세션 기준 실현손익은 +29,190원이다.
- 현재 보유 평가손익은 +220,677원이고, 보유 종목은 센서뷰 1005주와 원텍 400주다.
- 오늘 09:03 기준 총자산 대비로는 -113,857원이라, 실현손익/보유평가 기준은 플러스지만 총자산 기준은 아직 소폭 마이너스다.
- 동양고속 매도는 10:17 본전스탑 상향 후 재시작 복원으로 발생했다. 오작동 주문은 아니지만, 이후 보유 AI가 더 낮은 stop을 `TIGHTEN_STOP`으로 제안하며 메모리/DB 기준이 갈라질 수 있는 문제가 있어 수정했다.

## 코드 변경

- SELL 주문 체결 확인 전 `PENDING_CONFIRM` audit row를 생성하도록 스케줄러 SELL 확인 경로를 보강했다.
- SELL 체결 확인 timeout은 보유수량 변화 추론을 먼저 시도하도록 보강했다.
- 보유 종목 stop 조정은 기존 보호 stop보다 낮아지지 않도록 TradingAgent와 스케줄러 보유 재평가 경로에 보존 규칙을 추가했다.
- 보유 AI가 stop/take threshold를 갱신하면 open BUY DB에도 안전하게 반영한다.
- `SQLALCHEMY_ECHO=false` 설정과 `aiosqlite` 로그 억제로 로컬 로그 폭증을 막았다.

## 검증

- `.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py -q`: `173 passed, 3 warnings`
- `python scripts/check_runtime_integrity.py --days 7`: OK
- `python scripts/check_task_harness.py --strict-current`: passed
- Pending orders API: empty

## 남은 리스크

- 상태 API의 orders WARN은 10:01 SG세계물산 과거 경고를 아직 표시한다. 현재 주문/장부 대사는 정상이며 UI 경고 만료 정책은 별도 개선 대상이다.
- 기존 `CONFIRM_FAILED` 8건은 현재 pending drift는 아니지만 과거 이력 정리 과제로 남겨둔다.
- 자동매매가 `FULL` 모드로 계속 실행 중이므로 시장 가격 변동 리스크는 열린 상태다.
