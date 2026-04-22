function parseActivityDetailObject(detail) {
  if (!detail) return null;
  if (typeof detail === "object") return detail;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

export function buildTaskCardDescriptor(data) {
  const summary = String(data?.summary || "");
  const type = String(data?.activity_type || "").toUpperCase();

  if (type === "SCAN") {
    return { key: "scan", title: "시장 스캔", icon: "📡" };
  }
  if (type === "REPORT") {
    return { key: "report", title: "일일 리포트 작업", icon: "📝" };
  }
  if (/뉴스|공시|수집|poll/i.test(summary)) {
    return { key: "news", title: "뉴스 수집/해석", icon: "🛰️" };
  }
  if (type === "QA") {
    return { key: "qa", title: "Q&A 작업", icon: "💬" };
  }
  if (type === "DAILY_PLAN") {
    return { key: "daily-plan", title: "일일 계획 작업", icon: "📅" };
  }
  if (type === "LLM_CALL") {
    return { key: "llm", title: "공용 LLM 작업", icon: "🤖" };
  }
  if (type === "EVENT") {
    return { key: "event", title: "운영 이벤트", icon: "📣" };
  }
  if (type === "SCHEDULE" || type === "TRADING_RULE" || type === "HOLDINGS_CHECK") {
    return { key: "operations", title: "운영 스케줄 작업", icon: "⚙️" };
  }
  return { key: `task-${type || "misc"}`, title: type || "기타 작업", icon: "📌" };
}

export function resolveTaskCardRouting({
  activity,
  lastActivityGroupKey,
  latestTaskCardKeyByGroup,
  taskCards,
}) {
  const descriptor = buildTaskCardDescriptor(activity);
  const detail = parseActivityDetailObject(activity?.detail);
  const stableIdentity = String(
    activity?.cycle_id
      || detail?.task_key
      || detail?.source_code
      || detail?.report_date
      || detail?.mode
      || "",
  ).trim();
  const stable = Boolean(stableIdentity);
  const groupIdentity = stable ? `${descriptor.key}:${stableIdentity}` : descriptor.key;
  const groupKey = `task:${groupIdentity}`;
  const existingCardKey = latestTaskCardKeyByGroup[groupIdentity];
  const hasExistingCard = Boolean(existingCardKey && taskCards?.[existingCardKey]);
  const needsNewCard = stable
    ? !hasExistingCard
    : (lastActivityGroupKey !== groupKey || !hasExistingCard);

  return {
    descriptor,
    stable,
    groupIdentity,
    groupKey,
    existingCardKey,
    needsNewCard,
  };
}
