import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";

import {
  createQaPendingCard,
  renderQaAnswer,
  renderQaError,
} from "../../admin/static/js/qa_state.js";

describe("qa_state", () => {
  test("creates a pending Q&A card inside the chat container", () => {
    const dom = new JSDOM('<div id="chat-container"></div>');
    global.document = dom.window.document;

    const container = document.getElementById("chat-container");
    const card = createQaPendingCard(container, { question: "왜 주문이 없지?" });

    expect(container.querySelectorAll(".qa-card")).toHaveLength(1);
    expect(card.statusEl.textContent).toBe("답변 생성 중");
    expect(card.answerEl.textContent).toBe("답변 생성 중...");
    expect(container.textContent).toContain("왜 주문이 없지?");
  });

  test("updates the same card with the answer result", () => {
    const dom = new JSDOM('<div id="chat-container"></div>');
    global.document = dom.window.document;

    const container = document.getElementById("chat-container");
    const card = createQaPendingCard(container, { question: "상태 알려줘" });

    renderQaAnswer(card, {
      answer: "현재는 대기 중입니다.",
      context_summary: "오늘 전체",
      llm_provider: "CODEX",
      execution_time_ms: 1234,
    });

    expect(container.querySelectorAll(".qa-card")).toHaveLength(1);
    expect(card.statusEl.textContent).toBe("답변 완료");
    expect(card.metaEl.textContent).toBe("오늘 전체 | CODEX | 1.2s");
    expect(card.answerEl.textContent).toBe("현재는 대기 중입니다.");
  });

  test("renders failures in the same Q&A card", () => {
    const dom = new JSDOM('<div id="chat-container"></div>');
    global.document = dom.window.document;

    const container = document.getElementById("chat-container");
    const card = createQaPendingCard(container, { question: "뉴스는?" });

    renderQaError(card, "요청 실패");

    expect(card.statusEl.textContent).toBe("답변 실패");
    expect(card.answerEl.textContent).toBe("요청 실패");
  });
});
