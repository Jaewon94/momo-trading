import { describe, expect, test } from "vitest";

import {
  buildTaskCardDescriptor,
  resolveTaskCardRouting,
} from "../../admin/static/js/activity_card_state.js";

describe("activity_card_state", () => {
  test("treats scan activities as a stable task group keyed by cycle_id", () => {
    const activity = {
      activity_type: "SCAN",
      summary: "📡 시장 스캔 중... 거래량/등락 상위 종목 조회",
      cycle_id: "cycle-1",
    };

    const descriptor = buildTaskCardDescriptor(activity);
    const routing = resolveTaskCardRouting({
      activity,
      lastActivityGroupKey: "task:llm",
      latestTaskCardKeyByGroup: {
        "scan:cycle-1": "scan:cycle-1:1",
      },
      taskCards: {
        "scan:cycle-1:1": {},
      },
    });

    expect(descriptor).toMatchObject({
      key: "scan",
      title: "시장 스캔",
    });
    expect(routing.groupKey).toBe("task:scan:cycle-1");
    expect(routing.stable).toBe(true);
    expect(routing.needsNewCard).toBe(false);
  });

  test("starts a new scan card when a new cycle begins", () => {
    const activity = {
      activity_type: "SCAN",
      summary: "📡 시장 스캔 중... 거래량/등락 상위 종목 조회",
      cycle_id: "cycle-2",
    };

    const routing = resolveTaskCardRouting({
      activity,
      lastActivityGroupKey: "task:scan:cycle-1",
      latestTaskCardKeyByGroup: {
        "scan:cycle-1": "scan:cycle-1:1",
      },
      taskCards: {
        "scan:cycle-1:1": {},
      },
    });

    expect(routing.groupKey).toBe("task:scan:cycle-2");
    expect(routing.stable).toBe(true);
    expect(routing.needsNewCard).toBe(true);
  });

  test("keeps contiguous grouping for generic task types without a stable identity", () => {
    const activity = {
      activity_type: "EVENT",
      summary: "운영 이벤트 발생",
    };

    const routing = resolveTaskCardRouting({
      activity,
      lastActivityGroupKey: "task:qa",
      latestTaskCardKeyByGroup: {
        event: "event:1",
      },
      taskCards: {
        "event:1": {},
      },
    });

    expect(routing.groupKey).toBe("task:event");
    expect(routing.stable).toBe(false);
    expect(routing.needsNewCard).toBe(true);
  });
});
