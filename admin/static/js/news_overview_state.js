function defaultFormatInteger(value) {
  return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
}

function defaultFormatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  }).format(date);
}

function defaultFormatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(numeric)}원`;
}

export function buildTradeBaselineNotice(overview = {}) {
  const baseline = overview?.baseline || {};
  return {
    active: Boolean(baseline?.active),
    label: String(baseline?.label || ""),
    effectiveDate: String(baseline?.effective_date || ""),
    summary: String(baseline?.summary || ""),
    details: Array.isArray(baseline?.details)
      ? baseline.details.map((item) => String(item || "")).filter(Boolean)
      : [],
  };
}

export function pickNewsDisplayFields(item = {}) {
  const displayTitle = String(item.display_title || item.title || "-");
  const displaySummary = String(item.display_summary || item.summary || "");
  const originalTitle = String(item.original_title || item.title || "");
  const originalSummary = String(item.original_summary || item.summary || "");

  return {
    title: displayTitle,
    summary: displaySummary,
    originalTitle,
    originalSummary,
    hasTranslation: Boolean(
      item.display_title
      && item.original_title
      && String(item.display_title).trim() !== String(item.original_title).trim()
    ),
  };
}

export function buildNewsOverviewCards(
  overview,
  {
    formatInteger = defaultFormatInteger,
    formatDateTime = defaultFormatDateTime,
  } = {},
) {
  const ingestion = overview?.ingestion || {};
  const performance = overview?.performance || {};
  const settings = overview?.settings || {};
  const storage = overview?.storage || {};
  const runtime = overview?.runtime?.overall || {};

  return [
    {
      label: "최근 24시간",
      value: `${formatInteger(ingestion.recent_24h_count || 0)}건`,
      help: storage.ready
        ? (ingestion.latest_published_at
          ? `마지막 적재 ${formatDateTime(ingestion.latest_published_at)}`
          : "아직 적재된 뉴스가 없습니다.")
        : `저장소 준비 필요 · ${storage.message || "news_items 테이블이 아직 없습니다."}`,
    },
    {
      label: "마지막 폴링",
      value: String(runtime.last_status || "IDLE"),
      help: runtime.last_run_at
        ? `${String(runtime.last_mode || "UNKNOWN")} · ${formatDateTime(runtime.last_run_at)} · ${String(runtime.last_message || "")}`.trim()
        : "아직 수집 이력이 없습니다.",
    },
    {
      label: "뉴스 게이트",
      value: `${formatInteger(performance.news_gate_blocks || 0)}회`,
      help: settings.gate_enabled ? "부정 압력 임계치 초과 시 매수 차단" : "현재 게이트 비활성화",
    },
    {
      label: "재검증",
      value: `${formatInteger(performance.news_rechecks || 0)}회`,
      help: settings.poll_enabled ? "신규 뉴스 도착 시 관련 종목만 증분 재검토" : "현재 자동 폴링 비활성화",
    },
  ];
}

export function buildReportNewsStripModel(
  overview,
  {
    formatInteger = defaultFormatInteger,
    formatDateTime = defaultFormatDateTime,
    formatSignedKrW = defaultFormatSignedKrW,
    recentLimit = 3,
  } = {},
) {
  const ingestion = overview?.ingestion || {};
  const performance = overview?.performance || {};
  const settings = overview?.settings || {};
  const sources = overview?.sources || {};
  const periodic = overview?.periodic || {};
  const runtime = overview?.runtime?.overall || {};
  const recentItems = Array.isArray(overview?.recent_items) ? overview.recent_items.slice(0, recentLimit) : [];
  const implementedCatalog = Array.isArray(sources.catalog)
    ? sources.catalog.filter((item) => item?.implemented)
    : [];
  const weeklyBucket = Array.isArray(periodic?.weekly?.buckets) && periodic.weekly.buckets.length
    ? periodic.weekly.buckets[periodic.weekly.buckets.length - 1]
    : null;
  const monthlyBucket = Array.isArray(periodic?.monthly?.buckets) && periodic.monthly.buckets.length
    ? periodic.monthly.buckets[periodic.monthly.buckets.length - 1]
    : null;
  const rollout = performance.rollout || {};

  return {
    statusLabel: String(runtime.last_status || "IDLE"),
    pollLabel: runtime.last_run_at
      ? String(runtime.last_mode || "UNKNOWN")
      : "대기",
    pollAtLabel: runtime.last_run_at ? formatDateTime(runtime.last_run_at) : "-",
    message: runtime.last_run_at
      ? String(runtime.last_message || "")
      : "아직 수집 이력이 없습니다.",
    recentCountLabel: `${formatInteger(ingestion.recent_24h_count || 0)}건`,
    recentAtLabel: ingestion.latest_published_at
      ? formatDateTime(ingestion.latest_published_at)
      : "최근 적재 없음",
    sourceSummary: `실구현 ${formatInteger(sources.implemented_count || 0)} / 전체 ${formatInteger(sources.enabled_count || 0)}`,
    sourceCodes: implementedCatalog.map((item) => String(item.code || "")).filter(Boolean),
    impactSummary: `뉴스 반영 거래 ${formatInteger(performance.trade_count_with_news || 0)}건 · 평균 부정 압력 ${Number(performance.avg_negative_pressure || 0).toFixed(2)}`,
    rolloutSummary: `${String(rollout.status || "HOLDOUT")} · ${String(rollout.reason || "표본 수집 중")}`,
    periodicSummary: [
      weeklyBucket
        ? `주간 E ${formatInteger(weeklyBucket?.metrics?.expectancy || 0)}`
        : "주간 집계 대기",
      monthlyBucket
        ? `월간 손익 ${formatSignedKrW(monthlyBucket?.metrics?.total_pnl || 0)}`
        : "월간 집계 대기",
    ].join(" · "),
    settingSummary: [
      String(settings.llm_provider || "AUTOMATIC"),
      settings.gate_enabled ? "게이트 ON" : "게이트 OFF",
      settings.domestic_media_enabled ? "국내 미디어 ON" : "국내 미디어 OFF",
      settings.nasdaq_enabled ? "Nasdaq ON" : "Nasdaq OFF",
      settings.include_foreign ? "해외 포함" : "국내 중심",
    ].join(" · "),
    recentItems,
  };
}

export function describeManualNewsFetchResult(sourceLabel, summary = {}) {
  const label = String(sourceLabel || "뉴스");
  const received = Number(summary.received || 0);
  const created = Number(summary.created || 0);
  const duplicates = Number(summary.duplicates || 0);

  if (created > 0) {
    return `${label} 수집 완료 · 신규 ${created}건 / 중복 ${duplicates}건`;
  }
  if (received > 0 && duplicates >= received) {
    return `${label} 수집 완료 · 모두 기존 기사라 중복 처리됐습니다. (${duplicates}건)`;
  }
  return `${label} 조회 완료 · 현재 조회 구간에 새 데이터가 없습니다.`;
}

export function buildNewsOverviewSourcePills(overview) {
  const settings = overview?.settings || {};
  const storage = overview?.storage || {};
  const sources = overview?.sources || {};
  const ingestion = overview?.ingestion || {};
  const runtimeSources = overview?.runtime?.sources || {};
  const catalog = Array.isArray(sources.catalog) ? sources.catalog : [];
  const sourceCounts = new Map(
    (Array.isArray(ingestion.by_source_24h) ? ingestion.by_source_24h : []).map((item) => [
      String(item?.source_code || ""),
      Number(item?.count || 0),
    ]),
  );

  return [
    `<div class="news-source-pill"><strong>${String(settings.llm_provider || "AUTOMATIC")}</strong><span>${settings.llm_enabled ? "뉴스 AI ON" : "규칙 기반만"}</span></div>`,
    `<div class="news-source-pill"><strong>${settings.include_foreign ? "해외 포함" : "국내 중심"}</strong><span>${String(sources.enabled_count || 0)}개 소스 · 실구현 ${String(sources.implemented_count || 0)}개</span></div>`,
    `<div class="news-source-pill"><strong>${storage.ready ? "저장소 준비" : "저장소 미준비"}</strong><span>${storage.ready ? "집계 가능" : "마이그레이션 필요"}</span></div>`,
    ...catalog.slice(0, 6).map((item) => {
      const runtime = runtimeSources?.[item.code] || {};
      const status = String(runtime.status || "IDLE");
      const count24h = sourceCounts.get(String(item.code || "")) || 0;
      const details = [];
      details.push(`24h ${count24h}건`);
      if (runtime.last_success_at) {
        details.push(`마지막 성공 ${defaultFormatDateTime(runtime.last_success_at)}`);
      }
      if (Number(runtime.consecutive_failures || 0) > 0) {
        details.push(`실패 ${Number(runtime.consecutive_failures || 0)}회`);
      } else if (runtime.last_error_at && status === "ERROR") {
        details.push(`마지막 실패 ${defaultFormatDateTime(runtime.last_error_at)}`);
      }
      details.push(
        runtime.message
          ? String(runtime.message)
          : (item.implemented ? `${String(item.tier || "-")} · ${String(item.region || "-")}` : "실수집 미연결"),
      );
      return `<div class="news-source-pill"><strong>${String(item.code || "")}</strong><span>${status} · ${details.join(" · ")}</span></div>`;
    }),
  ];
}
