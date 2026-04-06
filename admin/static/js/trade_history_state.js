import { parseTradeNotes, resolveTradeExecutionState } from "./trade_status_state.js";

export { parseTradeNotes } from "./trade_status_state.js";

export function buildTradeCardViewModel(trade = {}, type = "opened") {
  const notes = parseTradeNotes(trade?.notes);
  const executionState = resolveTradeExecutionState({
    side: trade?.side || (type === "completed" ? "BUY" : ""),
    status: trade?.status,
    notes,
    hasExit: type === "completed",
  });
  const isPartialExit = executionState.code === "SELL_PARTIAL" || executionState.code === "BUY_PARTIALLY_CLOSED";
  const remainingOpenQuantity = executionState.remainingOpenQuantity || 0;

  return {
    isPartialExit,
    executionStateLabel: executionState.label,
    fillStatusLabel: isPartialExit
      ? `${executionState.label}${remainingOpenQuantity > 0 ? ` · 잔량 ${remainingOpenQuantity}주` : ""}`
      : (executionState.detailLabel || ""),
  };
}
