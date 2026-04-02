export function buildTradeSummaryCounts(trades = {}) {
  const opened = trades?.opened || [];
  const completed = trades?.completed || [];
  const pendingConfirms = trades?.pending_confirms || [];

  return {
    todayTradeCount: opened.length + completed.length + pendingConfirms.length,
    pendingConfirmCount: pendingConfirms.length,
  };
}

export function buildTradePanelState(data = {}) {
  const opened = data?.opened || [];
  const completed = data?.completed || [];
  const pendingConfirms = data?.pending_confirms || [];
  const openPositions = data?.open_positions || [];
  const sections = [];

  if (completed.length) sections.push("completed");
  if (pendingConfirms.length) sections.push("pending_confirms");
  if (opened.length) sections.push("opened");
  if (openPositions.length) sections.push("open_positions");

  return {
    opened,
    completed,
    pendingConfirms,
    openPositions,
    todayCount: opened.length + completed.length + pendingConfirms.length,
    hasContent: sections.length > 0,
    sections,
  };
}
