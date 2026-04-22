function parseActivityDetail(detail) {
  if (!detail) return null;
  if (typeof detail === "object") return detail;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function extractBracketTitle(summary, fallback = "") {
  const match = String(summary || "").match(/\[([^\]]+)\]/);
  return match?.[1]?.trim() || fallback;
}

function extractReason(summary, detail) {
  if (detail?.reason) return String(detail.reason).trim();
  const raw = String(summary || "").trim();
  const colonIndex = raw.indexOf(":");
  if (colonIndex >= 0) return raw.slice(colonIndex + 1).trim();
  return raw.replace(/^[^\u3131-\uD79D\w]+/u, "").trim();
}

function classifyBlockedActivity(summary, detail) {
  const text = `${String(summary || "")} ${String(detail?.reason || "")}`;
  if (text.includes("뉴스 게이트")) {
    return { key: "news", label: "뉴스 게이트" };
  }
  if (text.includes("비용 게이트")) {
    return { key: "cost", label: "비용 게이트" };
  }
  return { key: "risk", label: "기타 리스크" };
}

export function buildReportActivityInsights(activities = []) {
  const blockedItems = [];
  let newsBlocked = 0;
  let costBlocked = 0;
  let riskBlocked = 0;
  let recheckCount = 0;

  for (const activity of Array.isArray(activities) ? activities : []) {
    const summary = String(activity?.summary || "");
    const activityType = String(activity?.activity_type || "").toUpperCase();
    const phase = String(activity?.phase || "").toUpperCase();
    const detail = parseActivityDetail(activity?.detail);

    if (activityType === "RISK_GATE" && phase === "SKIP") {
      const category = classifyBlockedActivity(summary, detail);
      if (category.key === "news") newsBlocked += 1;
      else if (category.key === "cost") costBlocked += 1;
      else riskBlocked += 1;

      blockedItems.push({
        category: category.key,
        label: category.label,
        symbol: String(activity?.symbol || "").trim(),
        title: extractBracketTitle(summary, String(activity?.symbol || "").trim() || "후보 종목"),
        reason: extractReason(summary, detail),
        createdAt: activity?.created_at || "",
      });
      continue;
    }

    if (summary.includes("신규 뉴스 감지 → 관련 종목 재검증")) {
      const symbols = Array.isArray(detail?.symbols) ? detail.symbols.filter(Boolean) : [];
      recheckCount += symbols.length || 1;
    }
  }

  blockedItems.sort((left, right) => String(right.createdAt || "").localeCompare(String(left.createdAt || "")));

  return {
    hasContent: blockedItems.length > 0 || recheckCount > 0,
    blockedCount: blockedItems.length,
    recheckCount,
    cards: [
      { key: "news", label: "뉴스 게이트", count: newsBlocked },
      { key: "cost", label: "비용 게이트", count: costBlocked },
      { key: "risk", label: "기타 리스크", count: riskBlocked },
      { key: "recheck", label: "뉴스 재검증", count: recheckCount },
    ],
    items: blockedItems.slice(0, 5),
  };
}
