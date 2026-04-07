# Pending Buy Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 자동 매수 전에 같은 종목의 기존 미체결 매수가 있으면 신규 주문을 차단한다.

**Architecture:** 자동 주문 진입점인 `DecisionMaker._execute_autonomous()`에서 브로커의 현재 미체결 주문을 조회해 같은 종목의 pending buy를 하드 게이트로 막는다. 기존 주문 추적/체결 확인 흐름은 유지하고, 이번 라운드에서는 멱등 키나 cancel/replace는 도입하지 않는다.

**Tech Stack:** Python, pytest, Kiwoom broker adapter, SQLite activity logging

---

### Task 1: Pending Buy 차단 회귀 테스트

**Files:**
- Modify: `tests/agent/test_decision_maker.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_decision_maker_skips_buy_when_pending_buy_exists(monkeypatch) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_decision_maker.py::test_decision_maker_skips_buy_when_pending_buy_exists -q`
Expected: FAIL because `place_order()` is still called.

### Task 2: 최소 구현

**Files:**
- Modify: `agent/decision_maker.py`

- [ ] **Step 1: Add pending buy gate**

```python
if signal.action == SignalAction.BUY and existing_pending_buy:
    return skipped_result
```

- [ ] **Step 2: Log skip + publish event**

```python
await activity_logger.log(...)
await event_bus.publish(...)
```

### Task 3: 검증

**Files:**
- Test: `tests/agent/test_decision_maker.py`

- [ ] **Step 1: Run targeted tests**

Run: `pytest tests/agent/test_decision_maker.py -q`
Expected: PASS
