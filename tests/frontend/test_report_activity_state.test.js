import { describe, expect, test } from "vitest";

import { buildReportActivityInsights } from "../../admin/static/js/report_activity_state.js";

describe("report_activity_state", () => {
  test("summarizes blocked buys and news rechecks by category", () => {
    const insights = buildReportActivityInsights([
      {
        activity_type: "RISK_GATE",
        phase: "SKIP",
        symbol: "005930",
        summary: "🚫 [삼성전자] 뉴스 게이트 차단: 부정 뉴스 압력 0.80 >= 0.55",
        detail: JSON.stringify({
          reason: "부정 뉴스 압력 0.80 >= 0.55",
          negative_pressure: 0.8,
        }),
        created_at: "2026-04-03T09:12:00+09:00",
      },
      {
        activity_type: "RISK_GATE",
        phase: "SKIP",
        symbol: "003280",
        summary: "🚫 [흥아해운] 비용 게이트 차단: 기대수익 부족",
        detail: JSON.stringify({
          reason: "예상 슬리피지 대비 기대수익 부족",
        }),
        created_at: "2026-04-03T09:10:00+09:00",
      },
      {
        activity_type: "RISK_GATE",
        phase: "SKIP",
        symbol: "215790",
        summary: "🛑 연속 5회 손실 → 매수 차단 (하드 룰)",
        detail: null,
        created_at: "2026-04-03T09:08:00+09:00",
      },
      {
        activity_type: "EVENT",
        phase: "PROGRESS",
        symbol: null,
        summary: "📰 신규 뉴스 감지 → 관련 종목 재검증 (005930, 003280)",
        detail: JSON.stringify({
          symbols: ["005930", "003280"],
          title: "삼성전자 시설투자 공시",
        }),
        created_at: "2026-04-03T09:07:00+09:00",
      },
    ]);

    expect(insights.hasContent).toBe(true);
    expect(insights.blockedCount).toBe(3);
    expect(insights.recheckCount).toBe(2);
    expect(insights.cards).toEqual([
      { key: "news", label: "뉴스 게이트", count: 1 },
      { key: "cost", label: "비용 게이트", count: 1 },
      { key: "risk", label: "기타 리스크", count: 1 },
      { key: "recheck", label: "뉴스 재검증", count: 2 },
    ]);
    expect(insights.items[0]).toMatchObject({
      category: "news",
      label: "뉴스 게이트",
      symbol: "005930",
      title: "삼성전자",
    });
    expect(insights.items[0].reason).toContain("부정 뉴스 압력");
  });

  test("returns empty state when there are no relevant activities", () => {
    const insights = buildReportActivityInsights([
      {
        activity_type: "TIER1_ANALYSIS",
        phase: "COMPLETE",
        summary: "분석 완료",
        detail: null,
        created_at: "2026-04-03T09:00:00+09:00",
      },
    ]);

    expect(insights.hasContent).toBe(false);
    expect(insights.blockedCount).toBe(0);
    expect(insights.recheckCount).toBe(0);
    expect(insights.items).toEqual([]);
  });
});
