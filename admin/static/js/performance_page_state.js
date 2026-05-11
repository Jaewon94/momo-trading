function formatInteger(value) {
  return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
}

function formatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(numeric)}원`;
}

function formatKrW(value) {
  return `${new Intl.NumberFormat("ko-KR").format(Number(value || 0))}원`;
}

function formatFixed(value, digits = 2) {
  return Number(value || 0).toFixed(digits);
}

function formatProfitFactor(metrics = {}) {
  const tradeCount = Number(metrics?.trade_count || 0);
  const totalPnl = Number(metrics?.total_pnl || 0);
  const expectancy = Number(metrics?.expectancy || 0);
  const profitFactor = Number(metrics?.profit_factor || 0);
  if (tradeCount > 0 && totalPnl === 0 && expectancy === 0) {
    return "-";
  }
  return formatFixed(profitFactor);
}

function sortMetricRows(entries = {}) {
  return Object.entries(entries)
    .map(([label, metrics]) => ({
      label,
      tradeCount: `${formatInteger(metrics?.trade_count || 0)}건`,
      expectancy: formatSignedKrW(metrics?.expectancy || 0),
      profitFactor: formatProfitFactor(metrics),
      totalPnl: formatSignedKrW(metrics?.total_pnl || 0),
    }))
    .sort((left, right) => Number(right.totalPnl.replace(/[^\d-]/g, "")) - Number(left.totalPnl.replace(/[^\d-]/g, "")));
}

function mapPeriodRows(buckets = []) {
  return (Array.isArray(buckets) ? buckets : [])
    .slice()
    .sort((left, right) => String(right?.end || "").localeCompare(String(left?.end || "")))
    .map((bucket) => ({
      periodLabel: String(bucket?.end || "-"),
      expectancy: formatSignedKrW(bucket?.metrics?.expectancy || 0),
      profitFactor: formatProfitFactor(bucket?.metrics || {}),
      totalPnl: formatSignedKrW(bucket?.metrics?.total_pnl || 0),
    }));
}

function normalizeLifecycleStatus(status) {
  const normalized = String(status || "").toUpperCase();
  if (["OK", "WARN", "FAIL"].includes(normalized)) {
    return normalized;
  }
  return "UNKNOWN";
}

function buildLifecycleState(lifecycle = {}) {
  const status = normalizeLifecycleStatus(lifecycle?.status);
  const summary = lifecycle?.summary || {};
  const statusMeta = {
    OK: {
      label: "정상",
      tone: "emerald",
      help: "BUY/SELL/성과 반영 흐름에서 확인할 항목이 없습니다.",
    },
    WARN: {
      label: "주의",
      tone: "amber",
      help: "성과 반영 전에 확인해야 할 거래 흐름이 있습니다.",
    },
    FAIL: {
      label: "오류",
      tone: "rose",
      help: "주문 확인 또는 거래 기록 흐름에 실패 항목이 있습니다.",
    },
    UNKNOWN: {
      label: "대기",
      tone: "gray",
      help: "라이프사이클 점검 데이터를 아직 받지 못했습니다.",
    },
  }[status];

  return {
    status,
    statusLabel: statusMeta.label,
    tone: statusMeta.tone,
    help: String(lifecycle?.message || statusMeta.help),
    days: Number(lifecycle?.days || lifecycle?.window?.days || 0),
    generatedAt: String(lifecycle?.generated_at || ""),
    summaryRows: [
      { key: "account_baseline_count", label: "계좌 기준선", value: `${formatInteger(summary.account_baseline_count || 0)}건` },
      { key: "account_equity_snapshot_count", label: "계좌 스냅샷", value: `${formatInteger(summary.account_equity_snapshot_count || 0)}건` },
      { key: "pending_confirm_count", label: "확인 대기", value: `${formatInteger(summary.pending_confirm_count || 0)}건` },
      { key: "confirm_failed_count", label: "확인 실패", value: `${formatInteger(summary.confirm_failed_count || 0)}건` },
      { key: "open_buy_count", label: "열린 BUY", value: `${formatInteger(summary.open_buy_count || 0)}건` },
      { key: "unpaired_sell_count", label: "미연결 SELL", value: `${formatInteger(summary.unpaired_sell_count || 0)}건` },
      { key: "broker_missing_open_buy_count", label: "브로커 미보유 BUY", value: `${formatInteger(summary.broker_missing_open_buy_count || 0)}건` },
      { key: "repairable_sell_count", label: "대사 후보", value: `${formatInteger(summary.repairable_sell_count || 0)}건` },
      { key: "performance_trade_count", label: "성과 거래", value: `${formatInteger(summary.performance_trade_count || 0)}건` },
    ],
    checks: Array.isArray(lifecycle?.checks)
      ? lifecycle.checks.map((item) => ({
        key: String(item?.key || ""),
        label: String(item?.label || ""),
        status: normalizeLifecycleStatus(item?.status),
        actual: String(item?.actual ?? "-"),
        target: String(item?.target ?? "-"),
        unmatchedQuantity: Number(item?.unmatched_quantity || 0),
        missingQuantity: Number(item?.missing_quantity || 0),
        mismatchedQuantity: Number(item?.mismatched_quantity || 0),
      }))
      : [],
  };
}

export function buildPerformanceDashboardState({
  summary = {},
  weekly = {},
  monthly = {},
  newsOverview = {},
  lifecycle = {},
} = {}) {
  const baseline = summary?.baseline || newsOverview?.baseline || {};
  const overall = summary?.overall || {};
  const currentAccount = summary?.current_account || {};
  const pnlTruth = summary?.pnl_truth || {};
  const metricContract = summary?.metric_contract || {};
  const dataQuality = summary?.data_quality || {};
  const shadow = summary?.shadow || {};
  const rollout = summary?.rollout || {};
  const comparisons = summary?.comparisons || {};
  const newsEnriched = comparisons?.news_enriched || {};
  const plain = comparisons?.plain || {};
  const delta = comparisons?.delta || {};
  const newsPerformance = newsOverview?.performance || {};

  return {
    baseline: {
      active: Boolean(baseline?.active),
      label: String(baseline?.label || ""),
      effectiveDate: String(baseline?.effective_date || ""),
      summary: String(baseline?.summary || ""),
      details: Array.isArray(baseline?.details)
        ? baseline.details.map((item) => String(item || "")).filter(Boolean)
        : [],
    },
    currentAccount: {
      synced: Boolean(currentAccount?.synced),
      unrealizedPnl: formatSignedKrW(currentAccount?.unrealized_pnl || 0),
      unrealizedPnlRate: `${formatFixed(currentAccount?.unrealized_pnl_rate || 0)}%`,
      holdingCount: `${formatInteger(currentAccount?.holding_count || 0)}종목`,
      pendingOrderCount: `${formatInteger(currentAccount?.pending_order_count || 0)}건`,
      totalAsset: formatKrW(currentAccount?.total_asset || 0),
      warning: String(currentAccount?.warning || ""),
    },
    accountPnl: {
      sampleStatus: String(metricContract?.sample_status || pnlTruth?.account_pnl_sample_status || "UNKNOWN"),
      closedTradeSampleStatus: String(metricContract?.closed_trade_sample_status || pnlTruth?.sample_status || "UNKNOWN"),
      reconciliationStatus: String(metricContract?.pnl_reconciliation_status || pnlTruth?.pnl_reconciliation_status || "UNKNOWN"),
      totalAssetDelta: formatSignedKrW(pnlTruth?.total_asset_delta || 0),
      cashOrSnapshotDelta: formatSignedKrW(pnlTruth?.cash_or_snapshot_delta || 0),
      brokerUnrealizedPnl: formatSignedKrW(pnlTruth?.unrealized_broker_pnl || 0),
      message: String(pnlTruth?.pnl_reconciliation_message || ""),
    },
    dataQuality: {
      closedTradeRows: `${formatInteger(dataQuality?.closed_trade_rows || 0)}건`,
      excludedReconciliationCloseRows: `${formatInteger(dataQuality?.excluded_reconciliation_close_rows || 0)}건`,
      performanceTradeCount: `${formatInteger(dataQuality?.performance_trade_count || overall.trade_count || 0)}건`,
      reason: String(dataQuality?.excluded_reconciliation_close_reason || ""),
    },
    lifecycle: buildLifecycleState(lifecycle),
    helperLabel:
      String(metricContract?.sample_status || "").includes("UNRECONCILED")
        ? "계좌 손익 대사가 맞지 않아 닫힌 거래 성과는 참고용입니다."
        : Number(overall.trade_count || 0) === 0
        ? "닫힌 거래 표본이 없어 현재 계좌 기준 상태를 함께 표시 중"
        : "",
    summaryCards: [
      { label: "성과 거래", value: `${formatInteger(overall.trade_count || 0)}건` },
      { label: "닫힌 기대값", value: formatSignedKrW(overall.expectancy || 0) },
      { label: "닫힌 PF", value: formatProfitFactor(overall) },
      { label: "닫힌 MDD", value: formatSignedKrW(overall.max_drawdown || 0) },
      { label: "닫힌 비용차감", value: formatSignedKrW(overall.net_pnl_after_cost || 0) },
      { label: "대사 종료 제외", value: `${formatInteger(dataQuality?.excluded_reconciliation_close_rows || 0)}건` },
    ],
    rollout: {
      status: String(rollout.status || "HOLDOUT"),
      reason: String(rollout.reason || "표본 수집 중"),
      details: Array.isArray(rollout.details)
        ? rollout.details.map((item) => String(item || "")).filter(Boolean)
        : [],
      checks: Array.isArray(rollout.checks)
        ? rollout.checks.map((item) => ({
          key: String(item?.key || ""),
          label: String(item?.label || ""),
          passed: Boolean(item?.passed),
          actual: String(item?.actual || "-"),
          target: String(item?.target || "-"),
        }))
        : [],
    },
    shadowSummaryRows: [
      { label: "Shadow 후보", value: `${formatInteger(shadow.candidate_count || 0)}건` },
      { label: "뉴스 차단", value: `${formatInteger(shadow.blocked_by_news_count || 0)}건` },
      { label: "실제 BUY", value: `${formatInteger(shadow.actual_buy_count || 0)}건` },
      { label: "기준 BUY", value: `${formatInteger(shadow.baseline_buy_count || 0)}건` },
    ],
    comparisonRows: [
      {
        label: "뉴스 반영 거래",
        tradeCount: `${formatInteger(newsEnriched.trade_count || 0)}건`,
        expectancy: formatSignedKrW(newsEnriched.expectancy || 0),
        profitFactor: formatProfitFactor(newsEnriched),
        totalPnl: formatSignedKrW(newsEnriched.total_pnl || 0),
      },
      {
        label: "일반 거래",
        tradeCount: `${formatInteger(plain.trade_count || 0)}건`,
        expectancy: formatSignedKrW(plain.expectancy || 0),
        profitFactor: formatProfitFactor(plain),
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
    byExecutionProfileRows: sortMetricRows(summary?.by_execution_profile || summary?.by_strategy || {}),
    weeklyRows: mapPeriodRows(weekly?.buckets || []),
    monthlyRows: mapPeriodRows(monthly?.buckets || []),
  };
}
