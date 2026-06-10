# Brief

## Metadata

- Task ID: `2026-06-10-011-horizon-scheduled-news-analysis`
- Created: `2026-06-10T14:38:03+09:00`
- Repo: `momo-trading`
- Title: Horizon scheduled news-aware analysis

## Goal

Implement horizon-specific deterministic filtering and news-aware LLM scheduling for short, mid, and long trading analysis without bypassing central risk/order policy.

## Scope

In scope:

- Add a central horizon scan profile for SHORT/MID/LONG.
- Route market scanner candidate breadth, news pressure checks, news context lookback, and daily candle depth by horizon.
- Add optional scheduled MID daily and LONG weekly scans through the existing `trading_agent.run_cycle` path.
- Keep existing risk gates, order gates, and broker execution flow authoritative.
- Add focused tests for horizon profile, scanner, news context, and scheduler registration.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- New broker order implementation.
- New external data provider integration beyond current news items.
- Runtime DB reconciliation for existing stale pending order.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Previous task `2026-06-10-010-horizon-llm-architecture-plan`.
- Current implementation:
  - `agent/market_scanner.py`
  - `agent/trading_agent.py`
  - `services/news_context_service.py`
  - `services/candidate_scoring_service.py`
  - `scheduler/scheduler.py`
  - `core/config.py`
  - `core/runtime_settings.py`

Plan implications:

- Adopt: SHORT frequent, MID daily, LONG weekly scan cadence.
- Adopt: Horizon-specific pre-LLM candidate breadth and news windows.
- Adopt: Existing central policy/risk/order flow remains the only order path.
- Defer: Structured-output LLM schema split and DART fundamental ingestion to the next phase.
- Reject: Running three LLM analyses for every candidate on every cycle.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Focused pytest for changed scanner/scheduler/news/trading-agent surfaces.
- `python scripts/check_runtime_integrity.py --days 7` as an operational status check; existing stale pending issue is tracked separately.
