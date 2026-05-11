from trading.symbols import normalize_krx_symbol


def test_normalize_strips_a_prefix_from_numeric():
    assert normalize_krx_symbol("A005930") == "005930"


def test_normalize_strips_a_prefix_from_alphanumeric():
    # 우선주/특수 종목 코드 (예: 0011T0 채비)
    assert normalize_krx_symbol("A0011T0") == "0011T0"


def test_normalize_passthrough_when_no_prefix():
    assert normalize_krx_symbol("005930") == "005930"
    assert normalize_krx_symbol("0011T0") == "0011T0"


def test_normalize_handles_lowercase_prefix():
    assert normalize_krx_symbol("a005930") == "005930"


def test_normalize_does_not_strip_partial_match():
    # 5자리, 7자리는 KRX 표준 아님 → 보존
    assert normalize_krx_symbol("A12345") == "A12345"
    assert normalize_krx_symbol("A1234567") == "A1234567"


def test_normalize_handles_blank_input():
    assert normalize_krx_symbol("") == ""
    assert normalize_krx_symbol(None) == ""
