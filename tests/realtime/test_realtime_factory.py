from realtime.adapters.kis_realtime_adapter import KISRealtimeAdapter
from realtime.adapters.kiwoom_realtime_adapter import KiwoomRealtimeAdapter
from realtime.adapters.null_realtime_adapter import NullRealtimeAdapter
from realtime.realtime_factory import get_realtime_adapter


def test_get_realtime_adapter_returns_kis_adapter_for_kis(monkeypatch) -> None:
    monkeypatch.setattr("core.config.settings.BROKER_PROVIDER", "KIS")
    get_realtime_adapter.cache_clear()

    assert isinstance(get_realtime_adapter(), KISRealtimeAdapter)


def test_get_realtime_adapter_returns_kiwoom_adapter_for_kiwoom(monkeypatch) -> None:
    monkeypatch.setattr("core.config.settings.BROKER_PROVIDER", "KIWOOM")
    get_realtime_adapter.cache_clear()

    assert isinstance(get_realtime_adapter(), KiwoomRealtimeAdapter)


def test_get_realtime_adapter_returns_null_adapter_for_unknown(monkeypatch) -> None:
    monkeypatch.setattr("core.config.settings.BROKER_PROVIDER", "UNKNOWN")
    get_realtime_adapter.cache_clear()

    assert isinstance(get_realtime_adapter(), NullRealtimeAdapter)
