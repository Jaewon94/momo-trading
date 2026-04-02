import { describe, expect, test } from "vitest";

import {
  buildRuntimeControlState,
  buildRuntimeSettingCopy,
  formatAutonomyModeLabel,
  formatRiskAppetiteLabel,
  getMcpBadgeState,
} from "../../admin/static/js/runtime_state.js";

describe("runtime_state", () => {
  test("marks MCP as unnecessary for non-MCP brokers", () => {
    expect(
      getMcpBadgeState({
        broker_provider: "KIWOOM",
        mcp_required: false,
        mcp_connected: false,
      }).label,
    ).toBe("MCP:불필요");
  });

  test("marks MCP as disconnected when KIS requires it but connection is down", () => {
    expect(
      getMcpBadgeState({
        broker_provider: "KIS",
        mcp_required: true,
        mcp_connected: false,
      }).label,
    ).toBe("MCP:끊김");
  });

  test("builds scheduler mismatch message from settings and runtime state", () => {
    const state = buildRuntimeControlState({
      runtimeSettings: {
        TRADING_ENABLED: true,
        AUTONOMY_MODE: "SEMI_AUTO",
        SCHEDULER_ENABLED: false,
      },
      runtimeSystemStatus: {
        trading_enabled: true,
        scheduler_running: true,
        agent_running: false,
      },
      runtimeControlPending: false,
    });

    expect(state.schedulerMismatchMessage).toContain("설정은 비활성");
    expect(state.schedulerMismatchMessage).toContain("현재 실행은 동작");
    expect(state.buttonStates["runtime-scheduler-start"]).toEqual({
      active: true,
      disabled: true,
      tone: "green",
    });
  });

  test("describes trading toggle as real order execution control", () => {
    const copy = buildRuntimeSettingCopy({
      runtimeSettings: {
        TRADING_ENABLED: false,
        AUTONOMY_MODE: "SEMI_AUTO",
      },
      runtimeSystemStatus: {
        trading_enabled: false,
      },
    });

    expect(copy.tradingLabel).toBe("실주문 실행");
    expect(copy.tradingHelp).toContain("실제 주문은 보내지 않습니다");
    expect(copy.modeHelp).toContain("추천으로만 남기고");
    expect(copy.modeHelp).toContain("손절/익절");
  });

  test("formats autonomy mode labels for human-readable display", () => {
    expect(formatAutonomyModeLabel("SEMI_AUTO")).toBe("추천 후 승인");
    expect(formatAutonomyModeLabel("AUTONOMOUS")).toBe("자동 주문");
  });

  test("formats risk appetite labels for compact sidebar summaries", () => {
    expect(formatRiskAppetiteLabel("CONSERVATIVE")).toBe("보수적");
    expect(formatRiskAppetiteLabel("MODERATE")).toBe("중립");
    expect(formatRiskAppetiteLabel("AGGRESSIVE")).toBe("공격적");
  });
});
