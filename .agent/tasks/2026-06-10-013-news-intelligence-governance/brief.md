# Brief

## Metadata

- Task ID: `2026-06-10-013-news-intelligence-governance`
- Created: `2026-06-10T16:53:10+09:00`
- Repo: `momo-trading`
- Title: News intelligence governance

## Goal

Centralize news intelligence policy and document a product-grade after-hours news planning approach without changing live order behavior.

## Scope

In scope:

- Centralize horizon-specific news thresholds, prompt windows, pressure candidate
  caps, severity keywords, event taxonomy, and after-hours LLM guardrails in one
  policy module.
- Route existing news signal/context/scanner code through the centralized policy
  without changing live order behavior.
- Document how after-hours news planning should work before any scheduled LLM
  spend is enabled.
- Update agent-facing docs so future news changes are checked against the same
  policy and governance document.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.
- Enabling an after-hours LLM job, adding new API keys, or changing live buy/sell
  thresholds.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- Tetlock (2007), `Giving Content to Investor Sentiment`: news tone can be
  predictive, but it must be measured rather than assumed.
- MacKinlay (1997), `Event Studies in Economics and Finance`: event/news impact
  should be evaluated against normal-return baselines.
- Goldsmith-Pinkham and Lyu (2025), causal inference in event studies: longer
  windows and volatile markets can bias event-effect attribution.
- Lumer et al. (2025), financial RAG comparison: retrieval quality, answer
  quality, latency, and cost must be optimized together.
- Yin et al. (2026), financial RAG hallucination study: retrieved context does
  not eliminate hallucination risk in financial answers.
- OWASP LLM01:2025 Prompt Injection: external news/web text is untrusted content
  and must be isolated from tool authority.

Reference links:

- https://doi.org/10.1111/j.1540-6261.2007.01232.x
- https://www.jstor.org/stable/2729691
- https://arxiv.org/abs/2511.15123
- https://arxiv.org/abs/2511.18177
- https://arxiv.org/abs/2602.05723
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/

Plan implications:

- Adopt: central news policy module, event taxonomy, after-hours research
  contract, source/item-id citation requirements, and shadow/outcome metric
  requirements.
- Defer: actual scheduled after-hours LLM research generation, persistence
  schema, admin UI, new provider keys, and prompt additions until the contract is
  implemented with cost/quality metrics.
- Reject: raising news weight directly, letting LLM-generated news summaries
  place orders, or treating unsourced web/news text as trusted instructions.

## Completion Criteria

- Required code/docs changes are implemented.
- Focused verification is run or a reason is recorded.
- Remaining risks are documented.
- No protected broker action, DB mutation, migration, or liquidation command is
  run as part of this task.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- `.venv313/bin/python -m pytest tests/strategy/test_news_intelligence_policy.py tests/services/test_news_signal_service.py tests/services/test_news_context_service.py tests/agent/test_market_scanner.py tests/strategy/policy/test_policy_registry.py tests/strategy/policy/test_settings_catalog.py -q`
- `.venv313/bin/python -m py_compile agent/market_scanner.py services/news_signal_service.py services/news_context_service.py strategy/news_intelligence_policy.py strategy/policy/registry.py`
- `python scripts/change_harness.py <changed paths>`
- `python scripts/task_harness.py verify 2026-06-10-013-news-intelligence-governance`
