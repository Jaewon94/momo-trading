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
  const cash = Number(balance?.cash || 0);
  const stockValue = Number(balance?.stock_value || 0);
  const cashRatio = totalAsset > 0 ? (cash / totalAsset) * 100 : 0;
  const holdingCount = Array.isArray(holdings) ? holdings.length : 0;
  const pendingCount = Array.isArray(pendingOrders) ? pendingOrders.length : 0;
  const opened = Array.isArray(trades?.opened) ? trades.opened : [];
  const sellExecutions = Array.isArray(trades?.sell_executions) ? trades.sell_executions : [];
  const completed = Array.isArray(trades?.completed) ? trades.completed : [];
  const realizedTodayPnl = completed.reduce((sum, item) => sum + Number(item?.pnl || 0), 0);
  const tradeCounts = buildTradeSummaryCounts(trades);

  return {
    totalAsset,
    unrealizedPnl,
    unrealizedPnlRate,
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
