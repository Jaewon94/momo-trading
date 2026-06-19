"""현재 브로커에 맞는 실시간 어댑터 선택."""
from functools import lru_cache

from core.config import settings
from realtime.adapters.base import RealtimeAdapter
from realtime.adapters.kis_realtime_adapter import KISRealtimeAdapter
from realtime.adapters.kiwoom_realtime_adapter import KiwoomRealtimeAdapter
from realtime.adapters.null_realtime_adapter import NullRealtimeAdapter
from trading.enums import BrokerProvider


@lru_cache(maxsize=1)
def get_realtime_adapter() -> RealtimeAdapter:
    provider = (settings.BROKER_PROVIDER or BrokerProvider.KIS.value).upper()
    if provider == BrokerProvider.KIS.value:
        return KISRealtimeAdapter()
    if provider == BrokerProvider.KIWOOM.value:
        return KiwoomRealtimeAdapter()
    return NullRealtimeAdapter()
