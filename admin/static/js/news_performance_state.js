function defaultFormatInteger(value) {
  return new Intl.NumberFormat("ko-KR").format(Number(value || 0));
}

function defaultFormatSignedKrW(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ko-KR").format(numeric)}원`;
}

function defaultFormatPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

export function buildNewsPerformanceCards(
  overview,
  {
    formatInteger = defaultFormatInteger,
    formatSignedKrW = defaultFormatSignedKrW,
    formatPercent = defaultFormatPercent,
  } = {},
) {
  const overall = overview?.performance?.overall || {};
  const shadow = overview?.performance?.shadow || {};
  const blockedByNews = Number(shadow.blocked_by_news_count || 0);
  const candidateCount = Number(shadow.candidate_count || 0);
  const blockRate = Number(shadow.block_rate || 0);

  return [
    {
      label: "기대값",
      value: formatSignedKrW(overall.expectancy || 0),
      help: "거래 1건당 기대 원화 손익",
    },
    {
      label: "PF",
      value: Number(overall.profit_factor || 0).toFixed(2),
      help: "총이익 / 총손실",
    },
    {
      label: "MDD",
      value: formatSignedKrW(overall.max_drawdown || 0),
      help: "누적 손익 기준 최대 낙폭",
    },
    {
      label: "비용 차감 손익",
      value: formatSignedKrW(overall.net_pnl_after_cost || 0),
      help: `추정 비용 ${formatSignedKrW(overall.estimated_cost_total || 0)} 반영`,
    },
    {
      label: "Shadow 후보",
      value: `${formatInteger(candidateCount)}건`,
      help: `뉴스ON/OFF 비교 후보 ${formatInteger(candidateCount)}건`,
    },
    {
      label: "뉴스 차단율",
      value: formatPercent(blockRate),
      help: `후보 ${formatInteger(candidateCount)}건 중 ${formatInteger(blockedByNews)}건 차단 (${formatPercent(blockRate)})`,
    },
  ];
}

export function buildNewsRolloutPolicy(
  overview,
  {
    formatInteger = defaultFormatInteger,
    formatSignedKrW = defaultFormatSignedKrW,
  } = {},
) {
  const settings = overview?.settings || {};
  const rollout = overview?.performance?.rollout || {};
  const maxDrawdownLimit = -Math.abs(Number(settings.rollout_max_drawdown_krw || 0));

  return {
    status: String(rollout.status || "HOLDOUT"),
    reason: String(rollout.reason || "표본 수집 중"),
    lines: [
      settings.shadow_enabled ? "Shadow ON · 뉴스ON/OFF 비교 기록 중" : "Shadow OFF · 비교 집계 중단",
      `표본 ${formatInteger(settings.rollout_min_sample_size || 0)}건 · PF ${Number(settings.rollout_min_profit_factor || 0).toFixed(2)} · 기대값 ${formatSignedKrW(settings.rollout_min_expectancy || 0)} 이상`,
      `MDD ${formatSignedKrW(maxDrawdownLimit)} 이상 방어`,
    ],
  };
}
