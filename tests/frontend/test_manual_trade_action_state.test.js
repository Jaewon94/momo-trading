import { describe, expect, test } from "vitest";

import {
  buildManualTradeSupportViewModel,
  buildManualTradeSymbolMap,
  buildPendingOrderAction,
  getImmediateSellAction,
} from "../../admin/static/js/manual_trade_action_state.js";

describe("manual_trade_action_state", () => {
  test("enables immediate sell when holdings exist and no pending sell exists", () => {
    const symbolMap = buildManualTradeSymbolMap({
      holdings: [{ symbol: "005930", quantity: 7, name: "삼성전자" }],
      pendingOrders: [],
      tradingEnabled: true,
      runtimeSystemStatus: {
        market_open: true,
        market_session_label: "정규장",
        broker_capabilities: { supported_order_sessions: ["REGULAR"] },
      },
    });

    const action = getImmediateSellAction("005930", symbolMap);

    expect(action).toMatchObject({
      kind: "sell-now",
      disabled: false,
      quantity: 7,
      label: "즉시 매도",
    });
    expect(action.hint).toContain("잔량");
  });

  test("disables immediate sell when pending sell already exists", () => {
    const symbolMap = buildManualTradeSymbolMap({
      holdings: [{ symbol: "005930", quantity: 7, name: "삼성전자" }],
      pendingOrders: [{ order_id: "S-1", symbol: "005930", side: "매도", remaining_qty: 7 }],
      tradingEnabled: true,
      runtimeSystemStatus: {
        market_open: true,
        market_session_label: "정규장",
        broker_capabilities: { supported_order_sessions: ["REGULAR"] },
      },
    });

    const action = getImmediateSellAction("005930", symbolMap);

    expect(action.disabled).toBe(true);
    expect(action.reason).toContain("매도 주문");
  });

  test("builds cancel action for pending buy orders", () => {
    const symbolMap = buildManualTradeSymbolMap({
      holdings: [],
      pendingOrders: [{ order_id: "B-1", symbol: "215790", side: "매수", remaining_qty: 100 }],
      tradingEnabled: true,
      runtimeSystemStatus: {
        market_open: false,
        market_session_label: "장외",
        broker_capabilities: { supported_order_sessions: ["REGULAR"] },
      },
    });

    const action = buildPendingOrderAction(
      { order_id: "B-1", symbol: "215790", side: "매수", remaining_qty: 100 },
      symbolMap,
    );

    expect(action).toMatchObject({
      kind: "cancel-buy",
      label: "주문 취소",
      disabled: false,
    });
  });

  test("builds cancel-and-sell action for pending sell orders", () => {
    const symbolMap = buildManualTradeSymbolMap({
      holdings: [{ symbol: "005930", quantity: 5 }],
      pendingOrders: [{ order_id: "S-1", symbol: "005930", side: "매도", remaining_qty: 5 }],
      tradingEnabled: true,
      runtimeSystemStatus: {
        market_open: true,
        market_session_label: "정규장",
        broker_capabilities: { supported_order_sessions: ["REGULAR"] },
      },
    });

    const action = buildPendingOrderAction(
      { order_id: "S-1", symbol: "005930", side: "매도", remaining_qty: 5 },
      symbolMap,
    );

    expect(action).toMatchObject({
      kind: "cancel-and-sell",
      label: "취소 후 즉시 매도",
      disabled: false,
    });
    expect(action.hint).toContain("잔량");
  });

  test("disables immediate sell outside the regular session", () => {
    const symbolMap = buildManualTradeSymbolMap({
      holdings: [{ symbol: "005930", quantity: 7, name: "삼성전자" }],
      pendingOrders: [],
      tradingEnabled: true,
      runtimeSystemStatus: {
        market_open: false,
        market_session_label: "장외",
        broker_capabilities: { supported_order_sessions: ["REGULAR"] },
      },
    });

    const action = getImmediateSellAction("005930", symbolMap);

    expect(action.disabled).toBe(true);
    expect(action.reason).toContain("현재 세션(장외)");
  });

  test("builds manual trade support summary from runtime session and broker capabilities", () => {
    const support = buildManualTradeSupportViewModel({
      market_open: false,
      market_session_label: "장외",
      broker_capabilities: { supported_order_sessions: ["REGULAR"] },
    });

    expect(support.regularReady).toBe(false);
    expect(support.summary).toContain("현재 세션: 장외");
    expect(support.summary).toContain("REGULAR");
    expect(support.detail).toContain("시간외단일가");
  });
});
