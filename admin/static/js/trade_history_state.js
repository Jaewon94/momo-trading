import {
  buildTradeExecutionCopy,
  parseTradeNotes,
  resolveTradeExecutionState,
} from "./trade_status_state.js";

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
  const executionCopy = buildTradeExecutionCopy(executionState);

  return {
    isPartialExit,
    executionStateLabel: executionCopy.primaryLabel,
    fillStatusLabel: executionCopy.supportingLabel,
  };
}
