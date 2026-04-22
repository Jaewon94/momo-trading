import { pickNewsDisplayFields } from "./news_overview_state.js";

function formatArchiveDateKey(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function formatArchiveDateLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function formatArchiveTimeLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function normalizeText(value) {
  return String(value || "").trim();
}

function normalizeFilters(filters = {}) {
  return {
    published_from: normalizeText(filters.published_from),
    published_to: normalizeText(filters.published_to),
    source_code: normalizeText(filters.source_code).toUpperCase(),
    symbol: normalizeText(filters.symbol),
    sentiment_label: normalizeText(filters.sentiment_label).toUpperCase(),
    query: normalizeText(filters.query),
  };
}

function buildSentimentTone(label) {
  const normalized = String(label || "").toUpperCase();
  if (normalized === "POSITIVE") {
    return { label: "긍정", toneClass: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" };
  }
  if (normalized === "NEGATIVE") {
    return { label: "부정", toneClass: "text-rose-300 border-rose-500/30 bg-rose-500/10" };
  }
  if (normalized === "NEUTRAL") {
    return { label: "중립", toneClass: "text-gray-300 border-gray-600 bg-dark-800/80" };
  }
  return { label: normalized || "미분류", toneClass: "text-gray-300 border-gray-600 bg-dark-800/80" };
}

function buildSourceOptions(catalog = [], items = []) {
  const names = new Map(
    (Array.isArray(catalog) ? catalog : []).map((item) => [
      String(item?.code || "").toUpperCase(),
      String(item?.name || item?.code || "").trim(),
    ]),
  );
  (Array.isArray(items) ? items : []).forEach((item) => {
    const code = String(item?.source_code || "").toUpperCase();
    if (!code || names.has(code)) return;
    names.set(code, String(item?.source_name || code));
  });

  return Array.from(names.entries())
    .map(([code, name]) => ({ code, name }))
    .sort((a, b) => a.code.localeCompare(b.code));
}

export function buildNewsArchiveState(items = [], { filters = {}, catalog = [] } = {}) {
  const normalizedFilters = normalizeFilters(filters);
  const rows = Array.isArray(items) ? items : [];
  const groups = new Map();
  const symbolSet = new Set();
  const sourceCounts = new Map();

  rows.forEach((item) => {
    const display = pickNewsDisplayFields(item);
    const dateKey = formatArchiveDateKey(item?.published_at);
    const sourceCode = String(item?.source_code || "-");
    const symbols = Array.isArray(item?.symbols) ? item.symbols.filter(Boolean).map((value) => String(value)) : [];
    symbols.forEach((symbol) => symbolSet.add(symbol));
    sourceCounts.set(sourceCode, (sourceCounts.get(sourceCode) || 0) + 1);
    const sectorLabels = Array.isArray(item?.metadata?.matched_sector_labels)
      ? item.metadata.matched_sector_labels.map((value) => String(value)).filter(Boolean)
      : [];
    const sectorLabel = normalizeText(item?.metadata?.sector_label) || sectorLabels[0] || "";
    const group = groups.get(dateKey) || {
      dateKey,
      dateLabel: formatArchiveDateLabel(item?.published_at),
      count: 0,
      items: [],
    };
    const sentiment = buildSentimentTone(item?.sentiment_label);
    group.count += 1;
    group.items.push({
      id: String(item?.id || `${dateKey}-${group.count}`),
      publishedAt: String(item?.published_at || ""),
      timeLabel: formatArchiveTimeLabel(item?.published_at),
      title: display.title,
      summary: display.summary,
      originalTitle: display.originalTitle,
      originalSummary: display.originalSummary,
      hasTranslation: display.hasTranslation,
      sourceCode,
      sourceName: String(item?.source_name || item?.source_code || "-"),
      sourceLabel: String(item?.source_name || item?.source_code || "-"),
      sentimentLabel: sentiment.label,
      sentimentToneClass: sentiment.toneClass,
      impactLabel: `영향 ${Number(item?.impact_score || 0).toFixed(2)}`,
      trustLabel: `신뢰 ${Number(item?.trust_score || 0).toFixed(2)}`,
      symbols,
      symbolLabel: symbols.length ? symbols.join(", ") : "-",
      sectorLabel,
      regionLabel: String(item?.region || "-"),
      url: normalizeText(item?.url),
      metadata: item?.metadata || {},
    });
    groups.set(dateKey, group);
  });

  const sortedGroups = Array.from(groups.values())
    .sort((a, b) => String(b.dateKey).localeCompare(String(a.dateKey)))
    .map((group) => ({
      ...group,
      items: group.items.sort((a, b) => String(b.publishedAt).localeCompare(String(a.publishedAt))),
    }));

  return {
    filters: normalizedFilters,
    totalCount: rows.length,
    groupCount: sortedGroups.length,
    symbolCount: symbolSet.size,
    sourceSummary: Array.from(sourceCounts.entries())
      .map(([code, count]) => ({ code, count }))
      .sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count;
        return a.code.localeCompare(b.code);
      }),
    sourceOptions: buildSourceOptions(catalog, rows),
    sentimentOptions: [
      { value: "", label: "전체 감성" },
      { value: "POSITIVE", label: "긍정" },
      { value: "NEUTRAL", label: "중립" },
      { value: "NEGATIVE", label: "부정" },
    ],
    groups: sortedGroups,
    emptyMessage: rows.length
      ? ""
      : "조건에 맞는 뉴스가 없습니다. 날짜 범위나 소스 필터를 넓혀서 다시 확인해 주세요.",
  };
}

export function buildNewsArchiveCountSummary({ filteredCount = 0, overallCount = 0 } = {}) {
  const formatInteger = (value) => new Intl.NumberFormat("ko-KR").format(Number(value || 0));
  return {
    filteredLabel: `${formatInteger(filteredCount)}건`,
    overallLabel: `${formatInteger(overallCount)}건`,
    helper: `현재 필터 결과 ${formatInteger(filteredCount)}건 · 전체 적재 ${formatInteger(overallCount)}건`,
  };
}
