# Decision Record

## Decision

Add an AI-reviewed hold extension path to overnight smart liquidation.

## Rationale

- The existing max-hold fallback is safe, but the overnight LLM prompt framed max-hold as unconditional `SELL`, which contradicts the requested MID/LONG-oriented swing operation.
- Extension should be AI-reviewed because the judgment depends on trend quality, remaining upside, market regime, and news context.
- Extension still needs deterministic rails: invalid holdings data, missing trade records, average-price errors, LLM failure, and total hold-cap exhaustion must not be overridden by a vague LLM response.

## Deferred

- Intraday holdings-review actions remain unchanged for now; this task targets the 15:10 overnight hold/liquidation decision.
- No DB schema migration is needed because extension state fits in existing `TradeResult.notes`.

## Risks

- This touches liquidation/hold behavior, so focused tests and runtime read-only checks are required before reporting operational safety.
- Existing `notes` values can include JSON plus text markers; parsing/updating must preserve marker text such as partial take-profit flags.
