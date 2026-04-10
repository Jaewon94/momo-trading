# Broker Realtime Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove KIS-specific realtime branching from the core monitoring path by introducing an explicit realtime-adapter contract, delegating stream orchestration through that contract, and aligning broker capabilities with what is actually implemented today.

**Architecture:** Add a focused realtime adapter slice under `realtime/adapters/` plus a cached factory that selects the adapter for the current broker. Refactor `StreamManager` to own only callback wiring, subscription bookkeeping, and reconnect orchestration, and refactor `RealtimeMonitor` to choose realtime versus polling solely from broker capabilities. Keep `trading/kis_websocket.py` intact, but hide it behind a `KISRealtimeAdapter`. Treat Kiwoom as `polling-only` for now by exposing `supports_realtime_quotes=False` until a real Kiwoom realtime adapter exists.

**Tech Stack:** Python 3.13, FastAPI, asyncio, loguru, pytest, pytest-asyncio

## File Structure

- Create: `realtime/adapters/base.py`
  - Realtime adapter protocol shared by KIS/null implementations.
- Create: `realtime/adapters/kis_realtime_adapter.py`
  - Thin wrapper around `trading.kis_websocket.kis_websocket`.
- Create: `realtime/adapters/null_realtime_adapter.py`
  - No-op adapter for brokers without realtime support.
- Create: `realtime/realtime_factory.py`
  - Cached factory returning the adapter for the current broker.
- Create: `tests/realtime/test_realtime_factory.py`
  - Selection tests for KIS/KIWOOM adapter resolution.
- Create: `tests/realtime/test_stream_manager.py`
  - Provider-agnostic stream manager orchestration tests.
- Modify: `realtime/stream_manager.py`
  - Remove provider checks; delegate everything through the realtime adapter.
- Modify: `realtime/monitor.py`
  - Use broker capability instead of provider name to choose realtime versus polling.
- Modify: `realtime/stream_backend.py`
  - Reduce to compatibility shim or re-export so older imports/tests stay stable during migration.
- Modify: `tests/realtime/test_monitor.py`
  - Replace provider-name assertions with capability-based behavior tests.
- Modify: `tests/conftest.py`
  - Clear `get_realtime_adapter()` cache between tests.
- Modify: `trading/adapters/kiwoom_adapter.py`
  - Set `supports_realtime_quotes=False` until a real Kiwoom realtime adapter exists.
- Modify: `tests/trading/test_kiwoom_adapter.py`
  - Update capability expectation to match current implementation reality.
- Modify: `tests/services/test_broker_smoke_service.py`
  - Keep the fake broker realistic by using the corrected capability flag.

---

### Task 1: Add realtime adapter contract and factory

**Files:**
- Create: `realtime/adapters/base.py`
- Create: `realtime/adapters/kis_realtime_adapter.py`
- Create: `realtime/adapters/null_realtime_adapter.py`
- Create: `realtime/realtime_factory.py`
- Modify: `realtime/stream_backend.py`
- Modify: `tests/conftest.py`
- Test: `tests/realtime/test_realtime_factory.py`
- Test: `tests/realtime/test_stream_backend.py`

- [ ] **Step 1: Write the failing factory tests**

```python
from realtime.realtime_factory import get_realtime_adapter
from realtime.adapters.kis_realtime_adapter import KISRealtimeAdapter
from realtime.adapters.null_realtime_adapter import NullRealtimeAdapter

def test_get_realtime_adapter_returns_kis_adapter_for_kis(monkeypatch):
    monkeypatch.setattr("core.config.settings.BROKER_PROVIDER", "KIS")
    get_realtime_adapter.cache_clear()
    assert isinstance(get_realtime_adapter(), KISRealtimeAdapter)

def test_get_realtime_adapter_returns_null_adapter_for_kiwoom(monkeypatch):
    monkeypatch.setattr("core.config.settings.BROKER_PROVIDER", "KIWOOM")
    get_realtime_adapter.cache_clear()
    assert isinstance(get_realtime_adapter(), NullRealtimeAdapter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_realtime_factory.py tests/realtime/test_stream_backend.py -q`
