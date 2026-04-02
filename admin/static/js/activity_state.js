function parseDetail(detail) {
  if (!detail || typeof detail !== "string") return null;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function extractStockNameFromSummary(summary = "", symbol = "") {
  const bracketMatch = summary.match(/\[([^\]]+)\]/);
  if (bracketMatch && bracketMatch[1] && bracketMatch[1] !== symbol) {
    return bracketMatch[1];
  }

  if (symbol) {
    const suffixPattern = new RegExp(`([^\\s()]+)\\(${symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\)`);
    const suffixMatch = summary.match(suffixPattern);
    if (suffixMatch && suffixMatch[1] && suffixMatch[1] !== symbol) {
      return suffixMatch[1];
    }
  }

  return "";
}

export function resolveActivityStockMeta({
  symbol = "",
  summary = "",
  detail = null,
  knownNames = {},
} = {}) {
  const detailData = parseDetail(detail);
  const stockName = extractStockNameFromSummary(summary, symbol)
    || detailData?.stock_name
    || detailData?.name
    || knownNames[symbol]
    || symbol;

  return {
    symbol,
    stockName,
  };
}
