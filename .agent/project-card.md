# Momo Trading Project Card

## Purpose

momo-trading은 국내 주식 자동 매매와 운영 대시보드를 위한 FastAPI 기반 시스템이다. 실시간 후보 탐색, deterministic gate, LLM 분석, 주문/체결 추적, 보유 종목 심사, 뉴스/공시 신호, 관리자 UI를 함께 다룬다.

## Important Directories

- `agent/`: 매매 의사결정과 trading agent orchestration
- `analysis/`: LLM provider, technical analysis, model catalog
- `api/routes/`: 관리자/상태 API
- `services/`: runtime settings, pre-analysis, holdings review, observability, reporting
- `strategy/`: risk profile, guard, trade horizon, scoring rules
- `scheduler/`: market cycle, portfolio sync, after-hours jobs
- `admin/static/js/`: 관리자 UI state/rendering
- `tests/`: Python unit/API tests and frontend state tests
- `.agent/`: 작업 컨텍스트와 하네스 artifact
- `.understand-anything/`: Understand-Anything 플러그인이 생성한 코드베이스 지식 그래프 (`/understand`로 갱신, `/understand-dashboard`로 시각화, `/understand-diff`로 변경 영향도 확인)
- 뉴스/공시 판단 정책은 `strategy/news_intelligence_policy.py`와 `docs/architecture/news-intelligence-governance.md`를 함께 본다.
- 전체 시스템 개선 우선순위는 `docs/고도화/2026-06-11-service-improvement-roadmap.md`를 본다 (보안 → PnL 데이터 신뢰성 → 가드 ENFORCE 졸업 → 구조 개선 순).
- 일일 운영 종합 리포트(전 기능 집계 + LLM 코멘터리)는 평일 16:40 자동 생성되어 `runtime/reports/daily_ops_<날짜>.md`에 쌓인다. 병목/개선점 분석 작업은 이 리포트를 먼저 읽는다. 수동 실행: `.venv313/bin/python scripts/dev/run_daily_ops_report.py`

## Common Commands

```bash
bash start.sh
bash start.sh stop
python scripts/check_task_harness.py --strict-current
python -m pytest tests/scripts/test_check_task_harness.py tests/scripts/test_task_harness.py -q
python scripts/task_harness.py verify <task-id>
python scripts/guard_git_command.py scan-secrets
```

대표 운영 확인:

```bash
curl -s http://127.0.0.1:9000/api/v1/health
curl -s http://127.0.0.1:9000/api/v1/admin/system/status
curl -s http://127.0.0.1:9000/api/v1/admin/account/holdings
```

## Current Operating Notes

- Admin server commonly runs on port `9000`.
- Kiwoom/broker state and local DB state can diverge; reconcile before judging trade outcomes.
- Recent strategy direction: deterministic Tier 1 filters should remove obvious skips cheaply; LLM should focus on important buy/sell decisions.
- Sell behavior should not be treated as same-day forced liquidation by default; holding horizon and risk profile matter.
- Runtime settings may select CLI/API LLM providers and concurrency behavior.

## Protected Areas

Ask before:

- deleting or resetting runtime DB data
- changing migrations or production schemas
- forcing liquidation behavior
- pushing, deploying, or creating external side effects
- altering broker credentials, API keys, or token files

## Context Rules

- Keep task-specific assumptions in `.agent/tasks/<task-id>/brief.md`.
- Keep decision tradeoffs in `decision-record.md`.
- Keep verification commands and results in `test-plan.md`, `run-log.json`, and `quality-scorecard.md`.
- Promote only stable project facts into this project card.

## Code And Commit Harness

- Code-writing flow and commit readiness live in `docs/workflows/code-commit-harness.md`.
- `scripts/task_harness.py verify <task-id>` is the standard pre-commit readiness check.
- `scripts/guard_git_command.py` classifies `git commit`, `git push`, force push, protected ref deletion, and scans obvious secret patterns.
