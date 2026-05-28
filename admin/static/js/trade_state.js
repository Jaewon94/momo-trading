export function buildTradeSummaryCounts(trades = {}) {
  const opened = trades?.opened || [];
  const sellExecutions = trades?.sell_executions || [];
  const pendingConfirms = trades?.pending_confirms || [];

  return {
    todayTradeCount: opened.length + sellExecutions.length + pendingConfirms.length,
    pendingConfirmCount: pendingConfirms.length,
    sellExecutionCount: sellExecutions.length,
  };
}

export function isNeutralReconciliationClose(trade = {}) {
  const exitReason = String(trade?.exit_reason || "");
  const notes = String(trade?.notes || "");
  if (notes.includes("CLOSE_RECONCILIATION_APPLY")) return false;
  return exitReason === "BROKER_HOLDING_MISSING"
    || notes.includes("HOLDING_RECONCILIATION_CLOSE");
}

function visibleCompletedTrades(trades = {}) {
  const completed = Array.isArray(trades?.completed) ? trades.completed : [];
  return completed.filter((trade) => !isNeutralReconciliationClose(trade));
}

function visibleOpenedTrades(trades = {}) {
  const opened = Array.isArray(trades?.opened) ? trades.opened : [];
  return opened.filter((trade) => !isNeutralReconciliationClose(trade));
}

export function buildPortfolioQuickStatsModel(
  balance = {},
  holdings = [],
  pendingOrders = [],
  trades = {},
) {
  const totalAsset = Number(balance?.total_asset || 0);
  const unrealizedPnl = Number(balance?.total_pnl || 0);
  const unrealizedPnlRate = Number(balance?.total_pnl_rate || 0);
  const sessionMetrics = balance?.session_metrics || {};
  const sessionAvailable = sessionMetrics?.available === true;
  const cash = Number(balance?.cash || 0);
  const stockValue = Number(balance?.stock_value || 0);
  const cashRatio = totalAsset > 0 ? (cash / totalAsset) * 100 : 0;
  const holdingCount = Array.isArray(holdings) ? holdings.length : 0;
  const pendingCount = Array.isArray(pendingOrders) ? pendingOrders.length : 0;
  const opened = visibleOpenedTrades(trades);
  const sellExecutions = Array.isArray(trades?.sell_executions) ? trades.sell_executions : [];
  const completed = visibleCompletedTrades(trades);
  const currentExposureKrw = sessionAvailable
    ? Number(sessionMetrics?.current_exposure_krw || stockValue)
    : stockValue;
  const currentExposurePct = sessionAvailable
    ? Number(sessionMetrics?.current_exposure_pct || (totalAsset > 0 ? (currentExposureKrw / totalAsset) * 100 : 0))
    : (totalAsset > 0 ? (stockValue / totalAsset) * 100 : 0);
  const tradeCounts = buildTradeSummaryCounts(trades);

  return {
    totalAsset,
    unrealizedPnl,
    unrealizedPnlRate,
    assetDelta: sessionAvailable ? Number(sessionMetrics?.asset_delta || 0) : 0,
    assetDeltaRate: sessionAvailable ? Number(sessionMetrics?.asset_delta_rate || 0) : 0,
    assetDeltaAvailable: sessionAvailable,
    dailyUnrealizedDelta: sessionAvailable ? Number(sessionMetrics?.daily_unrealized_delta || 0) : 0,
    dailyUnrealizedAvailable: sessionAvailable,
    realizedTodayPnl: sessionAvailable ? Number(sessionMetrics?.realized_today_pnl || 0) : 0,
    brokerUnrealizedPnl: sessionAvailable ? Number(sessionMetrics?.broker_unrealized_pnl || unrealizedPnl) : unrealizedPnl,
    cashOrSnapshotDelta: sessionAvailable ? Number(sessionMetrics?.cash_or_snapshot_delta || 0) : 0,
    currentExposureKrw,
    currentExposurePct,
    marketExposure: sessionAvailable ? sessionMetrics?.market_exposure === true : stockValue > 0,
    riskLabel: sessionAvailable ? String(sessionMetrics?.risk_label || "") : "",
    riskMessage: sessionAvailable ? String(sessionMetrics?.risk_message || "") : "",
    intradayHighAsset: sessionAvailable
      ? Number(sessionMetrics?.intraday_high_asset || totalAsset)
      : totalAsset,
    intradayLowAsset: sessionAvailable
      ? Number(sessionMetrics?.intraday_low_asset || totalAsset)
      : totalAsset,
    baselineTotalAsset: sessionAvailable ? Number(sessionMetrics?.baseline_total_asset || 0) : 0,
    tradingDate: sessionAvailable ? String(sessionMetrics?.trading_date || "") : "",
    baselineAt: sessionAvailable ? String(sessionMetrics?.baseline_at || "") : "",
    latestSnapshotAt: sessionAvailable ? String(sessionMetrics?.latest_snapshot_at || "") : "",
    snapshotAgeSec: sessionAvailable
      && sessionMetrics?.snapshot_age_sec !== null
      && sessionMetrics?.snapshot_age_sec !== undefined
      ? Number(sessionMetrics?.snapshot_age_sec || 0)
      : null,
    snapshotFreshnessStatus: sessionAvailable ? String(sessionMetrics?.snapshot_freshness_status || "") : "",
    snapshotStaleReason: sessionAvailable ? String(sessionMetrics?.snapshot_stale_reason || "") : "",
    snapshotStaleMessage: sessionAvailable ? String(sessionMetrics?.snapshot_stale_message || "") : "",
    snapshotStaleBlocksBuy: sessionAvailable ? sessionMetrics?.snapshot_stale_blocks_buy === true : false,
    snapshotIsStale: sessionAvailable ? sessionMetrics?.is_stale === true : false,
    cash,
    stockValue,
    cashRatio,
    holdingCount,
    pendingCount,
    openedCount: opened.length,
    sellExecutionCount: tradeCounts.sellExecutionCount,
    completedCount: completed.length,
    unmatchedSellExecutions: Math.max(0, sellExecutions.length - completed.length),
  };
}

