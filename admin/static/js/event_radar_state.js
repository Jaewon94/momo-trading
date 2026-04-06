import { resolveTradeExecutionState } from "./trade_status_state.js";

function formatScore(value) {
  return `${Number(value || 0)}점`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  const numeric = Number(value);
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function formatVolumeRatio(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value)) || Number(value) <= 0) return "";
  return `${Number(value).toFixed(1)}배`;
}

function formatTime(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function mapStateLabel(state = "") {
  const normalized = String(state || "").toUpperCase();
  if (normalized === "ACTIONABLE") return "즉시 대응";
  if (normalized === "COOLDOWN") return "쿨다운";
  if (normalized === "TRIGGERED") return "감지됨";
  return normalized || "이벤트";
}

function toneFromDirection(direction = "") {
  const normalized = String(direction || "").toUpperCase();
  if (normalized === "SELL") return "sell";
  if (normalized === "BUY") return "buy";
  return "watch";
}

export function buildEventRadarCard(event = {}) {
  const tone = toneFromDirection(event.direction);
  const changeRate = formatPercent(event.change_rate);
  const volumeRatio = formatVolumeRatio(event.volume_ratio);
  const metaLine = [changeRate, volumeRatio].filter(Boolean).join(" · ");
  const cooldownRemainingSec = Number(event.cooldown_remaining_sec || 0);

  return {
    ...event,
    tone,
    title: event.name ? `${event.name} (${event.symbol})` : event.symbol || "종목 미상",
    subtitle: event.event_label || event.event_type || "이벤트",
    scoreLabel: formatScore(event.score),
    stateLabel: mapStateLabel(event.state),
    cooldownLabel: cooldownRemainingSec > 0 ? `${cooldownRemainingSec}초 남음` : "",
    occurredTimeLabel: formatTime(event.occurred_at),
    metaLine,
  };
}

function buildFilters(cards = []) {
  return [
    { key: "all", label: "전체", count: cards.length },
    { key: "buy", label: "매수 후보", count: cards.filter((card) => card.tone === "buy").length },
    { key: "sell", label: "매도 후보", count: cards.filter((card) => card.tone === "sell").length },
    { key: "cooldown", label: "쿨다운", count: cards.filter((card) => String(card.state || "").toUpperCase() === "COOLDOWN").length },
  ];
}

export function buildEventRadarState(payload = {}) {
  const cards = (payload.events || []).map(buildEventRadarCard);
  const summary = payload.summary || {};

  return {
    cards,
    summaryPills: [
      { label: "실시간 이벤트", value: String(summary.total || cards.length || 0) },
      { label: "확인 대기", value: String(summary.cooldown || 0) },
      { label: "강한 매도 후보", value: String(summary.sell_candidates || 0) },
      { label: "강한 매수 후보", value: String(summary.buy_candidates || 0) },
    ],
    filters: buildFilters(cards),
    emptyMessage: "실시간 이벤트가 없습니다.",
  };
}

export function buildTradeStageLabel(snapshot = {}, symbol = "") {
  const data = snapshot || {};
  const trades = data?.trades || {};
  const pendingOrders = Array.isArray(data?.pendingOrders) ? data.pendingOrders : [];
  const opened = Array.isArray(trades?.opened) ? trades.opened : [];
  const completed = Array.isArray(trades?.completed) ? trades.completed : [];
  const pendingConfirms = Array.isArray(trades?.pending_confirms) ? trades.pending_confirms : [];
  const openPositions = Array.isArray(trades?.open_positions) ? trades.open_positions : [];

  const sameTradeSymbol = (value) => String(value || "").trim() === String(symbol || "").trim();
  if (!symbol) return "미진입";

  const pendingSell = pendingOrders.find((item) => sameTradeSymbol(item?.symbol) && String(item?.side || "") === "매도");
  if (pendingSell) {
    return resolveTradeExecutionState({ side: "SELL", status: "PENDING_CONFIRM", source: "order" }).label;
  }

  const pendingBuy = pendingOrders.find((item) => sameTradeSymbol(item?.symbol) && String(item?.side || "") === "매수");
  if (pendingBuy) {
    return resolveTradeExecutionState({ side: "BUY", status: "PENDING_CONFIRM", source: "order" }).label;
  }

  const pendingConfirm = pendingConfirms.find((item) => sameTradeSymbol(item?.stock_symbol));
  if (pendingConfirm) {
    return resolveTradeExecutionState({ side: pendingConfirm?.side || "BUY", status: pendingConfirm?.status || "PENDING_CONFIRM" }).label;
  }

  const openPosition = openPositions.find((item) => sameTradeSymbol(item?.stock_symbol));
  if (openPosition) {
    return resolveTradeExecutionState({
      side: openPosition?.side || "BUY",
      status: openPosition?.status || "CONFIRMED",
      isHolding: true,
    }).label;
  }

  const openedTrade = opened.find((item) => sameTradeSymbol(item?.stock_symbol));
  if (openedTrade) {
    return resolveTradeExecutionState({ side: openedTrade?.side || "BUY", status: openedTrade?.status || "CONFIRMED" }).label;
  }

  const completedTrade = completed.find((item) => sameTradeSymbol(item?.stock_symbol));
  if (completedTrade) {
    return resolveTradeExecutionState({
      side: completedTrade?.side || "BUY",
      status: completedTrade?.status || "CONFIRMED",
      notes: completedTrade?.notes,
      hasExit: true,
    }).label;
  }

  return "미진입";
}
