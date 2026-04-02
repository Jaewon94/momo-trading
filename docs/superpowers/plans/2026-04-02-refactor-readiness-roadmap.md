# Refactor Readiness Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the highest-value regression tests needed to refactor the trading runtime safely, then execute refactors in small verified slices instead of chasing exhaustive full-product coverage first.

**Architecture:** Keep strengthening behavior-focused tests around the orchestration seams that are about to change, not every internal method in the system. Use the current test gains as the safety net, raise `scheduler` and `trading_agent` confidence a bit more, then refactor one boundary at a time with fresh verification after each slice.

**Tech Stack:** `pytest`, `pytest-asyncio`, `monkeypatch`, async fakes, `loguru`, existing FastAPI/JS test setup, branch `jaewon-ver`

---

## File Map

**Existing files to modify**
- `tests/scheduler/test_scheduler_runtime_paths.py`
- `tests/agent/test_trading_agent_cycles.py`
- `scheduler/scheduler.py`
- `agent/trading_agent.py`
- `docs/superpowers/plans/2026-04-02-refactor-readiness-roadmap.md`

**Existing files likely to inspect while refactoring**
- `tests/agent/test_decision_maker.py`
- `tests/trading/test_kiwoom_constraints.py`
- `tests/trading/test_mcp_client.py`
- `realtime/event_detector.py`
- `trading/account_manager.py`

**Current verified baseline**
- `tests/` full suite: `173 passed`
- `agent/decision_maker.py`: `96%`
- `scheduler/scheduler.py`: `70%`
- Remaining large refactor risk: startup/bootstrap, pre-market orchestration, holdings-check edge paths, and `trading_agent` orchestration seams

---

### Task 1: Finish Scheduler Refactor Safety Net

**Files:**
- Modify: `tests/scheduler/test_scheduler_runtime_paths.py`
- Test: `tests/scheduler/test_scheduler_runtime_paths.py`
- Optional modify only if behavior bug is exposed: `scheduler/scheduler.py`

- [ ] **Step 1: Write failing tests for startup/bootstrap and pre-market paths**

Cover these cases:
- `_on_startup()` during trading hours schedules `_market_open_scan()`
- `_on_startup()` outside trading hours schedules `_post_market_if_needed()`
- `_setup_jobs()` registers the expected job ids
- `_pre_market()` skips on holiday and logs the reason
- `_pre_market()` sets daily start balance, loads yesterday lessons, runs overnight restore in swing mode, and applies active trading rules

- [ ] **Step 2: Run only the new scheduler tests**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
```

Expected:
- New tests fail first if a branch is not yet protected or if mocks need to be tightened

- [ ] **Step 3: Patch scheduler only if a real behavior gap is exposed**

Rules:
- No broad scheduler refactor in this task
- Keep any production patch branch-local and behavior-preserving

- [ ] **Step 4: Re-run scheduler suite and targeted coverage**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
.venv313/bin/python -m pytest tests/ -q --cov=scheduler.scheduler --cov-report=term-missing
```

- [ ] **Step 5: Commit**

```bash
git add tests/scheduler/test_scheduler_runtime_paths.py scheduler/scheduler.py
git commit -m "test: finish scheduler refactor safety net"
```

---

### Task 2: Add Trading Agent Characterization Tests Before Refactor

**Files:**
- Modify: `tests/agent/test_trading_agent_cycles.py`
- Optional create if needed: `tests/agent/test_trading_agent_runtime_paths.py`
- Test: `tests/agent/test_trading_agent_cycles.py`
- Optional modify only if test exposes drift: `agent/trading_agent.py`

- [ ] **Step 1: Write failing tests for orchestration seams we plan to refactor**

Cover these cases:
- `run_cycle()` lock, buy cutoff, trading-hours branch, after-hours branch, provider override forwarding
- `_run_trading_cycle()` returns early on account snapshot failure
- no selected candidates ends the cycle cleanly
- symbol-name cache and threshold application happen from scan results
- `_run_after_hours_cycle()` stays behaviorally stable for the current LLM/review entry point

- [ ] **Step 2: Run trading-agent focused tests**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py -q
```

- [ ] **Step 3: Patch only if tests expose true drift**

- [ ] **Step 4: Re-run focused agent verification**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py tests/agent/test_decision_maker.py -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_trading_agent_cycles.py tests/agent/test_decision_maker.py agent/trading_agent.py
git commit -m "test: add trading agent refactor characterization"
```

---

### Task 3: Refactor Scheduler in Small Slices

**Files:**
- Modify: `scheduler/scheduler.py`
- Modify: `tests/scheduler/test_scheduler_runtime_paths.py`

- [ ] **Step 1: Extract startup/pre-market helper boundaries without changing behavior**

Likely helpers:
- startup dispatch
- pre-market review/rule application
- subscription refresh helper reuse

- [ ] **Step 2: Run scheduler tests immediately after each slice**

Run:
```bash
.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q
```

- [ ] **Step 3: Run full suite after the slice stabilizes**

Run:
```bash
.venv313/bin/python -m pytest tests/ -q
```

- [ ] **Step 4: Commit the slice**

```bash
git add scheduler/scheduler.py tests/scheduler/test_scheduler_runtime_paths.py
git commit -m "refactor: split scheduler orchestration helpers"
```

---

### Task 4: Refactor Trading Agent in Small Slices

**Files:**
- Modify: `agent/trading_agent.py`
- Modify: `tests/agent/test_trading_agent_cycles.py`

- [ ] **Step 1: Extract one orchestration concern at a time**

Recommended order:
- portfolio snapshot / buy-block gate
- scan result normalization
- cycle result assembly / logging
- after-hours review entry

- [ ] **Step 2: Re-run focused agent tests after each extraction**

Run:
```bash
.venv313/bin/python -m pytest tests/agent/test_trading_agent_cycles.py tests/agent/test_decision_maker.py -q
```

- [ ] **Step 3: Re-run full suite before closing the task**

Run:
```bash
.venv313/bin/python -m pytest tests/ -q
```

- [ ] **Step 4: Commit the slice**

```bash
git add agent/trading_agent.py tests/agent/test_trading_agent_cycles.py
git commit -m "refactor: isolate trading agent cycle orchestration"
```

---

### Task 5: Final Refactor Readiness Verification

**Files:**
- Modify if needed: `docs/superpowers/plans/2026-04-02-refactor-readiness-roadmap.md`

- [ ] **Step 1: Run full verification**

Run:
```bash
.venv313/bin/python -m pytest tests/ -q
.venv313/bin/python -m pytest tests/ -q --cov=agent.decision_maker --cov=scheduler.scheduler --cov=agent.trading_agent --cov-report=term-missing
pnpm test:ui
```

- [ ] **Step 2: Record the ready-to-refactor baseline**

Capture:
- pass count
- warning count
- module coverage for `scheduler`, `trading_agent`, `decision_maker`
- any intentionally deferred integration gaps

- [ ] **Step 3: Commit docs/status update if needed**

```bash
git add docs/superpowers/plans/2026-04-02-refactor-readiness-roadmap.md
git commit -m "docs: record refactor readiness baseline"
```
