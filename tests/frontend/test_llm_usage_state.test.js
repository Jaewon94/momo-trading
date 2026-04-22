import { describe, expect, test } from "vitest";

import {
  buildClaudeUsageCopy,
  buildCodexUsageCopy,
  buildCodexAuthLabel,
} from "../../admin/static/js/llm_usage_state.js";

describe("llm_usage_state", () => {
  test("builds codex auth label from login state and auth mode", () => {
    expect(
      buildCodexAuthLabel({
        auth: {
          logged_in: true,
          auth_mode: "ChatGPT",
        },
      }),
    ).toBe("로그인됨 · ChatGPT");
  });

  test("builds codex support copy with explicit unsupported local quota message", () => {
    expect(
      buildCodexUsageCopy({
        official: {
          availability_reason:
            "OpenAI 공식 문서상 플랜별 사용량 정책은 안내되지만, local environment usage는 제공되지 않습니다.",
        },
      }),
    ).toEqual({
      supportedLabel: "공식 지원: 로그인 상태 확인, 플랜별 일반 사용량 정책 안내",
      unsupportedLabel: "공식 미지원: 로컬 잔여 사용량 퍼센트, 정확한 리셋 타이머",
      detail:
        "OpenAI 공식 문서상 플랜별 사용량 정책은 안내되지만, local environment usage는 제공되지 않습니다.",
    });
  });

  test("builds claude copy that distinguishes server runtime counters from local history", () => {
    expect(buildClaudeUsageCopy()).toEqual({
      supportedLabel: "공식 지원: 5시간/7일 사용률, 리셋 시각, 컨텍스트 잔량",
      appUsageLabel: "현재 서버 실행 누적 호출",
      appCostLabel: "현재 서버 실행 누적 비용",
      historyLabel: "로컬 히스토리 세션",
    });
  });
});
