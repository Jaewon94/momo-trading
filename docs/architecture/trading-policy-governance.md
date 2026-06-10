# Trading Policy Governance

This document defines how trading policy layers should be ordered and reviewed so
new strategy changes do not silently conflict with older controls.

Detailed refactor design:
[Trading Policy Engine Refactor Plan](trading-policy-engine-refactor-plan.md)

Before changing trading policy code, prompts, or runtime settings, use:
[Trading Policy Change Checklist](../workflows/trading-policy-change-checklist.md)

## Policy Priority

1. Hard safety controls
   - Kill switch, account drawdown, broker/session availability, post-liquidation
     buy block, and operator-disabled modes.
   - These controls can block BUY/SELL execution regardless of model output or
     risk appetite.
2. Broker and market constraints
   - Buying power, orderable quantity, tick/price limits, market session rules,
     pending order reconciliation, and provider errors.
   - These controls can reduce quantity or block execution after internal checks.
3. Portfolio risk manager
   - Position cap, order cap, minimum cash policy, risk/reward, volatility sizing,
     daily trade limits, and trading guard warnings.
   - This layer owns final internal quantity reduction before broker checks.
4. Exposure alignment
   - Converts an operator intent such as `RISK_APPETITE=AGGRESSIVE` into a target
     exposure behavior when market regime and confidence allow it.
   - This layer may raise an already-approved BUY quantity, but it must run before
     the risk manager and must not bypass hard safety or broker checks.
5. LLM and deterministic strategy decision
   - Produces BUY/HOLD/SELL intent, confidence, horizon, and initial sizing.
   - Model output is advisory until deterministic policy layers approve it.
6. Scanner and pre-analysis filters
   - Reduce the candidate universe and attach structured evidence for later
     decisions.
   - These filters should not own final portfolio exposure or order sizing.

## Ownership Rules

- Risk appetite is an intent, not a complete policy. It may select limits and
  targets, but a named downstream layer must own each concrete behavior.
- Target exposure belongs to exposure alignment.
- Final internal order size belongs to the risk manager.
- Final executable order size belongs to broker buying-power/orderability checks.
- Holding period and forced-exit behavior belong to holding/exit policy.
- Candidate breadth belongs to scanner policy.
- Any layer that mutates action, quantity, price, horizon, or thresholds must
  emit structured metadata with the previous value, final value, owner layer,
  and reason. Silent mutation is treated as a policy bug.

## Change Protocol

Every change that touches buy/sell thresholds, risk profile behavior, holding
horizon, order placement, end-of-day handling, or broker reconciliation should:

- Name the affected policy owner in the task brief or decision record.
- State whether the change can increase order size, decrease order size, block
  orders, or force/accelerate sells.
- Add or update tests at the policy-owner layer.
- Preserve downstream hard safety checks unless the task explicitly approves a
  protected behavior change.
- Add activity-log or trade-note metadata when a later review would need to know
  why a quantity or action changed.
- When a policy layer mutates a `TradeSignal` directly, its return value must
  still describe the mutation. Callers should not have to infer changes by
  comparing object state before and after the call.
- Keep the policy owner, priority, runtime settings, and focused tests aligned
  with the refactor plan. If a new setting or gate cannot be assigned to an
  owner, treat that as a design gap before implementation.

## Policy Registry

The table below is generated from `strategy/policy/registry.py`; update the
registry first and keep this section in sync.

