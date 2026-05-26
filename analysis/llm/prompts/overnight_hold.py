"""오버나이트 보유 판정 프롬프트 — LLM Tier1 기반 HOLD/SELL/EXTEND 판단

스마트 청산(15:10) 시 보유종목 전체를 LLM에 전달하여
포트폴리오 맥락(섹터 집중도, 상관관계 등)을 고려한 판정을 받는다.
"""

OVERNIGHT_HOLD_SYSTEM = """당신은 한국 주식 스윙 트레이딩 오버나이트 보유 판정 전문가입니다.
장 마감 직전(15:10), 보유종목 데이터를 보고 종목별로 오버나이트 HOLD/SELL을 판단합니다.

## 판단 프레임워크
1. **손익 상태**: 현재 수익률과 손절가/목표가 대비 위치
2. **보유일 vs 최대보유일**: 잔여 보유 여유가 있는지
3. **AI 신뢰도**: 매수 시점의 분석 신뢰도
4. **전략 특성**: 전략별 손절 기준과 보유 기간이 다름
5. **포트폴리오 전체 맥락**: 섹터 집중도, 동시 보유 종목 수, 시장 국면

## 스윙 트레이딩 핵심 원칙
- 당일 소폭 손실(-2~3% 이내)은 스윙 트레이딩에서 **정상적 변동**임. 손절가에 근접하지 않았다면 보유 유지가 합리적
- 수익 중 + 목표가 미도달 + 보유일 여유 → HOLD 근거 충분
- 손절가 근접/돌파 → 명확한 SELL 신호
- 최대보유일 도달/초과는 자동 SELL이 아니라 **연장심사 지점**임
- 연장심사 지점에서 상승 논거, 목표가 여유, 시장/뉴스 지원, 리스크 대비 보상이 충분하면 EXTEND
- MID 연장은 LONG 전환이며, LONG 30일 이후는 15일 단위 재심사로만 연장 가능
- 연장 근거가 약하거나 손절/목표 도달 후 추세 약화/악재가 있으면 SELL
- 신뢰도가 매우 낮은(0.4 미만) 종목 → SELL 고려

## 액션 정의
- HOLD: 아직 최대보유일 여유가 있거나 보유 논거가 유효한 일반 보유
- EXTEND: 최대보유일에 도달했지만 보유 논거가 강해 다음 보유 구간으로 연장
- SELL: 손절/익절/논거 훼손/연장 근거 부족으로 청산

## 금지 사항
- "보수적으로 SELL" 같은 편향된 판단 금지 — 데이터 근거로만 판단
- 시장 국면만으로 전량 SELL 판정 금지 — 종목별 개별 판단 필수
- 반드시 한국어로 답변"""

OVERNIGHT_HOLD_PROMPT = """## 오버나이트 보유 판정 요청

### 시장 국면
{market_regime}

### 보유종목 현황
{holdings_detail}

---

위 데이터를 종합하여 종목별로 오버나이트 HOLD/SELL/EXTEND를 판정하세요.
각 종목에 대해 핵심 근거 1~2문장을 작성하세요.

JSON 형식으로 답변:
```json
{{
  "decisions": [
    {{
      "symbol": "종목코드",
      "action": "HOLD 또는 SELL 또는 EXTEND",
      "reason": "판단 근거 1~2문장",
      "confidence": 0.00,
      "extend_horizon": "EXTEND일 때 LONG 또는 EXTENDED_LONG, 아니면 null",
      "extension_days": "EXTEND일 때 요청 연장일수 숫자, 아니면 null"
    }}
  ]
}}
```"""


def build_overnight_prompt(
    holdings_data: list[dict],
    market_regime: str = "",
) -> str:
    """오버나이트 판정용 유저 프롬프트 생성

    Args:
        holdings_data: 종목별 데이터 딕셔너리 리스트
        market_regime: 시장 국면 (BULL/BEAR/SIDEWAYS/THEME)

    Returns:
        포맷된 프롬프트 문자열
    """
    lines = []
    for i, d in enumerate(holdings_data, 1):
        pnl_rate = d.get("pnl_rate", 0.0)
        target_text = f"{d['target_price']:,.0f}원" if d.get("target_price") else "미설정"
        stop_text = f"{d['stop_loss_price']:,.0f}원" if d.get("stop_loss_price") else "미설정"
        horizon = d.get("trade_horizon") or "N/A"
        extension_count = int(d.get("hold_extension_count") or 0)
        extension_until = d.get("hold_extension_until_days") or d.get("max_hold_days", 0)
        extension_cap = d.get("hold_extension_total_cap_days") or "미설정"
        review_due = "필요" if d.get("hold_days", 0) >= d.get("max_hold_days", 0) else "아직 아님"

        lines.append(
            f"#### {i}. {d.get('stock_name', '')} ({d['symbol']})\n"
            f"- 매입가: {d.get('avg_price', 0):,.0f}원 → 현재가: {d.get('current_price', 0):,.0f}원\n"
            f"- 수익률: {pnl_rate:+.2f}%\n"
            f"- 보유수량: {d.get('quantity', 0)}주\n"
            f"- 보유일수: {d.get('hold_days', 0)}일 / 현재 최대 {d.get('max_hold_days', 0)}일\n"
            f"- 호라이즌: {horizon} | 연장심사: {review_due} | 연장 {extension_count}회, 다음 한도 {extension_until}일, 총상한 {extension_cap}일\n"
            f"- AI 신뢰도: {d.get('confidence', 0):.2f}\n"
            f"- 목표가: {target_text} | 손절가: {stop_text}\n"
            f"- 전략: {d.get('strategy_type', 'N/A')}"
        )

    holdings_detail = "\n\n".join(lines) if lines else "보유종목 없음"
    regime_text = market_regime if market_regime else "정보 없음"

    return OVERNIGHT_HOLD_PROMPT.format(
        market_regime=regime_text,
        holdings_detail=holdings_detail,
    )
