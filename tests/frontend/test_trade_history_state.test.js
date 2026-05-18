import { describe, expect, test } from "vitest";

import { buildTradeCardViewModel, parseTradeNotes } from "../../admin/static/js/trade_history_state.js";

describe("trade_history_state", () => {
  test("parses json notes safely", () => {
    expect(parseTradeNotes('{"fill_type":"PARTIAL_EXIT","remaining_open_quantity":2}')).toMatchObject({
      fill_type: "PARTIAL_EXIT",
      remaining_open_quantity: 2,
    });
    expect(parseTradeNotes("not-json")).toEqual({});
  });

  test("builds partial exit label for completed trades", () => {
    const viewModel = buildTradeCardViewModel({
      notes: JSON.stringify({
        fill_type: "PARTIAL_EXIT",
        remaining_open_quantity: 2,
      }),
    }, "completed");

    expect(viewModel.isPartialExit).toBe(true);
    expect(viewModel.executionStateLabel).toBe("부분 매도");
    expect(viewModel.fillStatusLabel).toBe("부분 매도 후 정리 · 잔량 2주 보유 중");
  });

  test("keeps regular completed trades clean when no partial note exists", () => {
    const viewModel = buildTradeCardViewModel({ notes: null }, "completed");

    expect(viewModel.isPartialExit).toBe(false);
    expect(viewModel.executionStateLabel).toBe("매도 완료");
    expect(viewModel.fillStatusLabel).toBe("");
  });
});
