function withMirroredButtons(baseStates) {
  return Object.entries(baseStates).reduce((acc, [id, value]) => {
    acc[id] = value;
    if (id.startsWith("runtime-")) {
      acc[id.replace("runtime-", "header-")] = value;
    }
    return acc;
  }, {});
}

export function formatAutonomyModeLabel(mode = "SEMI_AUTO") {
  return mode === "AUTONOMOUS" ? "자동 주문" : "추천 후 승인";
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

export function buildRuntimeSettingCopy({
  runtimeSettings = null,
  runtimeSystemStatus = null,
} = {}) {
  const { tradingEnabled, autonomyMode } = buildRuntimeControlState({
    runtimeSettings,
    runtimeSystemStatus,
  });

  return {
    tradingLabel: "실주문 실행",
    tradingTitle: "끄면 분석과 추천은 계속되지만 실제 매수·매도 주문은 보내지 않습니다.",
    tradingHelp: tradingEnabled
      ? "ON: 조건이 맞으면 실제 매수·매도 주문을 전송합니다."
      : "OFF: 분석과 추천은 계속되지만 실제 주문은 보내지 않습니다.",
    modeLabel: "주문 처리 방식",
    modeTitle: "AI가 낸 BUY/SELL 시그널을 추천으로 둘지, 즉시 주문할지 정합니다.",
    modeHelp: autonomyMode === "AUTONOMOUS"
      ? "AUTONOMOUS: AI가 만든 BUY/SELL 시그널을 즉시 주문합니다."
      : "SEMI_AUTO: AI 시그널을 추천으로만 남기고 사용자 승인을 기다립니다. 단, 손절/익절 같은 안전매도는 실주문 실행이 ON이면 자동 실행될 수 있습니다.",
  };
}
