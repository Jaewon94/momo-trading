import { describe, expect, test } from "vitest";

import {
  buildRuntimeControlState,
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
});
