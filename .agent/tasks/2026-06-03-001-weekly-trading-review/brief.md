# Brief

## Metadata

- Task ID: `2026-06-03-001-weekly-trading-review`
- Created: `2026-06-03T17:06:40+09:00`
- Repo: `momo-trading`
- Title: Review weekly trading behavior

## Goal

Analyze this week trading/runtime behavior for unintended settings, abnormal trades, and fix candidates

## Scope

In scope:

- Review local runtime DB and logs for 2026-06-01 through 2026-06-06 KST.
- Identify unintended settings, abnormal trade lifecycle behavior, report/data quality gaps, and candidate fixes.
- Keep findings operational; no broker commands, DB reset, order placement, or migration.

Out of scope:

- Unrelated trading behavior changes.
- DB reset, migration, deploy, broker-affecting command unless separately approved.

## Constraints

- Preserve unrelated dirty worktree changes.
- Keep broker and runtime safety boundaries explicit.

## Research Gate

Sources checked:

- `.agent/project-card.md`
- `.agent/current-task.json`
- `runtime/data/app.db` read-only SQLite queries
- `runtime/logs/momo-trading.log` tail/DB-backed activity and error tables
- `services/daily_report_service.py`
- `repositories/trade_result_repository.py`
- `scheduler/scheduler.py`
- `agent/decision_maker.py`

Plan implications:

- Adopt: Treat `trade_results` as the active order/position lifecycle source; `orders` is legacy and currently empty.
- Adopt: Treat 2026-06-03 Samsung decision events as test contamination, not live trading, because they match test fixture values and have no corresponding activity or trade records.
- Defer: Any cleanup of production DB test rows until explicit user approval.
- Reject: Judging weekly trading purely from `daily_reports.total_pnl`; it disagrees with confirmed trade rows and account snapshots.

## Findings

- Runtime settings currently persisted in DB are aggressive/autonomous: `TRADING_ENABLED=true`, `AUTONOMY_MODE=AUTONOMOUS`, `ORDER_SUBMISSION_MODE=FULL`, `SCHEDULER_ENABLED=true`, `RISK_APPETITE=AGGRESSIVE`. These override safer `.env` values.
- 2026-06-01 confirmed closed BUY PnL from `trade_results`: +520,250 KRW when including the overnight gap-check close; account snapshot total asset delta was -787,272 KRW. Stored daily report PnL is +520,250 but its review text says individual trade PnL was unavailable.
- 2026-06-02 confirmed closed BUY PnL from `trade_results`: -208,570 KRW if neutral reconciliation close is excluded; account snapshot total asset delta was -60,460 KRW.
- `trade_results` contains repeated `CONFIRM_FAILED` and `TRADE_RESULT_MISSING` patterns:
  - 2026-06-01 `058970` had partial/stale BUY confirmation and repeated holdings review required metrics.
  - 2026-06-02 `475400` had partial/stale BUY confirmation and repeated holdings review required metrics.
  - `036930` decision quantity was 50, but broker-confirmed/recorded position quantity became 23, then generated a neutral `BROKER_HOLDING_QUANTITY_MISMATCH` close for 16 shares.
- 2026-06-03 decision events for `005930` use fixture-like values (`ORD-1`, `ORD-PENDING`, `analysis-123`) and no `agent_activity_logs` or `trade_results` records exist for that window.
- News polling had repeated handled partial errors on 2026-06-01 and 2026-06-02, mostly DART/KRX/YONHAP timeouts plus one YONHAP date parse error.
- LLM calls generally succeeded, but activity logs show several transient Claude API/Codex timeout failures.
- 2026-06-04 broker ledger repair cleared the previously open `004060` SG Global mismatch with a neutral close. Current 7-day lifecycle integrity is OK: pending confirms 0, broker/db pending mismatch 0, broker-missing open BUY 0, broker-untracked holdings 0.
- 2026-06-01 through 2026-06-05 daily reports sum to +294,500 KRW, while the 7-day performance summary reports +290,900 KRW. The 3,600 KRW difference appears tied to 2026-06-02 closed trade inclusion/exclusion, so report and performance summary still need one canonical PnL source.
- Current account state on 2026-06-06 is no exposure: total asset/cash 472,669,543 KRW, stock value 0, holdings 0, pending orders 0. Today's session metrics are unavailable because it is outside a trading session/holiday context.
- The week was profitable on closed-trade performance summary (+290,900 KRW gross, +152,446 KRW estimated net after costs, PF 1.255), but rollout status remains `ROLLBACK` because max drawdown (-533,030 KRW) exceeded the -500,000 KRW threshold and news-enriched comparison was negative.
- Confirm-failed rows remain as historical closed states: 10 total in the 7-day lifecycle window. Current reconciliation is clean, but 2026-06-01/02/05 stale BUY pending patterns blocked later orders and should be treated as a fix candidate.
- Additional fixture-like `decision_events` contamination exists on 2026-06-04: repeated `005930` rows with confidence 0 and reasons such as `ORDER_SUBMISSION_MODE=READ_ONLY`, `SELL_ONLY`, `ORD-PENDING`, and invalid quantity. These rows do not appear in `trade_results` or broker reconciliation, but can pollute decision benchmarks.
- A 2026-06-05 schedule warning reported an inverted Pre-LLM indicator: `fast_gate_score` Spearman IC -0.8966 over n=13. This should not trigger an immediate trading change from one small sample, but it is a review item before relying on the fast gate as a positive rank signal.

## Completion Criteria

- Findings and fix candidates are documented.
- No protected broker/DB mutation is performed.
- Harness checks pass.

## Verification Plan

- `python scripts/check_task_harness.py --strict-current`
- Read-only `sqlite3 runtime/data/app.db ...` queries for trade/report/settings/activity/error tables.
