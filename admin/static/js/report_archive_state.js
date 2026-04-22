import { buildReportPerformanceState } from "./report_performance_state.js";

function formatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(numeric)}원`;
}

export function buildReportArchiveCardState(report = {}) {
  const performance = buildReportPerformanceState(report);
  const deltaLabel = performance.ready
    ? `E ${performance.delta.expectancy} · 비용차감 ${performance.delta.netPnlAfterCost}`
    : "비교 표본 수집 중";

  return {
    dateLabel: String(report?.report_date || "-"),
    summaryLabel: [
      `실현손익 ${formatSignedKrW(report?.total_pnl || 0)}`,
      `매수 ${Number(report?.buy_count || 0)}건 / 매도 ${Number(report?.sell_count || 0)}건`,
      `보유 ${Number(report?.open_position_count || 0)}종목`,
    ].join(" · "),
    comparison: {
      hasContent: performance.hasContent,
      ready: performance.ready,
      headline: performance.ready
        ? `뉴스 ${performance.rows[0].tradeCount} vs 일반 ${performance.rows[1].tradeCount}`
        : performance.helperLabel,
      deltaLabel,
    },
  };
}