function formatWon(value, { signed = false } = {}) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return signed ? "+0원" : "0원";
  const rounded = Math.round(numeric);
  const prefix = signed && rounded > 0 ? "+" : "";
  return `${prefix}${rounded.toLocaleString()}원`;
}

function formatPercent(value, { signed = false, digits = 1 } = {}) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return signed ? "+0.0%" : "0.0%";
  const prefix = signed && numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(digits)}%`;
}

function toneFromNumber(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return "positive";
  if (numeric < 0) return "negative";
  return "neutral";
}

export function buildAccountOverviewModel(stats = {}) {
  const totalAsset = Number(stats?.totalAsset || 0);
  const cash = Number(stats?.cash || 0);
  const stockValue = Number(stats?.stockValue || 0);
  const cashRatio = totalAsset > 0 ? (cash / totalAsset) * 100 : 0;
  const stockRatio = totalAsset > 0 ? (stockValue / totalAsset) * 100 : 0;
  const pnlTone = toneFromNumber(stats?.unrealizedPnl);
  const totalAssetMeta = stats?.assetDeltaAvailable
    ? `장시작 대비 ${formatWon(stats.assetDelta, { signed: true })} / ${formatPercent(stats.assetDeltaRate, { signed: true, digits: 2 })}`
    : "장시작 기준선 대기";
  const exposureMeta = stats?.riskMessage
    || (stats?.marketExposure ? "보유 노출 있음" : "현재 시장 노출 없음");

  return {
    totalAssetLabel: formatWon(totalAsset),
    totalAssetMeta,
    assetDeltaTone: stats?.assetDeltaAvailable ? toneFromNumber(stats?.assetDelta) : "neutral",
    exposureLabel: formatWon(stats?.currentExposureKrw),
    exposureMeta,
    exposureTone: stats?.marketExposure ? "negative" : "neutral",
    cashRatio,
    stockRatio,
    pnlLabel: formatWon(stats?.unrealizedPnl, { signed: true }),
    pnlTone,
    rows: [
      {
        label: "현금",
        value: formatWon(cash),
        meta: formatPercent(cashRatio),
        tone: "neutral",
      },
      {
        label: "주식 평가액",
        value: formatWon(stockValue),
        meta: `${formatPercent(stockRatio)} · 노출 ${formatPercent(stats?.currentExposurePct || 0)}`,
        tone: "neutral",
      },
      {
        label: "평가손익",
        value: formatWon(stats?.unrealizedPnl, { signed: true }),
        meta: formatPercent(stats?.unrealizedPnlRate, { digits: 2 }),
        tone: pnlTone,
      },
    ],
  };
}

/**
 * 오늘 자산 변화의 세부 분해를 별도 카드용 모델로 정리한다.
 *
 * 메인 잔고 카드는 사용자가 바로 확인해야 할 핵심 수치(총자산·현금·주식·평가손익)만
 * 표시하고, "장시작 대비"를 매매(실현+미실현)와 정산/스냅샷 잔차로 분해한
 * 진단성 데이터는 이 모델을 통해 보조 카드에 노출한다.
 */
export function buildAccountSessionDetailModel(stats = {}) {
  if (!stats?.assetDeltaAvailable) {
    return {
      available: false,
      title: "오늘 자산 변화 분석",
      caption: "장시작 기준선이 준비되면 표시됩니다.",
      baselineMeta: "",
      rows: [],
      footnote: "",
    };
  }

  const assetDelta = Number(stats?.assetDelta || 0);
  const realized = Number(stats?.realizedTodayPnl || 0);
  const brokerUnrealized = Number(stats?.brokerUnrealizedPnl || 0);
  const cashOrSnapshotDelta = Number(stats?.cashOrSnapshotDelta || 0);

  const baselineAt = stats?.baselineAt ? formatTimeShort(stats.baselineAt) : "";
  const baselineAsset = Number(stats?.baselineTotalAsset || 0);
  const baselineMeta = baselineAt && baselineAsset > 0
    ? `장시작 ${baselineAt} · ${formatWon(baselineAsset)}`
    : (stats?.baselineAt ? `장시작 기준 ${baselineAt}` : "");

  return {
    available: true,
    title: "오늘 자산 변화 분석",
    caption: stats?.riskMessage || "장시작 대비 자산 변화를 매매와 정산 잔차로 분해한 참고 지표입니다.",
    baselineMeta,
    rows: [
      {
        label: "장시작 대비",
        value: formatWon(assetDelta, { signed: true }),
        meta: formatPercent(stats?.assetDeltaRate || 0, { signed: true, digits: 2 }),
        tone: toneFromNumber(assetDelta),
      },
      {
        label: "오늘 실현 손익",
        value: formatWon(realized, { signed: true }),
        meta: "오늘 청산된 거래 합",
        tone: toneFromNumber(realized),
      },
      {
        label: "현재 평가손익",
        value: formatWon(brokerUnrealized, { signed: true }),
        meta: "보유분 미실현 손익 (현 시점)",
        tone: toneFromNumber(brokerUnrealized),
      },
      {
        label: "정산 잔차",
        value: formatWon(cashOrSnapshotDelta, { signed: true }),
        meta: "매매로 설명되지 않는 차이",
        tone: toneFromNumber(cashOrSnapshotDelta),
      },
    ],
    footnote: "정산 잔차는 어제 보유분의 미실현 변화·스냅샷 시점 차이·정산 시간차 등으로 발생합니다.",
  };
}

function formatTimeShort(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return "";
  }
}

export function buildTradePanelState(data = {}) {
  const opened = visibleOpenedTrades(data);
  const sellExecutions = data?.sell_executions || [];
  const completed = visibleCompletedTrades(data);
  const pendingConfirms = data?.pending_confirms || [];
  const openPositions = data?.open_positions || [];
  const sections = [];

  if (sellExecutions.length) sections.push("sell_executions");
  if (completed.length) sections.push("completed");
  if (pendingConfirms.length) sections.push("pending_confirms");
  if (opened.length) sections.push("opened");
  if (openPositions.length) sections.push("open_positions");

  return {
    opened,
    sellExecutions,
    completed,
    pendingConfirms,
    openPositions,
    todayCount: opened.length + sellExecutions.length + pendingConfirms.length,
    hasContent: sections.length > 0,
    sections,
  };
}