Expected: FAIL because `realtime_factory` and the new adapter modules do not exist yet.

- [ ] **Step 3: Implement the minimal adapter slice**

Implementation notes:
- Define a `RealtimeAdapter` protocol with:
  - `set_on_price(callback)`
  - `start()`
  - `stop()`
  - `subscribe(symbol, market="KRX")`
  - `unsubscribe(symbol, market="KRX")`
  - `listen()`
  - `subscription_count`
  - `is_connected`
- `KISRealtimeAdapter` should delegate directly to `kis_websocket`.
- `NullRealtimeAdapter.listen()` should `await asyncio.sleep(1)` so it yields control cleanly.
- `get_realtime_adapter()` should be the only place that maps `BROKER_PROVIDER` to an adapter.
- Keep `realtime/stream_backend.py` as a compatibility shim that re-exports the same behavior for existing imports and tests.
- Update `tests/conftest.py` to clear `get_realtime_adapter.cache_clear()` along with other cached singletons.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_realtime_factory.py tests/realtime/test_stream_backend.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add realtime/adapters/base.py realtime/adapters/kis_realtime_adapter.py realtime/adapters/null_realtime_adapter.py realtime/realtime_factory.py realtime/stream_backend.py tests/conftest.py tests/realtime/test_realtime_factory.py tests/realtime/test_stream_backend.py
git commit -m "feat: add realtime adapter factory"
```

### Task 2: Refactor stream manager to depend only on the realtime adapter

**Files:**
- Modify: `realtime/stream_manager.py`
- Create: `tests/realtime/test_stream_manager.py`

- [ ] **Step 1: Write the failing stream manager tests**

```python
class FakeRealtimeAdapter:
    def __init__(self):
        self.started = 0
        self.subscribed = []
        self.listen_calls = 0
        self.connected = True

    async def start(self):
        self.started += 1

    async def stop(self):
        return None

    async def subscribe(self, symbol, market="KRX"):
        self.subscribed.append((symbol, market))
        return True

    async def unsubscribe(self, symbol, market="KRX"):
        return None

    async def listen(self):
        self.listen_calls += 1
        raise asyncio.CancelledError

def test_stream_manager_constructor_accepts_adapter():
    adapter = FakeRealtimeAdapter()
    manager = StreamManager(realtime_adapter=adapter)
    assert manager.subscription_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_stream_manager.py -q`
Expected: FAIL because `StreamManager` does not accept injected adapters and the test file is new.

- [ ] **Step 3: Implement the minimal refactor**

Implementation notes:
- Add an optional `realtime_adapter` constructor argument to `StreamManager`; default to `get_realtime_adapter()`.
- Remove `_supports_kis_streams()` and all provider-name guards.
- Add `set_on_price(callback)` so the monitor no longer needs to import the adapter factory directly.
- Preserve:
  - subscription bookkeeping in `_priority_symbols`
  - reconnect/restart loop
  - resubscription on reconnect
- `subscription_count` and `is_connected` should read directly from the injected adapter.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_stream_manager.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add realtime/stream_manager.py tests/realtime/test_stream_manager.py
git commit -m "refactor: decouple stream manager from broker provider"
```

### Task 3: Refactor realtime monitor to use broker capability instead of provider name

**Files:**
- Modify: `realtime/monitor.py`
- Modify: `tests/realtime/test_monitor.py`

- [ ] **Step 1: Write the failing monitor tests**

