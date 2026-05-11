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
        current_account: {
          synced: true,
          unrealized_pnl: -2704805,
          unrealized_pnl_rate: -1.32,
          holding_count: 4,
          pending_order_count: 1,
          total_asset: 527064565,
        },
        pnl_truth: {
          account_pnl_sample_status: "UNRECONCILED_ACCOUNT_PNL",
          sample_status: "OK",
          pnl_reconciliation_status: "UNEXPLAINED_ASSET_DELTA",
          total_asset_delta: -3781680,
          cash_or_snapshot_delta: -3781680,
          unrealized_broker_pnl: 0,
          pnl_reconciliation_message: "총자산 변화 중 설명되지 않는 차이가 있습니다.",
        },
        metric_contract: {
          sample_status: "UNRECONCILED_ACCOUNT_PNL",
          closed_trade_sample_status: "OK",
          pnl_reconciliation_status: "UNEXPLAINED_ASSET_DELTA",
        },
        data_quality: {
          closed_trade_rows: 90,
          excluded_reconciliation_close_rows: 72,
          performance_trade_count: 18,
          excluded_reconciliation_close_reason: "neutral close rows are not performance",
        },
        by_horizon: {
          SHORT: { trade_count: 7, expectancy: 500, profit_factor: 1.1, total_pnl: 60000 },
          MID: { trade_count: 8, expectancy: 1800, profit_factor: 1.7, total_pnl: 120000 },
        },
        by_strategy: {
          STABLE_SHORT: { trade_count: 10, expectancy: 1400, profit_factor: 1.5, total_pnl: 150000 },
        },
        by_execution_profile: {
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
          { end: "2026-04-13", metrics: { expectancy: 1200, total_pnl: 75000, profit_factor: 1.6 } },
        ],
      },
      monthly: {
        buckets: [
          { end: "2026-04-01", metrics: { expectancy: 640, total_pnl: 125000, profit_factor: 1.35 } },
          { end: "2026-05-01", metrics: { expectancy: -200, total_pnl: -5000, profit_factor: 0.8 } },
        ],
      },
      newsOverview: {
        performance: {
          news_gate_blocks: 4,
          news_rechecks: 7,
          avg_negative_pressure: 0.31,
        },
      },
      lifecycle: {
        status: "WARN",
        window: { days: 7 },
        message: "성과 반영 전에 확인해야 할 거래 흐름이 있습니다.",
        summary: {
          pending_confirm_count: 1,
          confirm_failed_count: 0,
          account_baseline_count: 1,
          account_equity_snapshot_count: 1,
          open_buy_count: 2,
          unpaired_sell_count: 3,
          broker_missing_open_buy_count: 1,
          repairable_sell_count: 1,
          performance_trade_count: 18,
        },
        checks: [
          { key: "pending_confirms", label: "주문 확인 대기", status: "WARN", actual: "1건", target: "0건" },
        ],
      },
    });

    expect(state.summaryCards).toHaveLength(6);
    expect(state.currentAccount.synced).toBe(true);
    expect(state.currentAccount.unrealizedPnl).toBe("-2,704,805원");
    expect(state.currentAccount.totalAsset).toBe("527,064,565원");
    expect(state.currentAccount.holdingCount).toBe("4종목");
    expect(state.accountPnl.totalAssetDelta).toBe("-3,781,680원");
    expect(state.accountPnl.cashOrSnapshotDelta).toBe("-3,781,680원");
    expect(state.helperLabel).toContain("계좌 손익 대사");
    expect(state.baseline.active).toBe(true);
    expect(state.baseline.effectiveDate).toBe("2026-04-06");
    expect(state.summaryCards[0]).toMatchObject({ label: "성과 거래", value: "18건" });
    expect(state.summaryCards[1]).toMatchObject({ label: "닫힌 기대값", value: "+1,200원" });
    expect(state.summaryCards[5]).toMatchObject({ label: "대사 종료 제외", value: "72건" });
    expect(state.dataQuality.closedTradeRows).toBe("90건");
    expect(state.dataQuality.performanceTradeCount).toBe("18건");
    expect(state.rollout.status).toBe("PROMOTE");
    expect(state.rollout.details[0]).toContain("Shadow 후보 24건");
    expect(state.rollout.checks[0]).toMatchObject({ key: "sample", passed: true });
    expect(state.lifecycle.status).toBe("WARN");
    expect(state.lifecycle.statusLabel).toBe("주의");
    expect(state.lifecycle.tone).toBe("amber");
    expect(state.lifecycle.days).toBe(7);
    expect(state.lifecycle.summaryRows[0]).toMatchObject({ label: "계좌 기준선", value: "1건" });
    expect(state.lifecycle.summaryRows[2]).toMatchObject({ label: "확인 대기", value: "1건" });
    expect(state.lifecycle.summaryRows[5]).toMatchObject({ label: "미연결 SELL", value: "3건" });
    expect(state.lifecycle.summaryRows[6]).toMatchObject({ label: "브로커 미보유 BUY", value: "1건" });
    expect(state.lifecycle.checks[0]).toMatchObject({ key: "pending_confirms", status: "WARN" });
    expect(state.shadowSummaryRows[2]).toMatchObject({ label: "실제 BUY", value: "18건" });
    expect(state.newsOps.newsGateBlocks).toBe("4회");
    expect(state.comparisonRows[0].label).toBe("뉴스 반영 거래");
    expect(state.comparisonRows[1].label).toBe("일반 거래");
    expect(state.comparisonDelta.expectancy).toBe("+700원");
    expect(state.byHorizonRows[0].label).toBe("MID");
    expect(state.byStrategyRows[0].label).toBe("STABLE_SHORT");
    expect(state.byExecutionProfileRows[0].label).toBe("STABLE_SHORT");
    expect(state.weeklyRows[0].periodLabel).toBe("2026-04-13");
    expect(state.monthlyRows[0].periodLabel).toBe("2026-05-01");
    expect(state.monthlyRows[1].totalPnl).toBe("+125,000원");
  });

  test("does not display infinite profit factor for zero-pnl closed samples", () => {
    const state = buildPerformanceDashboardState({
      summary: {
        overall: {
          trade_count: 72,
          expectancy: 0,
          profit_factor: 999,
          total_pnl: 0,
        },
        by_horizon: {
          SHORT: { trade_count: 72, expectancy: 0, profit_factor: 999, total_pnl: 0 },
        },
      },
      weekly: {
        buckets: [
          { end: "2026-04-27", metrics: { trade_count: 72, expectancy: 0, profit_factor: 999, total_pnl: 0 } },
        ],
      },
    });

    expect(state.summaryCards[2]).toMatchObject({ label: "닫힌 PF", value: "-" });
    expect(state.byHorizonRows[0].profitFactor).toBe("-");
    expect(state.weeklyRows[0].profitFactor).toBe("-");
  });

  test("returns empty-friendly defaults", () => {
    const state = buildPerformanceDashboardState({});

    expect(state.summaryCards[0]).toMatchObject({ value: "0건" });
    expect(state.currentAccount.synced).toBe(false);
    expect(state.helperLabel).toContain("닫힌 거래 표본");
    expect(state.comparisonRows).toHaveLength(2);
    expect(state.byHorizonRows).toEqual([]);
    expect(state.weeklyRows).toEqual([]);
    expect(state.rollout.status).toBe("HOLDOUT");
    expect(state.shadowSummaryRows[0].value).toBe("0건");
    expect(state.baseline.active).toBe(false);
    expect(state.lifecycle.status).toBe("UNKNOWN");
    expect(state.lifecycle.statusLabel).toBe("대기");
    expect(state.lifecycle.summaryRows[0]).toMatchObject({ label: "계좌 기준선", value: "0건" });
  });
});
