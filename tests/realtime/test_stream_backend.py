import pytest

from realtime.stream_backend import NullStreamBackend


@pytest.mark.asyncio
async def test_null_stream_backend_listen_yields_control(monkeypatch) -> None:
    backend = NullStreamBackend()
    observed: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        observed.append(seconds)

    monkeypatch.setattr("realtime.adapters.null_realtime_adapter.asyncio.sleep", fake_sleep)

    await backend.listen()

    assert observed == [1]
