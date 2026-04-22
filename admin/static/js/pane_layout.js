export const PANE_STORAGE_KEY = "momo-admin-pane-layout-v1";
export const PANE_DEFAULT_WIDTH = { left: 320, right: 360 };
export const PANE_MIN_WIDTH = { left: 280, right: 300 };
export const PANE_MAX_WIDTH = { left: 520, right: 560 };
export const CENTER_MIN_WIDTH_DESKTOP = 620;
export const CENTER_MIN_WIDTH_COMPACT = 460;

function toValidWidth(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

export function normalizeSavedPaneLayout(savedLayout) {
  return {
    leftWidth: toValidWidth(savedLayout?.leftWidth, PANE_DEFAULT_WIDTH.left),
    rightWidth: toValidWidth(savedLayout?.rightWidth, PANE_DEFAULT_WIDTH.right),
    leftCollapsed: savedLayout?.leftCollapsed === true,
    rightCollapsed: savedLayout?.rightCollapsed === true,
  };
}

export function clampPaneWidth(
  side,
  width,
  {
    layout = null,
    workspaceWidth = 0,
    isCompactViewport = false,
    centerMinWidth = CENTER_MIN_WIDTH_DESKTOP,
  } = {},
) {
  const requestedWidth = toValidWidth(width, PANE_DEFAULT_WIDTH[side]);
  const normalizedLayout = normalizeSavedPaneLayout(layout);

  if (!workspaceWidth || isCompactViewport) {
    return Math.max(PANE_MIN_WIDTH[side], Math.min(PANE_MAX_WIDTH[side], requestedWidth));
  }

  const otherSide = side === "left" ? "right" : "left";
  const otherVisibleWidth = normalizedLayout[`${otherSide}Collapsed`]
    ? 0
    : normalizedLayout[`${otherSide}Width`];
  const dividerWidth = isCompactViewport ? 0 : 28;
  const maxByCenter = workspaceWidth - centerMinWidth - otherVisibleWidth - dividerWidth;
  const hardMax = Math.min(
    PANE_MAX_WIDTH[side],
    Math.max(PANE_MIN_WIDTH[side], maxByCenter),
  );

  return Math.max(PANE_MIN_WIDTH[side], Math.min(hardMax, requestedWidth));
}
