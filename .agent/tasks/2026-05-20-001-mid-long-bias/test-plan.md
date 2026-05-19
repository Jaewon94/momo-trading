# Test Plan

Task: `2026-05-20-001-mid-long-bias`

## Commands

```bash
python scripts/check_task_harness.py --strict-current
python -m py_compile strategy/trade_horizon.py services/candidate_scoring_service.py services/deterministic_prompt_context_service.py strategy/stable_short.py strategy/aggressive_short.py strategy/base.py strategy/holding_policy.py core/config.py services/holdings_precheck_service.py agent/trading_agent.py scheduler/scheduler.py
.venv313/bin/python -m pytest tests/strategy/test_trade_horizon.py tests/services/test_candidate_scoring_service.py tests/strategy/test_strategy_profiles.py tests/services/test_holdings_precheck_service.py -q
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py tests/scheduler/test_scheduler_runtime_paths.py -q
git diff --check
python scripts/check_runtime_integrity.py --days 7
```

## Results

- py_compile changed modules: passed.
- Focused horizon/scoring/profile/holding tests: `21 passed`.
- Agent cycle and scheduler regression tests: `113 passed`.
- `python scripts/check_task_harness.py --strict-current`: passed.
- `git diff --check`: passed.
- Runtime restart: passed, PID `31799`.
- Runtime hold-day settings after `.env` update: SHORT `5`, MID `15`, LONG `30`, STABLE `15`, AGGRESSIVE `10`.
- Runtime integrity after restart: passed.

## Manual Checks

- Confirm protected operations were not run without approval.
- Confirm task-specific behavior is covered by focused tests or documented as manual verification.
- Confirmed no broker order placement, liquidation, DB reset, or schema migration was run.
