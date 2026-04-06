import { describe, expect, test } from "vitest";

import { buildRuntimeOperationsViewModel } from "../../admin/static/js/runtime_state.js";

describe("runtime_operations_state", () => {
  test("운영 상태 요약을 카드용 뷰모델로 변환한다", () => {
    const items = buildRuntimeOperationsViewModel({
      operations: {
        broker: {
          status: "ERROR",
          label: "브로커 확인 필요",
          message: "KIS MCP 연결이 끊겨 있습니다.",
        },
        news_polling: {
          status: "WARN",
          label: "뉴스 폴링 대기",
          message: "아직 자동 뉴스 수집 이력이 없습니다.",
          last_run_at: "2026-04-06T09:10:00+09:00",
        },
        orders: {
          status: "OK",
          label: "주문 오류 없음",
          message: "최근 주문 오류 로그가 없습니다.",
        },
      },
    });

    expect(items).toHaveLength(3);
    expect(items[0]).toMatchObject({
      key: "broker",
      tone: "red",
      label: "브로커 확인 필요",
    });
    expect(items[1].tone).toBe("yellow");
    expect(items[1].meta).toContain("2026-04-06T09:10:00+09:00");
    expect(items[2].tone).toBe("green");
  });
});
