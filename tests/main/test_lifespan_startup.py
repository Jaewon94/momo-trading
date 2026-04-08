import pytest

import main
from main import app


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


@pytest.mark.asyncio
async def test_app_lifespan_starts_even_when_mcp_connect_fails(monkeypatch) -> None:
    recorder = Recorder()

    async def fake_event_bus_start() -> None:
        recorder.calls.append("event_bus.start")

    async def fake_event_bus_stop() -> None:
        recorder.calls.append("event_bus.stop")

    async def fake_runtime_startup() -> None:
        recorder.calls.append("runtime.startup")
        raise RuntimeError("mcp down")

    async def fake_runtime_shutdown() -> None:
        recorder.calls.append("runtime.shutdown")

    monkeypatch.setattr("main.setup_logging", lambda: recorder.calls.append("setup_logging"))
    monkeypatch.setattr(
        type(main.settings),
        "validate_on_startup",
        lambda self: recorder.calls.append("validate"),
    )
    monkeypatch.setattr("main.event_bus.start", fake_event_bus_start)
    monkeypatch.setattr("main.event_bus.stop", fake_event_bus_stop)
    monkeypatch.setattr("main.broker_runtime_service.startup", fake_runtime_startup)
    monkeypatch.setattr("main.broker_runtime_service.shutdown", fake_runtime_shutdown)
    monkeypatch.setattr("main.settings.BROKER_PROVIDER", "KIS")
    monkeypatch.setattr("realtime.monitor.realtime_monitor", recorder)
    monkeypatch.setattr("agent.trading_agent.trading_agent", recorder)
    monkeypatch.setattr("scheduler.scheduler.trading_scheduler", recorder)

    async with app.router.lifespan_context(app):
        recorder.calls.append("inside")

    assert recorder.calls[:4] == ["setup_logging", "validate", "event_bus.start", "runtime.startup"]
    assert recorder.calls.count("start") == 3
    assert recorder.calls.count("stop") == 3
    assert "inside" in recorder.calls
    assert "runtime.shutdown" in recorder.calls
    assert recorder.calls[-2:] == ["runtime.shutdown", "event_bus.stop"]


@pytest.mark.asyncio
async def test_app_lifespan_completes_in_kiwoom_mode_without_kis_mcp(monkeypatch) -> None:
    recorder = Recorder()

    async def fake_event_bus_start() -> None:
        recorder.calls.append("event_bus.start")

    async def fake_event_bus_stop() -> None:
        recorder.calls.append("event_bus.stop")

    async def fake_runtime_startup() -> None:
        recorder.calls.append("runtime.startup")
        raise RuntimeError("kis mcp unavailable")

    async def fake_runtime_shutdown() -> None:
        recorder.calls.append("runtime.shutdown")

    monkeypatch.setattr("main.setup_logging", lambda: None)
    monkeypatch.setattr("main.event_bus.start", fake_event_bus_start)
    monkeypatch.setattr("main.event_bus.stop", fake_event_bus_stop)
    monkeypatch.setattr("main.broker_runtime_service.startup", fake_runtime_startup)
    monkeypatch.setattr("main.broker_runtime_service.shutdown", fake_runtime_shutdown)
    monkeypatch.setattr(
        type(main.settings),
        "validate_on_startup",
        lambda self: None,
    )
    monkeypatch.setattr("main.settings.BROKER_PROVIDER", "KIWOOM")
    monkeypatch.setattr("realtime.monitor.realtime_monitor", recorder)
    monkeypatch.setattr("agent.trading_agent.trading_agent", recorder)
    monkeypatch.setattr("scheduler.scheduler.trading_scheduler", recorder)

    async with app.router.lifespan_context(app):
        pass

    assert recorder.calls.count("runtime.startup") == 1
    assert recorder.calls.count("start") == 3
    assert recorder.calls[-2:] == ["runtime.shutdown", "event_bus.stop"]
