from analysis.llm.prompts.risk_tuning import RISK_APPETITE_GUIDELINES


RISK_APPETITE_INSIGHTS = {
    "CONSERVATIVE": {
        "label": "보수적",
        "headline": "확실한 시그널 위주로 작게 진입합니다.",
        "description": "현금을 더 두껍게 유지하고, 손실 변동성을 낮추는 방향으로 매매 한도를 좁힙니다.",
        "system_effects": [
            "AI 자율 한도 결정에 반영",
            "현금 비율 가이드 40% 이상",
            "일일 거래 횟수 5~10회 기준",
            "포지션 크기를 더 작게 제한하는 방향",
        ],
    },
    "MODERATE": {
        "label": "중립",
        "headline": "기회를 놓치지 않되 과도한 공격도 피합니다.",
        "description": "현금, 포지션, 거래 횟수를 균형형으로 잡아 일반적인 장세에서 무리 없는 기본 운용을 목표로 합니다.",
        "system_effects": [
            "AI 자율 한도 결정에 반영",
            "현금 비율 가이드 25% 이상",
            "일일 거래 횟수 10~20회 기준",
            "포지션 크기를 균형형으로 조정",
        ],
    },
    "AGGRESSIVE": {
        "label": "공격적",
        "headline": "현금보다 기회 포착을 우선합니다.",
        "description": "강한 모멘텀을 빠르게 따라가도록 한도를 넓게 잡고, 현금 비중도 낮게 허용합니다.",
        "system_effects": [
            "AI 자율 한도 결정에 반영",
            "현금 비율 0%도 허용 가능",
            "일일 거래 횟수 제한 없음",
            "포지션 크기를 더 크게 허용하는 방향",
        ],
    },
}


def build_strategy_insights(selected_risk_appetite: str) -> dict:
    selected_key = selected_risk_appetite if selected_risk_appetite in RISK_APPETITE_INSIGHTS else "MODERATE"
    risk_appetites = {}

    for key, info in RISK_APPETITE_INSIGHTS.items():
        risk_appetites[key] = {
            **info,
            "guideline": RISK_APPETITE_GUIDELINES[key],
        }

    return {
        "selected_risk_appetite": selected_key,
        "risk_appetites": risk_appetites,
        "notes": [
            "리스크 성향은 전략 문구가 아니라 AI 자율 한도 결정 입력값입니다.",
            "계좌 상태와 최근 성과를 함께 보고 일일 거래 수, 주문 한도, 포지션 비중, 최소 현금 비율을 조정합니다.",
        ],
    }
