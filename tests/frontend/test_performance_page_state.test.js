import { describe, expect, test } from "vitest";

import { buildPerformanceDashboardState } from "../../admin/static/js/performance_page_state.js";

describe("performance_page_state", () => {
  test("builds dashboard cards, by-horizon rows, and period rows", () => {
    const state = buildPerformanceDashboardState({
      summary: {
        overall: {
          trade_count: 18,
          expectancy: 1200,
          profit_factor: 1.42,
          max_drawdown: -320000,
          net_pnl_after_cost: 210000,
        },
        by_horizon: {
          SHORT: { trade_count: 7, expectancy: 500, profit_factor: 1.1, total_pnl: 60000 },
          MID: { trade_count: 8, expectancy: 1800, profit_factor: 1.7, total_pnl: 120000 },
        },
        by_strategy: {
          STABLE_SHORT: { trade_count: 10, expectancy: 1400, profit_factor: 1.5, total_pnl: 150000 },
        },
        shadow: {
          candidate_count: 24,
          blocked_by_news_count: 6,
          block_rate: 0.25,
        },
        rollout: {
          status: "PROMOTE",
          reason: "비중 확대 권장",
        },
        comparisons: {
          news_enriched: { trade_count: 11, expectancy: 1500, profit_factor: 1.6, total_pnl: 170000 },
          plain: { trade_count: 7, expectancy: 800, profit_factor: 1.2, total_pnl: 40000 },
          delta: { expectancy: 700, profit_factor: 0.4, net_pnl_after_cost: 130000 },
        },
      },
      weekly: {
        buckets: [
          { end: "2026-04-06", metrics: { expectancy: 820, total_pnl: 45000, profit_factor: 1.2 } },
        ],
      },
      monthly: {
        buckets: [
          { end: "2026-04-01", metrics: { expectancy: 640, total_pnl: 125000, profit_factor: 1.35 } },
        ],
      },
      newsOverview: {
        performance: {
          news_gate_blocks: 4,
          news_rechecks: 7,
          avg_negative_pressure: 0.31,
        },
      },
    });

    expect(state.summaryCards).toHaveLength(6);
    expect(state.summaryCards[0]).toMatchObject({ label: "총 거래", value: "18건" });
    expect(state.summaryCards[1]).toMatchObject({ label: "기대값", value: "+1,200원" });
    expect(state.rollout.status).toBe("PROMOTE");
    expect(state.newsOps.newsGateBlocks).toBe("4회");
    expect(state.comparisonRows[0].label).toBe("뉴스 반영 거래");
    expect(state.comparisonRows[1].label).toBe("일반 거래");
    expect(state.comparisonDelta.expectancy).toBe("+700원");
    expect(state.byHorizonRows[0].label).toBe("MID");
    expect(state.byStrategyRows[0].label).toBe("STABLE_SHORT");
    expect(state.weeklyRows[0].periodLabel).toBe("2026-04-06");
    expect(state.monthlyRows[0].totalPnl).toBe("+125,000원");
  });

  test("returns empty-friendly defaults", () => {
    const state = buildPerformanceDashboardState({});

    expect(state.summaryCards[0]).toMatchObject({ value: "0건" });
    expect(state.comparisonRows).toHaveLength(2);
    expect(state.byHorizonRows).toEqual([]);
    expect(state.weeklyRows).toEqual([]);
    expect(state.rollout.status).toBe("HOLDOUT");
  });
});
