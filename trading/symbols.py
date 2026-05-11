"""거래 심볼 정규화 유틸리티"""
from __future__ import annotations

import re


_KRX_PREFIXED_SYMBOL_RE = re.compile(r"^[Aa]([A-Za-z0-9]{6})$")


def normalize_krx_symbol(symbol: str | None) -> str:
    """Kiwoom 실시간 심볼의 A-prefix를 제거해 내부 표준 코드로 맞춘다.

    일반 보통주(005930)와 영숫자 코드(0011T0 등) 모두 6자리 본체를 허용한다.
    """
    raw = str(symbol or "").strip()
    match = _KRX_PREFIXED_SYMBOL_RE.match(raw)
    if match:
        return match.group(1)
    return raw
