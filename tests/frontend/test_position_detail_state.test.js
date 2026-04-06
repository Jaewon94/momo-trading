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
        decision_insight: {
          recommendation: "BUY",
          confidence: 0.82,
          reason: "추세 유지",
          target_price: 76000,
          stop_loss_price: 69000,
          horizon: "MID",
          chart: {
            market_regime: "BULL",
            rsi: 54.2,
            macd_hist: 1.24,
            pattern: "상승 추세 지속",
            direction: "BULLISH",
            signal_confidence: 0.74,
          },
          cost: {
            edge_bps: 182.4,
            cost_bps: 61,
            ratio: 2.99,
            min_ratio: 1.3,
          },
          news: {
            negative_pressure: 0.22,
            negative_count: 2,
            source_count: 2,
            threshold: 0.75,
            contributors: [
              { headline: "한글 번역 제목", pressure: 0.11 },
              { headline: "공급 차질 우려", pressure: 0.07 },
            ],
          },
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
    expect(state.decisionInsight.hero).toBe("BUY · MID");
    expect(state.decisionInsight.cards[1].hero).toBe("2.99x");
    expect(state.decisionInsight.cards[2].body[0]).toContain("한글 번역 제목");
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
        {
          type: "news",
          at: "2026-04-03T07:55:00+09:00",
          title: "삼성전자 시설투자 공시",
          summary: "대규모 설비투자 계획 공시",
          detail: {
            source_code: "DART",
            source_tier: "A",
            impact_score: 0.88,
            trust_score: 1.0,
            sentiment_label: "POSITIVE",
            sentiment_score: 0.76,
          },
        },
      ],
    });

    expect(state.timelineFilters).toEqual([
      { key: "all", label: "전체", count: 3 },
      { key: "trade", label: "거래", count: 1 },
      { key: "ai", label: "AI", count: 0 },
      { key: "news", label: "뉴스", count: 1 },
      { key: "error", label: "오류", count: 1 },
    ]);
    expect(state.timelinePage.hasMore).toBe(false);
  });

  test("formats news timeline entries with source and impact labels", () => {
    const entry = buildPositionTimelineEntry({
      type: "news",
      at: "2026-04-03T07:55:00+09:00",
      title: "삼성전자 시설투자 공시",
      summary: "대규모 설비투자 계획 공시",
      detail: {
        source_code: "DART",
        source_tier: "A",
        impact_score: 0.88,
        trust_score: 1.0,
        sentiment_label: "POSITIVE",
        sentiment_score: 0.76,
      },
    });

    expect(entry.filterKey).toBe("news");
    expect(entry.kindLabel).toBe("뉴스");
    expect(entry.badge).toBe("DART");
    expect(entry.meta).toContain("DART");
    expect(entry.detailLines[0]).toContain("영향도");
  });

  test("renders closed buy lots with partial-exit label instead of buy-filled label", () => {
    const entry = buildPositionTimelineEntry({
      type: "trade",
      at: "2026-04-03T10:15:00+09:00",
      title: "부분 매도",
      side: "BUY",
      status: "CONFIRMED",
      summary: "삼성전자 · 1주",
      detail: {
        notes: JSON.stringify({
          fill_type: "PARTIAL_EXIT",
          remaining_open_quantity: 2,
        }),
        trade_state_kind_label: "부분 매도",
        trade_state_badge: "PARTIAL_EXIT",
        trade_state_tone: "sell",
        trade_state_icon: "부분",
      },
    });

    expect(entry.kindLabel).toBe("부분 매도");
    expect(entry.badge).toBe("PARTIAL_EXIT");
    expect(entry.tone).toBe("sell");
  });

  test("renders closed buy lots as final-close lots instead of buy-filled labels", () => {
    const entry = buildPositionTimelineEntry({
      type: "trade",
      at: "2026-04-03T10:25:00+09:00",
      title: "최종 청산 lot",
      side: "BUY",
      status: "CONFIRMED",
      summary: "삼성전자 · 1주",
      detail: {
        notes: null,
        trade_state_kind_label: "최종 청산 lot",
        trade_state_badge: "FINAL_EXIT",
        trade_state_tone: "sell",
        trade_state_icon: "청산",
      },
    });

    expect(entry.kindLabel).toBe("최종 청산 lot");
    expect(entry.badge).toBe("FINAL_EXIT");
    expect(entry.tone).toBe("sell");
  });

  test("builds recent event chips for the summary header", () => {
    const state = buildPositionDetailState({
      symbol: "215790",
      name: "이노인스트루먼트",
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
        recent_events: [
          {
            event_label: "익절 도달",
            direction: "SELL",
            score: 92,
            state: "ACTIONABLE",
          },
          {
            event_label: "거래량 급증",
            direction: "BUY",
            score: 74,
            state: "TRIGGERED",
          },
        ],
      },
      timeline: [],
    });

    expect(state.recentEventChips).toEqual([
      {
        label: "익절 도달",
        tone: "sell",
        meta: "92점 · ACTIONABLE",
      },
      {
        label: "거래량 급증",
        tone: "buy",
        meta: "74점 · TRIGGERED",
      },
    ]);
  });
});
