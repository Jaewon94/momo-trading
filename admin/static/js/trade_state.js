export function buildTradeSummaryCounts(trades = {}) {
  const opened = trades?.opened || [];
  const sellExecutions = trades?.sell_executions || [];
  const pendingConfirms = trades?.pending_confirms || [];

  return {
    todayTradeCount: opened.length + sellExecutions.length + pendingConfirms.length,
    pendingConfirmCount: pendingConfirms.length,
    sellExecutionCount: sellExecutions.length,
  };
}

export function buildPortfolioQuickStatsModel(
  balance = {},
  holdings = [],
  pendingOrders = [],
  trades = {},
) {
  const totalAsset = Number(balance?.total_asset || 0);
  const unrealizedPnl = Number(balance?.total_pnl || 0);
  const unrealizedPnlRate = Number(balance?.total_pnl_rate || 0);
  const sessionMetrics = balance?.session_metrics || {};
  const sessionAvailable = sessionMetrics?.available === true;
  const cash = Number(balance?.cash || 0);
  const stockValue = Number(balance?.stock_value || 0);
  const cashRatio = totalAsset > 0 ? (cash / totalAsset) * 100 : 0;
  const holdingCount = Array.isArray(holdings) ? holdings.length : 0;
  const pendingCount = Array.isArray(pendingOrders) ? pendingOrders.length : 0;
  const opened = Array.isArray(trades?.opened) ? trades.opened : [];
  const sellExecutions = Array.isArray(trades?.sell_executions) ? trades.sell_executions : [];
  const completed = Array.isArray(trades?.completed) ? trades.completed : [];
  const fallbackRealizedTodayPnl = completed.reduce((sum, item) => sum + Number(item?.pnl || 0), 0);
  const realizedTodayPnl = sessionAvailable
    ? Number(sessionMetrics?.realized_today_pnl || 0)
    : fallbackRealizedTodayPnl;
  const tradeCounts = buildTradeSummaryCounts(trades);

  return {
    totalAsset,
    unrealizedPnl,
    unrealizedPnlRate,
    assetDelta: sessionAvailable ? Number(sessionMetrics?.asset_delta || 0) : 0,
    assetDeltaRate: sessionAvailable ? Number(sessionMetrics?.asset_delta_rate || 0) : 0,
    assetDeltaAvailable: sessionAvailable,
    dailyUnrealizedDelta: sessionAvailable ? Number(sessionMetrics?.daily_unrealized_delta || 0) : 0,
    dailyUnrealizedAvailable: sessionAvailable,
    intradayHighAsset: sessionAvailable
      ? Number(sessionMetrics?.intraday_high_asset || totalAsset)
      : totalAsset,
    intradayLowAsset: sessionAvailable
      ? Number(sessionMetrics?.intraday_low_asset || totalAsset)
      : totalAsset,
    baselineTotalAsset: sessionAvailable ? Number(sessionMetrics?.baseline_total_asset || 0) : 0,
    realizedTodayPnl,
    cash,
    stockValue,
    cashRatio,
    holdingCount,
    pendingCount,
    openedCount: opened.length,
    sellExecutionCount: tradeCounts.sellExecutionCount,
    completedCount: completed.length,
    unmatchedSellExecutions: Math.max(0, sellExecutions.length - completed.length),
  };
}

function formatWon(value, { signed = false } = {}) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return signed ? "+0원" : "0원";
  const rounded = Math.round(numeric);
  const prefix = signed && rounded > 0 ? "+" : "";
  return `${prefix}${rounded.toLocaleString()}원`;
}

function formatPercent(value, { signed = false, digits = 1 } = {}) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return signed ? "+0.0%" : "0.0%";
  const prefix = signed && numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(digits)}%`;
}

function toneFromNumber(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return "positive";
  if (numeric < 0) return "negative";
  return "neutral";
}

export function buildAccountOverviewModel(stats = {}) {
  const totalAsset = Number(stats?.totalAsset || 0);
  const cash = Number(stats?.cash || 0);
  const stockValue = Number(stats?.stockValue || 0);
  const cashRatio = totalAsset > 0 ? (cash / totalAsset) * 100 : 0;
  const stockRatio = totalAsset > 0 ? (stockValue / totalAsset) * 100 : 0;
  const pnlTone = toneFromNumber(stats?.unrealizedPnl);
  const realizedTodayTone = toneFromNumber(stats?.realizedTodayPnl);
  const totalAssetMeta = stats?.assetDeltaAvailable
    ? `장시작 대비 ${formatWon(stats.assetDelta, { signed: true })} / ${formatPercent(stats.assetDeltaRate, { signed: true, digits: 2 })}`
    : "장시작 기준선 대기";

  return {
    totalAssetLabel: formatWon(totalAsset),
    totalAssetMeta,
    assetDeltaTone: stats?.assetDeltaAvailable ? toneFromNumber(stats?.assetDelta) : "neutral",
    cashRatio,
    stockRatio,
    pnlLabel: formatWon(stats?.unrealizedPnl, { signed: true }),
    pnlTone,
    rows: [
      {
        label: "현금",
        value: formatWon(cash),
        meta: formatPercent(cashRatio),
        tone: "neutral",
      },
      {
        label: "주식 평가액",
        value: formatWon(stockValue),
        meta: formatPercent(stockRatio),
        tone: "neutral",
      },
      {
        label: "평가손익",
        value: formatWon(stats?.unrealizedPnl, { signed: true }),
        meta: formatPercent(stats?.unrealizedPnlRate, { digits: 2 }),
        tone: pnlTone,
      },
      {
        label: "당일 실현손익",
        value: formatWon(stats?.realizedTodayPnl, { signed: true }),
        meta: "청산 완료 기준",
        tone: realizedTodayTone,
      },
    ],
  };
}

export function buildTradePanelState(data = {}) {
  const opened = data?.opened || [];
  const sellExecutions = data?.sell_executions || [];
  const completed = data?.completed || [];
  const pendingConfirms = data?.pending_confirms || [];
  const openPositions = data?.open_positions || [];
  const sections = [];

  if (sellExecutions.length) sections.push("sell_executions");
  if (completed.length) sections.push("completed");
  if (pendingConfirms.length) sections.push("pending_confirms");
  if (opened.length) sections.push("opened");
  if (openPositions.length) sections.push("open_positions");

  return {
    opened,
    sellExecutions,
    completed,
    pendingConfirms,
    openPositions,
    todayCount: opened.length + sellExecutions.length + pendingConfirms.length,
    hasContent: sections.length > 0,
    sections,
  };
}
