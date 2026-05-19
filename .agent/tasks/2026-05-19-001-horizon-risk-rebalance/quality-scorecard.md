# Quality Scorecard

## Context Quality

- Status: passed
- Notes: Loss-streak, horizon, LLM latency, and current runtime settings were recorded in the brief and decision record.

## Implementation Quality

- Status: passed
- Notes: Changes are scoped to loss-streak recovery semantics, horizon classification, candidate type hints, and the scanner news-gate horizon.

## Test Quality

- Status: passed
- Notes: Added focused tests for SHADOW observation behavior, overheated MID fallback, non-trigger aggressive MID fallback, and overheated candidate scoring.

## Operational Safety

- Status: passed
- Notes: Protected behavior change was approved and recorded. Runtime setting is PROBATION, server health is OK after restart, and order reconciliation is green.

## Residual Risks

- Off-hours news polling reported one `INVESTING` source error after restart. This is outside the order path, but should be watched if it repeats past the configured source-failure threshold.
