function normalizeSymbol(value) {
  return String(value || "").replace(/^A/i, "").trim();
}

function normalizeList(value) {
  return Array.isArray(value) ? value : [];
}

function getSymbolEntry(map, symbol, tradingEnabled) {
  const normalized = normalizeSymbol(symbol);
  if (!normalized) return null;
  if (!map[normalized]) {
    map[normalized] = {
      symbol: normalized,
      name: normalized,
      holdingQuantity: 0,
      pendingBuyOrders: [],
      pendingSellOrders: [],
      tradingEnabled,
    };
  }
  return map[normalized];
}

export function buildManualTradeSymbolMap({
  holdings = [],
  pendingOrders = [],
  tradingEnabled = true,
} = {}) {
  const map = {};

  normalizeList(holdings).forEach((holding) => {
    const entry = getSymbolEntry(map, holding?.symbol, tradingEnabled);
    if (!entry) return;
    entry.name = holding?.name || entry.name;
    entry.holdingQuantity = Number(holding?.quantity || 0);
  });

  normalizeList(pendingOrders).forEach((order) => {
    const entry = getSymbolEntry(map, order?.symbol, tradingEnabled);
    if (!entry) return;
    entry.name = order?.name || entry.name;
    if (String(order?.side || "") === "매도") {
      entry.pendingSellOrders.push(order);
    } else {
      entry.pendingBuyOrders.push(order);
    }
  });

  Object.values(map).forEach((entry) => {
    entry.hasHolding = entry.holdingQuantity > 0;
    entry.hasPendingSell = entry.pendingSellOrders.length > 0;
    entry.hasPendingBuy = entry.pendingBuyOrders.length > 0;
  });

  return map;
}

export function getImmediateSellAction(symbol, symbolMap = {}) {
  const normalized = normalizeSymbol(symbol);
  const entry = symbolMap[normalized] || {
    symbol: normalized,
    holdingQuantity: 0,
    hasPendingSell: false,
    tradingEnabled: true,
  };

  if (!entry.tradingEnabled) {
    return {
      kind: "sell-now",
      label: "즉시 매도",
      disabled: true,
      reason: "실주문이 OFF 상태입니다.",
      quantity: entry.holdingQuantity || 0,
    };
  }

  if (!entry.holdingQuantity) {
    return {
      kind: "sell-now",
      label: "즉시 매도",
      disabled: true,
      reason: "보유 수량이 없습니다.",
      quantity: 0,
    };
  }

  if (entry.hasPendingSell) {
    return {
      kind: "sell-now",
      label: "매도 대기중",
      disabled: true,
      reason: "이미 매도 주문이 대기 중입니다.",
      quantity: entry.holdingQuantity,
      pendingSellOrderId: entry.pendingSellOrders[0]?.order_id || null,
    };
  }

  return {
    kind: "sell-now",
    label: "즉시 매도",
    disabled: false,
    reason: "",
    quantity: entry.holdingQuantity,
    hint: "시장가 주문도 일부 체결 후 잔량이 잠시 대기할 수 있습니다.",
  };
}

export function buildPendingOrderAction(order, symbolMap = {}) {
  const normalized = normalizeSymbol(order?.symbol);
  const entry = symbolMap[normalized] || {
    symbol: normalized,
    holdingQuantity: 0,
    tradingEnabled: true,
  };
  const isBuy = String(order?.side || "") === "매수";

  if (isBuy) {
    return {
      kind: "cancel-buy",
      label: "주문 취소",
      disabled: !entry.tradingEnabled,
      reason: entry.tradingEnabled ? "" : "실주문이 OFF 상태입니다.",
    };
  }

  if (!entry.tradingEnabled) {
    return {
      kind: "cancel-and-sell",
      label: "취소 후 즉시 매도",
      disabled: true,
      reason: "실주문이 OFF 상태입니다.",
    };
  }

  if (!entry.holdingQuantity) {
    return {
      kind: "cancel-and-sell",
      label: "취소 후 즉시 매도",
      disabled: true,
      reason: "보유 수량이 없어 재매도할 수 없습니다.",
    };
  }

  return {
    kind: "cancel-and-sell",
    label: "취소 후 즉시 매도",
    disabled: false,
    reason: "",
    quantity: entry.holdingQuantity,
    hint: "시장가 재매도도 일부 체결 후 잔량이 잠시 대기할 수 있습니다.",
  };
}
