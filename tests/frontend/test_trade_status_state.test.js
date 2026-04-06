import { describe, expect, test } from "vitest";

import {
  parseTradeNotes,
  resolveTradeExecutionState,
} from "../../admin/static/js/trade_status_state.js";

describe("trade_status_state", () => {
  test("parses trade notes safely", () => {
    expect(parseTradeNotes('{"fill_type":"PARTIAL_EXIT"}')).toEqual({ fill_type: "PARTIAL_EXIT" });
    expect(parseTradeNotes("not-json")).toEqual({});
  });

  test("resolves completed buy with partial exit as archived partial-close state", () => {
    const state = resolveTradeExecutionState({
      side: "BUY",
      status: "CONFIRMED",
      notes: { fill_type: "PARTIAL_EXIT", remaining_open_quantity: 2 },
      hasExit: true,
    });

    expect(state.code).toBe("BUY_PARTIALLY_CLOSED");
    expect(state.label).toBe("부분 매도 후 정리");
    expect(state.badge).toBe("PARTIAL_EXIT");
    expect(state.detailLabel).toBe("잔량 2주 보유 중");
  });

  test("resolves pending sell as sell-pending state", () => {
    const state = resolveTradeExecutionState({
      side: "SELL",
      status: "PENDING_CONFIRM",
    });

    expect(state.code).toBe("SELL_PENDING");
    expect(state.label).toBe("매도 대기중");
  });

  test("distinguishes submitted orders from confirm-pending trades", () => {
    const buySubmitted = resolveTradeExecutionState({
      side: "BUY",
      status: "PENDING_CONFIRM",
      source: "order",
    });
    const sellSubmitted = resolveTradeExecutionState({
      side: "SELL",
      status: "PENDING_CONFIRM",
      source: "order",
    });

    expect(buySubmitted.code).toBe("BUY_SUBMITTED");
    expect(buySubmitted.label).toBe("매수 접수중");
    expect(sellSubmitted.code).toBe("SELL_SUBMITTED");
    expect(sellSubmitted.label).toBe("매도 접수중");
  });

  test("marks open confirmed buys as holding state when requested", () => {
    const state = resolveTradeExecutionState({
      side: "BUY",
      status: "CONFIRMED",
      isHolding: true,
    });

    expect(state.code).toBe("BUY_HOLDING");
    expect(state.label).toBe("보유 중");
  });

  test("resolves closed buy lot without remaining quantity as final-close state", () => {
    const state = resolveTradeExecutionState({
      side: "BUY",
      status: "CONFIRMED",
      hasExit: true,
    });

    expect(state.code).toBe("BUY_CLOSED");
    expect(state.label).toBe("최종 청산 lot");
    expect(state.badge).toBe("FINAL_EXIT");
  });
});
