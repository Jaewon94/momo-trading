import { describe, expect, test } from "vitest";

import {
  buildAccountOverviewModel,
  buildPortfolioQuickStatsModel,
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

  test("builds portfolio quick stats with separate unrealized and today's realized pnl", () => {
    expect(
      buildPortfolioQuickStatsModel(
        {
          total_asset: 1000000,
          total_pnl: 120000,
          total_pnl_rate: 12,
          cash: 250000,
          stock_value: 750000,
        },
        [{}, {}],
        [{}],
        {
          opened: [{}, {}],
          sell_executions: [{}],
          completed: [{ pnl: 30000 }, { pnl: -5000 }],
        },
      ),
    ).toMatchObject({
      totalAsset: 1000000,
      unrealizedPnl: 120000,
      unrealizedPnlRate: 12,
      realizedTodayPnl: 25000,
      cashRatio: 25,
      holdingCount: 2,
      pendingCount: 1,
      openedCount: 2,
      sellExecutionCount: 1,
      completedCount: 2,
      unmatchedSellExecutions: 0,
    });
  });

  test("builds precise account overview labels without large-unit abbreviation", () => {
    const stats = buildPortfolioQuickStatsModel(
      {
        total_asset: 527064565,
        total_pnl: -2704805,
        total_pnl_rate: -1.32,
        cash: 181724859,
        stock_value: 341909010,
        session_metrics: {
          available: true,
          asset_delta: -7942186,
          asset_delta_rate: -2.29,
        },
      },
      [{}, {}, {}, {}, {}, {}],
      [{}, {}],
      {},
    );

    expect(buildAccountOverviewModel(stats)).toMatchObject({
      totalAssetLabel: "527,064,565원",
      totalAssetMeta: "장시작 대비 -7,942,186원 / -2.29%",
      pnlLabel: "-2,704,805원",
      pnlTone: "negative",
      rows: [
        { label: "현금", value: "181,724,859원", meta: "34.5%" },
        { label: "주식 평가액", value: "341,909,010원", meta: "64.9%" },
        { label: "보유", value: "6종목", meta: "미체결 2건" },
        { label: "평가손익", value: "-2,704,805원", meta: "-1.32%", tone: "negative" },
      ],
    });
  });

  test("uses session metrics for day-session asset and unrealized movement", () => {
    expect(
      buildPortfolioQuickStatsModel(
        {
          total_asset: 1000000,
          total_pnl: 120000,
          total_pnl_rate: 12,
          cash: 230000,
          stock_value: 770000,
          session_metrics: {
            available: true,
            baseline_total_asset: 980000,
            asset_delta: 20000,
            asset_delta_rate: 2.04,
            realized_today_pnl: 25000,
            daily_unrealized_delta: -5000,
            intraday_high_asset: 1015000,
            intraday_low_asset: 972000,
          },
        },
        [{}],
        [],
        {
          completed: [{ pnl: 999999 }],
        },
      ),
    ).toMatchObject({
      totalAsset: 1000000,
      assetDelta: 20000,
      assetDeltaRate: 2.04,
      assetDeltaAvailable: true,
      dailyUnrealizedDelta: -5000,
      dailyUnrealizedAvailable: true,
      realizedTodayPnl: 25000,
      intradayHighAsset: 1015000,
      intradayLowAsset: 972000,
    });
  });

  test("falls back safely when session metrics are unavailable", () => {
    expect(
      buildPortfolioQuickStatsModel(
        {
          total_asset: 1000000,
          total_pnl: 120000,
          total_pnl_rate: 12,
          cash: 250000,
          stock_value: 750000,
          session_metrics: {
            available: false,
          },
        },
        [],
        [],
        {
          completed: [{ pnl: 30000 }, { pnl: -5000 }],
        },
      ),
    ).toMatchObject({
      assetDelta: 0,
      assetDeltaRate: 0,
      assetDeltaAvailable: false,
      dailyUnrealizedDelta: 0,
      dailyUnrealizedAvailable: false,
      realizedTodayPnl: 25000,
      intradayHighAsset: 1000000,
      intradayLowAsset: 1000000,
    });
  });
});
