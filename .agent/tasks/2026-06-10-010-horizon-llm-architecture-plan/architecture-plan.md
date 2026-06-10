# Horizon-Specific LLM Architecture Plan

## Summary

The user's concern is valid. The system currently has strong horizon policy text and deterministic hold/exit guardrails, but the buy/review analysis path is still mostly one chart-first LLM workflow with light recent-news context. MID and LONG decisions need different evidence from SHORT decisions: broader price history, event/news windows, filings, financial statements, valuation, and a persistent investment thesis.

The recommended direction is not to run three independent LLMs for every stock in the live path. The safer architecture is:

1. Expand deterministic candidate filtering broadly without LLM.
2. Route each candidate to a likely horizon using deterministic features and data completeness.
3. Build a horizon-specific context package.
4. Run the matching horizon analyst LLM contract.
5. Run a central risk/policy gate before any order.
6. Shadow-test MID/LONG modules before live activation.

## Current Implementation Findings

- `strategy/trade_horizon.py` chooses `SHORT`, `MID`, or `LONG` from strategy type, trigger, price change, confidence, and market regime. It does not evaluate financial statement quality, revenue trend, longer news windows, or thesis durability.
- `agent/trading_agent.py` uses one Tier1 analysis path, computes a projected horizon, then sends the same broad context into Tier2. Horizon is guidance, not a separate analysis module.
- `analysis/llm/prompts/stock_analysis.py` already tells the model to prefer MID/LONG and includes a 20-day daily data block plus optional PER/PBR/market cap and news. This is better than pure intraday charting, but still insufficient for true MID/LONG thesis work.
- `services/news_context_service.py` defaults to a 24-hour news window and prompt items are capped. That is reasonable for SHORT risk, but too narrow for MID/LONG.
- `agent/market_scanner.py` still starts from market activity candidates such as surge/drop/volume/scored candidates. This is useful for short and swing candidates, but weak for long-term discovery unless fundamentals and filings are added.
- `analysis/llm/llm_factory.py` and `analysis/llm/selection_policy.py` route by `TIER1`, `TIER2`, `MANUAL`, and `NEWS`, not by horizon. CLI providers are serialized, so adding more live CLI calls would increase latency and contention.

## External Reference Implications

- QuantConnect's Algorithm Framework separates alpha generation, portfolio construction, execution, and risk. That supports modularizing our system around signal/context, decision, sizing, execution, and risk instead of embedding all policy in prompts.
- OpenAI Structured Outputs support schema-constrained JSON. Horizon-specific decisions should move toward typed schemas so a LONG analyst cannot silently omit required fields such as thesis horizon, invalidation events, financial evidence, and data completeness.
- OpenDART provides official Korean filing and financial-statement APIs, including major accounts, full financial statements, XBRL downloads, and financial ratios. This is the right first source for Korean MID/LONG fundamentals.
- Finance NLP research supports using text/news/filings for stock prediction and sentiment; BloombergGPT and FinBERT also reinforce that financial language is domain-specific and should not be treated as generic chat text.

## Proposed Architecture

### 1. Canonical Decision Context

Add a typed `DecisionContext` built from reusable sections:

- `market_context`: market regime, index trend, liquidity, sector/theme.
- `technical_context`: intraday, 20-day, 60-day, 120-day, 240-day trend features.
- `news_event_context`: horizon-aware news and event summaries.
- `fundamental_context`: revenue, operating profit, net income, debt, cash, PER/PBR, market cap, reporting date, restatement risk.
- `filing_context`: recent DART filings and material disclosures.
- `portfolio_context`: current position, concentration, cash, existing thesis, holding age.
- `risk_context`: stop/profit policy, max exposure, liquidity/slippage, policy registry version.
- `data_completeness`: required/optional fields by horizon with explicit missing-data reasons.

### 2. Horizon Context Builders

Create separate builders behind one interface:

- `ShortTermContextBuilder`
  - Uses intraday/1-5 day price action, volume shock, liquidity, spread/slippage, immediate news.
  - Optimized for speed and strict rejection.
- `MidTermContextBuilder`
  - Uses 20-120 trading-day trend, pullback/reversal context, 7-30 day news, sector/theme persistence, recent filings, earnings direction.
  - Optimized for swing thesis and hold discipline.
