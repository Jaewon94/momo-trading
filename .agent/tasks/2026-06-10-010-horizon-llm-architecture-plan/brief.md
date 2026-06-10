# Brief

## Metadata

- Task ID: `2026-06-10-010-horizon-llm-architecture-plan`
- Created: `2026-06-10T14:14:52+09:00`
- Repo: `momo-trading`
- Title: Horizon-specific LLM architecture plan

## Goal

Assess whether short/mid/long trading decisions should use separate data inputs and LLM modules, then produce an evidence-backed implementation plan without changing runtime behavior.

## Scope

In scope:

- Audit the current short/mid/long horizon decision flow.
- Compare current implementation against external architecture and finance LLM references.
- Produce a phased implementation plan only; do not change live trading behavior.
- Document operational verification findings found during planning.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Immediate rollout of horizon-specific LLM trading.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Current repo implementation:
  - `strategy/trade_horizon.py`
  - `agent/trading_agent.py`
  - `agent/market_scanner.py`
  - `analysis/llm/llm_factory.py`
  - `analysis/llm/selection_policy.py`
  - `analysis/llm/prompts/*`
  - `services/news_context_service.py`
  - `services/deterministic_prompt_context_service.py`
  - `core/config.py`
- QuantConnect Algorithm Framework official docs:
  - https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/overview
- OpenAI Structured Outputs official docs:
  - https://platform.openai.com/docs/guides/structured-outputs
- OpenDART official developer guide:
  - https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS003
- Finance LLM / NLP papers:
  - Lopez-Lira and Tang, "Can ChatGPT Forecast Stock Price Movements?"
  - Wu et al., "BloombergGPT: A Large Language Model for Finance"
  - Araci, "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models"

Plan implications:

- Adopt: horizon-specific context builders and LLM contracts, with one deterministic policy registry as the source of truth.
- Adopt: API/structured-output path for new horizon modules where machine-validated JSON matters; keep existing CLI path during transition.
- Adopt: shadow mode before any live order-impacting behavior.
- Defer: running all SHORT/MID/LONG LLMs for every candidate in the live path.
- Defer: adding new paid data providers until the built-in/open-source data completeness contract is defined.
- Reject: treating MID/LONG as only "same chart, longer hold"; the evidence needed is materially different.

## Completion Criteria

- Planning document is created.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.
- No runtime trading behavior is changed.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `python scripts/check_runtime_integrity.py --days 7`
- Manual review of generated plan against current code and protected-operation boundaries.
