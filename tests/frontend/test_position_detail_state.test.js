import { describe, expect, test } from "vitest";

import {
  buildPositionDetailState,
  buildPositionTimelineEntry,
  groupPositionTimeline,
} from "../../admin/static/js/position_detail_state.js";

describe("position_detail_state", () => {
  test("derives compact summary cards from payload", () => {
    const state = buildPositionDetailState({
      symbol: "005930",
      name: "삼성전자",
      summary: {
        holding: {
          quantity: 2,
          avg_buy_price: 71000,
          current_price: 73500,
          pnl: 5000,
          pnl_rate: 3.52,
          market_value: 147000,
        },
        latest_signal: {
          recommendation: "BUY",
          confidence: 0.82,
          target_price: 76000,
          stop_loss_price: 69000,
          reason: "추세 유지",
        },
        trade_stats: {
          total_trades: 1,
          open_buy_count: 1,
          completed_count: 0,
          realized_pnl: 0,
        },
        holding_status: "ok",
      },
      timeline: [],
    });

    expect(state.title).toBe("삼성전자 · 005930");
    expect(state.summaryCards).toHaveLength(3);
    expect(state.summaryCards[0].hero).toContain("2주");
    expect(state.summaryCards[1].hero).toBe("BUY");
    expect(state.summaryCards[2].metrics[2].value).toContain("0원");
    expect(state.emptyMessage).toBe("표시할 이벤트가 없습니다.");
  });

  test("shows holding delay copy when live holding lookup times out", () => {
    const state = buildPositionDetailState({
      symbol: "005930",
      name: "삼성전자",
      summary: {
        holding: null,
        holding_status: "timeout",
        holding_message: "실시간 보유 정보 조회가 지연되어 최근 거래 이력만 표시합니다.",
        latest_signal: null,
        trade_stats: {
          total_trades: 1,
          open_buy_count: 1,
          completed_count: 0,
          realized_pnl: 0,
        },
      },
      timeline: [],
    });

    expect(state.summaryCards[0].hero).toBe("지연");
    expect(state.summaryCards[0].heroMeta).toContain("지연");
  });

  test("keeps cached holding data visible with cache status", () => {
    const state = buildPositionDetailState({
      symbol: "005930",
      name: "삼성전자",
      summary: {
        holding: {
          quantity: 2,
          avg_buy_price: 71000,
          current_price: 73500,
          pnl: 5000,
          pnl_rate: 3.52,
          market_value: 147000,
        },
        holding_status: "cached",
        holding_message: "최근 캐시된 보유 정보를 표시합니다.",
        latest_signal: null,
        trade_stats: {
          total_trades: 1,
          open_buy_count: 1,
          completed_count: 0,
          realized_pnl: 0,
        },
      },
      timeline: [],
    });

    expect(state.summaryCards[0].hero).toContain("2주");
    expect(state.summaryCards[0].caption).toContain("캐시");
  });

  test("formats activity timeline entries with phase labels", () => {
    const entry = buildPositionTimelineEntry({
      type: "activity",
      at: "2026-04-03T09:04:00",
      title: "Tier1 분석 완료",
      phase: "COMPLETE",
      summary: "삼성전자 분석 완료",
      confidence: 0.82,
    });

    expect(entry.badge).toBe("COMPLETE");
    expect(entry.meta).toContain("82%");
    expect(entry.filterKey).toBe("ai");
    expect(entry.timeLabel).toBeTruthy();
  });

  test("groups timeline entries by day and filters by category", () => {
    const entries = [
      buildPositionTimelineEntry({
        type: "trade",
        at: "2026-04-03T09:04:00+09:00",
        title: "매수 체결",
        side: "BUY",
        status: "CONFIRMED",
        summary: "삼성전자 2주",
        detail: { entry_price: 71000 },
      }),
      buildPositionTimelineEntry({
        type: "activity",
        at: "2026-04-03T08:00:00+09:00",
        title: "분석 완료",
        phase: "COMPLETE",
        summary: "삼성전자 분석 완료",
      }),
      buildPositionTimelineEntry({
        type: "activity",
        at: "2026-04-02T18:14:00+09:00",
        title: "분석 실패",
        phase: "ERROR",
        summary: "응답 파싱 실패",
      }),
    ];

    const allGroups = groupPositionTimeline(entries);
    const aiGroups = groupPositionTimeline(entries, "ai");

    expect(allGroups).toHaveLength(2);
    expect(allGroups[0].entries).toHaveLength(2);
    expect(aiGroups).toHaveLength(1);
    expect(aiGroups[0].entries[0].filterKey).toBe("ai");
  });

  test("builds filter counts from timeline entries", () => {
    const state = buildPositionDetailState({
      symbol: "005930",
      name: "삼성전자",
      summary: {
        holding: null,
        holding_status: "missing",
        holding_message: "실시간 보유 목록에는 현재 보이지 않습니다.",
        latest_signal: null,
        trade_stats: {
          total_trades: 2,
          open_buy_count: 1,
          completed_count: 1,
          realized_pnl: 12000,
        },
      },
      timeline: [
        {
          type: "trade",
          at: "2026-04-03T09:04:00+09:00",
          title: "매수 체결",
          side: "BUY",
          status: "CONFIRMED",
          summary: "삼성전자 2주",
        },
        {
          type: "activity",
          at: "2026-04-03T08:00:00+09:00",
          title: "분석 실패",
          phase: "ERROR",
          summary: "응답 파싱 실패",
        },
      ],
    });

    expect(state.timelineFilters).toEqual([
      { key: "all", label: "전체", count: 2 },
      { key: "trade", label: "거래", count: 1 },
      { key: "ai", label: "AI", count: 0 },
      { key: "error", label: "오류", count: 1 },
    ]);
    expect(state.timelinePage.hasMore).toBe(false);
  });
});
