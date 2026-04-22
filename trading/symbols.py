"""거래 심볼 정규화 유틸리티"""
from __future__ import annotations

import re


_KRX_PREFIXED_SYMBOL_RE = re.compile(r"^[Aa](\d{6})$")


def normalize_krx_symbol(symbol: str | None) -> str:
    """Kiwoom 실시간 심볼의 A-prefix를 제거해 내부 표준 코드로 맞춘다."""
    raw = str(symbol or "").strip()
    match = _KRX_PREFIXED_SYMBOL_RE.match(raw)
    if match:
        return match.group(1)
    return raw
