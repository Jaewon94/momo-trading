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
