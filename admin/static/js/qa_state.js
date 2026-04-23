export function createQaPendingCard(container, { question }) {
  const card = document.createElement('div');
  card.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble qa-card';

  const header = document.createElement('div');
  header.className = 'flex items-center justify-between gap-3 mb-3';

  const title = document.createElement('div');
  title.className = 'text-sm font-semibold text-gray-100';
  title.textContent = 'Q&A';

  const status = document.createElement('span');
  status.className = 'qa-status text-xs px-2 py-0.5 rounded bg-blue-900/40 text-blue-200';
  status.textContent = '답변 생성 중';

  header.append(title, status);

  const questionEl = document.createElement('div');
  questionEl.className = 'mb-3 rounded-lg bg-dark-800/80 border border-gray-700 px-3 py-2 text-sm text-gray-200 whitespace-pre-wrap';
  questionEl.textContent = question;

  const meta = document.createElement('div');
  meta.className = 'qa-meta text-xs text-gray-500 mb-2';
  meta.textContent = '';

  const answer = document.createElement('div');
  answer.className = 'qa-answer text-sm text-gray-300 whitespace-pre-wrap';
  answer.textContent = '답변 생성 중...';

  card.append(header, questionEl, meta, answer);
  container.appendChild(card);

  return { element: card, statusEl: status, metaEl: meta, answerEl: answer };
}

export function renderQaAnswer(card, data) {
  card.statusEl.className = 'qa-status text-xs px-2 py-0.5 rounded bg-green-900/40 text-green-200';
  card.statusEl.textContent = '답변 완료';
  card.metaEl.textContent = `${data.context_summary || '컨텍스트'} | ${data.llm_provider || 'UNKNOWN'} | ${formatElapsed(data.execution_time_ms)}`;
  card.answerEl.textContent = data.answer || '';
}

export function renderQaError(card, message) {
  card.statusEl.className = 'qa-status text-xs px-2 py-0.5 rounded bg-red-900/40 text-red-200';
  card.statusEl.textContent = '답변 실패';
  card.metaEl.textContent = '';
  card.answerEl.textContent = message || '답변 생성 실패';
}

function formatElapsed(ms) {
  const value = Number(ms || 0);
  if (!Number.isFinite(value) || value <= 0) return '0.0s';
  return `${(value / 1000).toFixed(1)}s`;
}
