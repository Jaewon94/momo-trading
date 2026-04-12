# Position Detail Timeline Label Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock down the position-detail API contract so closed BUY lots never regress back to misleading buy-filled labels.

**Architecture:** Keep the backend position-detail timeline as the source of truth for archived BUY execution labels. Add API regression tests for partial-close and final-close BUY lots, then make only the minimal route changes needed to satisfy those tests. Frontend state remains render-focused and continues to prefer `trade_state_*` fields from the API.

**Tech Stack:** FastAPI, Python 3.13, pytest, vanilla JS

---

## File Structure

- Add: `docs/superpowers/specs/2026-04-10-position-detail-timeline-label-hardening-design.md`
  - Narrow design doc for the timeline-label hardening scope.
- Create: `docs/superpowers/plans/2026-04-10-position-detail-timeline-label-hardening.md`
  - Execution plan for the API-only hardening pass.
- Modify: `tests/api/test_admin_position_detail_routes.py`
  - Add API regression coverage for closed BUY lot label normalization.
- Modify: `api/routes/admin.py`
  - Keep `_build_position_timeline()` consistent for closed BUY partial/final exit cases.

### Task 1: Add failing API regression coverage

**Files:**
- Modify: `tests/api/test_admin_position_detail_routes.py`

- [ ] **Step 1: Add failing tests for closed BUY partial-exit and final-close timeline labels**

```python
assert payload["timeline"][0]["title"] == "부분 매도 후 정리"
assert payload["timeline"][0]["detail"]["trade_state_kind_label"] == "부분 매도 후 정리"
assert payload["timeline"][0]["detail"]["trade_state_detail_label"] == "잔량 2주 보유 중"

assert payload["timeline"][0]["title"] == "최종 청산 lot"
assert payload["timeline"][0]["detail"]["trade_state_kind_label"] == "최종 청산 lot"
assert payload["timeline"][0]["detail"]["trade_state_detail_label"] == "전체 수량 청산 완료"
```

- [ ] **Step 2: Run the targeted route tests to verify they fail for the intended reason**

Run: `.venv313/bin/python -m pytest tests/api/test_admin_position_detail_routes.py -q`
Expected: FAIL only if the backend route does not consistently emit the archived BUY labels.

### Task 2: Apply the minimal route fix

**Files:**
- Modify: `api/routes/admin.py`

- [ ] **Step 1: Keep `_build_position_timeline()` aligned with the closed BUY lot contract**

Implementation notes:
- `side == "BUY"` and `has_exit` with `fill_type == "PARTIAL_EXIT"` or `remaining_open_quantity > 0` must emit `부분 매도 후 정리`.
- `side == "BUY"` and `has_exit` without partial-exit evidence must emit `최종 청산 lot`.
- Preserve existing SELL and pending behavior unchanged.

- [ ] **Step 2: Re-run the targeted route tests**

Run: `.venv313/bin/python -m pytest tests/api/test_admin_position_detail_routes.py -q`
Expected: PASS

### Task 3: Verify no frontend regression in timeline interpretation

**Files:**
- Verify: `tests/frontend/test_position_detail_state.test.js`

- [ ] **Step 1: Run the relevant frontend timeline tests**

Run: `pnpm test:ui -- tests/frontend/test_position_detail_state.test.js`
Expected: PASS

- [ ] **Step 2: Summarize residual follow-ups**

Residual follow-ups:
- Trade-history cards and other surfaces still use adjacent state logic and may need a later unification pass.
- This task intentionally hardens only the position-detail API contract.
