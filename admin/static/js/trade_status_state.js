function safeParseJson(value) {
  if (!value || typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function parseTradeNotes(notes) {
  const parsed = safeParseJson(notes);
  return parsed && typeof parsed === "object" ? parsed : {};
}

function toUpper(value) {
  return String(value || "").trim().toUpperCase();
}

function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function resolveTradeExecutionState({
  side = "",
  status = "",
  notes = null,
  hasExit = false,
  source = "trade",
  isHolding = false,
} = {}) {
  const normalizedSide = toUpper(side);
  const normalizedStatus = toUpper(status);
  const normalizedSource = toUpper(source);
  const parsedNotes = typeof notes === "object" && notes !== null ? notes : parseTradeNotes(notes);
  const fillType = toUpper(parsedNotes?.fill_type);
  const remainingOpenQuantity = toNumber(parsedNotes?.remaining_open_quantity, 0);

  if (normalizedSide === "SELL") {
    if (normalizedStatus === "PENDING_CONFIRM") {
      return {
        code: normalizedSource === "ORDER" ? "SELL_SUBMITTED" : "SELL_PENDING",
        label: normalizedSource === "ORDER" ? "매도 접수중" : "매도 대기중",
        shortLabel: normalizedSource === "ORDER" ? "매도 접수중" : "매도 대기중",
        badge: normalizedStatus || "SELL",
        tone: "pending",
        remainingOpenQuantity,
      };
    }
    if (fillType === "PARTIAL_EXIT" || remainingOpenQuantity > 0) {
      return {
        code: "SELL_PARTIAL",
        label: "부분 매도",
        shortLabel: "부분 매도",
        badge: fillType || "PARTIAL_EXIT",
        tone: "sell",
        remainingOpenQuantity,
      };
    }
    return {
      code: "SELL_FILLED",
      label: "매도 완료",
      shortLabel: "매도 완료",
      badge: normalizedStatus || "SELL",
      tone: "sell",
      remainingOpenQuantity,
    };
  }

  if (normalizedStatus === "PENDING_CONFIRM") {
    return {
      code: normalizedSource === "ORDER" ? "BUY_SUBMITTED" : "BUY_PENDING",
      label: normalizedSource === "ORDER" ? "매수 접수중" : "매수 대기중",
      shortLabel: normalizedSource === "ORDER" ? "매수 접수중" : "매수 대기중",
      badge: normalizedStatus || "BUY",
      tone: "pending",
      remainingOpenQuantity,
    };
  }

  if (hasExit) {
    if (fillType === "PARTIAL_EXIT" || remainingOpenQuantity > 0) {
      return {
        code: "SELL_PARTIAL",
        label: "부분 매도",
        shortLabel: "부분 매도",
        badge: fillType || "PARTIAL_EXIT",
        tone: "sell",
        remainingOpenQuantity,
      };
    }
    return {
      code: "SELL_FILLED",
      label: "매도 완료",
      shortLabel: "매도 완료",
      badge: normalizedStatus || "SELL",
      tone: "sell",
      remainingOpenQuantity,
    };
  }

  if (isHolding) {
    return {
      code: "BUY_HOLDING",
      label: "보유 중",
      shortLabel: "보유 중",
      badge: normalizedStatus || "BUY",
      tone: "buy",
      remainingOpenQuantity,
    };
  }

  return {
    code: "BUY_FILLED",
    label: "매수 완료",
    shortLabel: "매수 완료",
    badge: normalizedStatus || "BUY",
    tone: "buy",
    remainingOpenQuantity,
  };
}
