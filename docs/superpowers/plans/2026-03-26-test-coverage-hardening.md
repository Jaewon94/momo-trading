# Test Coverage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen automated test coverage so recent broker-adapter and Kiwoom work is protected by meaningful happy-path, failure-path, and integration-level tests.

**Architecture:** Keep the existing fast unit-test style built on fake adapters and mocked transports, then add a thin integration layer around FastAPI lifespan, scheduler entry points, and realtime/event paths. Prioritize tests that lock in broker-provider behavior differences and catch remaining KIS-direct regressions when `BROKER_PROVIDER=KIWOOM`.

**Tech Stack:** `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, FastAPI dependency overrides, in-memory SQLite test DB, fake broker adapters, `monkeypatch`

---

## File Map

**Existing files to modify**
- `tests/conftest.py`
- `tests/agent/test_decision_maker.py`
- `tests/agent/test_trading_agent_market_data.py`
- `tests/api/test_admin_account_routes.py`

**New test files to create**
- `tests/main/test_lifespan_startup.py`
- `tests/scheduler/test_scheduler_broker_paths.py`
- `tests/realtime/test_realtime_monitor_broker_paths.py`
- `tests/trading/test_kiwoom_constraints.py`
- `tests/trading/test_broker_provider_selection.py`

**Primary production files these tests will exercise**
- `main.py`
- `agent/decision_maker.py`
- `agent/trading_agent.py`
- `scheduler/scheduler.py`
- `realtime/monitor.py`
- `realtime/stream_manager.py`
- `trading/broker_factory.py`
- `trading/adapters/kiwoom_adapter.py`
- `trading/kiwoom_clients.py`

---

### Task 1: Harden Decision/Agent Failure Paths

**Files:**
- Modify: `tests/agent/test_decision_maker.py`
- Modify: `tests/agent/test_trading_agent_market_data.py`
- Test: `tests/agent/test_decision_maker.py`
- Test: `tests/agent/test_trading_agent_market_data.py`

- [ ] **Step 1: Write failing tests for broker failure paths**

Add tests covering:
- `DecisionMaker.confirm_and_record()` when `get_order_status()` returns `None`
- `DecisionMaker.confirm_and_record()` when filled quantity is `0`
- `TradingAgent._build_portfolio_snapshot()` when `balance.is_valid == False`
- `TradingAgent._execute_exit_order()` when holdings are missing

- [ ] **Step 2: Run only the new failing tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_market_data.py -v
```

Expected:
- New tests fail first if behavior is not yet locked in
- Existing tests remain green

- [ ] **Step 3: Adjust implementation only if tests reveal incorrect behavior**

Likely files:
- `agent/decision_maker.py`
- `agent/trading_agent.py`

Rules:
- Do not refactor broadly
- Fix only root-cause behavior exposed by the new tests

- [ ] **Step 4: Re-run the focused agent tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/agent/test_trading_agent_market_data.py -v
```

Expected:
- All focused tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_decision_maker.py tests/agent/test_trading_agent_market_data.py agent/decision_maker.py agent/trading_agent.py
git commit -m "test: harden decision maker and trading agent failure coverage"
```

---

### Task 2: Lock In Kiwoom-Specific Constraints

**Files:**
- Create: `tests/trading/test_kiwoom_constraints.py`
- Test: `tests/trading/test_kiwoom_constraints.py`

- [ ] **Step 1: Write failing tests for explicit Kiwoom limitations**

Cover these behaviors:
- Overseas market quote request returns failure
- Overseas candle request returns failure
- Cancel order returns explicit unsupported message
- Volume/fluctuation rank methods return empty list consistently
- Broker capabilities expose `supports_overseas_stocks=False` and `supports_order_cancellation=False`

- [ ] **Step 2: Run only the new Kiwoom constraint tests**

Run:
```bash
.venv313/bin/python -m pytest tests/trading/test_kiwoom_constraints.py -v
```

Expected:
- Tests fail first if current implementation does not fully match intended contract

- [ ] **Step 3: Fix implementation only where contract is unclear or inconsistent**

Likely files:
- `trading/adapters/kiwoom_adapter.py`
- `trading/kiwoom_clients.py`

- [ ] **Step 4: Re-run all Kiwoom-related tests**

Run:
```bash
.venv313/bin/python -m pytest tests/trading/test_kiwoom_adapter.py tests/trading/test_kiwoom_clients.py tests/trading/test_kiwoom_constraints.py -v
```

