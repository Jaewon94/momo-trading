import pytest

from trading.adapters.kis_adapter import KisBrokerAdapter
from trading.broker_factory import build_broker_adapter
from trading.enums import BrokerProvider


def test_build_broker_adapter_returns_kis_adapter() -> None:
    adapter = build_broker_adapter(BrokerProvider.KIS)

    assert isinstance(adapter, KisBrokerAdapter)


def test_build_broker_adapter_rejects_unsupported_provider() -> None:
    with pytest.raises(ValueError):
        build_broker_adapter(BrokerProvider.KIWOOM)
