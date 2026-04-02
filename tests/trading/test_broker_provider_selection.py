import pytest

from trading.adapters.kis_adapter import KisBrokerAdapter
from trading.adapters.kiwoom_adapter import KiwoomBrokerAdapter
from trading.broker_factory import get_broker_adapter


def test_get_broker_adapter_selects_kiwoom_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("trading.broker_factory.settings.BROKER_PROVIDER", "KIWOOM")
    get_broker_adapter.cache_clear()

    adapter = get_broker_adapter()

    assert isinstance(adapter, KiwoomBrokerAdapter)
    get_broker_adapter.cache_clear()


def test_get_broker_adapter_selects_kis_when_configured(monkeypatch) -> None:
    monkeypatch.setattr("trading.broker_factory.settings.BROKER_PROVIDER", "KIS")
    get_broker_adapter.cache_clear()

    adapter = get_broker_adapter()

    assert isinstance(adapter, KisBrokerAdapter)
    get_broker_adapter.cache_clear()


def test_get_broker_adapter_raises_for_invalid_provider(monkeypatch) -> None:
    monkeypatch.setattr("trading.broker_factory.settings.BROKER_PROVIDER", "INVALID")
    get_broker_adapter.cache_clear()

    with pytest.raises(ValueError):
        get_broker_adapter()

    get_broker_adapter.cache_clear()
