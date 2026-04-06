import { describe, expect, test } from "vitest";

import {
  buildNewsOverviewCards,
  buildTradeBaselineNotice,
  buildReportNewsStripModel,
  buildNewsOverviewSourcePills,
  buildManualNewsFetchState,
  describeManualNewsFetchResult,
  pickNewsDisplayFields,
} from "../../admin/static/js/news_overview_state.js";

describe("news_overview_state", () => {
  test("builds runtime-focused overview cards", () => {
    const cards = buildNewsOverviewCards({
      ingestion: {
        recent_24h_count: 4,
        latest_published_at: "2026-04-06T09:12:00+09:00",
      },
      performance: {
        news_gate_blocks: 3,
        news_rechecks: 2,
        avg_negative_pressure: 0.27,
        trade_count_with_news: 5,
      },
      settings: {
        gate_enabled: true,
        poll_enabled: true,
      },
      storage: {
        ready: true,
      },
      runtime: {
        overall: {
          last_status: "EMPTY",
          last_mode: "AUTO_OFF_HOURS",
          last_message: "조회된 데이터 없음",
          last_run_at: "2026-04-06T09:20:00+09:00",
        },
      },
    });

    expect(cards[0].label).toBe("최근 24시간");
    expect(cards[0].help).toContain("마지막 적재");
    expect(cards[1].label).toBe("마지막 폴링");
    expect(cards[1].value).toBe("EMPTY");
    expect(cards[1].help).toContain("AUTO_OFF_HOURS");
    expect(cards[2].label).toBe("뉴스 게이트");
    expect(cards[3].label).toBe("재검증");
  });

  test("builds source pills with runtime status and unimplemented hints", () => {
    const pills = buildNewsOverviewSourcePills({
      settings: {
        llm_provider: "OLLAMA",
        llm_enabled: true,
        include_foreign: true,
      },
      storage: {
        ready: true,
      },
      sources: {
        enabled_count: 5,
        catalog: [
          { code: "DART", tier: "A", region: "KR", implemented: true },
          { code: "KRX", tier: "A", region: "KR", implemented: false },
        ],
      },
      ingestion: {
        by_source_24h: [
          { source_code: "DART", count: 3 },
          { source_code: "KRX", count: 0 },
        ],
      },
      runtime: {
        sources: {
          DART: {
            status: "SUCCESS",
            message: "신규 2건 적재",
            updated_at: "2026-04-06T09:19:00+09:00",
            last_success_at: "2026-04-06T09:18:00+09:00",
            consecutive_failures: 0,
            counts: { created: 2, duplicates: 1, skipped: 0 },
          },
          KRX: {
            status: "ERROR",
            message: "실수집 미연결",
            updated_at: "2026-04-06T09:17:00+09:00",
            last_error_at: "2026-04-06T09:17:00+09:00",
            consecutive_failures: 3,
            counts: { created: 0, duplicates: 0, skipped: 0 },
          },
        },
      },
    });

    expect(pills[0]).toContain("OLLAMA");
    expect(pills[1]).toContain("해외 포함");
    expect(pills.some((pill) => pill.includes("DART") && pill.includes("SUCCESS") && pill.includes("24h 3건") && pill.includes("최근 실행") && pill.includes("신규 2 · 중복 1") && pill.includes("마지막 성공"))).toBe(true);
    expect(pills.some((pill) => pill.includes("KRX") && pill.includes("24h 0건") && pill.includes("마지막 실패") && pill.includes("연속 실패 3회") && pill.includes("미연결"))).toBe(true);
  });

  test("builds trade baseline notice for reset guidance", () => {
    const notice = buildTradeBaselineNotice({
      baseline: {
        active: true,
        effective_date: "2026-04-06",
        label: "2026-04-06 기준선 리셋 이후 데이터",
        summary: "현재 브로커 계좌 상태와 복구된 열린 BUY lot를 기준선으로 사용 중",
        details: [
          "현재 보유 종목/수량은 브로커 응답 기준",
          "과거 실현손익은 완전 복구하지 않음",
        ],
      },
    });

    expect(notice.active).toBe(true);
    expect(notice.effectiveDate).toBe("2026-04-06");
    expect(notice.label).toContain("기준선 리셋");
    expect(notice.details).toHaveLength(2);
  });

  test("builds report news strip summary for today report header", () => {
    const model = buildReportNewsStripModel({
      ingestion: {
        recent_24h_count: 7,
        latest_published_at: "2026-04-06T09:12:00+09:00",
      },
      settings: {
        llm_provider: "OLLAMA",
        gate_enabled: true,
        include_foreign: false,
      },
      performance: {
        trade_count_with_news: 5,
        avg_negative_pressure: 0.31,
        rollout: {
          status: "PROMOTE",
          reason: "표본과 기대값이 안정적이라 뉴스 전략 비중 확대 권장",
        },
      },
      periodic: {
        weekly: {
          buckets: [
            { end: "2026-04-06", metrics: { expectancy: 820.0, total_pnl: 4500.0 } },
          ],
        },
        monthly: {
          buckets: [
            { end: "2026-04-01", metrics: { expectancy: 640.0, total_pnl: 12500.0 } },
          ],
        },
      },
      sources: {
        enabled_count: 5,
        implemented_count: 2,
        catalog: [
          { code: "DART", implemented: true },
          { code: "KRX", implemented: true },
          { code: "REUTERS", implemented: false },
        ],
      },
      runtime: {
        overall: {
          last_status: "SUCCESS",
          last_mode: "AUTO_TRADING",
          last_message: "신규 2건 적재",
          last_run_at: "2026-04-06T09:20:00+09:00",
        },
      },
      recent_items: [
        { id: 1, title: "첫 기사" },
        { id: 2, title: "둘 기사" },
        { id: 3, title: "셋 기사" },
        { id: 4, title: "넷 기사" },
      ],
    });

    expect(model.statusLabel).toBe("SUCCESS");
    expect(model.pollLabel).toBe("AUTO_TRADING");
    expect(model.message).toBe("신규 2건 적재");
    expect(model.recentCountLabel).toBe("7건");
    expect(model.sourceSummary).toBe("실구현 2 / 전체 5");
    expect(model.settingSummary).toContain("OLLAMA");
    expect(model.settingSummary).toContain("게이트 ON");
    expect(model.settingSummary).toContain("국내 중심");
    expect(model.impactSummary).toBe("뉴스 반영 거래 5건 · 평균 부정 압력 0.31");
    expect(model.rolloutSummary).toContain("PROMOTE");
    expect(model.rolloutSummary).toContain("비중 확대");
    expect(model.periodicSummary).toContain("주간 E 820");
    expect(model.periodicSummary).toContain("월간 손익 +12,500원");
    expect(model.sourceCodes).toEqual(["DART", "KRX"]);
    expect(model.recentItems).toHaveLength(3);
  });

  test("builds empty report news strip defaults", () => {
    const model = buildReportNewsStripModel(null);

    expect(model.statusLabel).toBe("IDLE");
    expect(model.pollLabel).toBe("대기");
    expect(model.message).toBe("아직 수집 이력이 없습니다.");
    expect(model.recentCountLabel).toBe("0건");
    expect(model.sourceSummary).toBe("실구현 0 / 전체 0");
    expect(model.recentItems).toEqual([]);
  });

  test("prefers translated display fields for foreign news items", () => {
    const fields = pickNewsDisplayFields({
      title: "Samsung and LG Rally as Chip Cycle Improves",
      summary: "Semiconductor demand outlook improved.",
      display_title: "반도체 사이클 개선에 삼성·LG 강세",
      display_summary: "반도체 수요 기대가 개선됐다는 내용",
      original_title: "Samsung and LG Rally as Chip Cycle Improves",
      original_summary: "Semiconductor demand outlook improved.",
    });

    expect(fields.title).toBe("반도체 사이클 개선에 삼성·LG 강세");
    expect(fields.summary).toBe("반도체 수요 기대가 개선됐다는 내용");
    expect(fields.originalTitle).toBe("Samsung and LG Rally as Chip Cycle Improves");
    expect(fields.originalSummary).toBe("Semiconductor demand outlook improved.");
    expect(fields.hasTranslation).toBe(true);
  });

  test("formats manual fetch results into operator-friendly summaries", () => {
    expect(describeManualNewsFetchResult("DART", {
      received: 0,
      created: 0,
      duplicates: 0,
      skipped: 0,
    })).toBe("DART 조회 완료 · 현재 조회 구간에 새 데이터가 없습니다.");

    expect(describeManualNewsFetchResult("Bloomberg", {
      received: 5,
      created: 2,
      duplicates: 3,
      skipped: 0,
    })).toBe("Bloomberg 수집 완료 · 신규 2건 / 중복 3건");

    expect(describeManualNewsFetchResult("KIND", {
      received: 6,
      created: 0,
      duplicates: 6,
      skipped: 0,
    })).toBe("KIND 수집 완료 · 모두 기존 기사라 중복 처리됐습니다. (6건)");
  });

  test("builds manual fetch panel state with counts", () => {
    const state = buildManualNewsFetchState("Seeking Alpha", {
      received: 4,
      created: 1,
      duplicates: 3,
      skipped: 0,
    }, "04/06 17:20");

    expect(state.tone).toBe("success");
    expect(state.title).toContain("신규 적재 1건");
    expect(state.summary).toContain("신규 1건 / 중복 3건");
    expect(state.fetchedAtLabel).toBe("04/06 17:20");
    expect(state.stats).toEqual([
      { label: "조회", value: 4 },
      { label: "신규", value: 1 },
      { label: "중복", value: 3 },
      { label: "스킵", value: 0 },
    ]);
  });
});
