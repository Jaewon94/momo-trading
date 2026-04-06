import { parseTradeNotes, resolveTradeExecutionState } from "./trade_status_state.js";

function formatInt(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function formatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toLocaleString("ko-KR")}원`;
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const numeric = Number(value);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${numeric.toFixed(2)}%`;
}

function formatBp(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)}bp`;
}

function formatTimelineDate(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatTimelineTime(value) {
  if (!value) return "";
  try {
    return new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return "";
  }
}

function formatTimelineDayParts(value) {
  if (!value) {
    return {
      dayKey: "unknown",
      dayLabel: "날짜 미상",
      dayStamp: "",
      relativeLabel: "",
    };
  }

  try {
    const date = new Date(value);
    const dayKey = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
    const dayStamp = new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
    }).format(date);
    const todayKey = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Seoul",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date());

    const relativeLabel = dayKey === todayKey ? "오늘" : "";
    const [month, day] = dayKey.split("-").slice(1);

    return {
      dayKey,
      dayLabel: `${month}.${day}`,
      dayStamp,
      relativeLabel,
    };
  } catch {
    return {
      dayKey: "unknown",
      dayLabel: "날짜 미상",
      dayStamp: "",
      relativeLabel: "",
    };
  }
}

function classifyTimelineEntry(entry) {
  const type = String(entry.type || "").toLowerCase();
  const phase = String(entry.phase || "").toUpperCase();
  const side = String(entry.side || "").toUpperCase();
  const status = String(entry.status || "").toUpperCase();
  const detail = entry.detail && typeof entry.detail === "object" ? entry.detail : {};

  if (type === "trade") {
    if (detail.trade_state_kind_label || detail.trade_state_badge) {
      return {
        filterKey: "trade",
        tone: detail.trade_state_tone || "buy",
        icon: detail.trade_state_icon || detail.trade_state_kind_label || "거래",
        badge: detail.trade_state_badge || status || side || "TRADE",
        kindLabel: detail.trade_state_kind_label || "거래",
      };
    }

    const executionState = resolveTradeExecutionState({
      side,
      status,
      notes: parseTradeNotes(detail.notes),
      hasExit: Boolean(detail.exit_price || entry.title?.includes("매도")),
    });

    if (executionState.code.startsWith("SELL") || executionState.code.startsWith("BUY_")) {
      return {
        filterKey: "trade",
        tone: executionState.tone,
        icon: executionState.code === "SELL_PARTIAL" || executionState.code === "BUY_PARTIALLY_CLOSED"
          ? "부분"
          : executionState.code === "BUY_CLOSED"
            ? "청산"
            : "매도",
        badge: executionState.badge,
        kindLabel: executionState.shortLabel,
      };
    }
    return {
      filterKey: "trade",
      tone: executionState.tone,
      icon: executionState.code === "BUY_PENDING" ? "대기" : "매수",
      badge: executionState.badge,
      kindLabel: executionState.shortLabel,
    };
  }

  if (type === "news") {
    const sourceCode = String(detail.source_code || "").toUpperCase();
    return {
      filterKey: "news",
      tone: "news",
      icon: "뉴스",
      badge: sourceCode || "NEWS",
      kindLabel: "뉴스",
    };
  }

  if (phase === "ERROR" || status === "ERROR") {
    return {
      filterKey: "error",
      tone: "error",
      icon: "오류",
      badge: "오류",
      kindLabel: "오류",
    };
  }

  if (phase === "START" || phase === "PROGRESS") {
    return {
      filterKey: "ai",
      tone: "progress",
      icon: "진행",
      badge: phase || "PROGRESS",
      kindLabel: "진행 중",
    };
  }

  if (type === "activity") {
    return {
      filterKey: "ai",
      tone: "analysis",
      icon: "AI",
      badge: phase || "ANALYSIS",
      kindLabel: "AI 분석",
    };
  }

  return {
    filterKey: "all",
    tone: "neutral",
    icon: "기록",
    badge: phase || status || type.toUpperCase() || "EVENT",
    kindLabel: "이벤트",
  };
}

function buildTimelineDetailLines(entry) {
  const detail = entry.detail || {};
  const lines = [];

  if (entry.type === "trade") {
    if (detail.strategy_type) lines.push(`전략 ${detail.strategy_type}`);
    if (detail.entry_price) lines.push(`진입가 ${formatInt(detail.entry_price)}원`);
    if (detail.exit_price) lines.push(`청산가 ${formatInt(detail.exit_price)}원`);
    if (detail.pnl) lines.push(`손익 ${formatSignedKrW(detail.pnl)}`);
    if (detail.return_pct) lines.push(`수익률 ${formatPercent(detail.return_pct)}`);
    if (detail.exit_reason) lines.push(`사유 ${detail.exit_reason}`);
  } else if (entry.type === "activity" && detail && typeof detail === "object") {
    if (detail.recommendation) lines.push(`추천 ${detail.recommendation}`);
    if (detail.target_price) lines.push(`목표가 ${formatInt(detail.target_price)}원`);
    if (detail.stop_loss_price) lines.push(`손절가 ${formatInt(detail.stop_loss_price)}원`);
    if (detail.reason) lines.push(`근거 ${detail.reason}`);
  } else if (entry.type === "news" && detail && typeof detail === "object") {
    if (detail.impact_score !== null && detail.impact_score !== undefined) {
      lines.push(`영향도 ${Number(detail.impact_score).toFixed(2)}`);
    }
    if (detail.trust_score !== null && detail.trust_score !== undefined) {
      lines.push(`신뢰도 ${Number(detail.trust_score).toFixed(2)}`);
    }
    if (detail.sentiment_label || detail.sentiment_score !== null && detail.sentiment_score !== undefined) {
      const sentimentLabel = detail.sentiment_label ? `${detail.sentiment_label} ` : "";
      lines.push(`감성 ${sentimentLabel}${Number(detail.sentiment_score || 0).toFixed(2)}`.trim());
    }
    if (detail.source_name) lines.push(`출처 ${detail.source_name}`);
    if (detail.source_tier) lines.push(`소스 등급 ${detail.source_tier}`);
  }

  return lines;
}

export function buildPositionTimelineEntry(entry) {
  const timelineClass = classifyTimelineEntry(entry);
  const meta = [];
  const dayParts = formatTimelineDayParts(entry.at);
  if (entry.at) meta.push(formatTimelineDate(entry.at));
  if (entry.confidence !== null && entry.confidence !== undefined) {
    meta.push(`${Math.round(Number(entry.confidence) * 100)}%`);
  }
  if (entry.type === "news" && entry.detail && typeof entry.detail === "object") {
    if (entry.detail.source_code) meta.push(String(entry.detail.source_code).toUpperCase());
    if (entry.detail.source_tier) meta.push(`Tier ${entry.detail.source_tier}`);
  }
  if (entry.side) meta.push(entry.side);
  if (entry.status) meta.push(entry.status);
  return {
    ...entry,
    badge: timelineClass.badge,
    filterKey: timelineClass.filterKey,
    tone: timelineClass.tone,
    icon: timelineClass.icon,
    kindLabel: timelineClass.kindLabel,
    timeLabel: formatTimelineTime(entry.at),
    dayKey: dayParts.dayKey,
    dayLabel: dayParts.dayLabel,
    dayStamp: dayParts.dayStamp,
    relativeLabel: dayParts.relativeLabel,
    meta: meta.join(" · "),
    detailLines: buildTimelineDetailLines(entry),
  };
}

function buildTimelineFilters(entries) {
  const counts = {
    all: entries.length,
    trade: entries.filter((entry) => entry.filterKey === "trade").length,
    ai: entries.filter((entry) => entry.filterKey === "ai").length,
    news: entries.filter((entry) => entry.filterKey === "news").length,
    error: entries.filter((entry) => entry.filterKey === "error").length,
  };

  return [
    { key: "all", label: "전체", count: counts.all },
    { key: "trade", label: "거래", count: counts.trade },
    { key: "ai", label: "AI", count: counts.ai },
    { key: "news", label: "뉴스", count: counts.news },
    { key: "error", label: "오류", count: counts.error },
  ];
}

function buildRecentEventChips(summary = {}) {
  const events = Array.isArray(summary.recent_events) ? summary.recent_events : [];
  return events.slice(0, 3).map((event) => ({
    label: event.event_label || event.event_type || "이벤트",
    tone: String(event.direction || "").toUpperCase() === "SELL" ? "sell" : "buy",
    meta: `${Number(event.score || 0)}점 · ${String(event.state || "").toUpperCase() || "TRIGGERED"}`,
  }));
}

function buildDecisionInsight(summary = {}) {
  const insight = summary.decision_insight;
  if (!insight || typeof insight !== "object") return null;

  const chart = insight.chart || {};
  const cost = insight.cost || {};
  const news = insight.news || {};
  const ratio = Number(cost.ratio || 0);
  const minRatio = Number(cost.min_ratio || 0);
  const pressure = Number(news.negative_pressure || 0);
  const threshold = Number(news.threshold || 0);

  const chartTone = String(chart.direction || "").toUpperCase() === "BULLISH"
    || String(chart.market_regime || "").toUpperCase() === "BULL"
    ? "buy"
    : String(chart.direction || "").toUpperCase() === "BEARISH"
      || String(chart.market_regime || "").toUpperCase() === "BEAR"
      ? "sell"
      : "analysis";
  const costTone = ratio >= Math.max(minRatio, 1.8)
    ? "buy"
    : ratio >= Math.max(minRatio, 1.0)
      ? "analysis"
      : "sell";
  const newsTone = threshold > 0 && pressure >= threshold * 0.85
    ? "sell"
    : threshold > 0 && pressure >= threshold * 0.4
      ? "analysis"
      : "buy";

  return {
    hero: `${insight.recommendation || "대기"} · ${insight.horizon || "MID"}`,
    heroMeta: insight.reason || "최근 진입 판단 근거 없음",
    metrics: [
      {
        label: "신뢰도",
        value: insight.confidence !== null && insight.confidence !== undefined
          ? `${Math.round(Number(insight.confidence) * 100)}%`
          : "-",
      },
      { label: "목표가", value: insight.target_price ? `${formatInt(insight.target_price)}원` : "-" },
      { label: "손절가", value: insight.stop_loss_price ? `${formatInt(insight.stop_loss_price)}원` : "-" },
    ],
    cards: [
      {
        title: "차트",
        accent: chartTone,
        hero: chart.direction || chart.market_regime || "중립",
        heroMeta: chart.pattern || "차트 컨텍스트 없음",
        metrics: [
          { label: "국면", value: chart.market_regime || "-" },
          { label: "RSI", value: chart.rsi !== null && chart.rsi !== undefined ? Number(chart.rsi).toFixed(1) : "-" },
          { label: "MACD", value: chart.macd_hist !== null && chart.macd_hist !== undefined ? Number(chart.macd_hist).toFixed(2) : "-" },
        ],
        body: [
          chart.signal_confidence !== null && chart.signal_confidence !== undefined
            ? `차트 신호 신뢰도 ${Math.round(Number(chart.signal_confidence) * 100)}%`
            : "차트 신호 신뢰도 정보 없음",
        ],
      },
      {
        title: "비용",
        accent: costTone,
        hero: ratio > 0 ? `${ratio.toFixed(2)}x` : "-",
        heroMeta: ratio > 0
          ? `엣지/비용 비율 · 기준 ${minRatio > 0 ? `${minRatio.toFixed(2)}x` : "-"}`
          : "비용 계산 정보 없음",
        metrics: [
          { label: "엣지", value: formatBp(cost.edge_bps) },
          { label: "비용", value: formatBp(cost.cost_bps) },
          { label: "기준", value: minRatio > 0 ? `${minRatio.toFixed(2)}x` : "-" },
        ],
        body: [
          ratio > 0
            ? (ratio >= minRatio ? "비용 대비 기대수익 여유가 있습니다." : "비용 대비 기대수익 여유가 좁습니다.")
            : "비용 게이트 계산 정보 없음",
        ],
      },
      {
        title: "뉴스",
        accent: newsTone,
        hero: news.negative_pressure !== null && news.negative_pressure !== undefined
          ? Number(news.negative_pressure).toFixed(2)
          : "-",
        heroMeta: threshold > 0
          ? `부정 압력 · 차단 기준 ${threshold.toFixed(2)}`
          : "뉴스 압력 정보 없음",
        metrics: [
          { label: "기사", value: `${Number(news.negative_count || 0)}건` },
          { label: "소스", value: `${Number(news.source_count || 0)}개` },
          { label: "임계", value: threshold > 0 ? threshold.toFixed(2) : "-" },
        ],
        body: Array.isArray(news.contributors) && news.contributors.length
          ? news.contributors.slice(0, 3).map((item) => item.headline || "뉴스")
          : ["최근 부정 뉴스 기여 항목 없음"],
      },
    ],
  };
}

export function groupPositionTimeline(entries, filterKey = "all") {
  const filteredEntries = entries.filter((entry) => {
    if (filterKey === "all") return true;
    return entry.filterKey === filterKey;
  });

  const groups = [];
  let currentGroup = null;
  for (const entry of filteredEntries) {
    if (!currentGroup || currentGroup.dayKey !== entry.dayKey) {
      currentGroup = {
        dayKey: entry.dayKey,
        dayLabel: entry.dayLabel,
        dayStamp: entry.dayStamp,
        relativeLabel: entry.relativeLabel,
        entries: [],
      };
      groups.push(currentGroup);
    }
    currentGroup.entries.push(entry);
  }
  return groups;
}

export function buildPositionDetailState(payload) {
  const summary = payload?.summary || {};
  const holding = summary.holding;
  const holdingStatus = summary.holding_status || "unavailable";
  const holdingMessage = summary.holding_message || "";
  const signal = summary.latest_signal;
  const stats = summary.trade_stats || {};

  let holdingItems;
  if (holding) {
    holdingItems = [
      `${formatInt(holding.quantity)}주 · 평단 ${formatInt(holding.avg_buy_price)}원`,
      `현재가 ${formatInt(holding.current_price)}원 · 평가 ${formatInt(holding.market_value)}원`,
      `손익 ${formatSignedKrW(holding.pnl)} · ${formatPercent(holding.pnl_rate)}`,
    ];
  } else if (holdingStatus === "timeout" && holdingMessage) {
    holdingItems = [holdingMessage];
  } else if (holdingStatus === "error" && holdingMessage) {
    holdingItems = [holdingMessage];
  } else if (holdingStatus === "missing" && holdingMessage) {
    holdingItems = [holdingMessage];
  } else {
    holdingItems = ["실시간 보유 정보 없음"];
  }

  const summaryCards = [
    {
      title: "보유 현황",
      eyebrow: holdingStatus === "ok" ? "Live Holding" : "Holding Snapshot",
      accent: holdingStatus === "ok" ? "buy" : holdingStatus === "cached" ? "analysis" : "neutral",
      hero: holding
        ? `${formatInt(holding.quantity)}주`
        : holdingStatus === "timeout"
          ? "지연"
          : holdingStatus === "missing"
            ? "미보유"
            : "없음",
      heroMeta: holding
        ? `평단 ${formatInt(holding.avg_buy_price)}원`
        : holdingMessage || "실시간 보유 정보 없음",
      metrics: holding ? [
        { label: "현재가", value: `${formatInt(holding.current_price)}원` },
        { label: "평가손익", value: formatSignedKrW(holding.pnl) },
        { label: "수익률", value: formatPercent(holding.pnl_rate) },
      ] : [],
      body: holdingItems.slice(1),
      caption: holdingMessage && holdingStatus === "cached" ? holdingMessage : "",
    },
    {
      title: "AI 요약",
      eyebrow: "Latest Signal",
      accent: "analysis",
      hero: signal?.recommendation || "대기",
      heroMeta: signal
        ? `신뢰도 ${formatPercent((signal.confidence || 0) * 100).replace(".00", "")}`
        : "최근 AI 분석 요약 없음",
      metrics: signal ? [
        { label: "목표가", value: `${formatInt(signal.target_price)}원` },
        { label: "손절가", value: `${formatInt(signal.stop_loss_price)}원` },
        { label: "판단 시각", value: signal.created_at ? formatTimelineTime(signal.created_at) : "-" },
      ] : [],
      body: signal ? [signal.reason || "최근 분석 이유 없음"] : ["최근 AI 분석 요약 없음"],
    },
    {
      title: "거래 통계",
      eyebrow: "Execution Flow",
      accent: "sell",
      hero: `${formatInt(stats.total_trades)}건`,
      heroMeta: "누적 거래 이벤트",
      metrics: [
        { label: "보유", value: `${formatInt(stats.open_buy_count)}건` },
        { label: "청산", value: `${formatInt(stats.completed_count)}건` },
        { label: "실현손익", value: formatSignedKrW(stats.realized_pnl) },
      ],
      body: [
        `현재 열린 매수 포지션 ${formatInt(stats.open_buy_count)}건`,
      ],
    },
  ];

  const timelinePage = payload?.timeline_page || {};

  const timelineEntries = (payload?.timeline || []).map(buildPositionTimelineEntry);

  return {
    title: `${payload?.name || payload?.symbol || "종목"} · ${payload?.symbol || ""}`.trim(),
    symbol: payload?.symbol || "",
    settingsShortcutTab: summary.settings_shortcut_tab || "strategy",
    summaryCards,
    decisionInsight: buildDecisionInsight(summary),
    recentEventChips: buildRecentEventChips(summary),
    timelineEntries,
    timelineFilters: buildTimelineFilters(timelineEntries),
    timelineGroups: groupPositionTimeline(timelineEntries),
    timelinePage: {
      limit: Number(timelinePage.limit || timelineEntries.length || 20),
      offset: Number(timelinePage.offset || 0),
      returned: Number(timelinePage.returned || timelineEntries.length || 0),
      hasMore: Boolean(timelinePage.has_more),
      nextOffset: Number(
        timelinePage.next_offset
          ?? (Number(timelinePage.offset || 0) + Number(timelinePage.returned || timelineEntries.length || 0))
      ),
    },
    emptyMessage: "표시할 이벤트가 없습니다.",
  };
}
