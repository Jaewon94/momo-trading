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

export function formatActivityHeadline(summary = "", meta = {}) {
  const stockName = meta.stockName || "";
  const normalizedSymbol = normalizeActivitySymbol(meta.symbol || "");
  const identity = stockName && stockName !== normalizedSymbol
    ? stockName
    : normalizedSymbol;
  const raw = String(summary || "").trim();
  if (!raw) return identity;

  let text = raw
    .replace(/^[^\p{L}\p{N}\[]+/u, "")
    .replace(/^\[[^\]]+\]\s*/u, "")
    .trim();

  if (!text) return identity;

  if (normalizedSymbol) {
    const escapedSymbol = normalizedSymbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const symbolPrefixPattern = new RegExp(`^(?:[Aa]?${escapedSymbol})\\s*[:|-]?\\s*`, "u");
    text = text.replace(symbolPrefixPattern, "").trim();
  }

  text = text
    .replace(/^Tier1\s+분석\s*/u, "분석 ")
    .replace(/^Tier2\s+최종 검토\s*/u, "최종 검토 ")
    .replace(/^Tier1\b\s*/u, "분석 ")
    .replace(/^Tier2\b\s*/u, "최종 검토 ")
    .replace(/^분석\s*:\s*/u, "분석 결과: ")
    .replace(/^최종 검토\s*:\s*/u, "최종 검토: ")
    .trim();

  if (!identity) return text;
  if (text.startsWith(identity)) return text;
  return `${identity} ${text}`.trim();
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
