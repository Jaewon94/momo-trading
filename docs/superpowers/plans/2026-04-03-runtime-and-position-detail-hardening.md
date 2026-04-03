# Runtime And Position Detail Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden local runtime operations, fix LLM catalog refresh UX/runtime failure handling, and add a holdings detail modal with per-symbol summary and timeline.

**Architecture:** Keep the existing FastAPI + static-admin architecture, but move more runtime/aggregation logic server-side where the frontend currently has weak visibility. `start.sh` should become a safer operator entrypoint with clear runtime detection, while the new holdings detail feature should use a dedicated API that assembles trade/activity state for a single symbol.

**Tech Stack:** Bash, FastAPI, SQLAlchemy async, static HTML/JS, pytest, vitest

---

### Task 1: Harden `start.sh` runtime detection

**Files:**
- Modify: `scripts/dev/start.sh`
- Test: `tests/scripts/test_start_script.py`

- [ ] **Step 1: Write failing tests**
- [ ] **Step 2: Run `pytest tests/scripts/test_start_script.py -v` and confirm failures**
- [ ] **Step 3: Implement minimal runtime detection**
  - Detect occupied target port before foreground/background start
  - Report a clear conflict message
  - Reorder sidecar sync to run only after start prechecks succeed
  - Improve `status` fallback beyond PID file when possible
- [ ] **Step 4: Re-run `pytest tests/scripts/test_start_script.py -v`**
- [ ] **Step 5: Commit**

### Task 2: Fix LLM catalog refresh error handling

**Files:**
- Modify: `analysis/llm/model_catalog.py`
- Modify: `admin/static/js/app.js`
- Test: `tests/api/test_admin_llm_catalog_routes.py`
- Test: `tests/frontend/test_llm_catalog_state.test.js`

- [ ] **Step 1: Add failing backend/frontend tests for refresh failure and stale fallback states**
- [ ] **Step 2: Run targeted pytest/vitest commands and confirm failures**
- [ ] **Step 3: Implement minimal fixes**
  - Preserve fallback payload semantics on forced refresh failure
  - Surface a clear, non-silent UI state for refresh failure
  - Avoid brittle assumptions in the refresh flow
- [ ] **Step 4: Re-run targeted tests**
- [ ] **Step 5: Commit**

### Task 3: Add holdings detail modal and symbol timeline API

**Files:**
- Modify: `api/routes/admin.py`
- Modify: `admin/static/index.html`
- Modify: `admin/static/js/app.js`
- Create: `admin/static/js/position_detail_state.js`
- Test: `tests/api/test_admin_position_detail_routes.py`
- Test: `tests/frontend/test_position_detail_state.test.js`

- [ ] **Step 1: Add failing API/state tests**
- [ ] **Step 2: Run targeted pytest/vitest commands and confirm failures**
- [ ] **Step 3: Implement minimal backend aggregation**
  - Add a symbol detail endpoint that returns summary cards + timeline events
  - Reuse existing trade/activity data instead of adding duplicate storage
- [ ] **Step 4: Implement minimal frontend modal**
  - Open from right-pane holding click
  - Render summary cards and timeline
  - Provide settings shortcut only
- [ ] **Step 5: Re-run targeted tests**
- [ ] **Step 6: Commit**

### Task 4: End-to-end verification

**Files:**
- Verify only

- [ ] **Step 1: Run backend targeted tests**
  - `pytest tests/scripts/test_start_script.py tests/api/test_admin_llm_catalog_routes.py tests/api/test_admin_position_detail_routes.py -v`
- [ ] **Step 2: Run frontend targeted tests**
  - `npm run test:ui -- tests/frontend/test_position_detail_state.test.js tests/frontend/test_llm_catalog_state.test.js`
- [ ] **Step 3: Manually verify `/admin` flows**
  - settings modal LLM refresh
  - holding click opens detail modal
- [ ] **Step 4: Summarize residual risks**
