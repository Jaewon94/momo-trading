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
          realized_today_pnl: 35000,
          trading_date: "2026-04-22",
          baseline_at: "2026-04-22T09:00:03+09:00",
          latest_snapshot_at: "2026-04-22T13:04:18+09:00",
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
        { label: "주식 평가액", value: "341,909,010원", meta: "64.9% · 노출 64.9%" },
        { label: "평가손익", value: "-2,704,805원", meta: "-1.32%", tone: "negative" },
        { label: "당일 실현손익", value: "+35,000원", meta: "2026-04-22 09:00 ~ 13:04", tone: "positive" },
        { label: "현금/스냅샷 차이" },
      ],
    });
    expect(buildAccountOverviewModel(stats).rows.map((row) => row.label)).not.toContain("보유");
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
            broker_unrealized_pnl: 120000,
            daily_unrealized_delta: -5000,
            cash_or_snapshot_delta: -125000,
            current_exposure_krw: 770000,
            current_exposure_pct: 77,
            market_exposure: true,
            risk_label: "EXPOSED_PROFIT",
            risk_message: "보유 평가이익이 있으나 가격 변동 리스크는 열려 있습니다.",
            intraday_high_asset: 1015000,
            intraday_low_asset: 972000,
            latest_snapshot_at: "2026-04-22T13:04:18+09:00",
            snapshot_age_sec: 120,
            snapshot_freshness_status: "FRESH",
            snapshot_stale_blocks_buy: false,
            is_stale: false,
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
      brokerUnrealizedPnl: 120000,
      cashOrSnapshotDelta: -125000,
      currentExposureKrw: 770000,
      currentExposurePct: 77,
      marketExposure: true,
      riskLabel: "EXPOSED_PROFIT",
      realizedTodayPnl: 25000,
      intradayHighAsset: 1015000,
      intradayLowAsset: 972000,
      latestSnapshotAt: "2026-04-22T13:04:18+09:00",
      snapshotAgeSec: 120,
      snapshotFreshnessStatus: "FRESH",
      snapshotStaleBlocksBuy: false,
      snapshotIsStale: false,
    });
  });

  test("separates cash snapshot variance from market exposure when no holdings exist", () => {
    const stats = buildPortfolioQuickStatsModel(
      {
        total_asset: 995000,
        total_pnl: 0,
        total_pnl_rate: 0,
        cash: 995000,
        stock_value: 0,
        session_metrics: {
          available: true,
          asset_delta: -5000,
          asset_delta_rate: -0.5,
          realized_today_pnl: 0,
          broker_unrealized_pnl: 0,
          daily_unrealized_delta: -5000,
          cash_or_snapshot_delta: -5000,
          current_exposure_krw: 0,
          current_exposure_pct: 0,
          market_exposure: false,
          risk_label: "CASH_OR_SNAPSHOT_VARIANCE",
          risk_message: "현재 보유 노출은 없고, 장시작 대비 차이는 현금/정산/스냅샷성 변동으로 분리됩니다.",
        },
      },
      [],
      [],
      {},
    );

    const overview = buildAccountOverviewModel(stats);
    expect(overview.exposureTone).toBe("neutral");
    expect(overview.rows[1]).toMatchObject({ label: "주식 평가액", value: "0원", tone: "neutral" });
    expect(overview.rows[4]).toMatchObject({
      label: "현금/스냅샷 차이",
      value: "-5,000원",
      tone: "negative",
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
