# Balanced Test Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen automated tests around trading orchestration, admin runtime controls, and frontend state logic so regressions are caught before runtime.

**Architecture:** Keep the current fast pytest-based style for backend paths, but add higher-value orchestration tests around `run_cycle`, scheduler job entry points, and admin setting validation. For frontend behavior, extract a few pure state helpers from the large static JS file and test them with a lightweight JS runner instead of trying to browser-test the entire page first.

**Tech Stack:** `pytest`, `pytest-asyncio`, `httpx.AsyncClient`, FastAPI dependency overrides, in-memory SQLite, `monkeypatch`, `vitest`, `jsdom`

---

## File Map

**Existing files to modify**
- `tests/agent/test_decision_maker.py`
- `tests/api/test_admin_settings_routes.py`
- `tests/api/test_admin_layout_routes.py`
- `agent/trading_agent.py`
- `agent/decision_maker.py`
- `api/routes/admin.py`
- `admin/static/js/app.js`

**New test files to create**
- `tests/agent/test_trading_agent_cycles.py`
- `tests/scheduler/test_scheduler_runtime_paths.py`
- `tests/api/test_admin_settings_validation.py`
- `tests/frontend/test_admin_runtime_state.test.js`
- `tests/frontend/test_pane_layout_state.test.js`

**New frontend support files to create**
- `package.json`
- `vitest.config.js`
- `admin/static/js/runtime_state.js`
- `admin/static/js/pane_layout.js`

**Primary production files these tests will exercise**
- `agent/trading_agent.py`
- `scheduler/scheduler.py`
- `agent/decision_maker.py`
- `api/routes/admin.py`
- `admin/static/js/app.js`

---

### Task 1: Cover Trading Agent Cycle Boundaries

**Files:**
- Create: `tests/agent/test_trading_agent_cycles.py`
- Modify: `agent/trading_agent.py`
- Test: `tests/agent/test_trading_agent_cycles.py`

- [ ] **Step 1: Write failing tests for `run_cycle()` boundary behavior**

Cover these cases:
- `_cycle_lock` already held → returns `{"skipped": True, "reason": "cycle_already_running"}`
- 장중 + 매수 마감 이후 + `DAY_TRADING_ONLY=true` → returns `buy_cutoff`
- 장중 → `_run_trading_cycle()` 호출
- 장외 → `_run_after_hours_cycle()` 호출
- `manual_provider_override`가 trading/after-hours 경로로 그대로 전달

Example skeleton:
```python
@pytest.mark.asyncio
async def test_run_cycle_skips_when_cycle_lock_is_held(monkeypatch):
    agent = TradingAgent(...)
    await agent._cycle_lock.acquire()
    try:
        result = await agent.run_cycle()
    finally:
        agent._cycle_lock.release()
    assert result["reason"] == "cycle_already_running"
```

- [ ] **Step 2: Run only the new cycle tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py -v
```

Expected:
- New tests fail first where current behavior is not locked in

- [ ] **Step 3: Patch implementation only if tests expose real behavior drift**

Likely file:
- `agent/trading_agent.py`

Rules:
- Do not refactor unrelated analysis logic
- Keep changes focused on cycle branching and argument forwarding

- [ ] **Step 4: Re-run focused agent tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py -v
```

Expected:
- All cycle and market-data tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_trading_agent_cycles.py tests/agent/test_trading_agent_market_data.py agent/trading_agent.py
git commit -m "test: cover trading agent cycle boundaries"
```

---

### Task 2: Cover Decision Mode Branches and Order Edge Cases

**Files:**
- Modify: `tests/agent/test_decision_maker.py`
- Modify: `agent/decision_maker.py`
- Test: `tests/agent/test_decision_maker.py`

- [ ] **Step 1: Write failing tests for autonomy-mode branching**

Cover these cases:
- `execute()` with `AUTONOMOUS` routes to `_execute_autonomous()`
- `execute()` with `SEMI_AUTO` routes to `_create_recommendation()`
- `suggested_quantity <= 0` returns failure without broker call
- `OrderResult.success=True` but `order_id=""` is treated as non-submitted

Example skeleton:
```python
@pytest.mark.asyncio
async def test_execute_routes_to_recommendation_in_semi_auto(monkeypatch):
    monkeypatch.setattr("agent.decision_maker.settings.AUTONOMY_MODE", "SEMI_AUTO")
    ...
    assert result["mode"] == "SEMI_AUTO"
