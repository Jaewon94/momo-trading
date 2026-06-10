# Brief

## Metadata

- Task ID: `2026-06-10-002-policy-governance-refactor`
- Created: `2026-06-10T11:45:38+09:00`
- Repo: `momo-trading`
- Title: Centralized trading policy refactor plan

## Goal

Scaffold a researched refactor plan to centralize trading policy ownership and prevent scattered buy/sell/risk rule conflicts while preserving current runtime behavior.

## Scope

In scope:

- Research policy governance patterns from official docs, best practices, and
  papers.
- Map current code owners for scanner, deterministic gates, LLM prompts,
  exposure alignment, risk manager, order submission, and holding/exit policy.
- Create a behavior-preserving refactor plan and repo checklist so later code
  changes do not silently conflict across policy layers.
- Update agent-facing instructions where needed so future policy changes follow
  the same process.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Runtime setting mutation and server restart. This task is a plan and docs
  refactor, not a live trading behavior change.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Open Policy Agent docs and policy testing.
- OASIS XACML 3.0 Core Specification.
- SEC Market Access Rule release.
- FINRA Regulatory Notice 15-09.
- Microsoft domain analysis guidance.
- AWS Well-Architected Operational Excellence.
- Feature toggles paper, arXiv:1907.06157.

Plan implications:

- Adopt: separate policy decision from enforcement, explicit priority/combining
  rules, settings catalog, traceable policy decisions, fixture-based policy tests.
- Defer: external policy engine adoption and runtime admin UI metadata until the
  internal contract is stable.
- Reject: threshold tuning as a substitute for owner/priority cleanup.

## Completion Criteria

- Current progress is committed separately before this task's docs changes.
- A refactor plan document exists and maps current code owners.
- A reusable policy change checklist exists.
- Agent/project docs point future policy edits to the checklist.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python scripts/check_markdown_links.py AGENTS.md .agent docs/architecture docs/workflows/code-commit-harness.md`
- `python scripts/check_docs_consistency.py`
- `python scripts/task_harness.py verify 2026-06-10-002-policy-governance-refactor`
