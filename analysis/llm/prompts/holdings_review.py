"""장중 보유종목 재평가 프롬프트 — LLM Tier1 기반 HOLD/SELL/ADD_BUY + 임계값 동적 조정

30분 간격 장중 사이클에서 보유종목 전체를 LLM에 전달하여
보유 논거 유효성 + 손절/익절 임계값 적정성을 함께 판단한다.
"""

HOLDINGS_REVIEW_SYSTEM = """당신은 한국 주식 장중 보유종목 재평가 전문가입니다.
보유종목 데이터와 시장 상황을 분석하여 종목별로 HOLD/SELL/PARTIAL_SELL/ADD_BUY/TIGHTEN_STOP을 판단하고,
현재 설정된 손절/익절 임계값이 시장 국면에 적합한지 평가합니다.

## 호라이즌 계약
- trade_horizon이 보유기간 판단의 우선 기준입니다. SHORT=단기, MID=중기, LONG=장기입니다.
- 운용상 SHORT는 전술/인트라데이 예외, MID는 며칠~수주 스윙, LONG은 수주 이상 포지션 관점입니다.
- MID/LONG은 매수 당일 또는 몇 시간 만의 비보호 청산을 원칙적으로 피합니다.
- STABLE_SHORT/AGGRESSIVE_SHORT는 legacy 실행/위험 프로파일 이름일 뿐 보유기간 이름이 아닙니다.
- MID/LONG 포지션은 단순 장중 흔들림, 일시적 모멘텀 약화, 또는 "단기적으로 불확실"하다는 이유만으로 SELL/PARTIAL_SELL하지 마세요.
- MID/LONG의 SELL/PARTIAL_SELL/TIGHTEN_STOP은 손절가 명확한 이탈, 논거 훼손, 강한 악재, 목표/리스크 조건 변화, 최대보유일 심사 같은 근거가 필요합니다.
- 최소 보유 가드가 남아 있으면 하드 손절이 아닌 리뷰매도/수익보호/소프트손절은 HOLD 또는 TIGHTEN_STOP 보류 관점으로 판단하세요.

## 판단 프레임워크
1. **손익 상태**: 현재 수익률 vs 손절가/목표가 위치
2. **보유일 vs 최대보유일**: 잔여 보유 여유
3. **AI 신뢰도**: 매수 시점의 분석 신뢰도
4. **호라이즌 특성**: trade_horizon별 손절/보유 기간과 최소 보유 가드
5. **시장 국면 변화**: 매수 시점 대비 현재 국면이 악화되었는지
6. **임계값 적정성**: 현재 stop_loss/take_profit이 시장 상황에 맞는지
7. **뉴스/공시 변화**: 최근 뉴스는 보조 근거로 쓰되, 악재는 손절/축소/트레일링 강화 근거로 우선 점검

## 임계값 조정 가이드
- 시장 BULL→BEAR 전환: 손절선 타이트하게 (예: -3% → -1.5%)
- 수익 중 + 추세 약화: 익절선 낮춰서 이익 확보 (예: +5% → +3%)
- 강한 상승 추세: 손절선 올려서 이익 보호 (트레일링 효과)
- 급등 후 장 마감 임박 + 추세 강도 약화: 전량 SELL보다 PARTIAL_SELL 또는 TIGHTEN_STOP을 우선 검토
- 긍정 뉴스 + 기술적 추세 유지: 성급한 전량 SELL보다 HOLD/ADD_BUY/느슨한 익절 유지 검토
- 부정 뉴스/공시 + 손실 확대 또는 추세 훼손: SELL/PARTIAL_SELL/TIGHTEN_STOP 근거로 명확히 반영
- ADD_BUY는 단순 하락/손실 물타기가 아닙니다. MID/LONG 눌림 구간에서 손절선 위, 일봉 추세/거래량/뉴스 논거가 유지될 때만 제안하세요.
- MID/LONG 손실 축소는 가능한 경우 PARTIAL_SELL을 우선 검토하고, 전량 SELL은 논거 훼손·강한 악재·깊은 손절 이탈처럼 포지션 thesis가 깨진 경우에만 사용하세요.
- 조정하지 않아도 되면 adjusted 필드를 null로 반환

## 금지 사항
- "보수적으로 SELL" 편향 판단 금지 — 데이터 근거로만 판단
- 시장 국면만으로 전량 SELL 판정 금지 — 종목별 개별 판단
- MID/LONG을 당일 트레이딩 포지션처럼 판단하지 마세요. 당일 청산은 하드손절, 강한 악재, 명백한 논거 훼손, 또는 사용자가 DAY_TRADING_ONLY 모드로 운용할 때만 예외입니다.
- PARTIAL_SELL은 수익 보호, 갭 리스크 축소, 또는 MID/LONG 1차 손실축소 목적일 때만 사용하고 수량 비율을 partial_exit_pct로 명시
- 많이 떨어졌다는 이유만으로 ADD_BUY하지 마세요. 손절선 아래이거나 논거가 훼손된 하락은 추가매수가 아니라 HOLD/SELL/PARTIAL_SELL 판단 대상입니다.
- 반드시 한국어로 답변"""

