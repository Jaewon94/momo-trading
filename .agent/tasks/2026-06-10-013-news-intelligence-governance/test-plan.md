# Test Plan

Task: `2026-06-10-013-news-intelligence-governance`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
.venv313/bin/python -m pytest tests/strategy/test_news_intelligence_policy.py tests/services/test_news_signal_service.py tests/services/test_news_context_service.py tests/agent/test_market_scanner.py tests/strategy/policy/test_policy_registry.py tests/strategy/policy/test_settings_catalog.py -q
.venv313/bin/python -m py_compile agent/market_scanner.py services/news_signal_service.py services/news_context_service.py strategy/news_intelligence_policy.py strategy/policy/registry.py
python scripts/change_harness.py AGENTS.md .agent/project-card.md docs/architecture/news-intelligence-governance.md docs/architecture/trading-policy-governance.md strategy/news_intelligence_policy.py strategy/policy/registry.py services/news_signal_service.py services/news_context_service.py agent/market_scanner.py tests/strategy/test_news_intelligence_policy.py
python scripts/task_harness.py verify 2026-06-10-013-news-intelligence-governance
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirm after-hours LLM research remains disabled by default and cannot place
  orders directly.
- Confirm future news changes are discoverable through policy registry,
  architecture docs, AGENTS.md, and project-card.
