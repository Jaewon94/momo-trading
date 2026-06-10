# Decision Record

## Decision

Plan a horizon-specific LLM architecture, but do not implement live behavior changes in this task.

Recommended target design:

- Shared typed `DecisionContext`.
- Separate SHORT/MID/LONG context builders.
- Separate SHORT/MID/LONG analyst prompt and schema contracts.
- Central orchestrator chooses one primary horizon per candidate.
- Risk, sizing, exit, and order execution remain centralized under the policy registry.
- New horizon modules start in shadow mode before any live order effect.

## Rationale

- Current code has horizon policy and hold-discipline guardrails, but horizon analysis is not truly modular.
- MID/LONG decisions need news, filings, financial trends, valuation, and thesis durability beyond a 20-day chart and 24-hour news window.
- Running all three LLMs for every candidate would increase latency, cost, and conflict risk. Routing first, then analyzing the selected horizon is safer.
- API structured outputs are a better long-term fit for typed trading decisions than free-form CLI output, but the current CLI path should remain during transition.

## Deferred

- Live order behavior changes.
- Broker reconciliation or runtime DB mutation.
- New paid market/fundamental data provider integration.
- Horizon-specific provider settings until schemas and shadow traces exist.

## Risks

- More LLM modules can create conflicting recommendations unless the orchestrator and policy registry stay authoritative.
- LONG analysis can become stale if financial data is not timestamped and completeness-scored.
- CLI-based multi-agent expansion can overload latency because CLI providers are serialized.
- Shadow-mode storage and analysis must avoid leaking secrets or oversized prompt payloads.
- Current runtime integrity has an unrelated stale order reconciliation issue that should be handled separately.
