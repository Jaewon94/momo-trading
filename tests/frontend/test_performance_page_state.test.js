import { describe, expect, test } from "vitest";

import { buildPerformanceDashboardState } from "../../admin/static/js/performance_page_state.js";

describe("performance_page_state", () => {
  test("builds dashboard cards, by-horizon rows, and period rows", () => {
    const state = buildPerformanceDashboardState({
      summary: {
        baseline: {
          active: true,
          effective_date: "2026-04-06",
          label: "2026-04-06 기준선 리셋 이후 데이터",
          summary: "현재 브로커 계좌 상태와 복구된 열린 BUY lot를 기준선으로 사용 중",
          details: ["현재 보유 종목/수량은 브로커 응답 기준"],
        },
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
          actual_buy_count: 18,
          baseline_buy_count: 22,
        },
        rollout: {
          status: "PROMOTE",
          reason: "비중 확대 권장",
          details: ["Shadow 후보 24건 · 실제 BUY 18건 · 기준 BUY 22건"],
          checks: [
            { key: "sample", label: "표본", passed: true, actual: "실거래 18건 / Shadow 24건", target: "각 12건 이상" },
          ],
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
    expect(state.baseline.active).toBe(true);
    expect(state.baseline.effectiveDate).toBe("2026-04-06");
    expect(state.summaryCards[0]).toMatchObject({ label: "총 거래", value: "18건" });
    expect(state.summaryCards[1]).toMatchObject({ label: "기대값", value: "+1,200원" });
    expect(state.rollout.status).toBe("PROMOTE");
    expect(state.rollout.details[0]).toContain("Shadow 후보 24건");
    expect(state.rollout.checks[0]).toMatchObject({ key: "sample", passed: true });
    expect(state.shadowSummaryRows[2]).toMatchObject({ label: "실제 BUY", value: "18건" });
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
    expect(state.shadowSummaryRows[0].value).toBe("0건");
    expect(state.baseline.active).toBe(false);
  });
});
