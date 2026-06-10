# Test Plan

Task: `2026-06-10-002-policy-governance-refactor`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python scripts/check_markdown_links.py AGENTS.md .agent docs/architecture docs/workflows/code-commit-harness.md
python scripts/check_docs_consistency.py
python scripts/task_harness.py verify 2026-06-10-002-policy-governance-refactor
```

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Re-read the created refactor plan against current code owners:
  `agent/market_scanner.py`, `agent/trading_agent.py`,
  `agent/decision_maker.py`, `strategy/risk_manager.py`,
  `strategy/trading_guard.py`, `strategy/position_exit_policy.py`,
  `strategy/holding_policy.py`, `core/runtime_settings.py`.
- Confirm this task does not change broker actions, runtime DB, order placement,
  liquidation behavior, or live runtime settings.
