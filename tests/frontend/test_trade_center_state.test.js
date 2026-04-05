import { describe, expect, test } from "vitest";

import { buildTradeCenterState } from "../../admin/static/js/trade_center_state.js";

describe("trade_center_state", () => {
  test("builds tab counts and KPI values from trade payload", () => {
    const state = buildTradeCenterState({
      holdings: [
        { symbol: "011930", current_price: 1700, pnl: 12000, pnl_rate: 5.2 },
      ],
      pendingOrders: [
        { symbol: "215790", remaining_qty: 100, order_qty: 200, side: "매수" },
      ],
      trades: {
        date: "2026-04-05",
        opened: [{ stock_symbol: "011930", quantity: 10, entry_price: 1600 }],
        completed: [{ stock_symbol: "065440", pnl: 30000, return_pct: 3.4 }],
        pending_confirms: [{ stock_symbol: "011930", quantity: 5 }],
        open_positions: [{ stock_symbol: "011930", stock_name: "신성이엔지", quantity: 10, entry_price: 1600 }],
      },
    });

    expect(state.tabs).toEqual([
      { key: "pending", label: "대기", count: 2 },
      { key: "opened", label: "오늘 진입", count: 1 },
      { key: "completed", label: "오늘 청산", count: 1 },
      { key: "positions", label: "현재 보유", count: 1 },
    ]);

    expect(state.kpis).toEqual([
      { label: "오늘 거래", value: 3 },
      { label: "확인 대기", value: 1 },
      { label: "미체결 주문", value: 1 },
      { label: "보유 종목", value: 1 },
    ]);
  });

  test("aggregates open positions by symbol and merges holding pnl", () => {
    const state = buildTradeCenterState({
      holdings: [
        { symbol: "011930", current_price: 1700, pnl: 15000, pnl_rate: 6.4 },
      ],
      trades: {
        opened: [],
        completed: [],
        pending_confirms: [],
        open_positions: [
          { stock_symbol: "011930", stock_name: "신성이엔지", quantity: 5, entry_price: 1600 },
          { stock_symbol: "011930", stock_name: "신성이엔지", quantity: 10, entry_price: 1500 },
        ],
      },
    });

    expect(state.sections.positions).toEqual([
      {
        symbol: "011930",
        name: "신성이엔지",
        quantity: 15,
        avgPrice: 1533,
        currentPrice: 1700,
        pnl: 15000,
        pnlRate: 6.4,
      },
    ]);
  });
});