```

- [ ] **Step 2: Run decision-maker tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py -v
```

Expected:
- New mode/edge-case tests fail first if branch behavior is not explicit enough

- [ ] **Step 3: Tighten implementation only where branching is ambiguous**

Likely file:
- `agent/decision_maker.py`

- [ ] **Step 4: Re-run decision and service-adjacent tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_decision_maker.py tests/services/test_trading_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_decision_maker.py agent/decision_maker.py
git commit -m "test: harden decision mode and order edge cases"
```

---

### Task 3: Add Scheduler Runtime Path Tests

**Files:**
- Create: `tests/scheduler/test_scheduler_runtime_paths.py`
- Modify: `scheduler/scheduler.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`

- [ ] **Step 1: Write failing tests for high-value scheduler entry points**

Cover these cases:
- `start()` returns early when `SCHEDULER_ENABLED=false`
- `start()` is idempotent when already running
- `_market_open_scan()` delegates to `trading_agent.run_cycle()`
- `_intraday_rescan()` skips after buy cutoff in day-trading mode
- `_holdings_check()` returns early outside KRX trading hours

Example skeleton:
```python
@pytest.mark.asyncio
async def test_scheduler_start_skips_when_disabled(monkeypatch):
    scheduler = TradingScheduler()
    monkeypatch.setattr("scheduler.scheduler.settings.SCHEDULER_ENABLED", False)
    await scheduler.start()
    assert scheduler.is_running is False
```

- [ ] **Step 2: Run the scheduler-focused suite**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -v
```

- [ ] **Step 3: Patch scheduler only if tests expose true control-flow gaps**

Likely file:
- `scheduler/scheduler.py`

- [ ] **Step 4: Re-run scheduler and related admin tests**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py tests/api/test_admin_scheduler_routes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/scheduler/test_scheduler_runtime_paths.py scheduler/scheduler.py tests/api/test_admin_scheduler_routes.py
git commit -m "test: cover scheduler runtime paths"
```

---

### Task 4: Add Admin Settings Validation and Error-Path Coverage

**Files:**
- Create: `tests/api/test_admin_settings_validation.py`
- Modify: `tests/api/test_admin_settings_routes.py`
- Modify: `api/routes/admin.py`
- Test: `tests/api/test_admin_settings_validation.py`
- Test: `tests/api/test_admin_settings_routes.py`

- [ ] **Step 1: Write failing validation tests for mutable settings**

Cover these cases:
- unknown keys are ignored cleanly
- invalid provider values do not overwrite existing settings
- invalid `MANUAL_LLM_PROVIDER` does not overwrite existing setting
- empty model values normalize to `DEFAULT`
- invalid numeric values return a clear 400 instead of crashing the route

Example skeleton:
```python
async def test_admin_settings_rejects_invalid_int_value(client):
    response = await client.put("/api/v1/admin/settings", json={"RECOMMENDATION_EXPIRE_MIN": "abc"})
    assert response.status_code == 400
