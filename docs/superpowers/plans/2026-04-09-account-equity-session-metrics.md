# Account Equity Session Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist trading-day baseline and intraday account equity snapshots, expose session metrics through the admin balance API, and update the admin right pane to show day-session asset and PnL movement clearly.

**Architecture:** Add a dedicated account-equity persistence slice with focused models, repositories, and a service that computes session metrics from broker state plus persisted snapshots. Keep rendering logic thin by having the backend return enriched session metrics and letting the frontend only format them.

**Tech Stack:** FastAPI, SQLAlchemy async, APScheduler, static HTML/JS, pytest, vitest

## Status Update (2026-04-10)

- Implemented in code:
  - `models/account_day_baseline.py`
  - `models/account_equity_snapshot.py`
  - `repositories/account_day_baseline_repository.py`
  - `repositories/account_equity_snapshot_repository.py`
  - `services/account_equity_service.py`
  - `api/routes/admin.py`
  - `scheduler/scheduler.py`
  - `admin/static/js/trade_state.js`
  - `admin/static/js/app.js`
- Migration added:
  - `alembic/versions/d204f5a8b1c7_add_account_equity_session_tables.py`
- Test coverage added:
  - `tests/services/test_account_equity_service.py`
  - `tests/api/test_admin_account_routes.py`
  - `tests/scheduler/test_scheduler_runtime_paths.py`
  - `tests/frontend/test_trade_state.test.js`
- Latest full verification on this branch:
  - backend: `/.venv313/bin/python -m pytest -q` -> `483 passed`
  - frontend: `pnpm test:ui` -> `110 passed`
- Residual risk:
  - `session_metrics` can be stale after the market close until the next snapshot/baseline refresh window.

---

### Task 1: Add persistence models and repositories

**Files:**
- Create: `models/account_day_baseline.py`
- Create: `models/account_equity_snapshot.py`
- Modify: `models/__init__.py`
- Create: `repositories/account_day_baseline_repository.py`
- Create: `repositories/account_equity_snapshot_repository.py`
- Create: `alembic/versions/<new_revision>_add_account_equity_session_tables.py`
- Test: `tests/services/test_account_equity_service.py`

- [x] **Step 1: Write the failing repository/service tests**
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/services/test_account_equity_service.py -q` and confirm failures**
- [x] **Step 3: Add the new SQLAlchemy models and repositories**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/services/test_account_equity_service.py -q`**

### Task 2: Implement account equity service with baseline and session metric calculation

**Files:**
- Create: `services/account_equity_service.py`
- Test: `tests/services/test_account_equity_service.py`

- [x] **Step 1: Add failing tests for**
  - baseline creation once per day
  - snapshot persistence
  - intraday high/low aggregation
  - `asset_delta` and `daily_unrealized_delta`
  - baseline-missing fallback
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/services/test_account_equity_service.py -q` and confirm failures**
- [x] **Step 3: Implement the minimal service**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/services/test_account_equity_service.py -q`**

### Task 3: Extend admin balance API

**Files:**
- Modify: `api/routes/admin.py`
- Modify: `tests/api/test_admin_account_routes.py`

- [x] **Step 1: Add failing API tests for enriched `session_metrics` and graceful fallback**
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/api/test_admin_account_routes.py -q` and confirm failures**
- [x] **Step 3: Implement minimal API integration using `account_equity_service`**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/api/test_admin_account_routes.py -q`**

### Task 4: Add scheduler integration for baseline and snapshots

**Files:**
- Modify: `scheduler/scheduler.py`
- Modify: `tests/scheduler/test_scheduler_runtime_paths.py`
- Test: `tests/services/test_account_equity_service.py`

- [x] **Step 1: Add failing scheduler tests for pre-market baseline sync and intraday snapshot job registration**
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q` and confirm failures**
- [x] **Step 3: Implement minimal scheduler wiring**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/scheduler/test_scheduler_runtime_paths.py -q`**

### Task 5: Update frontend quick stats state and rendering

**Files:**
- Modify: `admin/static/js/trade_state.js`
- Modify: `admin/static/js/app.js`
- Modify: `tests/frontend/test_trade_state.test.js`

- [x] **Step 1: Add failing frontend state tests for session metrics, daily unrealized delta, and fallback labels**
- [x] **Step 2: Run `pnpm test:ui -- tests/frontend/test_trade_state.test.js` and confirm failures**
- [x] **Step 3: Implement minimal frontend formatting/rendering changes**
- [x] **Step 4: Re-run `pnpm test:ui -- tests/frontend/test_trade_state.test.js`**

### Task 6: End-to-end verification

**Files:**
- Verify only

- [x] **Step 1: Run targeted backend tests**
  - `/.venv313/bin/python -m pytest tests/services/test_account_equity_service.py tests/api/test_admin_account_routes.py tests/scheduler/test_scheduler_runtime_paths.py -q`
- [x] **Step 2: Run targeted frontend tests**
  - `pnpm test:ui -- tests/frontend/test_trade_state.test.js`
- [x] **Step 3: Run full backend suite**
  - `/.venv313/bin/python -m pytest -q`
- [x] **Step 4: Run full frontend suite**
  - `pnpm test:ui`
- [x] **Step 5: Summarize residual risks**
