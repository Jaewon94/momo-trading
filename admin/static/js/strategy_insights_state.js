export function summarizeStrategyEffects(effects = []) {
  return (effects || []).slice(0, 3).join(" · ");
}

function buildStrategyContext(settings = {}, selected = null) {
  const autonomyMode = settings?.AUTONOMY_MODE || "SEMI_AUTO";
  const dayTradingOnly = Boolean(settings?.DAY_TRADING_ONLY);

  return [
    {
      key: "risk_appetite",
      label: "리스크 성향",
      value: selected?.label || "중립",
      description: "AI가 오늘의 주문 한도와 현금 비율을 자율 조정할 때 기준으로 사용합니다.",
    },
    {
      key: "autonomy_mode",
      label: "주문 처리 방식",
      value: autonomyMode === "AUTONOMOUS" ? "즉시 자동 주문" : "추천 후 승인",
      description: autonomyMode === "AUTONOMOUS"
        ? "BUY/SELL 시그널을 즉시 주문으로 연결합니다."
        : "AI 시그널은 추천으로 남기고 승인 후 주문합니다. 단, 안전매도는 자동 실행될 수 있습니다.",
    },
    {
      key: "holding_policy",
      label: "보유 정책",
      value: dayTradingOnly ? "당일 청산" : "스윙 허용",
      description: dayTradingOnly
        ? "장 마감 전 포지션 정리를 우선하는 운용입니다."
        : "조건이 맞으면 장 종료 후에도 포지션을 이어갈 수 있습니다.",
    },
  ];
}

export function buildStrategyInsightsViewModel(settings = {}) {
  const strategyInsights = settings?.strategy_insights || {};
  const selectedKey = strategyInsights.selected_risk_appetite || settings?.RISK_APPETITE || "MODERATE";
  const selected = strategyInsights.risk_appetites?.[selectedKey] || null;
  const options = Object.entries(strategyInsights.risk_appetites || {}).map(([key, insight]) => ({
    key,
    ...insight,
    effectSummary: summarizeStrategyEffects(insight.system_effects),
    isSelected: key === selectedKey,
  }));

  return {
    selected: selected
      ? {
          key: selectedKey,
          ...selected,
          effectSummary: summarizeStrategyEffects(selected.system_effects),
        }
      : null,
    options,
    context: buildStrategyContext(settings, selected),
    notes: strategyInsights.notes || [],
  };
}
