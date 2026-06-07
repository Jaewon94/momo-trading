# Decision Record

## Decision

1. 런타임 DB를 백업한 뒤 브로커 보유가 없는 SG세계물산 open BUY 1건을 `BROKER_HOLDING_MISSING` 중립 close로 정리한다.
2. SELL 체결 확인 누락 수정 코드를 반영하고 서비스를 tmux 세션에서 재시작한다.
3. 보유 종목의 기존 보호 손절선보다 낮은 AI stop 조정은 `TIGHTEN_STOP`이라도 적용하지 않는다.
4. 로컬 SQL echo를 기본 비활성화해 로그 폭증을 막는다.

## Rationale

- SG세계물산은 브로커 보유 0, DB open BUY 1500주였으므로 추가 주문 없이 장부만 현재 브로커 상태에 맞춰야 했다.
- 동양고속 10:45 매도는 10:17 본전스탑 상향 후 재시작 복원으로 발생했다. 문제는 매도 자체보다, 이후 AI가 `TIGHTEN_STOP` 명칭으로 더 낮은 stop을 제안하면서 메모리/DB 기준이 갈라질 수 있었던 점이다.
- 장중 재시작 후에도 보호 스탑이 느슨해지지 않아야 의도한 수익보호 정책과 일관된다.
- 66GB까지 커진 로컬 로그는 SQLAlchemy echo와 aiosqlite DEBUG 출력이 주원인이므로 설정으로 차단하는 것이 맞다.

## Deferred

- 기존 `CONFIRM_FAILED` 8건은 현재 pending/order drift가 아니며, 별도 과거 장부 정리 과제로 다룬다.
- SG세계물산 10:01 주문 경고는 상태 API에 최근 오류로 남아 있지만 lifecycle integrity와 브로커 대사는 OK이므로 UI 경고 만료/해소 정책은 별도 개선 대상이다.

## Risks

- 자동매매는 `FULL`/`AUTONOMOUS`로 운영 중이므로 가격 변동 리스크는 계속 열려 있다.
- 보유 종목 손절선 보존은 손실 확대를 줄이는 방향이지만, 급락 시 실제 체결가는 stop 가격보다 낮을 수 있다.
- 스타트업 스캔은 재시작 때마다 실행될 수 있으므로 재시작 직후 주문/대기열 확인이 필요하다.
