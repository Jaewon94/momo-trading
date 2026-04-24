function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)}%`;
}

function formatLatency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  return numeric >= 1000 ? `${(numeric / 1000).toFixed(1)}초` : `${numeric.toFixed(0)}ms`;
}

function formatMemory(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  return numeric >= 1024 ? `${(numeric / 1024).toFixed(2)}GB` : `${numeric.toFixed(1)}MB`;
}

function formatDateTimeLabel(value) {
  if (!value) return "-";
  try {
    const date = new Date(value);
    return new Intl.DateTimeFormat("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(date);
  } catch (_error) {
    return String(value);
  }
}

function buildLinePath(points, key, width = 360, height = 96, padding = 8) {
  if (!Array.isArray(points) || points.length < 2) {
    return { path: "", min: null, max: null, last: null };
  }
  const values = points.map((point) => Number(point?.[key])).filter((value) => Number.isFinite(value));
  if (values.length < 2) {
    return { path: "", min: null, max: null, last: null };
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - padding * 2) / Math.max(points.length - 1, 1);
  const path = points.map((point, index) => {
    const raw = Number(point?.[key]);
    const value = Number.isFinite(raw) ? raw : min;
    const x = padding + (stepX * index);
    const y = height - padding - (((value - min) / span) * (height - padding * 2));
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return {
    path,
    min,
    max,
    last: Number(points[points.length - 1]?.[key]),
  };
}

export function buildObservabilityDashboardState(payload = {}) {
  const latest = payload?.latest_snapshot || {};
  const resourceSummary = payload?.resource_summary || {};
  const series = Array.isArray(payload?.resource_series) ? payload.resource_series : [];
  const llm = payload?.llm || {};
  const aiSkipped = payload?.ai_skipped || {};
  const newsPoll = payload?.jobs?.news_poll || {};
  const maintenance = payload?.jobs?.maintenance || {};
  const storage = payload?.storage || {};
  const windowInfo = payload?.window || {};
  const trends = payload?.trends || {};
  const llmTrend = Array.isArray(trends?.llm) ? trends.llm : [];
  const newsTrend = Array.isArray(trends?.news_poll) ? trends.news_poll : [];
  const recommendations = payload?.recommendations || {};
  const machinePressure = recommendations?.machine_pressure || {};
  const newsRecommendation = recommendations?.news_translation || {};
  const manualRecommendation = recommendations?.manual_analysis || {};
  const concurrencyRecommendation = recommendations?.ollama_concurrency || {};
  const errors = payload?.errors || {};
  const recentErrors = Array.isArray(errors?.recent) ? errors.recent : [];
  const incidents = Array.isArray(errors?.incidents) ? errors.incidents : [];

  return {
    machine: {
      host: String(latest.host || "-"),
      runtime: [latest.app_name, latest.environment, latest.python_version].filter(Boolean).join(" · ") || "-",
      platform: [latest.platform_system, latest.platform_machine].filter(Boolean).join(" · ") || "-",
      latestCollectedAt: formatDateTimeLabel(resourceSummary.latest_collected_at),
    },
    window: {
      hours: Number(windowInfo.hours || 24),
      resolution: String(windowInfo.resolution || "raw"),
    },
    summaryCards: [
      {
        label: "메모리 사용률",
        value: formatPercent(latest.memory_percent),
        help: `평균 ${formatPercent(resourceSummary.avg_memory_percent)} · 최고 ${formatPercent(resourceSummary.peak_memory_percent)}`,
      },
      {
        label: "CPU Load Ratio",
        value: formatNumber(latest.cpu_load_ratio_1m, 2),
        help: `평균 ${formatNumber(resourceSummary.avg_cpu_load_ratio_1m, 2)} · 최고 ${formatNumber(resourceSummary.peak_cpu_load_ratio_1m, 2)}`,
      },
      {
        label: "앱 RSS",
        value: formatMemory(latest.app_rss_mb),
        help: `최고 ${formatMemory(resourceSummary.peak_app_rss_mb)}`,
      },
      {
        label: "Ollama RSS",
        value: latest.ollama_running ? formatMemory(latest.ollama_rss_mb) : "OFF",
        help: `최고 ${formatMemory(resourceSummary.peak_ollama_rss_mb)}`,
      },
      {
        label: "LLM 성공률",
        value: formatPercent(llm.success_rate),
        help: `호출 ${llm.total_calls || 0}회 · p95 ${formatLatency(llm.p95_elapsed_ms)}`,
      },
      {
        label: "AI 스킵",
        value: `${Number(aiSkipped.total_skipped || 0)}회`,
        help: `최근 ${String((aiSkipped.by_stage || [])[0]?.stage || "-")} ${Number((aiSkipped.by_stage || [])[0]?.count || 0)}회`,
      },
      {
        label: "뉴스 폴링",
        value: `${newsPoll.runs || 0}회`,
        help: `성공률 ${formatPercent(newsPoll.success_rate)} · 생성 ${newsPoll.created_total || 0}건`,
      },
      {
        label: "Raw 보존",
        value: `${Number(storage.raw_retention_days || 0)}일`,
        help: `현재 창에서 리소스 ${Number(storage.resource_rollup_buckets || 0)}개 bucket`,
      },
      {
        label: "Hourly Rollup",
        value: `${Number(storage.execution_rollup_buckets || 0)}개`,
        help: `보존 ${Number(storage.rollup_retention_days || 0)}일 · lookback ${Number(storage.rollup_lookback_hours || 0)}h`,
      },
    ],
    resourceCharts: [
      {
        key: "cpu_load_ratio_1m",
        label: "CPU Load Ratio",
        unit: "",
        line: buildLinePath(series, "cpu_load_ratio_1m"),
      },
      {
        key: "memory_percent",
        label: "Memory %",
        unit: "%",
        line: buildLinePath(series, "memory_percent"),
      },
      {
        key: "app_rss_mb",
        label: "App RSS",
        unit: "MB",
        line: buildLinePath(series, "app_rss_mb"),
      },
      {
        key: "ollama_rss_mb",
        label: "Ollama RSS",
        unit: "MB",
        line: buildLinePath(series, "ollama_rss_mb"),
      },
    ],
    trendCharts: [
      {
        key: "avg_elapsed_ms",
        label: "LLM Avg Latency",
        unit: "ms",
        line: buildLinePath(llmTrend, "avg_elapsed_ms"),
        meta: `호출 ${llmTrend.reduce((total, point) => total + Number(point.calls || 0), 0)}회`,
      },
      {
        key: "success_rate",
        label: "LLM Success Rate",
        unit: "%",
        line: buildLinePath(llmTrend, "success_rate"),
        meta: `최근 ${windowInfo.resolution || "raw"} 추세`,
      },
      {
        key: "avg_elapsed_ms",
        label: "News Poll Avg Latency",
        unit: "ms",
        line: buildLinePath(newsTrend, "avg_elapsed_ms"),
        meta: `실행 ${newsTrend.reduce((total, point) => total + Number(point.runs || 0), 0)}회`,
      },
      {
        key: "created_total",
        label: "News Created",
        unit: "",
        line: buildLinePath(newsTrend, "created_total"),
        meta: `생성 ${newsTrend.reduce((total, point) => total + Number(point.created_total || 0), 0)}건`,
      },
    ],
    providerRows: Array.isArray(llm.provider_breakdown)
      ? llm.provider_breakdown.map((row) => ({
        provider: String(row.provider || "UNKNOWN"),
        calls: `${Number(row.calls || 0)}회`,
        successRate: formatPercent(row.success_rate),
        avgLatency: formatLatency(row.avg_elapsed_ms),
        p95Latency: formatLatency(row.p95_elapsed_ms),
        fallbackRate: formatPercent(row.fallback_rate),
      }))
      : [],
    functionRows: Array.isArray(llm.function_breakdown)
      ? llm.function_breakdown.map((row) => ({
        functionName: String(row.function || "UNKNOWN"),
        calls: `${Number(row.calls || 0)}회`,
        successRate: formatPercent(row.success_rate),
        avgLatency: formatLatency(row.avg_elapsed_ms),
        p95Latency: formatLatency(row.p95_elapsed_ms),
        fallbackRate: formatPercent(row.fallback_rate),
        promptChars: `${Number(row.prompt_chars || 0).toLocaleString("ko-KR")}자`,
        responseChars: `${Number(row.response_chars || 0).toLocaleString("ko-KR")}자`,
      }))
      : [],
    newsRows: [
      { label: "실행 횟수", value: `${Number(newsPoll.runs || 0)}회` },
      { label: "평균 지연", value: formatLatency(newsPoll.avg_elapsed_ms) },
      { label: "p95 지연", value: formatLatency(newsPoll.p95_elapsed_ms) },
      { label: "수신 기사", value: `${Number(newsPoll.received_total || 0)}건` },
      { label: "생성 기사", value: `${Number(newsPoll.created_total || 0)}건` },
      { label: "소스 오류", value: `${Number(newsPoll.source_error_total || 0)}건` },
    ],
    maintenanceRows: [
      { label: "최근 실행", value: formatDateTimeLabel(maintenance.last_run_at) },
      { label: "최근 상태", value: String(maintenance.last_status || "-") },
      { label: "평균 성공률", value: formatPercent(maintenance.success_rate) },
      { label: "최근 지연", value: formatLatency(maintenance.last_elapsed_ms) },
      { label: "최근 raw 정리", value: `${Number(maintenance.last_deleted_resource_rows || 0) + Number(maintenance.last_deleted_execution_rows || 0)}건` },
      { label: "최근 rollup 생성", value: `${Number(maintenance.last_resource_rollups_created || 0) + Number(maintenance.last_execution_rollups_created || 0)}개` },
    ],
    aiSkippedRows: Array.isArray(aiSkipped.by_reason)
      ? aiSkipped.by_reason.map((row) => ({
        stage: String(row.stage || "UNKNOWN"),
        reasonCode: String(row.reason_code || "UNKNOWN"),
        count: `${Number(row.count || 0)}회`,
      }))
      : [],
    aiSkippedRecentRows: Array.isArray(aiSkipped.recent)
      ? aiSkipped.recent.map((row) => ({
        title: [row.stage, row.reason_code, row.symbol].filter(Boolean).join(" · ") || "-",
        meta: [row.skipped_tier, row.source, row.action].filter(Boolean).join(" · "),
        reason: String(row.reason || "-"),
        createdAt: formatDateTimeLabel(row.created_at),
      }))
      : [],
    statusRows: Array.isArray(newsPoll.status_breakdown)
      ? newsPoll.status_breakdown.map((row) => ({
        status: String(row.status || "UNKNOWN"),
        count: `${Number(row.count || 0)}회`,
      }))
      : [],
    recommendationCards: [
      {
        label: "머신 압박",
        value: String(machinePressure.severity || "-"),
        help: Array.isArray(machinePressure.reasons) ? machinePressure.reasons.join(" · ") : "-",
      },
      {
        label: "뉴스 번역 추천",
        value: `${String((newsRecommendation.recommended || {}).provider || "-")} / ${String((newsRecommendation.recommended || {}).model || "-")}`,
        help: `${String(newsRecommendation.action || "KEEP")} · ${Array.isArray(newsRecommendation.reasons) ? newsRecommendation.reasons.join(" · ") : "-"}`,
      },
      {
        label: "수동 분석 추천",
        value: `${String((manualRecommendation.recommended || {}).provider || "-")} / ${String((manualRecommendation.recommended || {}).model || "-")}`,
        help: `${String(manualRecommendation.action || "KEEP")} · ${Array.isArray(manualRecommendation.reasons) ? manualRecommendation.reasons.join(" · ") : "-"}`,
      },
      {
        label: "Ollama 병렬도",
        value: `${Number(concurrencyRecommendation.recommended_parallel_jobs || 0)}개`,
        help: Array.isArray(concurrencyRecommendation.reasons) ? concurrencyRecommendation.reasons.join(" · ") : "-",
      },
    ],
    recentErrors: recentErrors.map((row) => ({
      title: [row.component, row.operation].filter(Boolean).join(" · ") || "-",
      meta: [row.severity, row.exception_type, row.symbol].filter(Boolean).join(" · "),
      detail: String(row.exception_message || "-"),
      occurredAt: formatDateTimeLabel(row.created_at),
    })),
    incidentRows: incidents.map((row) => ({
      fingerprint: String(row.fingerprint || ""),
      title: String(row.title || "-"),
      meta: [row.severity, row.status, `${Number(row.occurrence_count || 0)}회`].filter(Boolean).join(" · "),
      status: String(row.status || "OPEN").toUpperCase(),
      detail: String(row.last_message || "-"),
      lastSeenAt: formatDateTimeLabel(row.last_seen_at),
      ownerNote: String(row.owner_note || "").trim(),
    })),
  };
}