```python
class FakeRealtimeCapableBroker:
    class capabilities:
        supports_realtime_quotes = True

class FakePollingOnlyBroker:
    class capabilities:
        supports_realtime_quotes = False

@pytest.mark.asyncio
async def test_realtime_monitor_starts_streams_when_broker_supports_realtime(monkeypatch):
    monitor = RealtimeMonitor()
    observed = []
    monkeypatch.setattr("realtime.monitor.get_broker_adapter", lambda: FakeRealtimeCapableBroker())
    monkeypatch.setattr("realtime.monitor.stream_manager.set_on_price", lambda cb: observed.append("callback"))
    monkeypatch.setattr("realtime.monitor.stream_manager.start", fake_async("start", observed))
    ...
    assert "start" in observed

@pytest.mark.asyncio
async def test_realtime_monitor_starts_polling_when_broker_lacks_realtime(monkeypatch):
    monitor = RealtimeMonitor()
    monkeypatch.setattr("realtime.monitor.get_broker_adapter", lambda: FakePollingOnlyBroker())
    ...
    assert monitor.is_polling is False after stop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_monitor.py -q`
Expected: FAIL because the monitor still checks provider names and imports `get_stream_backend()` directly.

- [ ] **Step 3: Implement the minimal monitor refactor**

Implementation notes:
- Remove `_uses_kis_websocket()`.
- Add a helper that reads `get_broker_adapter().capabilities.supports_realtime_quotes`.
- In `start()`:
  - if realtime supported, call `stream_manager.set_on_price(self._on_price_update)` and `await stream_manager.start()`
  - otherwise, start polling during trading hours
- In `_ws_health_loop()`, use capability plus `stream_manager.is_connected` and staleness checks; never branch on provider name.
- Keep existing polling fallback semantics unchanged.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_monitor.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add realtime/monitor.py tests/realtime/test_monitor.py
git commit -m "refactor: use realtime capability in monitor"
```

### Task 4: Align Kiwoom capability flags with implemented behavior

**Files:**
- Modify: `trading/adapters/kiwoom_adapter.py`
- Modify: `tests/trading/test_kiwoom_adapter.py`
- Modify: `tests/services/test_broker_smoke_service.py`

- [ ] **Step 1: Write the failing capability assertions**

```python
@pytest.mark.asyncio
async def test_kiwoom_adapter_exposes_current_realtime_capability() -> None:
    adapter, _ = build_adapter()
    assert adapter.capabilities.supports_realtime_quotes is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/.venv313/bin/python -m pytest tests/trading/test_kiwoom_adapter.py -q`
Expected: FAIL because the adapter still advertises realtime support as `True`.

- [ ] **Step 3: Implement the minimal capability correction**

Implementation notes:
- Change `KiwoomBrokerAdapter.capabilities.supports_realtime_quotes` to `False`.
- Update any fakes that are pretending to model the current Kiwoom implementation reality.
- Do not change KIS capabilities.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `/.venv313/bin/python -m pytest tests/trading/test_kiwoom_adapter.py tests/services/test_broker_smoke_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/adapters/kiwoom_adapter.py tests/trading/test_kiwoom_adapter.py tests/services/test_broker_smoke_service.py
git commit -m "fix: align kiwoom realtime capability with implementation"
```

### Task 5: Verify targeted and full backend regression coverage

**Files:**
- Verify only

- [ ] **Step 1: Run targeted realtime and capability tests**

Run: `/.venv313/bin/python -m pytest tests/realtime/test_realtime_factory.py tests/realtime/test_stream_backend.py tests/realtime/test_stream_manager.py tests/realtime/test_monitor.py tests/trading/test_kiwoom_adapter.py tests/services/test_broker_smoke_service.py -q`
Expected: PASS

- [ ] **Step 2: Run startup/runtime regression tests**

Run: `/.venv313/bin/python -m pytest tests/main/test_lifespan_startup.py tests/scheduler/test_scheduler_runtime_paths.py -q`
Expected: PASS

- [ ] **Step 3: Run the full backend suite**

Run: `/.venv313/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 4: Summarize residual risks**

Residual risks to call out after implementation:
- `stream_backend.py` may still exist as a compatibility layer and should be cleaned up in a later pass.
- Kiwoom remains polling-only until a real realtime adapter is implemented and validated.
- Reconnect behavior is only covered by fake adapter tests until a live broker smoke test is added.
