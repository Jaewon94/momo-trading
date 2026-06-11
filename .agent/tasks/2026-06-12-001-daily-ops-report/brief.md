# Brief

## Metadata

- Task ID: `2026-06-12-001-daily-ops-report`
- Created: `2026-06-12T08:30:05+09:00`
- Repo: `momo-trading`
- Title: Daily ops comprehensive report

## Goal

장마감 후 전 기능(매매 funnel, 게이트/가드, LLM 사용, 에러, 리소스, 뉴스, 스케줄러)의 하루치 운영 데이터를 집계해 사람이 읽기 좋은 Markdown + JSON 리포트를 매일 생성하고, LLM 코멘터리(병목/개선/신기능 제안)를 포함하는 daily ops report 체계를 구축한다

## Scope

In scope:

- `services/daily_ops_report_service.py` 신규: 매매/의사결정/LLM/AI스킵/잡/에러/리소스/뉴스/활동 섹션 집계, 전일 대비 delta, 이상 플래그, Markdown 렌더링, LLM 코멘터리(옵션), JSON+MD 저장.
- `scheduler/jobs/daily_ops_report_job.py` 신규 + scheduler.py에 평일 16:40 cron 등록 (id: daily_ops_report).
- `core/config.py`: DAILY_OPS_REPORT_ENABLED / DAILY_OPS_REPORT_LLM_ENABLED 추가.
- `scripts/dev/run_daily_ops_report.py` 수동 실행기 (--date, --no-llm).
- 단위 테스트 + 기존 잡 ID 테스트 갱신, project-card 연동.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- services/observability_reporting_service.py build_overview 반환 형태 (success_rate 0~100, provider_breakdown/by_reason 리스트, errors.incidents)
- services/daily_report_service.py 의 LLM generate_manual + repo 사용 패턴
- scheduler/jobs/calibration_review_job.py 의 cron + runtime/reports 저장 패턴

Plan implications:

- Adopt:
- Defer:
- Reject:

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `.venv313/bin/python -m pytest tests/services/test_daily_ops_report_service.py tests/scheduler/test_scheduler_runtime_paths.py -q`
- `.venv313/bin/python scripts/dev/run_daily_ops_report.py` 실DB 리포트 생성 확인
- `python scripts/check_task_harness.py --strict-current`
