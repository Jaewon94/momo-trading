function withMirroredButtons(baseStates) {
  return Object.entries(baseStates).reduce((acc, [id, value]) => {
    acc[id] = value;
    if (id.startsWith("runtime-")) {
      acc[id.replace("runtime-", "header-")] = value;
    }
    return acc;
  }, {});
}

export function getMcpBadgeState(systemStatus = {}) {
  const brokerProvider = systemStatus.broker_provider || "KIWOOM";
  const mcpRequired = systemStatus.mcp_required !== false;

  if (!mcpRequired) {
    return {
      label: "MCP:불필요",
      tone: "gray",
      dotClass: "bg-gray-500",
      detailLabel: `사용 안 함 (${brokerProvider})`,
    };
  }

  if (systemStatus.mcp_connected) {
    return {
      label: "MCP:정상",
      tone: "green",
      dotClass: "bg-green-400",
      detailLabel: "연결",
    };
  }

  return {
    label: "MCP:끊김",
    tone: "red",
    dotClass: "bg-red-400",
    detailLabel: "끊김",
  };
}

export function buildRuntimeControlState({
  runtimeSettings = null,
  runtimeSystemStatus = null,
  runtimeControlPending = false,
} = {}) {
  const tradingEnabled = runtimeSystemStatus?.trading_enabled ?? runtimeSettings?.TRADING_ENABLED ?? false;
  const autonomyMode = runtimeSettings?.AUTONOMY_MODE || "SEMI_AUTO";
  const schedulerRunning = runtimeSystemStatus?.scheduler_running ?? false;
  const schedulerEnabled = runtimeSettings?.SCHEDULER_ENABLED ?? schedulerRunning;
  const agentRunning = runtimeSystemStatus?.agent_running ?? false;
  const schedulerMismatchMessage = schedulerEnabled !== schedulerRunning
    ? `설정은 ${schedulerEnabled ? "활성" : "비활성"}이지만 현재 실행은 ${schedulerRunning ? "동작" : "중지"} 상태입니다.`
    : "";

  const buttonStates = withMirroredButtons({
    "runtime-trading-on": {
      active: tradingEnabled,
      disabled: runtimeControlPending || tradingEnabled,
      tone: "green",
    },
    "runtime-trading-off": {
      active: !tradingEnabled,
      disabled: runtimeControlPending || !tradingEnabled,
      tone: "red",
    },
    "runtime-mode-semi": {
      active: autonomyMode === "SEMI_AUTO",
      disabled: runtimeControlPending || autonomyMode === "SEMI_AUTO",
      tone: "blue",
    },
    "runtime-mode-auto": {
      active: autonomyMode === "AUTONOMOUS",
      disabled: runtimeControlPending || autonomyMode === "AUTONOMOUS",
      tone: "purple",
    },
    "runtime-scheduler-start": {
      active: schedulerRunning,
      disabled: runtimeControlPending || schedulerRunning,
      tone: "green",
    },
    "runtime-scheduler-stop": {
      active: !schedulerRunning,
      disabled: runtimeControlPending || !schedulerRunning,
      tone: "yellow",
    },
  });

  return {
    tradingEnabled,
    autonomyMode,
    schedulerRunning,
    schedulerEnabled,
    agentRunning,
    runtimeControlPending,
    schedulerMismatchMessage,
    buttonStates,
    headerTriggerDisabled: runtimeControlPending,
  };
}
