# Momo Trading Agent Guide

## Operating Context

- Human-facing plans, status updates, and reports should be written in Korean.
- Prompt contracts, schemas, fixture names, and deterministic test names may stay in English.
- Before non-trivial work, read `.agent/project-card.md` and `.agent/current-task.json` if they exist.
- Keep large decisions, verification results, and unresolved risks in `.agent/tasks/<task-id>/` instead of relying on chat history.

## Safety Boundaries

- This repo controls an automated trading system. Treat broker actions, runtime DB changes, migrations, liquidation behavior, and order placement logic as protected areas.
- Do not run destructive commands, production migrations, broker reset actions, or DB deletion without explicit user approval.
- Preserve unrelated dirty worktree changes. There are often active runtime and strategy changes in progress.
- If a trading behavior change affects buy/sell thresholds, end-of-day handling, risk profile behavior, or broker reconciliation, update the task brief and verification notes.

## Harness Workflow

- Current task pointer: `.agent/current-task.json`
- Project context: `.agent/project-card.md`
- Task artifacts: `.agent/tasks/<task-id>/`
- Required task files:
  - `brief.md`
  - `state.json`
  - `run-log.json`
  - `test-plan.md`
  - `decision-record.md`
  - `quality-scorecard.md`

Use:

```bash
python scripts/task_harness.py status
python scripts/check_task_harness.py --strict-current
```

For a new substantial task:

```bash
python scripts/task_harness.py start \
  --title "Short title" \
  --goal "Concrete goal" \
  --slug short-slug
```

## Code And Commit Harness

- Follow [docs/workflows/code-commit-harness.md](docs/workflows/code-commit-harness.md) for implementation and commit readiness.
- Before edits, identify whether the change touches broker actions, runtime DB, migrations, liquidation, order placement, credentials, or CI/CD.
- For trading policy changes, first follow [docs/workflows/trading-policy-change-checklist.md](docs/workflows/trading-policy-change-checklist.md) and keep [docs/architecture/trading-policy-governance.md](docs/architecture/trading-policy-governance.md) aligned.
- If a change touches buy/sell gates, risk profile behavior, holding horizon, runtime settings, or LLM prompt trading semantics, record the policy owner and behavior impact in the task artifacts before implementation.
- Before commit approval is requested, run `python scripts/task_harness.py verify <task-id>`.
- Use `python scripts/change_harness.py <paths...>` to classify risk, reviewers, and focused checks for code changes.
- `git commit` and `git push` are separate approval boundaries.
- Use `python scripts/guard_git_command.py check-command --command "<command>"` to classify risky git commands.

## Verification

- Prefer focused tests near the changed surface.
- For harness changes, run:

```bash
python scripts/check_task_harness.py --strict-current
python scripts/task_harness.py verify <task-id>
```

- If verification cannot be run, record the reason in the task run log or final report.
