"""브로커 어댑터 선택 팩토리"""
from functools import lru_cache

from core.config import settings
from trading.adapters.base import BrokerAdapter
from trading.adapters.kis_adapter import KisBrokerAdapter
from trading.enums import BrokerProvider


def build_broker_adapter(provider: BrokerProvider) -> BrokerAdapter:
    """브로커 제공자별 어댑터를 생성한다."""
    if provider == BrokerProvider.KIS:
        return KisBrokerAdapter()
    raise ValueError(f"지원하지 않는 브로커 제공자입니다: {provider.value}")


@lru_cache(maxsize=1)
def get_broker_adapter() -> BrokerAdapter:
    """현재 설정에 맞는 브로커 어댑터 싱글턴을 반환한다."""
    provider = BrokerProvider(settings.BROKER_PROVIDER.upper())
    return build_broker_adapter(provider)