```

- [ ] **Step 2: Run only the admin settings suite**

Run:
```bash
.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/api/test_admin_settings_validation.py -v
```

- [ ] **Step 3: Tighten route parsing and error handling**

Likely file:
- `api/routes/admin.py`

Implementation target:
- wrap type conversion failures and return deterministic client error
- keep existing valid-setting behavior unchanged

- [ ] **Step 4: Re-run adjacent admin suites**

Run:
```bash
.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/api/test_admin_settings_validation.py tests/api/test_admin_mcp_routes.py tests/api/test_admin_manual_actions.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_admin_settings_routes.py tests/api/test_admin_settings_validation.py api/routes/admin.py
git commit -m "test: harden admin settings validation"
```

---

### Task 5: Extract Frontend State Helpers and Test Them

**Files:**
- Create: `package.json`
- Create: `vitest.config.js`
- Create: `admin/static/js/runtime_state.js`
- Create: `admin/static/js/pane_layout.js`
- Create: `tests/frontend/test_admin_runtime_state.test.js`
- Create: `tests/frontend/test_pane_layout_state.test.js`
- Modify: `admin/static/js/app.js`
- Modify: `tests/api/test_admin_layout_routes.py`

- [ ] **Step 1: Introduce a JS test runner**

Add minimal dependencies:
- `vitest`
- `jsdom`

Minimal `package.json` shape:
```json
{
  "private": true,
  "scripts": {
    "test:ui": "vitest run"
  },
  "devDependencies": {
    "jsdom": "^26.0.0",
    "vitest": "^3.0.0"
  }
}
```

- [ ] **Step 2: Extract pure helpers from `app.js`**

Move logic that does not need direct DOM access into:
- `admin/static/js/runtime_state.js`
  - badge/status label selection
  - control-button enable/disable state
- `admin/static/js/pane_layout.js`
  - width clamp
  - collapsed-state resolution
  - `localStorage` payload normalize/restore

- [ ] **Step 3: Write failing JS unit tests**

Cover these cases:
- KIWOOM + `mcp_required=false` → `MCP:불필요`
- KIS + disconnected → `MCP:끊김`
- scheduler enabled/running mismatch message generation
- pane width clamp honors min/max
- invalid saved pane layout falls back to defaults

Example skeleton:
```js
import { clampPaneWidth, normalizeSavedLayout } from "../../admin/static/js/pane_layout.js";
import { describe, expect, test } from "vitest";

test("invalid saved layout falls back to defaults", () => {
  expect(normalizeSavedLayout(null).leftWidth).toBe(320);
});
```

- [ ] **Step 4: Run frontend tests and static checks**

Run:
```bash
pnpm install
pnpm test:ui
node --check admin/static/js/app.js
```

Expected:
- JS unit tests pass
- existing static JS check still passes

- [ ] **Step 5: Re-run admin shell tests**

Run:
```bash
.venv313/bin/python -m pytest tests/api/test_admin_layout_routes.py -v
```

- [ ] **Step 6: Commit**

```bash
git add package.json vitest.config.js admin/static/js/app.js admin/static/js/runtime_state.js admin/static/js/pane_layout.js tests/frontend/test_admin_runtime_state.test.js tests/frontend/test_pane_layout_state.test.js tests/api/test_admin_layout_routes.py
git commit -m "test: add frontend runtime state coverage"
```

---

### Task 6: Add Coverage Reporting for Core Risk Files

**Files:**
- Modify: `package.json`
- Create or Modify: `pytest.ini`
- Create: `scripts/test_core_coverage.sh`

- [ ] **Step 1: Add coverage tooling for Python tests**

Prefer:
- `pytest-cov`

Target files first:
- `agent/trading_agent.py`
- `scheduler/scheduler.py`
- `agent/decision_maker.py`
- `api/routes/admin.py`

- [ ] **Step 2: Add a focused coverage command**

Example:
```bash
.venv313/bin/python -m pytest \
  --cov=agent.trading_agent \
  --cov=scheduler.scheduler \
  --cov=agent.decision_maker \
  --cov=api.routes.admin \
  --cov-report=term-missing
```

- [ ] **Step 3: Set an initial realistic gate**

Start with:
- branch/statement enforcement only for the targeted files
- low but honest floor first, then raise later

Recommended initial threshold:
- `75%` for targeted modules

- [ ] **Step 4: Run the full suite with coverage**

Run:
```bash
.venv313/bin/python -m pytest -q
```

Then:
```bash
scripts/test_core_coverage.sh
```

- [ ] **Step 5: Commit**

```bash
git add package.json pytest.ini scripts/test_core_coverage.sh
git commit -m "chore: add focused coverage gate for core runtime files"
```

---

## Final Verification

- [ ] Run the full Python suite:

```bash
.venv313/bin/python -m pytest -q
```

- [ ] Run frontend unit tests:

```bash
pnpm test:ui
```

- [ ] Run static JS syntax check:

```bash
node --check admin/static/js/app.js
```

- [ ] Confirm the combined result:
- Python tests green
- Frontend tests green
- Coverage script green
- No regression in `/admin` shell route

---

## Notes

- Keep broad refactors out of scope. The point is to make current behavior testable, not redesign the app.
- Extract only pure frontend state helpers first. Do not move DOM-heavy rendering logic unless testability requires it.
- For backend gaps, prefer deterministic unit/integration tests over sleeps, real clocks, or live network.
- When a failing test exposes a real bug, fix the smallest production surface that makes the contract explicit.
