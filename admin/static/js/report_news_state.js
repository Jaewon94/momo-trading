function parseNotes(notes) {
  if (!notes) return null;
  if (typeof notes === "object") return notes;
  try {
    return JSON.parse(notes);
  } catch {
    return null;
  }
}

function pushTag(store, label, detail) {
  if (!label) return;
  const current = store.get(label) || { label, count: 0, detail: "" };
  current.count += 1;
  if (!current.detail && detail) {
    current.detail = String(detail);
  }
  store.set(label, current);
}

export function buildReportNewsRationale({ trades = {}, activityInsights = {} } = {}) {
  const buyTagMap = new Map();
  const blockTagMap = new Map();
  const tradeRows = [
    ...(Array.isArray(trades?.opened) ? trades.opened : []),
    ...(Array.isArray(trades?.completed) ? trades.completed : []),
    ...(Array.isArray(trades?.open_positions) ? trades.open_positions : []),
  ];

  for (const trade of tradeRows) {
    const notes = parseNotes(trade?.notes);
    if (!notes) continue;
    const negativePressure = Number(notes.news_negative_pressure);
    const threshold = Number(notes.news_threshold);
    if (Number.isFinite(negativePressure) && Number.isFinite(threshold) && negativePressure < threshold) {
      pushTag(buyTagMap, "뉴스 위험 낮음", `압력 ${negativePressure.toFixed(2)} / 임계 ${threshold.toFixed(2)}`);
    }
    if (Number(notes.news_source_count || 0) >= 2) {
      pushTag(buyTagMap, "다중 소스 확인", `소스 ${Number(notes.news_source_count || 0)}개`);
    }
    if (Number(notes.news_negative_count || 0) === 0) {
      pushTag(buyTagMap, "최근 악재 없음", "최근 룩백 내 부정 뉴스 미감지");
    }
    if (notes.entry_pattern) {
      pushTag(buyTagMap, "차트 패턴", String(notes.entry_pattern));
    }
    const contributor = Array.isArray(notes.news_top_contributors) ? notes.news_top_contributors[0] : null;
    if (contributor?.headline) {
      pushTag(buyTagMap, "주요 뉴스 점검", String(contributor.headline));
    }
  }

  for (const item of Array.isArray(activityInsights?.items) ? activityInsights.items : []) {
    pushTag(blockTagMap, String(item.label || item.category || "보류"), String(item.reason || ""));
  }

  const buyTags = Array.from(buyTagMap.values())
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, 4);
  const blockTags = Array.from(blockTagMap.values())
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label))
    .slice(0, 4);

  return {
    hasContent: buyTags.length > 0 || blockTags.length > 0,
    buyTags,
    blockTags,
  };
}
