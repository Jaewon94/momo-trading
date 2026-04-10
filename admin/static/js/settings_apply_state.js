function normalizeForComparison(value) {
  if (typeof value === "boolean") return value;
  if (value == null) return "";
  return String(value);
}

function isSameSettingValue(baseValue, nextValue) {
  if (typeof nextValue === "boolean") {
    return Boolean(baseValue) === nextValue;
  }
  return normalizeForComparison(baseValue) === normalizeForComparison(nextValue);
}

export function updateSettingsDraft(draft, change, baseSettings) {
  if (!change?.key) return { ...(draft || {}) };

  const nextDraft = { ...(draft || {}) };
  if (isSameSettingValue(baseSettings?.[change.key], change.value)) {
    delete nextDraft[change.key];
    return nextDraft;
  }

  nextDraft[change.key] = change.value;
  return nextDraft;
}

export function reconcileSettingsDraft(baseSettings, draft) {
  const reconciled = {};
  Object.entries(draft || {}).forEach(([key, value]) => {
    if (!isSameSettingValue(baseSettings?.[key], value)) {
      reconciled[key] = value;
    }
  });
  return reconciled;
}

export function buildMergedSettings(baseSettings, draft) {
  return {
    ...(baseSettings || {}),
    ...(draft || {}),
  };
}

export function buildSettingsApplyViewModel({ draft, applying }) {
  const dirtyCount = Object.keys(draft || {}).length;
  if (applying) {
    return {
      dirtyCount,
      hasChanges: dirtyCount > 0,
      saveDisabled: true,
      resetDisabled: true,
      closeDisabled: true,
      formDisabled: true,
      saveLabel: "저장 중...",
      summaryText: "설정 적용 중...",
      detailText: "새 작업은 막고 현재 작업이 끝나면 새 설정을 한 번에 적용합니다. 이 창을 닫지 마세요.",
      tone: "info",
    };
  }

  if (!dirtyCount) {
    return {
      dirtyCount: 0,
      hasChanges: false,
      saveDisabled: true,
      resetDisabled: true,
      closeDisabled: false,
      formDisabled: false,
      saveLabel: "저장",
      summaryText: "저장되지 않은 변경 없음",
      detailText: "값을 바꾼 뒤 저장을 누르면 새 작업을 멈추고 현재 작업이 끝난 뒤 한 번에 적용합니다.",
      tone: "idle",
    };
  }

  return {
    dirtyCount,
    hasChanges: true,
    saveDisabled: false,
    resetDisabled: false,
    closeDisabled: false,
    formDisabled: false,
    saveLabel: `변경 ${dirtyCount}건 저장`,
    summaryText: `저장되지 않은 변경 ${dirtyCount}건`,
    detailText: "저장을 누르면 새 작업을 멈추고 현재 작업이 끝난 뒤 새 설정 기준으로 재구성합니다.",
    tone: "dirty",
  };
}
