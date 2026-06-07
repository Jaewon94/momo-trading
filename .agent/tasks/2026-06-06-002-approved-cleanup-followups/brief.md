# Brief

## Metadata

- Task ID: `2026-06-06-002-approved-cleanup-followups`
- Created: `2026-06-06T16:51:36+09:00`
- Repo: `momo-trading`
- Title: Apply approved runtime cleanup follow-ups

## Goal

After explicit user approval, clean historical fixture-like runtime decision events safely, address remaining scheduler test warnings, restart the service, and verify normal operation

## Scope

In scope:

- 사용자 승인 후 runtime DB의 fixture-like decision_events와 연결된 waiting forward-return rows를 정리한다.
- DB 변경 전 백업과 삭제 전 대상 CSV를 남긴다.
- scheduler startup background task의 coroutine warning을 코드 차원에서 제거한다.
- 관련 테스트, 넓은 회귀 테스트, 하네스 검증을 수행한다.
- 서비스를 재시작하고 health/status/lifecycle/runtime API로 정상 동작을 확인한다.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command, liquidation, order placement.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- runtime DB schema for `decision_events` and `decision_forward_returns`
- previous task `2026-06-06-001-weekly-review-fixes`
- scheduler startup tests

Plan implications:

- Adopt: DB cleanup uses the same conservative fixture-like predicate already implemented for analysis exclusion.
- Adopt: Delete dependent `decision_forward_returns` first, then `decision_events`, inside a transaction.
- Adopt: Preserve deletion target list as a task artifact and create a runtime DB backup before mutation.
- Adopt: Change `_spawn_background_task` to accept a coroutine factory so startup tasks do not create inner coroutines before the runner executes.
- Reject: Do not relax trading gates or force buying to lower cash allocation in this cleanup task.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py::test_scheduler_start_registers_trading_jobs_when_enabled_after_news_only_start -q -W error::RuntimeWarning`
- `.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q -W error::RuntimeWarning`
- `.venv313/bin/python -m pytest tests/services/test_decision_event_service.py tests/services/test_decision_benchmark_service.py tests/scheduler/test_forward_return_label_job.py tests/scheduler/jobs/test_calibration_review_job.py tests/api/test_admin_report_routes.py tests/agent/test_decision_maker.py -q`
- `.venv313/bin/python -m pytest tests/agent tests/api tests/scheduler tests/services -q`
- DB checks: remaining fixture-like events 0, orphan forward returns 0, `PRAGMA integrity_check` = `ok`
- Service checks: health, admin system status, lifecycle integrity, runtime integrity
