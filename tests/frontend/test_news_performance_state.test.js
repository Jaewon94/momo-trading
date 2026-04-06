import { describe, expect, test } from "vitest";

import {
  buildNewsPerformanceCards,
  buildNewsRolloutPolicy,
} from "../../admin/static/js/news_performance_state.js";

describe("news_performance_state", () => {
  test("builds performance cards with rollout and cost-adjusted pnl", () => {
    const cards = buildNewsPerformanceCards({
      performance: {
        overall: {
          expectancy: 1280.0,
          profit_factor: 1.42,
          max_drawdown: -320000.0,
          net_pnl_after_cost: 189000.0,
        },
        shadow: {
          candidate_count: 18,
          blocked_by_news_count: 5,
          block_rate: 0.2778,
        },
      },
    });

    expect(cards).toHaveLength(6);
    expect(cards[0]).toMatchObject({ label: "기대값", value: "+1,280원" });
    expect(cards[1]).toMatchObject({ label: "PF", value: "1.42" });
    expect(cards[2]).toMatchObject({ label: "MDD", value: "-320,000원" });
    expect(cards[3]).toMatchObject({ label: "비용 차감 손익", value: "+189,000원" });
    expect(cards[4]).toMatchObject({ label: "Shadow 후보", value: "18건" });
    expect(cards[5].help).toContain("27.8%");
  });

  test("builds rollout policy summary from settings and status", () => {
    const policy = buildNewsRolloutPolicy({
      settings: {
        shadow_enabled: true,
        rollout_min_sample_size: 12,
        rollout_min_profit_factor: 1.15,
        rollout_min_expectancy: 0.0,
        rollout_max_drawdown_krw: 500000,
      },
      performance: {
        rollout: {
          status: "PROMOTE",
          reason: "비중 확대 권장",
          details: ["Shadow 후보 18건 · 실제 BUY 12건 · 기준 BUY 16건"],
          checks: [
            { key: "sample", label: "표본", passed: true, actual: "실거래 14건 / Shadow 18건", target: "각 12건 이상" },
          ],
        },
      },
    });

    expect(policy.status).toBe("PROMOTE");
    expect(policy.lines[0]).toContain("Shadow ON");
    expect(policy.lines[1]).toContain("표본 12건");
    expect(policy.lines[1]).toContain("PF 1.15");
    expect(policy.lines[2]).toContain("MDD -500,000원");
    expect(policy.details[0]).toContain("Shadow 후보 18건");
    expect(policy.checks[0]).toMatchObject({ key: "sample", passed: true });
  });
});
