import { describe, expect, test } from "vitest";

import {
  buildStrategyInsightsViewModel,
  summarizeStrategyEffects,
} from "../../admin/static/js/strategy_insights_state.js";

describe("strategy_insights_state", () => {
  test("builds selected risk appetite view model", () => {
    const model = buildStrategyInsightsViewModel({
      AUTONOMY_MODE: "AUTONOMOUS",
      DAY_TRADING_ONLY: true,
      strategy_insights: {
        selected_risk_appetite: "MODERATE",
        risk_appetites: {
          CONSERVATIVE: {
            label: "보수적",
            headline: "신중형",
            description: "작게 진입합니다.",
            system_effects: ["현금 비율 가이드 40% 이상"],
          },
          MODERATE: {
            label: "중립",
            headline: "균형형 운용",
            description: "과도하게 위축하지 않으면서 기회를 추적합니다.",
            system_effects: [
              "AI 자율 한도 결정에 반영",
              "현금 비율 가이드 25% 이상",
            ],
          },
        },
      },
    });

    expect(model.selected.key).toBe("MODERATE");
    expect(model.selected.label).toBe("중립");
    expect(model.selected.headline).toBe("균형형 운용");
    expect(model.options).toHaveLength(2);
    expect(model.options.find((item) => item.key === "MODERATE")?.isSelected).toBe(true);
    expect(model.context.find((item) => item.key === "autonomy_mode")?.value).toBe("즉시 자동 주문");
    expect(model.context.find((item) => item.key === "holding_policy")?.value).toBe("당일 청산");
  });

  test("summarizes first three system effects", () => {
    expect(summarizeStrategyEffects([
      "AI 자율 한도 결정에 반영",
      "현금 비율 가이드 25% 이상",
      "일일 거래 횟수 10~20회 기준",
      "추가 설명",
    ])).toBe("AI 자율 한도 결정에 반영 · 현금 비율 가이드 25% 이상 · 일일 거래 횟수 10~20회 기준");
  });
});
