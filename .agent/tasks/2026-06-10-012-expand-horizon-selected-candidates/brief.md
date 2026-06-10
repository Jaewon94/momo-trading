# Brief

## Metadata

- Task ID: `2026-06-10-012-expand-horizon-selected-candidates`
- Created: `2026-06-10T16:00:35+09:00`
- Repo: `momo-trading`
- Title: Expand horizon selected candidates

## Goal

Increase horizon-specific final LLM-selected candidate caps and document current SHORT/MID/LONG filter, LLM, and trading flow.

## Scope

In scope:

- Increase horizon-specific market-scan LLM selected caps.
- Keep broad deterministic candidate pools unchanged.
- Document how SHORT/MID/LONG filter, LLM selection, Tier1/Tier2 analysis, and trading execution connect.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- FINRA, Frequent Intraday Trading: Understanding the Basics, June 04, 2026:
  https://www.finra.org/investors/insights/frequent-intraday-trading
- FINRA Regulatory Notice 26-10, April 20, 2026:
  https://www.finra.org/rules-guidance/notices/26-10
- Mahata et al., Identification of short-term and long-term time scales in stock markets and effect of structural break:
  https://arxiv.org/abs/1907.03009
- Asness et al., Fact, Fiction and Momentum Investing:
  https://ssrn.com/abstract=2435323

Plan implications:

- Adopt: Increase selected caps from `SHORT 8 / MID 8 / LONG 6` to `SHORT 10 / MID 12 / LONG 12`.
- Adopt: Continue sending broad deterministic candidates to the market-scan LLM, then send only selected candidates to Tier1/Tier2.
- Adopt: Treat horizon criteria as deterministic policy rails plus LLM judgment, not LLM-only discretion.
- Adopt: Use source-backed principles only at the strategy-shape level: frequent intraday trading is materially different from multi-day/month holding, and medium/long signals should use wider price/news windows.
- Defer: Fundamental/DART financial context expansion for LONG analysis.
- Reject: Sending every deterministic candidate directly to Tier1/Tier2 because it creates excessive LLM calls and trading pressure.
- Note: The exact selected-candidate caps are system-specific operational parameters, not values prescribed by an external paper or regulator.

## Current Horizon Flow

- SHORT: deterministic scanner reviews up to `30` candidates, uses 24h news context and 60 daily candles, then market-scan LLM selects up to `10` names for deeper analysis.
- MID: deterministic scanner reviews up to `60` candidates, uses 168h news context and 120 daily candles, then market-scan LLM selects up to `12` names for deeper analysis.
- LONG: deterministic scanner reviews up to `100` candidates, uses 720h news context and 240 daily candles, then market-scan LLM selects up to `12` names for deeper analysis.
- Tier1/Tier2 analysis receives `target_horizon_hint` and horizon-specific news/price context.
- Execution remains gated by existing runtime risk profile, order mode, buying limits, portfolio constraints, and broker/session support.

## Completion Criteria

- Required changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Add task-specific commands here.