Expected:
- All Kiwoom contract tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/trading/test_kiwoom_constraints.py trading/adapters/kiwoom_adapter.py trading/kiwoom_clients.py
git commit -m "test: lock kiwoom broker constraints"
```

---

### Task 3: Add Broker Provider Selection and Lifespan Coverage

**Files:**
- Create: `tests/trading/test_broker_provider_selection.py`
- Create: `tests/main/test_lifespan_startup.py`
- Modify: `tests/conftest.py`
- Test: `tests/trading/test_broker_provider_selection.py`
- Test: `tests/main/test_lifespan_startup.py`

- [ ] **Step 1: Write failing provider-selection tests**

Cover:
- `BROKER_PROVIDER=KIWOOM` selects `KiwoomBrokerAdapter`
- `BROKER_PROVIDER=KIS` selects `KisBrokerAdapter`
- Invalid provider config raises cleanly
- Cached singleton is reset safely between tests

- [ ] **Step 2: Write failing lifespan tests**

Cover:
- App startup does not crash when MCP connection fails
- App startup under `BROKER_PROVIDER=KIWOOM` still completes lifespan when KIS MCP is unavailable
- Shutdown path calls disconnect/stop handlers cleanly

- [ ] **Step 3: Run the new focused tests**

Run:
```bash
.venv313/bin/python -m pytest tests/trading/test_broker_provider_selection.py tests/main/test_lifespan_startup.py -v
```

Expected:
- Tests fail first where startup/provider assumptions are still KIS-biased

- [ ] **Step 4: Patch startup/provider code minimally if needed**

Likely files:
- `main.py`
- `trading/broker_factory.py`
- `tests/conftest.py`

- [ ] **Step 5: Re-run the focused suite**

Run:
```bash
.venv313/bin/python -m pytest tests/trading/test_broker_provider_selection.py tests/main/test_lifespan_startup.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tests/trading/test_broker_provider_selection.py tests/main/test_lifespan_startup.py tests/conftest.py main.py trading/broker_factory.py
git commit -m "test: add provider selection and app lifespan coverage"
```

---

### Task 4: Cover Scheduler Broker Paths

**Files:**
- Create: `tests/scheduler/test_scheduler_broker_paths.py`
- Test: `tests/scheduler/test_scheduler_broker_paths.py`

- [ ] **Step 1: Write failing scheduler entry-point tests**

Target only a few high-value flows first:
- Balance/holding-dependent scheduler path uses broker abstraction
- Scheduler path does not crash when broker balance lookup fails
- Kiwoom provider path avoids assuming KIS-only realtime/order helpers where not supported

- [ ] **Step 2: Run the scheduler-focused tests**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_broker_paths.py -v
```

- [ ] **Step 3: Fix code only if a true KIS direct dependency blocks the tested path**

Likely file:
- `scheduler/scheduler.py`

- [ ] **Step 4: Re-run scheduler tests and nearby service tests**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_broker_paths.py tests/services/test_broker_smoke_service.py tests/services/test_trading_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/scheduler/test_scheduler_broker_paths.py scheduler/scheduler.py
git commit -m "test: cover scheduler broker paths"
```

---

### Task 5: Cover Realtime and Admin Runtime Gaps

**Files:**
- Create: `tests/realtime/test_realtime_monitor_broker_paths.py`
- Modify: `tests/api/test_admin_account_routes.py`
- Test: `tests/realtime/test_realtime_monitor_broker_paths.py`
- Test: `tests/api/test_admin_account_routes.py`

- [ ] **Step 1: Write failing realtime tests**

Cover:
- Realtime monitor uses broker-backed holdings snapshot correctly
- Realtime monitor handles broker lookup failure without crashing event processing
- Kiwoom mode does not silently rely on KIS websocket-only assumptions for quote enrichment

- [ ] **Step 2: Add admin route negative tests**

Cover:
- Broker adapter raises exception
- Empty holdings / empty pending orders
- Invalid balance response

- [ ] **Step 3: Run realtime and admin-focused tests**

Run:
```bash
.venv313/bin/python -m pytest tests/realtime/test_realtime_monitor_broker_paths.py tests/api/test_admin_account_routes.py -v
```

- [ ] **Step 4: Fix production code only if tests expose uncaught runtime assumptions**

Likely files:
- `realtime/monitor.py`
- `api/routes/admin.py`

- [ ] **Step 5: Commit**

```bash
git add tests/realtime/test_realtime_monitor_broker_paths.py tests/api/test_admin_account_routes.py realtime/monitor.py api/routes/admin.py
git commit -m "test: add realtime and admin runtime coverage"
```

---

### Task 6: Full Verification Pass

**Files:**
- Test: `tests/`

- [ ] **Step 1: Run the full test suite**

Run:
```bash
.venv313/bin/python -m pytest tests/ -v
```

Expected:
- Full suite passes

- [ ] **Step 2: Run a Kiwoom provider smoke verification**

Run:
```bash
BROKER_PROVIDER=KIWOOM .venv313/bin/python -c 'from trading.broker_factory import get_broker_adapter; a=get_broker_adapter(); print(type(a).__name__, a.provider.value)'
```

Expected:
- `KiwoomBrokerAdapter KIWOOM`

- [ ] **Step 3: Review coverage gaps still intentionally left open**

Document any remaining untested areas:
- Live broker network integration
- Docker/KIS MCP runtime path
- End-to-end realtime websocket integration

- [ ] **Step 4: Final commit**

```bash
git add tests docs/superpowers/plans/2026-03-26-test-coverage-hardening.md
git commit -m "docs: add test coverage hardening plan"
```

---

## Notes for Execution

- Keep unit tests fast; prefer fake adapters over real network access.
- When adding integration tests around FastAPI lifespan, patch side effects aggressively so startup does not touch live broker endpoints.
- Prefer one missing behavior per test.
- If a test reveals that current implementation is still KIS-specific, fix the narrowest production seam instead of broad refactoring.
- Do not delete existing tests unless they are redundant and replaced by a stronger one in the same commit.
