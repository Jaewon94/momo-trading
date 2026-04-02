import { describe, expect, test } from "vitest";

import {
  PANE_DEFAULT_WIDTH,
  PANE_MIN_WIDTH,
  clampPaneWidth,
  normalizeSavedPaneLayout,
} from "../../admin/static/js/pane_layout.js";

describe("pane_layout", () => {
  test("clamps pane width within configured min and max bounds", () => {
    const leftMax = clampPaneWidth("left", 900, {
      layout: {
        leftWidth: 320,
        rightWidth: 360,
        leftCollapsed: false,
        rightCollapsed: false,
      },
      workspaceWidth: 1600,
      isCompactViewport: false,
      centerMinWidth: 620,
    });
    const leftMin = clampPaneWidth("left", 100, {
      layout: {
        leftWidth: 320,
        rightWidth: 360,
        leftCollapsed: false,
        rightCollapsed: false,
      },
      workspaceWidth: 1600,
      isCompactViewport: false,
      centerMinWidth: 620,
    });

    expect(leftMax).toBe(520);
    expect(leftMin).toBe(PANE_MIN_WIDTH.left);
  });

  test("falls back to defaults when saved layout is invalid", () => {
    expect(normalizeSavedPaneLayout(null)).toEqual({
      leftWidth: PANE_DEFAULT_WIDTH.left,
      rightWidth: PANE_DEFAULT_WIDTH.right,
      leftCollapsed: false,
      rightCollapsed: false,
    });

    expect(
      normalizeSavedPaneLayout({
        leftWidth: "bad-width",
        rightWidth: -10,
        leftCollapsed: "yes",
        rightCollapsed: 0,
      }),
    ).toEqual({
      leftWidth: PANE_DEFAULT_WIDTH.left,
      rightWidth: PANE_DEFAULT_WIDTH.right,
      leftCollapsed: false,
      rightCollapsed: false,
    });
  });
});