<!-- POLICY_REGISTRY_START -->
| Priority | Owner | Scope | Description | Key settings | Required tests |
| --- | --- | --- | --- | --- | --- |
| 1 | `admin_safety` | ADMIN | Admin confirmation and protected runtime-operation controls. | - | `tests/api/test_admin_settings_routes.py` |
| 5 | `session_safety` | SESSION | Market-session and off-hours trading controls. | `DAY_TRADING_ONLY`, `BUY_CUTOFF_HOUR`, `BUY_CUTOFF_MINUTE` | `tests/scheduler/test_scheduler_runtime_paths.py` |
| 8 | `scheduler` | SESSION | Scheduler enabled/running state and recurring job controls. | `SCHEDULER_ENABLED`, `INTRADAY_RESCAN_INTERVAL_MIN`, `HORIZON_SCAN_ENABLED`, `HORIZON_SCAN_MID_HOUR`, `HORIZON_SCAN_LONG_DAY_OF_WEEK` | `tests/scheduler/test_scheduler_runtime_paths.py` |
| 10 | `candidate_scoring` | CANDIDATE | Scanner candidate breadth, ranking, and selected-symbol evidence. | `SCANNER_MAX_CANDIDATES`, `HORIZON_SHORT_MAX_CANDIDATES`, `HORIZON_MID_MAX_CANDIDATES`, `HORIZON_LONG_MAX_CANDIDATES`, `HORIZON_MID_NEWS_LOOKBACK_HOURS`, `HORIZON_LONG_DAILY_CANDLE_COUNT` | `tests/strategy/test_horizon_scan_policy.py`, `tests/services/test_candidate_scoring_service.py`, `tests/agent/test_market_scanner.py` |
| 20 | `pre_analysis_gate` | CANDIDATE | Cheap pre-LLM skips for missing data, insufficient cash, and bearish charts. | - | `tests/services/test_pre_analysis_gate_service.py` |
| 30 | `deterministic_tier1_fast_gate` | CANDIDATE | Deterministic LLM avoidance for clear non-buy scan candidates. | `DETERMINISTIC_TIER1_FAST_GATE_MODE`, `DETERMINISTIC_TIER1_FAST_GATE_ENABLED` | `tests/agent/test_trading_agent_cycles.py` |
| 35 | `tier1_analysis` | CANDIDATE | Tier1 LLM prompt/runtime contract and cache behavior. | `TIER1_LLM_TIMEOUT_SEC`, `TIER1_PROVIDER`, `TIER1_MODEL` | `tests/agent/test_trading_agent_cycles.py` |
| 40 | `deterministic_final_gate` | BUY | Tier2-before deterministic validation for confidence, RR, stop loss, and buying power. | - | `tests/services/test_deterministic_final_gate_service.py` |
| 45 | `tier1_cost_gate` | BUY | Pre-Tier2 execution-cost edge gate. | `COST_GATE_ENABLED`, `ESTIMATED_ENTRY_COST_BPS`, `ESTIMATED_EXIT_COST_BPS` | `tests/agent/test_trading_agent_cost_gate.py` |
| 50 | `cost_gate` | BUY | Final BUY execution-cost edge gate. | `COST_GATE_ENABLED`, `MIN_EDGE_TO_COST_RATIO_MID` | `tests/agent/test_trading_agent_cost_gate.py` |
| 55 | `news_gate` | BUY | News-signal negative-pressure BUY gate and rollout mode. | `NEWS_GATE_ENABLED`, `NEWS_GATE_ROLLOUT_MODE`, `NEWS_NEGATIVE_PRESSURE_THRESHOLD` | `tests/agent/test_trading_agent_news_gate.py`, `tests/services/test_news_gate_rollout_service.py` |
| 56 | `news_intel` | CANDIDATE | News polling, enrichment, runtime health, and prompt context evidence. | `NEWS_POLL_ENABLED`, `NEWS_LOOKBACK_HOURS` | `tests/services/test_news_signal_service.py`, `tests/services/test_news_context_service.py` |
| 60 | `exposure_alignment` | BUY | Risk-appetite target exposure sizing floor before risk manager caps. | `AGGRESSIVE_EXPOSURE_ALIGNMENT_ENABLED`, `AGGRESSIVE_TARGET_EXPOSURE_PCT` | `tests/agent/test_trading_agent_cycles.py` |
| 65 | `trading_guard` | BUY | Daily drawdown, account equity, loss streak, expectancy, and runtime kill-switch controls. | `MAX_DAILY_DRAWDOWN_PCT`, `MAX_CONSECUTIVE_LOSSES`, `AUTO_RISK_KILL_SWITCH_ENABLED` | `tests/strategy/test_trading_guard.py` |
| 70 | `risk_manager` | BUY | Final internal sizing caps, RR validation, cash limits, and position limits. | `MAX_DAILY_TRADES`, `MAX_SINGLE_ORDER_KRW`, `MIN_CASH_RATIO`, `MAX_POSITION_PCT` | `tests/strategy/test_risk_manager_enhancements.py` |
| 72 | `scale_in` | BUY | Scale-in eligibility and additional lot sizing constraints. | `SCALE_IN_ENABLED` | `tests/strategy/policy/test_settings_catalog.py` |
| 75 | `holding_review` | HOLDING_EXIT | Scheduled holding review prompts and hold/sell decision context. | `HOLDING_REVIEW_ENABLED` | `tests/scheduler/test_scheduler_runtime_paths.py` |
| 80 | `holding_exit` | HOLDING_EXIT | Stop loss, take profit, min-hold, staged exit, and event-triggered sell policy. | `DEFAULT_STOP_LOSS_PCT_MID`, `DEFAULT_TAKE_PROFIT_PCT_MID` | `tests/strategy/test_position_exit_policy.py`, `tests/agent/test_trading_agent_cycles.py` |
| 85 | `order_reservation` | ORDER_SUBMISSION | In-cycle BUY cash reservation before final order submission. | `ORDER_RESERVATION_ENFORCEMENT` | `tests/agent/test_order_reservation.py`, `tests/agent/test_trading_agent_risk_reservation.py` |
| 90 | `order_submission` | ORDER_SUBMISSION | Final order mode, post-liquidation BUY block, and pending order gates. | `TRADING_ENABLED`, `ORDER_SUBMISSION_MODE`, `POST_LIQUIDATION_BUY_BLOCK_ENABLED` | `tests/agent/test_decision_maker.py`, `tests/core/test_post_liquidation_guard.py` |
| 95 | `broker_reconciliation` | ORDER_SUBMISSION | Broker pending/open-position reconciliation and pending confirm recovery. | `BROKER_PROVIDER` | `tests/scheduler/test_portfolio_sync_job.py`, `tests/scripts/test_check_runtime_integrity.py` |
| 110 | `llm_runtime` | RUNTIME | LLM provider/model runtime selection, cooldown, and health controls. | `TIER1_PROVIDER`, `TIER2_PROVIDER`, `LLM_RUNTIME_COOLDOWN_SEC` | `tests/services/test_runtime_settings_service.py` |
| 111 | `manual_llm_runtime` | RUNTIME | Manual provider/model override runtime controls. | `MANUAL_LLM_PROVIDER`, `MANUAL_LLM_MODEL` | `tests/agent/test_trading_agent_cycles.py` |
| 120 | `recommendation_lifecycle` | RECOMMENDATION | Semi-auto recommendation expiry, approval, and lifecycle controls. | `RECOMMENDATION_EXPIRE_MIN` | `tests/agent/test_decision_maker.py` |
| 130 | `runtime_settings` | RUNTIME | Mutable runtime setting validation and persisted override lifecycle. | - | `tests/api/test_admin_settings_validation.py`, `tests/services/test_runtime_settings_service.py` |
<!-- POLICY_REGISTRY_END -->

## Runtime Settings Review

Runtime settings can outlive code changes. After restart or policy tuning, compare
live runtime settings with intended defaults for:

- risk appetite and dynamic caps
- cash/exposure targets
- daily trade/probation limits
- holding horizon and exit thresholds
- broker/session mode

If live settings conflict with a new policy, prefer an explicit runtime update and
record the source of the override rather than hiding the mismatch in code.

## Conflict Diagnosis Checklist

When behavior looks wrong, inspect the decision path in this order:

1. Was the candidate filtered out before LLM analysis?
2. Did the LLM return BUY/HOLD/SELL and what initial quantity?
3. Did exposure alignment change the BUY quantity?
4. Did the risk manager reduce or block the order?
5. Did cash reservation reduce or block the order within the cycle?
6. Did broker buying power/orderability reduce or block the order?
7. Did execution fail, partially fill, or remain pending?
8. Did runtime settings override the expected code defaults?

The answer should be visible in structured metadata or activity logs. If it is not
visible, observability should be fixed before tuning thresholds again.