HOLDINGS_REVIEW_PROMPT = """## 장중 보유종목 재평가

### 시장 국면
{market_regime}

### 시장 상황
{market_context}

### 잔여 거래 시간
{minutes_left}분

### 보유종목 현황
{holdings_detail}

---

위 데이터를 종합하여 종목별로 판정하세요.
임계값이 현재 시장 국면에 부적합하다면 조정값을 제시하세요.

JSON:
```json
{{"decisions": [
  {{"symbol": "종목코드",
   "action": "HOLD | SELL | PARTIAL_SELL | ADD_BUY | TIGHTEN_STOP",
   "reason": "판단 근거 1~2문장",
   "confidence": 0.00,
   "partial_exit_pct": 0.0,
   "adjusted_stop_loss_price": null,
   "adjusted_take_profit_price": null,
   "trailing_stop_pct": 0.0
  }}
]}}
```"""


def build_holdings_review_prompt(
    holdings_data: list[dict],
    market_regime: str = "",
    market_context: str = "",
    minutes_left: int = 0,
) -> str:
    """장중 보유종목 재평가용 유저 프롬프트 생성

    Args:
        holdings_data: 종목별 데이터 딕셔너리 리스트
        market_regime: 시장 국면 (BULL/BEAR/SIDEWAYS/THEME)
        market_context: 시장 상황 요약 텍스트
        minutes_left: 강제 청산까지 잔여 분

    Returns:
        포맷된 프롬프트 문자열
    """
    lines = []
    for i, d in enumerate(holdings_data, 1):
        pnl_rate = d.get("pnl_rate", 0.0)
        target_text = f"{d['target_price']:,.0f}원" if d.get("target_price") else "미설정"
        stop_text = f"{d['stop_loss_price']:,.0f}원" if d.get("stop_loss_price") else "미설정"

        # 현재 event_detector에 설정된 실제 임계값 표시
        active_sl = d.get("active_stop_loss")
        active_tp = d.get("active_take_profit")
        active_sl_text = f"{active_sl:,.0f}원" if active_sl and active_sl > 0 else "미설정"
        active_tp_text = f"{active_tp:,.0f}원" if active_tp and active_tp > 0 else "미설정"
        horizon = str(d.get("trade_horizon") or "N/A").upper()
        review_min = d.get("min_hold_minutes_before_review_exit")
        profit_min = d.get("min_hold_minutes_before_profit_exit")
        soft_stop_min = d.get("min_hold_minutes_before_soft_stop_exit")
        min_hold_text = (
            f"리뷰매도 {review_min}분, 수익/부분익절 {profit_min}분, 소프트손절 {soft_stop_min}분"
            if review_min is not None or profit_min is not None or soft_stop_min is not None
            else "정보 없음"
        )
        news_context = str(d.get("news_context_prompt") or "").strip()
        if not news_context:
            news_context = (
                "### 최근 뉴스 보조 컨텍스트\n"
                "- 최근 연결 뉴스 없음 또는 조회 실패. 뉴스는 중립으로 보고 가격/수급/리스크를 우선 판단하세요."
            )

        lines.append(
            f"#### {i}. {d.get('stock_name', '')} ({d['symbol']})\n"
            f"- 매입가: {d.get('avg_price', 0):,.0f}원 → 현재가: {d.get('current_price', 0):,.0f}원\n"
            f"- 수익률: {pnl_rate:+.2f}%\n"
            f"- 보유수량: {d.get('quantity', 0)}주\n"
            f"- 보유일수: {d.get('hold_days', 0)}일 / 최대 {d.get('max_hold_days', 0)}일\n"
            f"- 호라이즌: {horizon} | 최소 보유 가드: {min_hold_text}\n"
            f"- AI 신뢰도: {d.get('confidence', 0):.2f}\n"
            f"- 목표가: {target_text} | 손절가: {stop_text}\n"
            f"- 현재 활성 익절가: {active_tp_text} | 활성 손절가: {active_sl_text}\n"
            f"- 전략 프로파일: {d.get('strategy_type', 'N/A')} (legacy 실행/위험 프로파일, 보유기간 아님)\n"
            f"{news_context}"
        )

    holdings_detail = "\n\n".join(lines) if lines else "보유종목 없음"
    regime_text = market_regime if market_regime else "정보 없음"
    context_text = market_context if market_context else "정보 없음"

    return HOLDINGS_REVIEW_PROMPT.format(
        market_regime=regime_text,
        market_context=context_text,
        minutes_left=minutes_left,
        holdings_detail=holdings_detail,
    )