- `LongTermContextBuilder`
  - Uses 120-240+ day history, annual/quarterly financial trend, valuation versus peers/sector, major filings, balance-sheet risk, durable catalyst.
  - Should run as a slower background/cache job, not necessarily during intraday live order evaluation.

### 3. Horizon LLM Analysts

Split prompts and output schemas:

- `ShortTermTacticalAnalyst`
  - Output: `action`, `setup_type`, `time_stop`, `liquidity_risk`, `invalidations`, `confidence`.
- `MidTermSwingAnalyst`
  - Output: `action`, `expected_hold_days`, `thesis`, `technical_evidence`, `event_evidence`, `invalidation_price_or_event`, `partial_exit_plan`, `confidence`.
- `LongTermFundamentalAnalyst`
  - Output: `action`, `expected_hold_weeks_months`, `business_thesis`, `financial_evidence`, `valuation_view`, `filing_risks`, `review_cadence`, `confidence`.

The orchestrator should select one primary horizon per candidate. It may request a second opinion only when:

- position size is above a threshold,
- the current holding horizon conflicts with the new decision,
- a long-term candidate has incomplete or stale financial data,
- the model recommends selling before minimum hold rules.

### 4. Provider and Key Strategy

- Keep the current CLI provider path for existing Tier1/Tier2 while the refactor is in shadow mode.
- Add horizon-level provider profiles only after schemas are introduced:
  - `LLM_PROFILE_SHORT`
  - `LLM_PROFILE_MID`
  - `LLM_PROFILE_LONG`
  - each profile resolves provider, model, timeout, fallback, and execution mode.
- Prefer API providers for new horizon modules when strict JSON parsing, observability, concurrency, and typed validation matter.
- Reuse existing provider keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) rather than creating per-horizon secrets. Add no secrets to logs, DB rows, or prompt traces.
- Do not run multiple Codex/Claude CLI horizon calls in parallel; current factory serializes CLI providers and that should remain.

### 5. Policy Governance

The refactor should preserve the policy registry as the source of truth:

- Prompts may explain policy but cannot define new stop-loss, minimum-hold, or sizing rules.
- Horizon modules must consume policy from a shared object.
- Tests should fail if prompt text and policy registry drift on protected thresholds.
- Sell decisions should carry `decision_source`, `horizon`, `policy_version`, `thesis_id`, and `data_completeness`.

## Phased Implementation Plan

### Phase 1 - No Behavior Change

- Add `DecisionContext` and `DataCompleteness` schemas.
- Build adapters from current chart/news/fundamental inputs to the new schema.
- Add trace logging without changing order decisions.
- Tests: schema serialization, missing-data handling, no live order path changes.

### Phase 2 - Horizon Context Builders

- Add SHORT/MID/LONG context builder modules.
- Expand deterministic scanner output with horizon candidates and data completeness.
- Add longer news windows: SHORT 24h, MID 7-30d, LONG 90-365d.
- Add OpenDART ingestion plan behind feature flags.
- Tests: fixture-based context snapshots per horizon.

### Phase 3 - Prompt and Schema Split

- Split prompt templates into short/mid/long analyst contracts.
- Add strict structured output support for API-capable providers.
- Keep CLI fallback parser for transition, but mark it lower confidence if schema repair is needed.
- Tests: valid schema, invalid enum rejection, missing required field rejection.

### Phase 4 - Shadow Mode

- Run horizon-specific analysts in shadow for candidates and holdings.
- Store decisions without affecting orders.
- Compare forward outcomes by horizon, data completeness, and decision type.
- Do not activate live trading until sample size and review thresholds are met.

### Phase 5 - Controlled Activation

- Activate SHORT first only if latency and failure rates are acceptable.
- Activate MID only after hold-discipline and premature-exit metrics improve.
- Activate LONG as background thesis generation with low-frequency recheck; do not make intraday full-liquidation decisions from LONG analysis alone.
- Keep central risk and execution gates unchanged.

## Recommendation

Proceed with this refactor, but only as an incremental architecture change. The first implementation step should be schema/context extraction and shadow instrumentation, not immediately adding more LLM calls to live trading. This avoids new prompt-policy conflicts and gives us measurable evidence before changing order behavior.

## Operational Note Found During Planning

`python scripts/check_runtime_integrity.py --days 7` currently reports one stale `PENDING_CONFIRM`/broker-missing open buy condition. This is separate from the horizon architecture plan and should be reconciled before claiming the live system is fully healthy.
