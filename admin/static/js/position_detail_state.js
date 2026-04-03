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

  if (type === "trade") {
    if (side === "SELL") {
      return {
        filterKey: "trade",
        tone: "sell",
        icon: "매도",
        badge: status || "SELL",
        kindLabel: "매도",
      };
    }
    return {
      filterKey: "trade",
      tone: status === "PENDING_CONFIRM" ? "pending" : "buy",
      icon: status === "PENDING_CONFIRM" ? "대기" : "매수",
      badge: status || "BUY",
      kindLabel: status === "PENDING_CONFIRM" ? "매수 대기" : "매수",
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
    error: entries.filter((entry) => entry.filterKey === "error").length,
  };

  return [
    { key: "all", label: "전체", count: counts.all },
    { key: "trade", label: "거래", count: counts.trade },
    { key: "ai", label: "AI", count: counts.ai },
    { key: "error", label: "오류", count: counts.error },
  ];
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
