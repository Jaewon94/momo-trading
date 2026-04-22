import { describe, expect, test } from "vitest";

import { buildReportNewsRationale } from "../../admin/static/js/report_news_state.js";

describe("report_news_state", () => {
  test("builds buy and block rationale tags from trades and activities", () => {
    const rationale = buildReportNewsRationale({
      trades: {
        opened: [
          {
            notes: JSON.stringify({
              news_negative_pressure: 0.18,
              news_threshold: 0.75,
              news_source_count: 2,
              news_negative_count: 0,
              news_top_contributors: [
                { headline: "메모리 가격 반등 기대", pressure: 0.07 },
              ],
              entry_pattern: "거래량 동반 돌파",
            }),
          },
        ],
      },
      activityInsights: {
        items: [
          {
            category: "news",
            label: "뉴스 게이트",
            reason: "부정 뉴스 압력 0.80 >= 0.55",
          },
          {
            category: "cost",
            label: "비용 게이트",
            reason: "예상 슬리피지 대비 기대수익 부족",
          },
        ],
      },
    });

    expect(rationale.hasContent).toBe(true);
    expect(rationale.buyTags.some((item) => item.label === "뉴스 위험 낮음")).toBe(true);
    expect(rationale.buyTags.some((item) => item.label === "다중 소스 확인")).toBe(true);
    expect(rationale.buyTags.some((item) => item.label === "차트 패턴")).toBe(true);
    expect(rationale.blockTags[0]).toMatchObject({
      label: "뉴스 게이트",
      count: 1,
    });
  });

  test("returns empty state when there is no rationale data", () => {
    const rationale = buildReportNewsRationale({
      trades: { opened: [], completed: [], open_positions: [] },
      activityInsights: { items: [] },
    });

    expect(rationale.hasContent).toBe(false);
    expect(rationale.buyTags).toEqual([]);
    expect(rationale.blockTags).toEqual([]);
  });
});
