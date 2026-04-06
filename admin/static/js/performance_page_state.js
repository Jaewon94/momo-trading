function formatInteger(value) {
  return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
}

function formatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(numeric)}원`;
}

function formatFixed(value, digits = 2) {
  return Number(value || 0).toFixed(digits);
}

function sortMetricRows(entries = {}) {
  return Object.entries(entries)
    .map(([label, metrics]) => ({
      label,
      tradeCount: `${formatInteger(metrics?.trade_count || 0)}건`,
      expectancy: formatSignedKrW(metrics?.expectancy || 0),
      profitFactor: formatFixed(metrics?.profit_factor || 0),
      totalPnl: formatSignedKrW(metrics?.total_pnl || 0),
    }))
    .sort((left, right) => Number(right.totalPnl.replace(/[^\d-]/g, "")) - Number(left.totalPnl.replace(/[^\d-]/g, "")));
}

function mapPeriodRows(buckets = []) {
  return (Array.isArray(buckets) ? buckets : []).map((bucket) => ({
    periodLabel: String(bucket?.end || "-"),
    expectancy: formatSignedKrW(bucket?.metrics?.expectancy || 0),
    profitFactor: formatFixed(bucket?.metrics?.profit_factor || 0),
    totalPnl: formatSignedKrW(bucket?.metrics?.total_pnl || 0),
  }));
}

export function buildPerformanceDashboardState({
  summary = {},
  weekly = {},
  monthly = {},
  newsOverview = {},
} = {}) {
  const overall = summary?.overall || {};
  const shadow = summary?.shadow || {};
  const rollout = summary?.rollout || {};
  const comparisons = summary?.comparisons || {};
  const newsEnriched = comparisons?.news_enriched || {};
  const plain = comparisons?.plain || {};
  const delta = comparisons?.delta || {};
  const newsPerformance = newsOverview?.performance || {};

  return {
    summaryCards: [
      { label: "총 거래", value: `${formatInteger(overall.trade_count || 0)}건` },
      { label: "기대값", value: formatSignedKrW(overall.expectancy || 0) },
      { label: "PF", value: formatFixed(overall.profit_factor || 0) },
      { label: "MDD", value: formatSignedKrW(overall.max_drawdown || 0) },
      { label: "비용 차감 손익", value: formatSignedKrW(overall.net_pnl_after_cost || 0) },
      { label: "Shadow 후보", value: `${formatInteger(shadow.candidate_count || 0)}건` },
    ],
    rollout: {
      status: String(rollout.status || "HOLDOUT"),
      reason: String(rollout.reason || "표본 수집 중"),
    },
    comparisonRows: [
      {
        label: "뉴스 반영 거래",
        tradeCount: `${formatInteger(newsEnriched.trade_count || 0)}건`,
        expectancy: formatSignedKrW(newsEnriched.expectancy || 0),
        profitFactor: formatFixed(newsEnriched.profit_factor || 0),
        totalPnl: formatSignedKrW(newsEnriched.total_pnl || 0),
      },
      {
        label: "일반 거래",
        tradeCount: `${formatInteger(plain.trade_count || 0)}건`,
        expectancy: formatSignedKrW(plain.expectancy || 0),
        profitFactor: formatFixed(plain.profit_factor || 0),
        totalPnl: formatSignedKrW(plain.total_pnl || 0),
      },
    ],
    comparisonDelta: {
      expectancy: formatSignedKrW(delta.expectancy || 0),
      profitFactor: formatFixed(delta.profit_factor || 0),
      netPnlAfterCost: formatSignedKrW(delta.net_pnl_after_cost || 0),
    },
    newsOps: {
      newsGateBlocks: `${formatInteger(newsPerformance.news_gate_blocks || 0)}회`,
      newsRechecks: `${formatInteger(newsPerformance.news_rechecks || 0)}회`,
      avgNegativePressure: Number(newsPerformance.avg_negative_pressure || 0).toFixed(2),
      shadowBlockRate: `${(Number(shadow.block_rate || 0) * 100).toFixed(1)}%`,
    },
    byHorizonRows: sortMetricRows(summary?.by_horizon || {}),
    byStrategyRows: sortMetricRows(summary?.by_strategy || {}),
    weeklyRows: mapPeriodRows(weekly?.buckets || []),
    monthlyRows: mapPeriodRows(monthly?.buckets || []),
  };
}
