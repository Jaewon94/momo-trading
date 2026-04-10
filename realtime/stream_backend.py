"""기존 실시간 백엔드 import 경로를 위한 호환 레이어."""
from realtime.adapters.base import RealtimeAdapter as StreamBackend
from realtime.adapters.kis_realtime_adapter import KISRealtimeAdapter as KISStreamBackend
from realtime.adapters.null_realtime_adapter import NullRealtimeAdapter as NullStreamBackend
from realtime.realtime_factory import get_realtime_adapter


def get_stream_backend() -> StreamBackend:
    return get_realtime_adapter()
