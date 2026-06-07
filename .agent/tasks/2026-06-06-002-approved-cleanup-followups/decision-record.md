# Decision Record

## Decision

사용자 승인 후 runtime DB의 historical fixture-like decision_events를 삭제했다. 삭제 전 DB 백업과 CSV target export를 남겼고, 연결된 `decision_forward_returns`는 모두 `WAITING_DATA`였으므로 먼저 삭제했다.

스케줄러 coroutine warning은 테스트만 우회하지 않고 `_spawn_background_task`가 coroutine 객체 대신 coroutine factory를 받도록 코드 구조를 바꿨다.

## Rationale

- 기존 정리는 분석 경로 제외까지였지만 raw runtime DB에는 fixture-like rows가 남아 있었다. 사용자가 전체 승인했으므로 보호 영역인 runtime DB cleanup까지 수행했다.
- 삭제 조건은 `provider='UNKNOWN'`, `model='UNKNOWN'`, `cycle_id like 'cycle-%'`, `stock_name=symbol`로 제한했다. 이 조건은 실제 운영 후보의 UUID cycle_id, candidate scoring provider/model과 겹치지 않는다.
- child row를 먼저 삭제해 orphan을 만들지 않고, 삭제 후 orphan count와 SQLite integrity check를 확인했다.
- coroutine factory 방식은 delay 전에 inner coroutine을 만들지 않기 때문에 테스트 경고뿐 아니라 실제 background startup task의 객체 생명주기도 더 안전하다.

## Deferred

- Trading gate/LLM threshold 완화는 이번 cleanup 범위에서 제외했다. 공격적 리스크 모드라도 수익성과 리스크를 바꾸는 전략 변경은 별도 실험이 필요하다.
- 이미 존재하는 unrelated dirty worktree changes는 보존했다.

## Risks

- Runtime DB mutation은 되돌림이 필요한 경우 백업 `runtime/backups/db/app-cli-20260606-165233.db`를 기준으로 복구해야 한다.
- 삭제된 rows는 raw 감사 데이터에서 사라졌지만, task artifact CSV에 삭제 전 대상 목록이 남아 있다.
- Scheduler helper 변경은 startup task 호출 방식에 영향을 주므로 scheduler runtime path tests를 넓게 실행했다.
