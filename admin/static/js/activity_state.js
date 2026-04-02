function parseDetail(detail) {
  if (!detail || typeof detail !== "string") return null;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

export function normalizeActivitySymbol(symbol = "") {
  const raw = String(symbol || "").trim();
  const match = raw.match(/^[Aa](\d{6})$/);
  return match ? match[1] : raw;
}

function extractStockNameFromSummary(summary = "", symbol = "") {
  const normalizedSymbol = normalizeActivitySymbol(symbol);
  const isCodeToken = (value = "") => {
    const normalizedValue = normalizeActivitySymbol(value);
    return normalizedValue === normalizedSymbol || /^[Aa]?\d{6}$/.test(value);
  };

  const bracketMatch = summary.match(/\[([^\]]+)\]/);
  if (bracketMatch && bracketMatch[1] && !isCodeToken(bracketMatch[1])) {
    return bracketMatch[1];
  }

  if (normalizedSymbol) {
    const suffixPattern = new RegExp(`([^\\s()]+)\\(${normalizedSymbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\)`);
    const suffixMatch = summary.match(suffixPattern);
    if (suffixMatch && suffixMatch[1] && !isCodeToken(suffixMatch[1])) {
      return suffixMatch[1];
    }
  }

  return "";
}

export function buildStockMetaSummary(meta = {}) {
  const parts = [];

  if (Number.isFinite(meta.currentPrice) && meta.currentPrice > 0) {
    parts.push(`${Number(meta.currentPrice).toLocaleString()}원`);
  }
  if (Number.isFinite(meta.changeRate)) {
    const rate = Number(meta.changeRate);
    parts.push(`${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%`);
  } else if (Number.isFinite(meta.pnlRate)) {
    const rate = Number(meta.pnlRate);
    parts.push(`${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%`);
  }
  if (Number.isFinite(meta.quantity) && meta.quantity > 0) {
    parts.push(`${meta.quantity}주`);
  }

  return parts.join(" · ");
}

export function buildActivityIdentityLabel({
  symbol = "",
  stockName = "",
  summaryText = "",
} = {}) {
  const identity = [];
  const normalizedSymbol = normalizeActivitySymbol(symbol);

  if (stockName && stockName !== normalizedSymbol) {
    identity.push(`${stockName} (${normalizedSymbol})`);
  } else if (normalizedSymbol) {
    identity.push(normalizedSymbol);
  }

  if (summaryText) {
    identity.push(summaryText);
  }

  return identity.join(" · ");
}

export function resolveActivityStockMeta({
  symbol = "",
  summary = "",
  detail = null,
  knownNames = {},
  knownMeta = {},
} = {}) {
  const normalizedSymbol = normalizeActivitySymbol(symbol);
  const detailData = parseDetail(detail);
  const cachedMeta = knownMeta[normalizedSymbol] || knownMeta[symbol] || {};

  const stockName = extractStockNameFromSummary(summary, normalizedSymbol)
    || detailData?.stock_name
    || detailData?.name
    || knownNames[normalizedSymbol]
    || knownNames[symbol]
    || cachedMeta.stockName
    || normalizedSymbol;

  const summaryText = buildStockMetaSummary({
    currentPrice: detailData?.price ?? detailData?.current_price ?? cachedMeta.currentPrice,
    changeRate: detailData?.change_rate ?? cachedMeta.changeRate,
    pnlRate: cachedMeta.pnlRate,
    quantity: cachedMeta.quantity,
  });

  return {
    symbol: normalizedSymbol,
    stockName,
    summaryText,
  };
}
