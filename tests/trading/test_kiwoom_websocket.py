"""키움 WebSocket 실시간 시세 파싱/구성 회귀 테스트."""
from trading.kiwoom_websocket import KiwoomWebSocket


def _ws() -> KiwoomWebSocket:
    return KiwoomWebSocket()


def test_paper_uses_mock_ws_url(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(type(ws._rest_client), "is_paper_trading", property(lambda self: True))
    assert ws._ws_url == KiwoomWebSocket.MOCK_WS_URL


def test_real_uses_real_ws_url(monkeypatch):
    ws = _ws()
    monkeypatch.setattr(type(ws._rest_client), "is_paper_trading", property(lambda self: False))
    assert ws._ws_url == KiwoomWebSocket.REAL_WS_URL


def test_parse_real_0b_normalizes_symbol_and_abs_price():
    ws = _ws()
    item = {
        "type": "0B",
        "item": "A005930",  # 키움 실시간 A-prefix
        "values": {"10": "-73000", "11": "-1500", "12": "-2.01", "13": "1234567", "15": "320"},
    }
    out = ws._parse_real(item)
    assert out == {
        "market": "KRX",
        "symbol": "005930",      # A-prefix 제거
        "price": 73000.0,        # 부호 제거 + 절대값
        "change": -1500.0,
        "change_rate": -2.01,
        "volume": 320,
        "cumulative_volume": 1234567,
    }


def test_parse_real_ignores_other_types():
    ws = _ws()
    assert ws._parse_real({"type": "0D", "item": "005930", "values": {"10": "100"}}) is None


def test_parse_real_rejects_missing_or_zero_price():
    ws = _ws()
    assert ws._parse_real({"type": "0B", "item": "005930", "values": {}}) is None
    assert ws._parse_real({"type": "0B", "item": "005930", "values": {"10": "0"}}) is None


def test_initial_state_disconnected():
    ws = _ws()
    assert ws.is_connected is False
    assert ws.subscription_count == 0
