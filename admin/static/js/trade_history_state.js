function safeParseJson(value) {
  if (!value || typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function parseTradeNotes(notes) {
  const parsed = safeParseJson(notes);
  return parsed && typeof parsed === "object" ? parsed : {};
}

export function buildTradeCardViewModel(trade = {}, type = "opened") {
  const notes = parseTradeNotes(trade?.notes);
  const isPartialExit = type === "completed" && String(notes?.fill_type || "").toUpperCase() === "PARTIAL_EXIT";
  const remainingOpenQuantity = Number(notes?.remaining_open_quantity || 0);

  return {
    isPartialExit,
    fillStatusLabel: isPartialExit
      ? `부분 매도${remainingOpenQuantity > 0 ? ` · 잔량 ${remainingOpenQuantity}주` : ""}`
      : "",
  };
}
