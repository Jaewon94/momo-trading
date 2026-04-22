import { describe, expect, test } from "vitest";

import { buildNewsArchiveCountSummary, buildNewsArchiveState } from "../../admin/static/js/news_archive_state.js";

describe("news_archive_state", () => {
  test("groups items by date and prefers translated display fields", () => {
    const state = buildNewsArchiveState(
      [
        {
          id: "n1",
          source_code: "INVESTING",
          source_name: "Investing.com",
          published_at: "2026-04-06T09:10:00+09:00",
          display_title: "반도체 사이클 기대 회복",
          display_summary: "삼성전자 중심으로 반등 기대",
          original_title: "Chip cycle optimism returns",
          original_summary: "Samsung suppliers may recover",
          sentiment_label: "POSITIVE",
          impact_score: 0.71,
          trust_score: 0.83,
          symbols: ["005930"],
          metadata: {
            sector_label: "반도체",
          },
        },
        {
          id: "n2",
          source_code: "DART",
          source_name: "금융감독원 전자공시",
          published_at: "2026-04-05T18:30:00+09:00",
          title: "삼성전자 자사주 취득 결정",
          summary: "주주환원 정책 강화",
          sentiment_label: "NEUTRAL",
          impact_score: 0.42,
          trust_score: 1.0,
          symbols: ["005930"],
          metadata: {},
        },
      ],
      {
        filters: {
          published_from: "2026-04-05",
          published_to: "2026-04-06",
          source_code: "",
          symbol: "005930",
          sentiment_label: "",
          query: "",
        },
        catalog: [
          { code: "DART", name: "금융감독원 전자공시" },
          { code: "INVESTING", name: "Investing.com Stock Market News" },
        ],
      },
    );

    expect(state.totalCount).toBe(2);
    expect(state.groupCount).toBe(2);
    expect(state.symbolCount).toBe(1);
    expect(state.sourceSummary).toEqual([
      { code: "DART", count: 1 },
      { code: "INVESTING", count: 1 },
    ]);
    expect(state.groups[0].dateKey).toBe("2026-04-06");
    expect(state.groups[0].items[0].title).toBe("반도체 사이클 기대 회복");
    expect(state.groups[0].items[0].hasTranslation).toBe(true);
    expect(state.groups[0].items[0].sectorLabel).toBe("반도체");
    expect(state.groups[0].items[0].metadata.sector_label).toBe("반도체");
    expect(state.sourceOptions.map((item) => item.code)).toEqual(["DART", "INVESTING"]);
  });

  test("returns empty message when archive list is empty", () => {
    const state = buildNewsArchiveState([], {
      filters: {
        published_from: "2026-04-05",
        published_to: "2026-04-06",
      },
      catalog: [],
    });

    expect(state.totalCount).toBe(0);
    expect(state.emptyMessage).toContain("조건에 맞는 뉴스가 없습니다");
    expect(state.groups).toEqual([]);
  });

  test("builds count summary for filtered and overall totals", () => {
    const summary = buildNewsArchiveCountSummary({ filteredCount: 12, overallCount: 112 });

    expect(summary.filteredLabel).toBe("12건");
    expect(summary.overallLabel).toBe("112건");
    expect(summary.helper).toContain("현재 필터 결과 12건");
    expect(summary.helper).toContain("전체 적재 112건");
  });
});
