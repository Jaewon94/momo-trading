function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function normalizeTradeList(value) {
  return Array.isArray(value) ? value : [];
}

function groupOpenPositions(openPositions = [], holdings = []) {
  const grouped = {};
  normalizeTradeList(openPositions).forEach((trade) => {
    const symbol = trade?.stock_symbol;
    if (!symbol) return;
    if (!grouped[symbol]) {
      grouped[symbol] = {
        symbol,
        name: trade?.stock_name || symbol,
        quantity: 0,
        totalCost: 0,
      };
    }
    grouped[symbol].quantity += toNumber(trade?.quantity);
    grouped[symbol].totalCost += toNumber(trade?.entry_price) * toNumber(trade?.quantity);
  });

  const holdingBySymbol = {};
  normalizeTradeList(holdings).forEach((holding) => {
    if (!holding?.symbol) return;
    holdingBySymbol[holding.symbol] = holding;
  });

  return Object.values(grouped).map((item) => {
    const holding = holdingBySymbol[item.symbol];
    const avgPrice = item.quantity > 0 ? Math.round(item.totalCost / item.quantity) : 0;
    return {
      symbol: item.symbol,
      name: item.name,
      quantity: item.quantity,
      avgPrice,
      currentPrice: toNumber(holding?.current_price),
      pnl: toNumber(holding?.pnl),
      pnlRate: toNumber(holding?.pnl_rate),
    };
  });
}

export function buildTradeCenterState(payload = {}) {
  const trades = payload?.trades || {};
  const holdings = normalizeTradeList(payload?.holdings);
  const pendingOrders = normalizeTradeList(payload?.pendingOrders);
  const opened = normalizeTradeList(trades?.opened);
  const sellExecutions = normalizeTradeList(trades?.sell_executions);
  const completed = normalizeTradeList(trades?.completed);
  const pendingConfirms = normalizeTradeList(trades?.pending_confirms);
  const openPositions = groupOpenPositions(trades?.open_positions, holdings);

  const tabs = [
    { key: "pending", label: "대기", count: pendingConfirms.length + pendingOrders.length },
    { key: "opened", label: "오늘 진입", count: opened.length },
    { key: "sell-executions", label: "매도 체결", count: sellExecutions.length },
    { key: "completed", label: "전량 매도 완료", count: completed.length },
    { key: "positions", label: "현재 보유", count: openPositions.length },
  ];

  const kpis = [
    { label: "오늘 거래", value: opened.length + sellExecutions.length + pendingConfirms.length },
    { label: "매도 체결", value: sellExecutions.length },
    { label: "확인 대기", value: pendingConfirms.length },
    { label: "미체결 주문", value: pendingOrders.length },
    { label: "보유 종목", value: openPositions.length },
  ];

  return {
    date: trades?.date || null,
    tabs,
    kpis,
    sections: {
      pending: {
        pendingConfirms,
        pendingOrders,
      },
      opened,
      "sell-executions": sellExecutions,
      completed,
      positions: openPositions,
    },
  };
}
