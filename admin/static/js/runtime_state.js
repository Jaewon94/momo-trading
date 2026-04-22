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

export function formatRiskAppetiteLabel(mode = "MODERATE") {
  return {
    CONSERVATIVE: "보수적",
    MODERATE: "중립",
    AGGRESSIVE: "공격적",
  }[mode] || "중립";
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

export function buildRuntimeOperationsViewModel(systemStatus = {}) {
  const operations = systemStatus?.operations || {};
  const items = [
    { key: "broker", title: "브로커", ...operations.broker },
    { key: "news_polling", title: "뉴스", ...operations.news_polling },
    { key: "ollama", title: "Ollama", ...operations.ollama },
    { key: "orders", title: "주문", ...operations.orders },
  ].filter((item) => item.label || item.message);

  return items.map((item) => {
    const status = String(item.status || "OK").toUpperCase();
    const tone = status === "ERROR" ? "red" : status === "WARN" ? "yellow" : "green";
    const dotClass = status === "ERROR"
      ? "bg-red-400"
      : status === "WARN"
        ? "bg-yellow-400"
        : "bg-green-400";
    const metaParts = [];
    if (item.symbol) metaParts.push(String(item.symbol));
    if (item.created_at) metaParts.push(String(item.created_at));
    if (item.last_run_at) metaParts.push(String(item.last_run_at));
    if (Array.isArray(item.supported_sessions) && item.supported_sessions.length > 0) {
      metaParts.push(`세션:${item.supported_sessions.join(', ')}`);
    }
    return {
      key: item.key,
      title: item.title || item.key,
      label: String(item.label || ""),
      message: String(item.message || ""),
      tone,
      dotClass,
      meta: metaParts.join(" · "),
    };
  });
}

export function buildMarketSessionViewModel(systemStatus = {}) {
  const isHoliday = Boolean(systemStatus.market_holiday);
  const sessionCode = String(systemStatus.market_session || "CLOSED");
  const sessionLabel = String(systemStatus.market_session_label || (isHoliday ? `휴장 (${systemStatus.market_holiday})` : "장외"));
  const regularOpen = Boolean(systemStatus.market_open);
  const domesticOpen = Boolean(systemStatus.domestic_market_open);
  const tone = regularOpen ? "green" : domesticOpen ? "blue" : isHoliday ? "yellow" : "gray";
  const dotClass = regularOpen
    ? "bg-green-400"
    : domesticOpen
      ? "bg-blue-400"
      : isHoliday
        ? "bg-yellow-400"
        : "bg-gray-500";
  const badgeLabel = regularOpen ? "장:정규장" : domesticOpen ? `장:${sessionLabel}` : isHoliday ? "장:휴장" : "장:장외";
  const detailLabel = isHoliday ? `휴장 (${systemStatus.market_holiday})` : sessionLabel;
  const extra = domesticOpen
    ? `다음: ${String(systemStatus.next_market_session || "")}`
    : `다음: ${String(systemStatus.next_market_session || systemStatus.next_market_open || "")}`;
  return {
    sessionCode,
    sessionLabel,
    badgeLabel,
    detailLabel,
    tone,
    dotClass,
    extra,
    note: String(systemStatus.market_session_note || ""),
    autoTrading: Boolean(systemStatus.market_session_auto_trading),
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
  const sellAutomationReady = Boolean(tradingEnabled && schedulerRunning);
  const sellAutomationLabel = sellAutomationReady
    ? "보유 종목 자동 매도 준비됨"
    : "자동 매도 비활성";
  const sellAutomationHelp = sellAutomationReady
    ? "손절/익절, 장중 보유 재평가, 장마감 청산 경로가 실제 주문으로 이어질 수 있습니다."
    : "실주문 OFF 또는 스케줄러 중지 상태라 자동 매도 경로가 실제 주문으로 이어지지 않습니다.";
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
    sellAutomationReady,
    sellAutomationLabel,
    sellAutomationHelp,
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
