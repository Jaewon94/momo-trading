import { describe, expect, test } from "vitest";

import {
  buildEventRadarState,
  buildEventRadarCard,
  buildTradeStageLabel,
} from "../../admin/static/js/event_radar_state.js";

describe("event_radar_state", () => {
  test("builds summary counters and filter counts", () => {
    const state = buildEventRadarState({
      summary: {
        total: 3,
        actionable: 2,
        cooldown: 1,
        buy_candidates: 1,
        sell_candidates: 1,
      },
      events: [
        {
          symbol: "215790",
          name: "이노인스트루먼트",
          event_label: "익절 도달",
          event_type: "TAKE_PROFIT_HIT",
          score: 92,
          state: "ACTIONABLE",
          direction: "SELL",
          occurred_at: "2026-04-03T15:10:00+09:00",
          cooldown_remaining_sec: 0,
        },
        {
          symbol: "065440",
          name: "현대그린푸드",
          event_label: "급등",
          event_type: "PRICE_SURGE",
          score: 78,
          state: "TRIGGERED",
          direction: "BUY",
          occurred_at: "2026-04-03T14:41:00+09:00",
          cooldown_remaining_sec: 12,
        },
        {
          symbol: "093370",
          name: "후성",
          event_label: "쿨다운",
          event_type: "VOLUME_SPIKE",
          score: 61,
          state: "COOLDOWN",
          direction: "WATCH",
          occurred_at: "2026-04-03T14:30:00+09:00",
          cooldown_remaining_sec: 35,
        },
      ],
    });

    expect(state.summaryPills[0]).toEqual({ label: "실시간 이벤트", value: "3" });
    expect(state.summaryPills[2]).toEqual({ label: "강한 매도 후보", value: "1" });
    expect(state.filters).toEqual([
      { key: "all", label: "전체", count: 3 },
      { key: "buy", label: "매수 후보", count: 1 },
      { key: "sell", label: "매도 후보", count: 1 },
      { key: "cooldown", label: "쿨다운", count: 1 },
    ]);
  });

  test("builds card tone, score badge and cooldown copy", () => {
    const card = buildEventRadarCard({
      symbol: "065440",
      name: "현대그린푸드",
      event_label: "급등",
      event_type: "PRICE_SURGE",
      score: 78,
      state: "COOLDOWN",
      direction: "BUY",
      occurred_at: "2026-04-03T14:41:00+09:00",
      cooldown_remaining_sec: 12,
      change_rate: 5.12,
      volume_ratio: 2.8,
    });

    expect(card.tone).toBe("buy");
    expect(card.scoreLabel).toBe("78점");
    expect(card.stateLabel).toBe("쿨다운");
    expect(card.cooldownLabel).toBe("12초 남음");
    expect(card.metaLine).toContain("+5.12%");
    expect(card.metaLine).toContain("2.8배");
  });

  test("derives unified trade-stage labels from account snapshot", () => {
    expect(buildTradeStageLabel({
      pendingOrders: [{ symbol: "005930", side: "매수" }],
    }, "005930")).toBe("매수 접수중");

    expect(buildTradeStageLabel({
      pendingOrders: [{ symbol: "005930", side: "매도" }],
    }, "005930")).toBe("매도 접수중");

    expect(buildTradeStageLabel({
      trades: {
        pending_confirms: [{ stock_symbol: "005930", side: "BUY", status: "PENDING_CONFIRM" }],
      },
    }, "005930")).toBe("매수 대기중");

    expect(buildTradeStageLabel({
      trades: {
        open_positions: [{ stock_symbol: "005930" }],
      },
    }, "005930")).toBe("보유 중");

    expect(buildTradeStageLabel({
      trades: {
        completed: [{
          stock_symbol: "005930",
          side: "BUY",
          status: "CONFIRMED",
          notes: JSON.stringify({ fill_type: "PARTIAL_EXIT", remaining_open_quantity: 3 }),
        }],
      },
    }, "005930")).toBe("부분 매도");
  });
});
