import { describe, expect, test } from "vitest";

import {
  buildAccountOverviewModel,
  buildAccountSessionDetailModel,
  buildPortfolioQuickStatsModel,
  buildTradePanelState,
  buildTradeSummaryCounts,
  isNeutralReconciliationClose,
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

  test("filters neutral reconciliation closes from trade panel display state", () => {
    const state = buildTradePanelState({
      opened: [
        { stock_symbol: "005930", exit_reason: "" },
        {
          stock_symbol: "003280",
          exit_reason: "BROKER_HOLDING_MISSING",
          notes: "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        },
      ],
      sell_executions: [],
      completed: [
        { stock_symbol: "005930", pnl: 12000, exit_reason: "TAKE_PROFIT" },
        {
          stock_symbol: "003280",
          pnl: 0,
          exit_reason: "BROKER_HOLDING_MISSING",
          notes: "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
        },
      ],
      pending_confirms: [],
      open_positions: [],
    });

    expect(state.opened.map((trade) => trade.stock_symbol)).toEqual(["005930"]);
    expect(state.completed.map((trade) => trade.stock_symbol)).toEqual(["005930"]);
    expect(state.sections).toEqual(["completed", "opened"]);
  });

  test("recognizes neutral reconciliation closes but keeps applied corrections visible", () => {
    expect(isNeutralReconciliationClose({
      notes: "HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
    })).toBe(true);
    expect(isNeutralReconciliationClose({
      notes: "CLOSE_RECONCILIATION_APPLY: previous=HOLDING_RECONCILIATION_CLOSE: broker holding missing; neutral close",
    })).toBe(false);
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

  test("builds portfolio quick stats without surfacing local realized pnl", () => {
    const stats = buildPortfolioQuickStatsModel(
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
    );

    expect(stats).toMatchObject({
      totalAsset: 1000000,
      unrealizedPnl: 120000,
      unrealizedPnlRate: 12,
      cashRatio: 25,
      holdingCount: 2,
      pendingCount: 1,
      openedCount: 2,
      sellExecutionCount: 1,
      completedCount: 2,
      unmatchedSellExecutions: 0,
    });
    // session_metrics가 없으면 realizedTodayPnl은 0이어야 한다.
    // (로컬 completed trades의 pnl 합산 25,000원이 stats로 새어 들어가면 안 된다.)
    expect(stats.realizedTodayPnl).toBe(0);
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

    const overview = buildAccountOverviewModel(stats);
    expect(overview).toMatchObject({
      totalAssetLabel: "527,064,565원",
      totalAssetMeta: "장시작 대비 -7,942,186원 / -2.29%",
      pnlLabel: "-2,704,805원",
      pnlTone: "negative",
    });
    // 메인 카드는 핵심 3개 row만 노출하고 정산 잔차 같은 진단 지표는 빼야 한다.
    expect(overview.rows).toHaveLength(3);
    expect(overview.rows.map((row) => row.label)).toEqual([
      "현금",
      "주식 평가액",
      "평가손익",
    ]);
    expect(overview.rows.map((row) => row.label)).not.toContain("현금/스냅샷 차이");
    expect(overview.rows.map((row) => row.label)).not.toContain("보유");
    expect(overview.rows.map((row) => row.label)).not.toContain("당일 실현손익");
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
    // 정산 잔차는 메인 row가 아닌 진단 모델에서 노출되어야 한다.
    expect(overview.rows.map((row) => row.label)).not.toContain("현금/스냅샷 차이");
    const detail = buildAccountSessionDetailModel(stats);
    expect(detail.available).toBe(true);
    const varianceRow = detail.rows.find((row) => row.label === "정산 잔차");
    expect(varianceRow).toMatchObject({
      value: "-5,000원",
      tone: "negative",
    });
  });

  test("buildAccountSessionDetailModel 은 장시작 대비를 매매와 잔차로 분해한다", () => {
    const stats = buildPortfolioQuickStatsModel(
      {
        total_asset: 474_324_783,
        total_pnl: -129_906,
        total_pnl_rate: -0.03,
        cash: 462_287_232,
        stock_value: 12_037_551,
        session_metrics: {
          available: true,
          baseline_at: "2026-05-28T09:00:00+09:00",
          baseline_total_asset: 475_824_563,
          asset_delta: -1_499_780,
          asset_delta_rate: -0.32,
          realized_today_pnl: -2_385_080,
          broker_unrealized_pnl: -129_906,
          daily_unrealized_delta: 885_300,
          cash_or_snapshot_delta: 1_015_206,
          current_exposure_krw: 12_037_551,
          current_exposure_pct: 2.5,
          market_exposure: true,
          risk_message: "보유 평가손실이 있어 가격 변동 리스크가 열려 있습니다.",
        },
      },
      [{}],
      [],
      {},
    );

    const detail = buildAccountSessionDetailModel(stats);
    expect(detail.available).toBe(true);
    expect(detail.title).toBe("오늘 자산 변화 분석");
    const byLabel = Object.fromEntries(detail.rows.map((row) => [row.label, row]));
    expect(byLabel["장시작 대비"]).toMatchObject({ value: "-1,499,780원", tone: "negative" });
    expect(byLabel["오늘 실현 손익"]).toMatchObject({ value: "-2,385,080원", tone: "negative" });
    expect(byLabel["현재 평가손익"]).toMatchObject({ value: "-129,906원", tone: "negative" });
    expect(byLabel["정산 잔차"]).toMatchObject({ value: "+1,015,206원", tone: "positive" });
    expect(detail.footnote).toMatch(/정산 잔차/);
  });

  test("buildAccountSessionDetailModel 은 session 정보 없을 때 안전한 기본값을 반환한다", () => {
    const stats = buildPortfolioQuickStatsModel(
      { total_asset: 100_000, cash: 100_000, stock_value: 0 },
      [],
      [],
      {},
    );
    const detail = buildAccountSessionDetailModel(stats);
    expect(detail.available).toBe(false);
    expect(detail.rows).toEqual([]);
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
      intradayHighAsset: 1000000,
      intradayLowAsset: 1000000,
    });
  });
});
