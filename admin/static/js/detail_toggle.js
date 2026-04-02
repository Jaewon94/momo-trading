function getDetailToggleLabels(isLLMCall = false) {
  return isLLMCall
    ? { closed: "💬 LLM 대화 보기", open: "💬 LLM 대화 닫기" }
    : { closed: "▸ 상세 보기", open: "▾ 상세 닫기" };
}

export function buildDetailToggleMarkup({ detailId, isLLMCall = false, muted = false } = {}) {
  const labels = getDetailToggleLabels(isLLMCall);
  const toneClass = muted
    ? "text-xs text-gray-500 hover:text-gray-300 mt-1"
    : "text-xs text-gray-600 hover:text-gray-400 mt-0.5";

  return `
    <button
      type="button"
      class="${toneClass}"
      data-detail-toggle="${detailId}"
      data-detail-kind="${isLLMCall ? "llm" : "detail"}"
      aria-controls="${detailId}"
      aria-expanded="false"
    >
      ${labels.closed}
    </button>
  `;
}

function syncDetailButton(button, detailEl) {
  const isLLMCall = button.dataset.detailKind === "llm";
  const labels = getDetailToggleLabels(isLLMCall);
  const isOpen = detailEl.classList.contains("open");
  button.textContent = isOpen ? labels.open : labels.closed;
  button.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

export function bindDetailToggleHandlers(root = document) {
  const flagTarget = root.documentElement || root;
  if (flagTarget.dataset?.detailToggleBound === "true") return;

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-detail-toggle]");
    if (!button) return;

    const detailId = button.dataset.detailToggle;
    if (!detailId) return;

    const detailEl = root.getElementById
      ? root.getElementById(detailId)
      : document.getElementById(detailId);
    if (!detailEl) return;

    detailEl.classList.toggle("open");
    syncDetailButton(button, detailEl);
  });

  root.querySelectorAll("[data-detail-toggle]").forEach((button) => {
    const detailId = button.dataset.detailToggle;
    const detailEl = root.getElementById
      ? root.getElementById(detailId)
      : document.getElementById(detailId);
    if (detailEl) {
      syncDetailButton(button, detailEl);
    }
  });

  if (flagTarget.dataset) {
    flagTarget.dataset.detailToggleBound = "true";
  }
}
