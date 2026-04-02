import { beforeEach, describe, expect, test } from "vitest";

import {
  bindDetailToggleHandlers,
  buildDetailToggleMarkup,
} from "../../admin/static/js/detail_toggle.js";

describe("detail_toggle", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  test("renders a detail button with data attributes instead of inline handlers", () => {
    expect(buildDetailToggleMarkup({ detailId: "detail-1" })).toContain('data-detail-toggle="detail-1"');
    expect(buildDetailToggleMarkup({ detailId: "detail-1" })).toContain("상세 보기");
  });

  test("toggles target panel open state and button label", () => {
    document.body.innerHTML = `
      ${buildDetailToggleMarkup({ detailId: "detail-1" })}
      <div id="detail-1" class="detail-content">hello</div>
    `;

    bindDetailToggleHandlers(document);

    const button = document.querySelector("[data-detail-toggle='detail-1']");
    const detail = document.getElementById("detail-1");

    expect(button.textContent).toContain("상세 보기");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(detail.classList.contains("open")).toBe(false);

    button.click();

    expect(detail.classList.contains("open")).toBe(true);
    expect(button.textContent).toContain("상세 닫기");
    expect(button.getAttribute("aria-expanded")).toBe("true");

    button.click();

    expect(detail.classList.contains("open")).toBe(false);
    expect(button.textContent).toContain("상세 보기");
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  test("uses LLM-specific copy for LLM conversation details", () => {
    document.body.innerHTML = `
      ${buildDetailToggleMarkup({ detailId: "detail-llm", isLLMCall: true })}
      <div id="detail-llm" class="detail-content">hello</div>
    `;

    bindDetailToggleHandlers(document);

    const button = document.querySelector("[data-detail-toggle='detail-llm']");
    expect(button.textContent).toContain("LLM 대화 보기");

    button.click();
    expect(button.textContent).toContain("LLM 대화 닫기");
  });
});
