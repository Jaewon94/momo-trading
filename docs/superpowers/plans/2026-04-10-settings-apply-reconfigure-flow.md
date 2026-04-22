# Settings Apply Reconfigure Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-control autosave in the admin settings modal with a draft-and-apply flow that pauses new runtime work, waits briefly for in-flight analysis to drain, applies settings atomically, then resumes with the new configuration.

**Architecture:** Keep immediate runtime control buttons separate from the modal form. Add a dedicated runtime reconfiguration service that owns the apply lock, quiesce/restart sequence, and operator-facing result payload. On the frontend, track unsaved draft values locally, render a sticky save/reset bar, and show explicit “saving / applying / resumed” status instead of silently mutating the live runtime on each field change.

**Tech Stack:** FastAPI, SQLAlchemy async, APScheduler, vanilla JS admin UI, pytest, vitest

## Status Update (2026-04-10)

- Implemented:
  - `POST /api/v1/admin/settings/apply`
  - `RuntimeReconfigurationService` apply lock and scheduler quiesce/restart flow
  - atomic runtime setting coercion/persistence path
  - trading agent reconfiguration guard and idle wait helper
  - LLM runtime reset on apply
  - admin modal draft/save/reset UX with disabled state during apply
- Verified:
  - targeted backend: `36 passed`
  - full backend: `488 passed`
  - full frontend: `115 passed`
  - `node --check admin/static/js/app.js`
  - live runtime apply returned `200 OK` and persisted the requested settings
- Operator-visible behavior:
  - save button changes to `저장 중...`
  - modal controls, tabs, close button, and footer actions are disabled while apply is in flight
  - save completes with the new server-side settings loaded back into the form state
- Residual risk:
  - the current backend waits up to `idle_timeout_sec=60` for the agent to go idle, then applies anyway
  - result payload may therefore report `agent_idle=false` even on success
  - unchanged values included in the payload can still appear under `changed`

---

### Task 1: Add backend apply-orchestrator contract

**Files:**
- Create: `services/runtime_reconfiguration_service.py`
- Modify: `services/runtime_settings_service.py`
- Test: `tests/services/test_runtime_reconfiguration_service.py`

- [x] **Step 1: Write failing service tests**
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/services/test_runtime_reconfiguration_service.py -q` and confirm failures**
- [x] **Step 3: Implement atomic validation/update orchestration and quiesce flow**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/services/test_runtime_reconfiguration_service.py -q`**

### Task 2: Expose apply endpoint and runtime guards

**Files:**
- Modify: `api/routes/admin.py`
- Modify: `agent/trading_agent.py`
- Modify: `scheduler/scheduler.py`
- Modify: `tests/api/test_admin_settings_routes.py`
- Modify: `tests/agent/test_trading_agent_cycles.py`

- [x] **Step 1: Add failing API and agent-guard tests**
- [x] **Step 2: Run `/.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/agent/test_trading_agent_cycles.py -q` and confirm failures**
- [x] **Step 3: Implement `/api/v1/admin/settings/apply` and reconfiguration skip guards**
- [x] **Step 4: Re-run `/.venv313/bin/python -m pytest tests/api/test_admin_settings_routes.py tests/agent/test_trading_agent_cycles.py -q`**

### Task 3: Add draft/save frontend state

**Files:**
- Create: `admin/static/js/settings_apply_state.js`
- Modify: `admin/static/js/settings_action_state.js`
- Modify: `admin/static/js/app.js`
- Modify: `admin/static/index.html`
- Test: `tests/frontend/test_settings_apply_state.test.js`
- Modify: `tests/frontend/test_settings_action_state.test.js`

- [x] **Step 1: Add failing frontend state tests for draft tracking, dirty counting, and saving copy**
- [x] **Step 2: Run `pnpm test:ui -- tests/frontend/test_settings_apply_state.test.js tests/frontend/test_settings_action_state.test.js` and confirm failures**
- [x] **Step 3: Implement local draft state, save/reset controls, and applying UX**
- [x] **Step 4: Re-run `pnpm test:ui -- tests/frontend/test_settings_apply_state.test.js tests/frontend/test_settings_action_state.test.js`**

### Task 4: Verify operator-visible behavior

**Files:**
- Verify only

- [x] **Step 1: Run targeted backend tests**
  - `/.venv313/bin/python -m pytest tests/services/test_runtime_reconfiguration_service.py tests/api/test_admin_settings_routes.py tests/agent/test_trading_agent_cycles.py -q`
- [x] **Step 2: Run targeted frontend tests**
  - `pnpm test:ui -- tests/frontend/test_settings_apply_state.test.js tests/frontend/test_settings_action_state.test.js`
- [x] **Step 3: Run full backend suite**
  - `/.venv313/bin/python -m pytest -q`
- [x] **Step 4: Run full frontend suite**
  - `pnpm test:ui`
- [x] **Step 5: Summarize UX during apply**
  - Save button label while request is in flight: `저장 중...`
  - Form controls, modal tabs, close button, reset/save actions are disabled
  - Successful apply reloads server-side settings into the form; failure leaves the draft intact for retry
