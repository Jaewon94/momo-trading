import { describe, expect, test } from "vitest";

import {
  buildTradePanelState,
  buildTradeSummaryCounts,
} from "../../admin/static/js/trade_state.js";

describe("trade_state", () => {
  test("includes pending confirms in today count and sections", () => {
    const state = buildTradePanelState({
      opened: [{ stock_symbol: "005930" }],
      sell_executions: [{ stock_symbol: "005930", side: "SELL" }],
      completed: [],
      pending_confirms: [{ stock_symbol: "003280" }],
      open_positions: [{ stock_symbol: "215790" }],
    });

    expect(state.todayCount).toBe(3);
    expect(state.hasContent).toBe(true);
    expect(state.sections).toEqual(["sell_executions", "pending_confirms", "opened", "open_positions"]);
  });

  test("builds quick stats counts including pending confirms", () => {
    expect(
      buildTradeSummaryCounts({
        opened: [{}, {}],
        sell_executions: [{}],
        pending_confirms: [{}],
      }),
    ).toEqual({
      todayTradeCount: 4,
      pendingConfirmCount: 1,
      sellExecutionCount: 1,
    });
  });
});
