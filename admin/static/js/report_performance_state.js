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

export function buildReportPerformanceState(report = {}) {
  const comparison = report?.trade_comparison || {};
  const newsEnriched = comparison?.news_enriched || {};
  const plain = comparison?.plain || {};
  const delta = comparison?.delta || {};
  const newsCount = Number(newsEnriched.trade_count || 0);
  const plainCount = Number(plain.trade_count || 0);
  const ready = newsCount > 0 && plainCount > 0;
  const sampleCount = newsCount + plainCount;

  return {
    hasContent: sampleCount > 0,
    ready,
    emptyLabel: "비교할 청산 거래 표본이 아직 부족합니다.",
    helperLabel: ready
      ? `뉴스 반영 ${formatInteger(newsCount)}건 vs 일반 ${formatInteger(plainCount)}건`
      : `현재 표본 ${formatInteger(sampleCount)}건`,
    rows: [
      {
        label: "뉴스 반영 거래",
        tradeCount: `${formatInteger(newsCount)}건`,
        expectancy: formatSignedKrW(newsEnriched.expectancy || 0),
        profitFactor: formatFixed(newsEnriched.profit_factor || 0),
        totalPnl: formatSignedKrW(newsEnriched.total_pnl || 0),
      },
      {
        label: "일반 거래",
        tradeCount: `${formatInteger(plainCount)}건`,
        expectancy: formatSignedKrW(plain.expectancy || 0),
        profitFactor: formatFixed(plain.profit_factor || 0),
        totalPnl: formatSignedKrW(plain.total_pnl || 0),
      },
    ],
    delta: {
      expectancy: formatSignedKrW(delta.expectancy || 0),
      profitFactor: formatFixed(delta.profit_factor || 0),
      netPnlAfterCost: formatSignedKrW(delta.net_pnl_after_cost || 0),
    },
  };
}
