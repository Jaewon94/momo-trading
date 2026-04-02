/**
 * MOMO Trading Admin Dashboard — SSE + Stock-Grouped Chat UI
 */
import {
  CENTER_MIN_WIDTH_COMPACT,
  CENTER_MIN_WIDTH_DESKTOP,
  PANE_DEFAULT_WIDTH,
  PANE_MAX_WIDTH,
  PANE_MIN_WIDTH,
  PANE_STORAGE_KEY,
  clampPaneWidth as clampPaneWidthValue,
  normalizeSavedPaneLayout,
} from './pane_layout.js';
import {
  buildRuntimeControlState,
  buildRuntimeSettingCopy,
  formatAutonomyModeLabel,
  getMcpBadgeState,
} from './runtime_state.js';
import {
  buildClaudeUsageCopy,
  buildCodexAuthLabel,
  buildCodexUsageCopy,
} from './llm_usage_state.js';
import { buildTradePanelState, buildTradeSummaryCounts } from './trade_state.js';
import { resolveActivityStockMeta } from './activity_state.js';

const API = '/api/v1/admin';
let currentView = 'live';
let activityCount = 0;
let autoScroll = true;
let accountPollTimer = null;
let runtimeSettings = null;
let runtimeSystemStatus = null;
let llmUsageSnapshot = null;
let llmCatalog = null;
let runtimeControlPending = false;
const knownStockNames = {};
let paneLayout = {
  leftWidth: PANE_DEFAULT_WIDTH.left,
  rightWidth: PANE_DEFAULT_WIDTH.right,
  leftCollapsed: false,
  rightCollapsed: false,
};
let activePaneResize = null;

// Stock card tracking: key = "cycleId:symbol" → { element, headerEl, bodyEl, stepsEl, activities[], outcome }
let stockCards = {};

// Sidebar section state
const sidebarState = {
  account: true,
  holdings: true,
  pending: false,
  trades: true,
  settings: true,
  system: true,
};

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  loadPaneLayout();
  loadSettings();
  loadLLMCatalog();
  loadSystemStatus();
  loadLLMUsage();
  loadReportList();
  loadAccountInfo();
  loadLLMStatus();
  connectSSE();
  loadTodayActivities();
  initSidebarSections();
  initWorkspaceLayout();
  setInterval(loadSystemStatus, 15000);
  setInterval(loadLLMUsage, 60000);
  accountPollTimer = setInterval(loadAccountInfo, 30000);
});

// ── Sidebar Accordion ──
function initSidebarSections() {
  for (const [id, isOpen] of Object.entries(sidebarState)) {
    const body = document.getElementById(`body-${id}`);
    const arrow = document.getElementById(`arrow-${id}`);
    if (body) {
      body.classList.toggle('open', isOpen);
    }
    if (arrow) {
      arrow.classList.toggle('collapsed', !isOpen);
    }
  }
}

function toggleSidebarSection(id) {
  sidebarState[id] = !sidebarState[id];
  const body = document.getElementById(`body-${id}`);
  const arrow = document.getElementById(`arrow-${id}`);
  if (body) body.classList.toggle('open', sidebarState[id]);
  if (arrow) arrow.classList.toggle('collapsed', !sidebarState[id]);
}

// ── Workspace Layout ──
function loadPaneLayout() {
  try {
    const raw = localStorage.getItem(PANE_STORAGE_KEY);
    if (!raw) return;
    paneLayout = normalizeSavedPaneLayout(JSON.parse(raw));
  } catch (err) {
    console.warn('Pane layout load error:', err);
  }
}

function savePaneLayout() {
  try {
    localStorage.setItem(PANE_STORAGE_KEY, JSON.stringify(paneLayout));
  } catch (err) {
    console.warn('Pane layout save error:', err);
  }
}

function isCompactViewport() {
  return window.matchMedia('(max-width: 1023px)').matches;
}

function getWorkspaceCenterMinWidth() {
  return window.innerWidth < 1280 ? CENTER_MIN_WIDTH_COMPACT : CENTER_MIN_WIDTH_DESKTOP;
}

function clampPaneWidth(side, width) {
  const workspace = document.getElementById('workspace-shell');
  return clampPaneWidthValue(side, width, {
    layout: paneLayout,
    workspaceWidth: workspace?.clientWidth || window.innerWidth,
    isCompactViewport: isCompactViewport(),
    centerMinWidth: getWorkspaceCenterMinWidth(),
  });
}

function updatePaneDividerUI(side, collapsed) {
  const button = document.getElementById(side === 'left' ? 'toggle-left-pane' : 'toggle-right-pane');
  const resizer = document.getElementById(side === 'left' ? 'pane-resizer-left' : 'pane-resizer-right');
  if (button) {
    button.innerHTML = side === 'left'
      ? (collapsed ? '&#x203A;' : '&#x2039;')
      : (collapsed ? '&#x2039;' : '&#x203A;');
  }
  if (resizer) {
    const width = collapsed ? 0 : paneLayout[`${side}Width`];
    resizer.setAttribute('aria-valuemin', '0');
    resizer.setAttribute('aria-valuemax', String(PANE_MAX_WIDTH[side]));
    resizer.setAttribute('aria-valuenow', String(width));
    resizer.setAttribute('aria-expanded', String(!collapsed));
  }
}

function applyPaneLayout() {
  const leftPane = document.getElementById('admin-left-pane');
  const rightPane = document.getElementById('admin-right-pane');
  if (!leftPane || !rightPane) return;
  paneLayout = normalizeSavedPaneLayout(paneLayout);

  if (isCompactViewport()) {
    leftPane.classList.remove('pane-collapsed');
    rightPane.classList.remove('pane-collapsed');
    leftPane.style.width = 'auto';
    rightPane.style.width = 'auto';
    updatePaneDividerUI('left', false);
    updatePaneDividerUI('right', false);
    return;
  }

  paneLayout.leftWidth = clampPaneWidth('left', paneLayout.leftWidth || PANE_DEFAULT_WIDTH.left);
  paneLayout.rightWidth = clampPaneWidth('right', paneLayout.rightWidth || PANE_DEFAULT_WIDTH.right);

  leftPane.classList.toggle('pane-collapsed', paneLayout.leftCollapsed);
  rightPane.classList.toggle('pane-collapsed', paneLayout.rightCollapsed);
  leftPane.style.width = paneLayout.leftCollapsed ? '0px' : `${paneLayout.leftWidth}px`;
  rightPane.style.width = paneLayout.rightCollapsed ? '0px' : `${paneLayout.rightWidth}px`;
  updatePaneDividerUI('left', paneLayout.leftCollapsed);
  updatePaneDividerUI('right', paneLayout.rightCollapsed);
}

function togglePaneCollapse(side) {
  if (isCompactViewport()) return;
  paneLayout[`${side}Collapsed`] = !paneLayout[`${side}Collapsed`];
  if (!paneLayout[`${side}Width`]) {
    paneLayout[`${side}Width`] = PANE_DEFAULT_WIDTH[side];
  }
  applyPaneLayout();
  savePaneLayout();
}

function resetPaneWidth(side) {
  paneLayout[`${side}Collapsed`] = false;
  paneLayout[`${side}Width`] = PANE_DEFAULT_WIDTH[side];
  applyPaneLayout();
  savePaneLayout();
}

function startPaneResize(side, event) {
  if (isCompactViewport()) return;
  event.preventDefault();
  paneLayout[`${side}Collapsed`] = false;
  activePaneResize = {
    side,
    startX: event.clientX,
    startWidth: paneLayout[`${side}Width`] || PANE_DEFAULT_WIDTH[side],
  };
  const resizer = document.getElementById(side === 'left' ? 'pane-resizer-left' : 'pane-resizer-right');
  resizer?.classList.add('dragging');
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
}

function handlePaneResizeMove(event) {
  if (!activePaneResize) return;
  const { side, startX, startWidth } = activePaneResize;
  const delta = event.clientX - startX;
  const nextWidth = side === 'left' ? startWidth + delta : startWidth - delta;
  paneLayout[`${side}Width`] = clampPaneWidth(side, nextWidth);
  applyPaneLayout();
}

function stopPaneResize() {
  if (!activePaneResize) return;
  const resizer = document.getElementById(
    activePaneResize.side === 'left' ? 'pane-resizer-left' : 'pane-resizer-right'
  );
  resizer?.classList.remove('dragging');
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  activePaneResize = null;
  savePaneLayout();
}

function handlePaneResizerKeydown(side, event) {
  if (isCompactViewport()) return;
  const step = event.shiftKey ? 48 : 24;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    togglePaneCollapse(side);
    return;
  }
  if (event.key === 'Home') {
    event.preventDefault();
    paneLayout[`${side}Collapsed`] = false;
    paneLayout[`${side}Width`] = PANE_MIN_WIDTH[side];
    applyPaneLayout();
    savePaneLayout();
    return;
  }
  if (event.key === 'End') {
    event.preventDefault();
    paneLayout[`${side}Collapsed`] = false;
    paneLayout[`${side}Width`] = clampPaneWidth(side, PANE_MAX_WIDTH[side]);
    applyPaneLayout();
    savePaneLayout();
    return;
  }

  const keyDirection = event.key === 'ArrowLeft' ? -1 : event.key === 'ArrowRight' ? 1 : 0;
  if (!keyDirection) return;
  event.preventDefault();

  let nextWidth = paneLayout[`${side}Width`] || PANE_DEFAULT_WIDTH[side];
  if (side === 'left') {
    nextWidth += keyDirection * step;
  } else {
    nextWidth -= keyDirection * step;
  }
  paneLayout[`${side}Collapsed`] = false;
  paneLayout[`${side}Width`] = clampPaneWidth(side, nextWidth);
  applyPaneLayout();
  savePaneLayout();
}

function initWorkspaceLayout() {
  applyPaneLayout();

  const leftResizer = document.getElementById('pane-resizer-left');
  const rightResizer = document.getElementById('pane-resizer-right');
  if (leftResizer && !leftResizer.dataset.bound) {
    leftResizer.addEventListener('pointerdown', (event) => startPaneResize('left', event));
    leftResizer.addEventListener('keydown', (event) => handlePaneResizerKeydown('left', event));
    leftResizer.addEventListener('dblclick', () => resetPaneWidth('left'));
    leftResizer.dataset.bound = 'true';
  }
  if (rightResizer && !rightResizer.dataset.bound) {
    rightResizer.addEventListener('pointerdown', (event) => startPaneResize('right', event));
    rightResizer.addEventListener('keydown', (event) => handlePaneResizerKeydown('right', event));
    rightResizer.addEventListener('dblclick', () => resetPaneWidth('right'));
    rightResizer.dataset.bound = 'true';
  }

  if (!document.body.dataset.paneResizeBound) {
    window.addEventListener('pointermove', handlePaneResizeMove);
    window.addEventListener('pointerup', stopPaneResize);
    window.addEventListener('pointercancel', stopPaneResize);
    window.addEventListener('resize', applyPaneLayout);
    document.body.dataset.paneResizeBound = 'true';
  }
}

// ── SSE Connection ──
function connectSSE() {
  const es = new EventSource(`${API}/stream`);

  es.onopen = () => {
    setStatus('connected', 'SSE 연결됨');
    updateBadge('badge-sse', '연결', 'green');
  };

  es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'connected') return;
      if (msg.type === 'activity' && currentView === 'live') {
        appendActivity(msg.data);
        if (msg.data && msg.data.phase === 'COMPLETE' &&
            ['DECISION', 'ORDER', 'TRADE_RESULT'].includes(msg.data.activity_type)) {
          setTimeout(loadAccountInfo, 2000);
        }
      }
      if (msg.type === 'account_changed') {
        loadAccountInfo();
      }
    } catch (err) {
      console.error('SSE parse error', err);
    }
  };

  es.onerror = () => {
    setStatus('disconnected', 'SSE 재연결 중...');
    updateBadge('badge-sse', '끊김', 'red');
    setTimeout(() => {
      if (es.readyState === EventSource.CLOSED) connectSSE();
    }, 3000);
  };
}

// ── Account Info ──
async function loadAccountInfo() {
  try {
    const [balResp, holdResp, pendResp, tradeResp] = await Promise.all([
      fetch(`${API}/account/balance`),
      fetch(`${API}/account/holdings`),
      fetch(`${API}/account/pending-orders`),
      fetch(`${API}/trades`),
    ]);
    const balJson = await balResp.json();
    const holdJson = await holdResp.json();
    const pendJson = await pendResp.json();
    const tradeJson = await tradeResp.json();
    renderAccountBalance(balJson.data);
    renderAccountHoldings(holdJson.data);
    renderPendingOrders(pendJson.data);
    renderTodayTrades(tradeJson.data);
    renderPortfolioQuickStats(balJson.data, holdJson.data, pendJson.data, tradeJson.data);
  } catch (err) {
    console.error('Account info error:', err);
    const el = document.getElementById('account-info');
    if (el) el.innerHTML = '<div class="text-gray-600">조회 실패</div>';
  }
}

function renderAccountBalance(data) {
  const el = document.getElementById('account-info');
  if (!el || !data) {
    if (el) el.innerHTML = '<div class="text-gray-600">계좌 미연결</div>';
    return;
  }
  const pnlColor = data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400';
  const cashRatio = data.total_asset > 0
    ? ((data.cash / data.total_asset) * 100).toFixed(1)
    : '0.0';
  el.innerHTML = `
    <div class="flex justify-between">
      <span class="text-gray-400">총자산</span>
      <span class="text-white font-medium">${formatKRW(data.total_asset)}</span>
    </div>
    <div class="flex justify-between">
      <span class="text-gray-400">현금</span>
      <span>${formatKRW(data.cash)} <span class="text-gray-600">(${cashRatio}%)</span></span>
    </div>
    <div class="flex justify-between">
      <span class="text-gray-400">주식</span>
      <span>${formatKRW(data.stock_value)}</span>
    </div>
    <div class="flex justify-between">
      <span class="text-gray-400">손익</span>
      <span class="${pnlColor}">${data.total_pnl >= 0 ? '+' : ''}${formatKRW(data.total_pnl)} (${data.total_pnl_rate >= 0 ? '+' : ''}${data.total_pnl_rate.toFixed(2)}%)</span>
    </div>`;
}

function renderAccountHoldings(data) {
  const el = document.getElementById('holdings-info');
  const countEl = document.getElementById('holdings-count');
  if (!el) return;
  if (!data || !data.length) {
    if (countEl) countEl.textContent = '0';
    el.innerHTML = '<div class="text-gray-600 text-xs">보유종목 없음</div>';
    return;
  }
  if (countEl) countEl.textContent = `${data.length}`;
  el.innerHTML = data.map(h => {
    const pnlColor = h.pnl_rate >= 0 ? 'text-green-400' : 'text-red-400';
    const bgTint = h.pnl_rate >= 0 ? 'bg-green-900/5' : 'bg-red-900/5';
    const evalAmt = h.current_price * h.quantity;
    const barColor = h.pnl_rate >= 0 ? 'bg-green-500' : 'bg-red-500';
    const barWidth = Math.min(Math.abs(h.pnl_rate) * 10, 100);
    return `<div class="border border-gray-700 rounded p-1.5 space-y-0.5 ${bgTint}">
      <div class="flex justify-between items-center">
        <span class="text-gray-200 font-medium truncate" title="${h.symbol}">${h.name}</span>
        <span class="${pnlColor} font-bold text-sm">${h.pnl_rate >= 0 ? '+' : ''}${h.pnl_rate.toFixed(2)}%</span>
      </div>
      <div class="pnl-bar">
        <div class="pnl-bar-fill ${barColor}" style="width:${barWidth}%"></div>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>${h.quantity}주 | 평단 ${Number(h.avg_buy_price).toLocaleString()}원</span>
        <span>현재 ${Number(h.current_price).toLocaleString()}원</span>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>평가 ${formatKRW(evalAmt)}</span>
        <span class="${pnlColor} font-medium">${h.pnl >= 0 ? '+' : ''}${formatKRW(h.pnl)}</span>
      </div>
    </div>`;
  }).join('');
}

function renderPendingOrders(data) {
  const el = document.getElementById('pending-orders-info');
  const countEl = document.getElementById('pending-count');
  if (!el) return;
  if (!data || !data.length) {
    if (countEl) countEl.textContent = '0';
    el.innerHTML = '';
    return;
  }
  if (countEl) {
    countEl.textContent = `${data.length}`;
  }
  el.innerHTML = data.map(o => {
    const sideColor = o.side === '매수' ? 'text-red-400' : 'text-blue-400';
    const borderColor = o.side === '매수' ? 'border-yellow-700/60' : 'border-yellow-700/60';
    const orderAmt = o.order_price * o.remaining_qty;
    const timeStr = o.order_time ? o.order_time.slice(0,2) + ':' + o.order_time.slice(2,4) + ':' + o.order_time.slice(4,6) : '';
    return `<div class="border ${borderColor} bg-yellow-900/10 rounded p-1.5 space-y-0.5">
      <div class="flex justify-between items-center">
        <span class="text-gray-200 font-medium truncate" title="${o.symbol}">${o.name}</span>
        <span class="${sideColor} font-medium text-xs px-1.5 py-0.5 rounded ${o.side === '매수' ? 'bg-red-900/30' : 'bg-blue-900/30'}">${o.side}</span>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>미체결 ${o.remaining_qty}주 / ${o.order_qty}주</span>
        <span>${Number(o.order_price).toLocaleString()}원</span>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>${formatKRW(orderAmt)}</span>
        <span>${timeStr}</span>
      </div>
    </div>`;
  }).join('');
}

function renderPortfolioQuickStats(balance, holdings, pendingOrders, trades) {
  const el = document.getElementById('portfolio-quick-stats');
  if (!el) return;

  const totalAsset = balance?.total_asset || 0;
  const cash = balance?.cash || 0;
  const cashRatio = totalAsset > 0 ? `${((cash / totalAsset) * 100).toFixed(1)}%` : '-';
  const holdingCount = holdings?.length || 0;
  const pendingCount = pendingOrders?.length || 0;
  const tradeCount = buildTradeSummaryCounts(trades).todayTradeCount;

  el.innerHTML = `
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">총자산</div>
      <div class="portfolio-stat-value">${formatKRW(totalAsset)}</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">현금 비중</div>
      <div class="portfolio-stat-value">${cashRatio}</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">보유 종목</div>
      <div class="portfolio-stat-value">${holdingCount}개</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">미체결 / 오늘 거래</div>
      <div class="portfolio-stat-value">${pendingCount} / ${tradeCount}</div>
    </div>
  `;
}

function renderTodayTrades(data) {
  const el = document.getElementById('today-trades-info');
  const countEl = document.getElementById('trades-count');
  if (!el) return;

  const state = buildTradePanelState(data);
  const {
    opened,
    completed,
    pendingConfirms,
    openPositions,
    todayCount,
    hasContent,
  } = state;

  if (countEl) countEl.textContent = String(todayCount);

  if (!hasContent) {
    el.innerHTML = '<div class="text-gray-600 text-xs">오늘 매매 내역 없음</div>';
    return;
  }

  const sections = [];

  if (completed.length) {
    sections.push(`
      <div>
        <div class="trade-mini-group-title">오늘 청산</div>
        ${completed.map((trade) => renderCompactTradeCard(trade, 'completed')).join('')}
      </div>
    `);
  }

  if (pendingConfirms.length) {
    sections.push(`
      <div>
        <div class="trade-mini-group-title flex items-center justify-between gap-2">
          <span>확인 대기</span>
          <span class="text-[11px] text-yellow-400">PENDING_CONFIRM</span>
        </div>
        ${pendingConfirms.map((trade) => renderCompactTradeCard(trade, 'pending')).join('')}
      </div>
    `);
  }

  if (opened.length) {
    sections.push(`
      <div>
        <div class="trade-mini-group-title">오늘 진입</div>
        ${opened.map((trade) => renderCompactTradeCard(trade, 'opened')).join('')}
      </div>
    `);
  }

  if (openPositions.length) {
    sections.push(`
      <div>
        <div class="trade-mini-group-title">보유 포지션</div>
        ${renderOpenPositionCards(openPositions)}
      </div>
    `);
  }

  el.innerHTML = sections.join('');
}

function renderCompactTradeCard(trade, type) {
  const isCompleted = type === 'completed';
  const isPending = type === 'pending';
  const time = isCompleted
    ? (trade.exit_at ? new Date(trade.exit_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '')
    : (trade.entry_at ? new Date(trade.entry_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '');

  if (isCompleted) {
    const pnlColor = trade.pnl >= 0 ? 'text-green-400' : 'text-red-400';
    const klass = trade.pnl >= 0 ? 'completed-win' : 'completed-loss';
    return `<div class="trade-mini-card ${klass}">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <div class="text-gray-100 font-medium truncate">${trade.stock_name}</div>
          <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time}</div>
        </div>
        <div class="text-right ${pnlColor}">
          <div class="font-semibold">${trade.pnl >= 0 ? '+' : ''}${formatKRW(trade.pnl)}</div>
          <div class="text-[11px]">${trade.return_pct >= 0 ? '+' : ''}${trade.return_pct}%</div>
        </div>
      </div>
    </div>`;
  }

  if (isPending) {
    return `<div class="trade-mini-card border border-yellow-700/40 bg-yellow-900/10">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <div class="text-gray-100 font-medium truncate">${trade.stock_name}</div>
          <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time}</div>
        </div>
        <div class="text-right text-yellow-300">
          <div class="font-semibold">${trade.quantity}주</div>
          <div class="text-[11px]">체결 확인 대기</div>
        </div>
      </div>
    </div>`;
  }

  return `<div class="trade-mini-card opened">
    <div class="flex items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="text-gray-100 font-medium truncate">${trade.stock_name}</div>
        <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time}</div>
      </div>
      <div class="text-right text-blue-300">
        <div class="font-semibold">${trade.quantity}주</div>
        <div class="text-[11px]">@ ${Number(trade.entry_price).toLocaleString()}원</div>
      </div>
    </div>
  </div>`;
}

function renderOpenPositionCards(openPositions) {
  const grouped = {};
  openPositions.forEach((trade) => {
    if (!grouped[trade.stock_symbol]) {
      grouped[trade.stock_symbol] = {
        stock_name: trade.stock_name,
        stock_symbol: trade.stock_symbol,
        total_qty: 0,
        total_cost: 0,
      };
    }
    grouped[trade.stock_symbol].total_qty += trade.quantity;
    grouped[trade.stock_symbol].total_cost += trade.entry_price * trade.quantity;
  });

  return Object.values(grouped).map((position) => {
    const avgPrice = position.total_qty > 0 ? Math.round(position.total_cost / position.total_qty) : 0;
    return `<div class="trade-mini-card position">
      <div class="flex items-center justify-between gap-2">
        <div class="min-w-0">
          <div class="text-gray-100 font-medium truncate">${position.stock_name}</div>
          <div class="text-[11px] text-gray-500">${position.stock_symbol}</div>
        </div>
        <div class="text-right text-purple-300">
          <div class="font-semibold">${position.total_qty}주</div>
          <div class="text-[11px]">평단 ${avgPrice.toLocaleString()}원</div>
        </div>
      </div>
    </div>`;
  }).join('');
}

function formatKRW(amount) {
  if (amount == null) return '-';
  if (Math.abs(amount) >= 100000000) return (amount / 100000000).toFixed(1) + '억';
  return amount.toLocaleString() + '원';
}

// ══════════════════════════════════════════════════════════
// ── Chat Rendering: Stock-Grouped View ──
// ══════════════════════════════════════════════════════════

/**
 * 활동 1건 추가 — 종목별 카드로 라우팅
 */
function appendActivity(data) {
  const container = document.getElementById('chat-container');

  // Remove placeholder
  if (container.children.length === 1 && container.children[0].classList.contains('text-center')) {
    container.innerHTML = '';
  }

  const symbol = data.symbol;
  const isCycleActivity = data.activity_type === 'CYCLE';
  const isDailyPlan = data.activity_type === 'DAILY_PLAN';
  const isLLMCall = data.activity_type === 'LLM_CALL';

  // Non-symbol activities → inline (cycle dividers, daily plan, events without symbol)
  if (!symbol || isCycleActivity || isDailyPlan) {
    if (isCycleActivity && data.phase === 'START') {
      const divider = createCycleDivider(data, true);
      container.appendChild(divider);
    } else if (isCycleActivity && (data.phase === 'COMPLETE' || data.phase === 'ERROR')) {
      // Remove matching START divider spinner
      const startKey = `cycle-start-${data.cycle_id}`;
      const existing = container.querySelector(`[data-cycle-start="${startKey}"]`);
      if (existing) {
        const spinner = existing.querySelector('.progress-spinner');
        if (spinner) spinner.remove();
        existing.querySelector('.cycle-text').textContent += ' → 완료';
      }
      container.appendChild(createCycleDivider(data, false));
    } else if (isLLMCall && !symbol) {
      // LLM calls without symbol → inline
      container.appendChild(createBubble(data));
    } else {
      container.appendChild(createBubble(data));
    }
  } else {
    // Symbol-specific → route to stock card
    const cardKey = `${data.cycle_id || 'ev'}:${symbol}`;
    let card = stockCards[cardKey];

    // 정확한 키 매칭 실패 시 → 같은 종목의 진행 중인 카드에 합류
    if (!card) {
      for (const [key, existing] of Object.entries(stockCards)) {
        if (key.endsWith(':' + symbol) && (!existing.outcome || existing.outcome === 'progress' || existing.outcome === 'buy')) {
          card = existing;
          stockCards[cardKey] = card;  // alias 등록
          break;
        }
      }
    }

    if (!card) {
      card = createStockCard(symbol, data);
      stockCards[cardKey] = card;
      container.appendChild(card.element);
    }
    addStepToCard(card, data);
    updateCardHeader(card);
  }

  activityCount++;
  document.getElementById('activity-count').textContent = `${activityCount}건`;

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

/**
 * 사이클 구분선 생성
 */
function createCycleDivider(data, isStart) {
  const div = document.createElement('div');
  div.className = 'cycle-divider';
  if (isStart) {
    div.setAttribute('data-cycle-start', `cycle-start-${data.cycle_id}`);
    div.innerHTML = `<span class="progress-spinner"></span><span class="cycle-text">${escapeHtml(data.summary)}</span>`;
  } else {
    const time = formatTime(data.created_at);
    const elapsed = data.execution_time_ms ? ` (${(data.execution_time_ms / 1000).toFixed(1)}초)` : '';
    div.innerHTML = `<span>${escapeHtml(data.summary)}${elapsed}</span><span class="text-gray-600">${time}</span>`;
  }
  return div;
}

function rememberStockName(symbol, stockName) {
  if (symbol && stockName && stockName !== symbol) {
    knownStockNames[symbol] = stockName;
  }
}

function renderCardIdentity(card) {
  const identityEl = card.headerEl.querySelector('.stock-identity');
  if (!identityEl) return;
  identityEl.innerHTML = `
    ${escapeHtml(card.stockName)} <span class="text-gray-500 text-xs">${escapeHtml(card.symbol)}</span>
  `;
  identityEl.title = `${card.stockName} (${card.symbol})`;
}

/**
 * 종목 카드 생성
 */
function createStockCard(symbol, firstActivity) {
  const el = document.createElement('div');
  el.className = 'stock-card outcome-progress';

  const meta = resolveActivityStockMeta({
    symbol,
    summary: firstActivity.summary,
    detail: firstActivity.detail,
    knownNames: knownStockNames,
  });
  const stockName = meta.stockName;
  rememberStockName(symbol, stockName);

  // Header
  const header = document.createElement('div');
  header.className = 'stock-card-header';
  header.innerHTML = `
    <span class="text-sm">📊</span>
    <span class="stock-identity text-sm font-medium text-white flex-1 truncate">
      ${escapeHtml(stockName)} <span class="text-gray-500 text-xs">${escapeHtml(symbol)}</span>
    </span>
    <span class="stock-confidence"></span>
    <span class="stock-outcome text-xs px-2 py-0.5 rounded bg-purple-900/40 text-purple-300">
      <span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px;margin-right:4px"></span>분석 중
    </span>
    <span class="stock-elapsed text-xs text-gray-600"></span>
    <span class="stock-expand text-gray-500 text-xs transition-transform" style="transform:rotate(-90deg)">▼</span>
  `;
  header.onclick = () => toggleCardBody(card);

  // Body
  const body = document.createElement('div');
  body.className = 'stock-card-body'; // default: collapsed

  const steps = document.createElement('div');
  steps.className = 'stock-card-steps';
  body.appendChild(steps);

  el.appendChild(header);
  el.appendChild(body);

  const card = {
    element: el,
    headerEl: header,
    bodyEl: body,
    stepsEl: steps,
    activities: [],
    symbol: symbol,
    stockName: stockName,
    outcome: null,       // BUY, SELL, HOLD, ERROR
    confidence: null,
    totalElapsed: 0,
    isOpen: false,
    startTime: Date.now(),
    liveTimer: null,
  };

  // Start live elapsed timer
  card.liveTimer = setInterval(() => {
    if (card.outcome && card.outcome !== 'progress') {
      clearInterval(card.liveTimer);
      card.liveTimer = null;
      return;
    }
    const elapsed = ((Date.now() - card.startTime) / 1000).toFixed(0);
    const elapsedEl = card.headerEl.querySelector('.stock-elapsed');
    if (elapsedEl) elapsedEl.textContent = `${elapsed}초`;
  }, 1000);

  return card;
}

/**
 * 카드에 활동 스텝 추가
 */
function addStepToCard(card, data) {
  const meta = resolveActivityStockMeta({
    symbol: card.symbol,
    summary: data.summary,
    detail: data.detail,
    knownNames: knownStockNames,
  });
  if (meta.stockName && meta.stockName !== card.stockName) {
    card.stockName = meta.stockName;
    rememberStockName(card.symbol, meta.stockName);
    renderCardIdentity(card);
  }

  card.activities.push(data);

  const progressKey = getProgressKey(data);

  // START → compact progress indicator
  if (data.phase === 'START') {
    const step = document.createElement('div');
    step.className = 'stock-step';
    step.setAttribute('data-progress-key', progressKey);
    const time = formatTime(data.created_at);
    const label = (data.summary || '').replace(/시작$/, '').trim();
    step.innerHTML = `
      <span class="text-xs text-gray-600 shrink-0 w-14">${time}</span>
      <span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px"></span>
      <span class="text-xs text-gray-400">${escapeHtml(label)}...</span>
    `;
    card.stepsEl.appendChild(step);
    return;
  }

  // COMPLETE/ERROR → remove matching START spinner
  if (data.phase === 'COMPLETE' || data.phase === 'ERROR') {
    const existing = card.stepsEl.querySelector(`[data-progress-key="${progressKey}"]`);
    if (existing) existing.remove();
  }

  // Create step element
  const step = document.createElement('div');
  step.className = 'stock-step';
  const time = formatTime(data.created_at);
  const typeColor = getTypeColor(data.activity_type);
  const elapsed = data.execution_time_ms ? `${(data.execution_time_ms / 1000).toFixed(1)}초` : '';

  // Activity type color dot
  const dotColor = getTypeDotColor(data.activity_type);

  let html = `
    <span class="text-xs text-gray-600 shrink-0 w-14">${time}</span>
    <span class="shrink-0 w-2 h-2 rounded-full bg-${dotColor}-400 mt-1.5"></span>
    <div class="flex-1 min-w-0">
      <div class="text-xs">${escapeHtml(data.summary)}</div>`;

  // Meta line
  const meta = [];
  if (data.llm_provider) meta.push(`<span class="text-${typeColor}-400">${data.llm_provider}</span>`);
  if (elapsed) meta.push(elapsed);
  if (data.confidence != null) {
    const pct = Math.round(data.confidence * 100);
    meta.push(`신뢰도 ${pct}%`);
  }
  if (meta.length) {
    html += `<div class="text-xs text-gray-600 mt-0.5">${meta.join(' · ')}</div>`;
  }

  // Detail (expandable)
  if (data.detail) {
    const detailId = 'sd-' + Math.random().toString(36).substr(2, 6);
    const isLLMCall = data.activity_type === 'LLM_CALL';
    html += `
      <button onclick="event.stopPropagation(); toggleDetail('${detailId}')" class="text-xs text-gray-600 hover:text-gray-400 mt-0.5">
        ${isLLMCall ? '💬 LLM 대화' : '▸ 상세'}
      </button>
      <div id="${detailId}" class="detail-content mt-1 text-xs bg-dark-900/50 rounded p-2 text-gray-400">
        ${isLLMCall ? formatLLMConversation(data.detail) : `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${formatDetail(data.detail)}</pre>`}
      </div>`;
  }

  // Error
  if (data.error_message) {
    html += `<div class="text-xs text-red-400 mt-0.5">${escapeHtml(data.error_message)}</div>`;
  }

  html += '</div>';
  step.innerHTML = html;
  card.stepsEl.appendChild(step);
}

/**
 * 카드 헤더 업데이트 (최신 활동 기반)
 */
function updateCardHeader(card) {
  const acts = card.activities;
  let outcome = 'progress';
  let outcomeText = '<span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px;margin-right:4px"></span>분석 중';
  let outcomeBg = 'bg-purple-900/40 text-purple-300';
  let totalMs = 0;

  for (const a of acts) {
    if (a.execution_time_ms) totalMs += a.execution_time_ms;

    // Error
    if (a.phase === 'ERROR' || a.error_message) {
      outcome = 'error';
      outcomeText = '❌ 오류';
      outcomeBg = 'bg-yellow-900/40 text-yellow-300';
    }

    // SKIP (데이터 부족, 리스크 차단 등) → HOLD 처리
    if (a.phase === 'SKIP' && outcome !== 'error') {
      outcome = 'hold';
      outcomeText = '⏭ 스킵';
      outcomeBg = 'bg-gray-700/60 text-gray-400';
    }

    // Tier1 result — 방향 결정
    if (a.activity_type === 'TIER1_ANALYSIS' && a.phase === 'COMPLETE') {
      const summ = a.summary || '';
      if (summ.includes('HOLD') || summ.includes('실패')) {
        outcome = 'hold';
        outcomeText = summ.includes('실패') ? '⚠ 분석 실패' : '⏸ HOLD';
        outcomeBg = 'bg-gray-700/60 text-gray-400';
      } else if (summ.includes('BUY')) {
        outcome = 'buy';
        outcomeText = '📈 매수';
        outcomeBg = 'bg-red-900/50 text-red-200 font-bold border border-red-700/50';
      } else if (summ.includes('SELL')) {
        outcome = 'sell';
        outcomeText = '📉 매도';
        outcomeBg = 'bg-blue-900/50 text-blue-200 font-bold border border-blue-700/50';
      }
    }

    // Tier2 — 미승인만 뒤집음, 승인은 기존 방향 유지
    if (a.activity_type === 'TIER2_REVIEW' && a.phase === 'COMPLETE') {
      const summ = a.summary || '';
      if (summ.includes('미승인')) {
        outcome = outcome !== 'error' ? 'hold' : outcome;
        outcomeText = '⛔ 미승인';
        outcomeBg = 'bg-gray-700/60 text-gray-400';
      }
    }

    // Strategy eval — HOLD/스킵
    if (a.activity_type === 'STRATEGY_EVAL' && a.phase === 'COMPLETE') {
      const summ = a.summary || '';
      if ((summ.includes('HOLD') || summ.includes('스킵')) && outcome !== 'error') {
        outcome = 'hold';
        outcomeText = '⏸ HOLD';
        outcomeBg = 'bg-gray-700/60 text-gray-400';
      }
    }

    // 주문 실행/체결 — 방향 유지, 상태만 갱신
    if (a.activity_type === 'DECISION' || a.activity_type === 'ORDER') {
      const summ = a.summary || '';
      const isSell = outcome === 'sell' || summ.includes('SELL') || summ.includes('매도');
      if (a.phase === 'COMPLETE' && (summ.includes('주문 접수') || summ.includes('체결'))) {
        outcome = isSell ? 'sell' : 'buy';
        outcomeText = isSell ? '📉 매도 완료' : '📈 매수 완료';
        outcomeBg = isSell ? 'bg-blue-900/50 text-blue-200 font-bold border border-blue-700/50' : 'bg-red-900/50 text-red-200 font-bold border border-red-700/50';
      } else if (summ.includes('주문 실행')) {
        // 주문 접수 전 — 방향만 표시
        if (outcome !== 'buy' && outcome !== 'sell') {
          outcome = isSell ? 'sell' : 'buy';
          outcomeText = isSell ? '📉 매도' : '📈 매수';
          outcomeBg = isSell ? 'bg-blue-900/50 text-blue-200 font-bold border border-blue-700/50' : 'bg-red-900/50 text-red-200 font-bold border border-red-700/50';
        }
      }
    }

    // Confidence
    if (a.confidence != null) {
      card.confidence = a.confidence;
    }
  }

  card.outcome = outcome;
  card.totalElapsed = totalMs;

  // Update outcome badge
  const outcomeEl = card.headerEl.querySelector('.stock-outcome');
  if (outcomeEl) {
    outcomeEl.className = `stock-outcome text-xs px-2 py-0.5 rounded ${outcomeBg}`;
    outcomeEl.innerHTML = outcomeText;
  }

  // Update confidence mini-bar
  const confEl = card.headerEl.querySelector('.stock-confidence');
  if (confEl && card.confidence != null) {
    const pct = Math.round(card.confidence * 100);
    let barColor = '#ef4444'; // red
    if (pct >= 70) barColor = '#22c55e'; // green
    else if (pct >= 50) barColor = '#eab308'; // yellow
    confEl.innerHTML = `
      <span class="text-xs text-gray-500">${pct}%</span>
      <span class="stock-confidence-bar">
        <span class="stock-confidence-fill" style="width:${pct}%;background:${barColor}"></span>
      </span>`;
  }

  // Update elapsed — when done, stop live timer and show final time
  if (outcome !== 'progress') {
    if (card.liveTimer) {
      clearInterval(card.liveTimer);
      card.liveTimer = null;
    }
    const elapsedEl = card.headerEl.querySelector('.stock-elapsed');
    if (elapsedEl && totalMs > 0) {
      elapsedEl.textContent = `${(totalMs / 1000).toFixed(1)}초`;
    }
  }

  // Update card border color
  card.element.className = `stock-card outcome-${outcome}`;
}

/**
 * 카드 바디 토글
 */
function toggleCardBody(card) {
  card.isOpen = !card.isOpen;
  card.bodyEl.classList.toggle('open', card.isOpen);
  const arrow = card.headerEl.querySelector('.stock-expand');
  if (arrow) arrow.style.transform = card.isOpen ? '' : 'rotate(-90deg)';
}

// ══════════════════════════════════════════════════════════
// ── Legacy Bubble (for non-grouped activities) ──
// ══════════════════════════════════════════════════════════

function createBubble(data) {
  const div = document.createElement('div');
  div.className = 'chat-bubble';

  const time = formatTime(data.created_at);
  const typeColor = getTypeColor(data.activity_type);

  let html = `
    <div class="flex items-start gap-2 px-3 py-1.5 rounded-lg hover:bg-dark-700/50 transition group">
      <span class="text-xs text-gray-500 mt-0.5 shrink-0 w-14">${time}</span>
      <div class="flex-1 min-w-0">
        <div class="text-sm whitespace-pre-wrap">${escapeHtml(data.summary)}</div>`;

  const meta = [];
  if (data.llm_provider) meta.push(`<span class="text-${typeColor}-400">${data.llm_provider}</span>`);
  if (data.execution_time_ms) meta.push(`${(data.execution_time_ms / 1000).toFixed(1)}초`);
  if (data.confidence != null) {
    const pct = Math.round(data.confidence * 100);
    meta.push(`신뢰도 ${pct}%`);
  }
  if (meta.length) {
    html += `<div class="flex items-center gap-3 mt-0.5 text-xs text-gray-500">${meta.join(' | ')}</div>`;
  }

  if (data.detail) {
    const detailId = 'detail-' + (data.id || Math.random().toString(36).substr(2, 6));
    const isLLMCall = data.activity_type === 'LLM_CALL';
    html += `
      <button onclick="toggleDetail('${detailId}')" class="text-xs text-gray-500 hover:text-gray-300 mt-1">
        ${isLLMCall ? '💬 LLM 대화 보기' : '▼ 상세 보기'}
      </button>
      <div id="${detailId}" class="detail-content mt-1 text-xs bg-dark-900 rounded p-2 text-gray-400">
        ${isLLMCall ? formatLLMConversation(data.detail) : `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${formatDetail(data.detail)}</pre>`}
      </div>`;
  }

  if (data.error_message) {
    html += `<div class="text-xs text-red-400 mt-1">${escapeHtml(data.error_message)}</div>`;
  }

  html += `</div></div>`;
  div.innerHTML = html;
  return div;
}

function toggleDetail(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('open');
}

// ── View Switching ──
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.nav-btn').forEach(b => {
    b.className = 'nav-btn w-full text-left px-3 py-2 rounded-lg text-sm text-gray-400 hover:bg-dark-700';
  });
  const activeBtn = document.getElementById(`nav-${view}`);
  if (activeBtn) {
    activeBtn.className = 'nav-btn w-full text-left px-3 py-2 rounded-lg text-sm font-medium bg-blue-900/30 text-blue-300';
  }
  if (view === 'live') {
    loadTodayActivities();
  } else if (view === 'today') {
    loadReport('today');
  }
}

function switchToReport(dateStr) {
  currentView = 'report';
  loadReport(dateStr);
}

// ── Data Loading ──
async function loadTodayActivities() {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">불러오는 중...</div>';
  // Clear card tracking
  cleanupStockCards();

  try {
    const resp = await fetch(`${API}/activities?limit=2000`);
    const json = await resp.json();
    container.innerHTML = '';
    activityCount = 0;

    if (json.data && json.data.length) {
      // Pre-process: filter resolved STARTs
      const activities = filterResolvedStarts(json.data);
      activities.forEach(a => appendActivity(a));

      // History load: stop all timers and finalize stuck cards
      for (const card of Object.values(stockCards)) {
        if (card.liveTimer) {
          clearInterval(card.liveTimer);
          card.liveTimer = null;
        }
        // 히스토리 로드 후 여전히 progress면 → 종료된 분석으로 처리
        if (card.outcome === 'progress') {
          card.outcome = 'hold';
          const outcomeEl = card.headerEl.querySelector('.stock-outcome');
          if (outcomeEl) {
            outcomeEl.className = 'stock-outcome text-xs px-2 py-0.5 rounded bg-gray-700/60 text-gray-400';
            outcomeEl.innerHTML = '⏸ 완료';
          }
          card.element.className = 'stock-card outcome-hold';
        }
      }

      requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;
      });
    } else {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">아직 활동 기록이 없습니다</div>';
    }
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">로드 실패: ${err.message}</div>`;
  }
}

function filterResolvedStarts(activities) {
  const resolved = new Set();
  activities.forEach(a => {
    if (a.phase === 'COMPLETE' || a.phase === 'ERROR') {
      resolved.add(getProgressKey(a));
    }
  });
  return activities.filter(a => {
    if (a.phase === 'START' && resolved.has(getProgressKey(a))) return false;
    return true;
  });
}

function getProgressKey(data) {
  const match = (data.summary || '').match(/\[([^\]]+)\]/);
  const symbol = match ? match[1] : '';
  return `${data.activity_type}:${symbol}`;
}

// ── Clear Chat ──
function clearChat() {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">화면을 비웠습니다. 새 활동이 들어오면 여기에 표시됩니다.</div>';
  activityCount = 0;
  document.getElementById('activity-count').textContent = '0건';
  cleanupStockCards();
}

function cleanupStockCards() {
  for (const card of Object.values(stockCards)) {
    if (card.liveTimer) clearInterval(card.liveTimer);
  }
  stockCards = {};
}

// ── Q&A ──
async function askQuestion() {
  const input = document.getElementById('qa-input');
  const btn = document.getElementById('qa-btn');
  const respEl = document.getElementById('qa-response');
  const question = input.value.trim();
  if (!question) return;

  btn.disabled = true;
  btn.textContent = '...';
  respEl.classList.remove('hidden');
  respEl.innerHTML = '<span class="text-gray-500">답변 생성 중...</span>';

  try {
    const res = await fetch(`${API}/qa/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const json = await res.json();
    if (json.data) {
      const d = json.data;
      respEl.innerHTML =
        `<div class="text-xs text-gray-500 mb-1">${d.context_summary} | ${d.llm_provider} | ${(d.execution_time_ms/1000).toFixed(1)}s</div>` +
        `<div class="whitespace-pre-wrap">${escapeHtml(d.answer)}</div>`;
    } else {
      respEl.innerHTML = `<span class="text-red-400">${json.message || '답변 생성 실패'}</span>`;
    }
  } catch (e) {
    respEl.innerHTML = `<span class="text-red-400">요청 실패: ${e.message}</span>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '질문';
    input.value = '';
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ── Reports ──
async function loadReport(dateStr) {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">리포트 불러오는 중...</div>';
  cleanupStockCards();

  try {
    let url = `${API}/reports/latest`;
    if (dateStr && dateStr !== 'today') url = `${API}/reports/${dateStr}`;
    const resp = await fetch(url);
    const json = await resp.json();
    const report = json.data;

    if (!report) {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">해당 날짜의 리포트가 없습니다</div>';
      if (dateStr && dateStr !== 'today') await loadDateActivities(dateStr, container);
      return;
    }
    container.innerHTML = '';
    container.appendChild(createReportCard(report));
    if (report.report_date) {
      await loadTradeHistory(report.report_date, container);
      await loadDateActivities(report.report_date, container);
    }
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">리포트 로드 실패: ${err.message}</div>`;
  }
}

async function loadDateActivities(dateStr, container) {
  try {
    const resp = await fetch(`${API}/activities?target_date=${dateStr}&limit=500`);
    const json = await resp.json();
    if (json.data && json.data.length) {
      const section = document.createElement('div');
      section.className = 'mt-4 border-t border-gray-800';
      const toggleBtn = document.createElement('button');
      toggleBtn.className = 'w-full text-center text-gray-500 hover:text-gray-300 text-xs py-3 flex items-center justify-center gap-2 transition';
      toggleBtn.innerHTML = `<span class="activity-toggle-icon">▶</span> ${dateStr} 활동 로그 (${json.data.length}건)`;
      const logContainer = document.createElement('div');
      logContainer.className = 'hidden';
      logContainer.style.maxHeight = '600px';
      logContainer.style.overflowY = 'auto';
      json.data.forEach(a => logContainer.appendChild(createBubble(a)));
      toggleBtn.onclick = () => {
        const isHidden = logContainer.classList.contains('hidden');
        logContainer.classList.toggle('hidden');
        toggleBtn.querySelector('.activity-toggle-icon').innerHTML = isHidden ? '▼' : '▶';
      };
      section.appendChild(toggleBtn);
      section.appendChild(logContainer);
      container.appendChild(section);
    }
  } catch (err) {
    console.error('Activities load error:', err);
  }
}

function createReportCard(report) {
  const div = document.createElement('div');
  div.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble';
  const winRate = (report.win_count + report.loss_count) > 0
    ? ((report.win_count / (report.win_count + report.loss_count)) * 100).toFixed(1)
    : '-';
  const realizedPnlColor = report.total_pnl >= 0 ? 'text-green-400' : 'text-red-400';
  const unrealizedPnl = report.unrealized_pnl || 0;
  const unrealizedPnlColor = unrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400';
  const buyCount = report.buy_count || 0;
  const sellCount = report.sell_count || 0;
  const openCount = report.open_position_count || 0;
  let topPicks = '';
  try {
    const picks = JSON.parse(report.top_picks || '[]');
    topPicks = picks.map(p => typeof p === 'string' ? p : `${p.name || ''}(${p.symbol || ''})`).filter(Boolean).join(', ');
  } catch(e) {}

  div.innerHTML = `
    <div class="text-lg font-bold text-white mb-4">📋 ${report.report_date} 일일 리포트</div>
    <div class="grid grid-cols-3 gap-3 mb-3">
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-blue-400">${report.total_cycles}</div>
        <div class="text-xs text-gray-500">사이클</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-purple-400">${report.total_analyses}</div>
        <div class="text-xs text-gray-500">분석</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-yellow-400">${buyCount}<span class="text-xs text-gray-500">매수</span> / ${sellCount}<span class="text-xs text-gray-500">매도</span></div>
        <div class="text-xs text-gray-500">주문 (보유 ${openCount}종목)</div>
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3 mb-4">
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-xl font-bold ${realizedPnlColor}">${report.total_pnl >= 0 ? '+' : ''}${report.total_pnl.toLocaleString()}원</div>
        <div class="text-xs text-gray-500">실현 손익 (승률 ${winRate}%)</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-xl font-bold ${unrealizedPnlColor}">${unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toLocaleString()}원</div>
        <div class="text-xs text-gray-500">미실현 손익</div>
      </div>
    </div>
    ${report.market_summary ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📝 오늘 리뷰</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(report.market_summary)}</div>
    </div>` : ''}
    ${report.performance_review ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📊 포트폴리오 진단</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(report.performance_review)}</div>
    </div>` : ''}
    ${report.lessons_learned ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">🔮 내일 전망</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(report.lessons_learned)}</div>
    </div>` : ''}
    ${report.next_day_plan ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📈 액션 플랜</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(report.next_day_plan)}</div>
    </div>` : ''}
    ${topPicks ? `
    <div class="mb-2">
      <div class="text-sm font-medium text-gray-300 mb-1">🎯 관심 종목</div>
      <div class="text-xs text-gray-400 bg-dark-900 rounded p-2">${escapeHtml(topPicks)}</div>
    </div>` : ''}`;
  return div;
}

// ── Trade History ──
async function loadTradeHistory(dateStr, container) {
  try {
    const resp = await fetch(`${API}/trades?target_date=${dateStr}`);
    const json = await resp.json();
    const data = json.data;
    if (!data) return;

    const opened = data.opened || [];
    const completed = data.completed || [];
    const pendingConfirms = data.pending_confirms || [];
    const openPositions = data.open_positions || [];
    if (!opened.length && !completed.length && !pendingConfirms.length && !openPositions.length) return;

    const section = document.createElement('div');
    section.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 mt-3 chat-bubble';

    let html = '<div class="text-sm font-bold text-white mb-3">💰 매매 내역</div>';

    // 청산 완료 (실현 손익)
    if (completed.length) {
      html += '<div class="text-xs font-medium text-gray-400 mb-2">청산 완료</div>';
      html += completed.map(t => renderTradeCard(t, 'completed')).join('');
    }

    if (pendingConfirms.length) {
      html += `<div class="text-xs font-medium text-gray-400 mb-2 ${completed.length ? 'mt-3' : ''}">확인 대기</div>`;
      html += pendingConfirms.map(t => renderTradeCard(t, 'pending')).join('');
    }

    // 오늘 매수
    if (opened.length) {
      html += `<div class="text-xs font-medium text-gray-400 mb-2 ${(completed.length || pendingConfirms.length) ? 'mt-3' : ''}">오늘 매수</div>`;
      html += opened.map(t => renderTradeCard(t, 'opened')).join('');
    }

    // 미청산 보유
    if (openPositions.length) {
      html += `<div class="text-xs font-medium text-gray-400 mb-2 mt-3">보유 중 (미청산)</div>`;
      // 종목별 그룹핑
      const grouped = {};
      openPositions.forEach(t => {
        if (!grouped[t.stock_symbol]) grouped[t.stock_symbol] = { name: t.stock_name, symbol: t.stock_symbol, trades: [] };
        grouped[t.stock_symbol].trades.push(t);
      });
      html += Object.values(grouped).map(g => {
        const totalQty = g.trades.reduce((s, t) => s + t.quantity, 0);
        const avgPrice = g.trades.reduce((s, t) => s + t.entry_price * t.quantity, 0) / totalQty;
        const entries = g.trades.map(t => {
          const time = t.entry_at ? new Date(t.entry_at).toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit'}) : '';
          return `${time} ${t.quantity}주 @${t.entry_price.toLocaleString()}원`;
        }).join(' → ');
        const conf = g.trades[0].ai_confidence;
        return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 border-blue-500">
          <div class="flex justify-between items-center">
            <span class="text-sm text-white font-medium">${g.name}<span class="text-gray-500 text-xs ml-1">${g.symbol}</span></span>
            <span class="text-xs text-blue-400">${totalQty}주 · 평단 ${Math.round(avgPrice).toLocaleString()}원</span>
          </div>
          <div class="text-xs text-gray-500 mt-1">${entries}</div>
          ${conf ? `<div class="text-xs text-gray-600 mt-1">신뢰도 ${(conf*100).toFixed(0)}%</div>` : ''}
        </div>`;
      }).join('');
    }

    section.innerHTML = html;
    container.appendChild(section);
  } catch (err) {
    console.error('Trade history load error:', err);
  }
}

function renderTradeCard(t, type) {
  const time = (type === 'completed' && t.exit_at)
    ? new Date(t.exit_at).toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit'})
    : (t.entry_at ? new Date(t.entry_at).toLocaleTimeString('ko-KR', {hour:'2-digit',minute:'2-digit'}) : '');

  if (type === 'completed') {
    const pnlColor = t.pnl >= 0 ? 'text-green-400' : 'text-red-400';
    const borderColor = t.pnl >= 0 ? 'border-green-500' : 'border-red-500';
    const pnlSign = t.pnl >= 0 ? '+' : '';
    const returnSign = t.return_pct >= 0 ? '+' : '';
    return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 ${borderColor}">
      <div class="flex justify-between items-center">
        <span class="text-sm text-white font-medium">${t.stock_name}<span class="text-gray-500 text-xs ml-1">${t.stock_symbol}</span></span>
        <span class="text-xs ${pnlColor} font-medium">${pnlSign}${t.pnl.toLocaleString()}원 (${returnSign}${t.return_pct}%)</span>
      </div>
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>${t.quantity}주 · ${t.entry_price.toLocaleString()} → ${t.exit_price.toLocaleString()}원</span>
        <span>${time} · ${t.exit_reason || 'SIGNAL'}${t.hold_days > 0 ? ` · ${t.hold_days}일 보유` : ''}</span>
      </div>
      ${t.ai_confidence ? `<div class="text-xs text-gray-600 mt-1">신뢰도 ${(t.ai_confidence*100).toFixed(0)}% · ${t.strategy_type || ''}</div>` : ''}
    </div>`;
  }

  if (type === 'pending') {
    const conf = t.ai_confidence ? `신뢰도 ${(t.ai_confidence*100).toFixed(0)}%` : '';
    return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 border-yellow-500">
      <div class="flex justify-between items-center">
        <span class="text-sm text-white font-medium">${t.stock_name}<span class="text-gray-500 text-xs ml-1">${t.stock_symbol}</span></span>
        <span class="text-xs text-yellow-400">대기 ${t.quantity}주 @${t.entry_price.toLocaleString()}원</span>
      </div>
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>${time} · 체결 확인 대기</span>
        <span>${conf}</span>
      </div>
    </div>`;
  }

  // opened (매수)
  const conf = t.ai_confidence ? `신뢰도 ${(t.ai_confidence*100).toFixed(0)}%` : '';
  return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 border-red-500">
    <div class="flex justify-between items-center">
      <span class="text-sm text-white font-medium">${t.stock_name}<span class="text-gray-500 text-xs ml-1">${t.stock_symbol}</span></span>
      <span class="text-xs text-red-400">매수 ${t.quantity}주 @${t.entry_price.toLocaleString()}원</span>
    </div>
    <div class="flex justify-between text-xs text-gray-500 mt-1">
      <span>${time} · ${t.strategy_type || ''}</span>
      <span>${conf}</span>
    </div>
  </div>`;
}

async function reconcilePendingTrades() {
  const button = document.getElementById('reconcile-pending-trades');
  const originalText = button?.textContent || '확인 대기 복구';

  try {
    if (button) {
      button.disabled = true;
      button.textContent = '복구 중...';
    }
    await fetch(`${API}/trades/reconcile-pending`, { method: 'POST' });
    await loadAccountInfo();
  } catch (err) {
    console.error('Pending trade reconcile error:', err);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

// ── Settings ──
async function loadSettings() {
  try {
    const resp = await fetch(`${API}/settings`);
    const json = await resp.json();
    const s = json.data;
    if (!s) return;
    runtimeSettings = s;
    document.getElementById('set-trading').checked = s.TRADING_ENABLED;
    document.getElementById('set-mode').value = s.AUTONOMY_MODE;
    const riskEl = document.getElementById('set-risk-appetite');
    if (riskEl && s.RISK_APPETITE) riskEl.value = s.RISK_APPETITE;
    const tier1ProviderEl = document.getElementById('set-llm-tier1-provider');
    if (tier1ProviderEl) tier1ProviderEl.value = s.LLM_PROVIDER_TIER1 || s.LLM_PROVIDER || 'CLAUDE_CODE';
    const tier2ProviderEl = document.getElementById('set-llm-tier2-provider');
    if (tier2ProviderEl) tier2ProviderEl.value = s.LLM_PROVIDER_TIER2 || s.LLM_PROVIDER || 'CLAUDE_CODE';
    const tier1FallbackEl = document.getElementById('set-llm-tier1-fallback');
    if (tier1FallbackEl) tier1FallbackEl.value = s.LLM_FALLBACK_PROVIDER_TIER1 || '';
    const tier2FallbackEl = document.getElementById('set-llm-tier2-fallback');
    if (tier2FallbackEl) tier2FallbackEl.value = s.LLM_FALLBACK_PROVIDER_TIER2 || '';
    const manualLlmEl = document.getElementById('set-manual-llm-provider');
    if (manualLlmEl && s.MANUAL_LLM_PROVIDER) manualLlmEl.value = s.MANUAL_LLM_PROVIDER;
    renderTierModelSelectors();
    updateBadge('badge-trading', s.TRADING_ENABLED ? '매매:ON' : '매매:OFF', s.TRADING_ENABLED ? 'green' : 'red');
    updateBadge('badge-mode', formatAutonomyModeLabel(s.AUTONOMY_MODE), 'purple');
    renderSettingGuidance();
    renderRuntimeControls();
  } catch (err) {
    console.error('Settings load error:', err);
  }
}

async function updateSetting(key, value) {
  try {
    const resp = await fetch(`${API}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value }),
    });
    if (!resp.ok) {
      throw new Error(`${key} 저장 실패`);
    }
    await Promise.all([
      loadSettings(),
      loadSystemStatus(),
      loadLLMStatus(),
    ]);
    return true;
  } catch (err) {
    console.error('Setting update error:', err);
    setStatus('error', `설정 변경 실패: ${err.message}`);
    return false;
  }
}

async function refreshRuntimePanels() {
  await Promise.all([
    loadSettings(),
    loadSystemStatus(),
    loadLLMStatus(),
    loadLLMUsage(),
  ]);
}

function setControlButtonState(id, { active = false, disabled = false, tone = 'blue' } = {}) {
  const el = document.getElementById(id);
  if (!el) return;

  const activeClasses = {
    green: 'border-green-500 bg-green-600/20 text-green-200',
    red: 'border-red-500 bg-red-600/20 text-red-200',
    yellow: 'border-yellow-500 bg-yellow-600/20 text-yellow-200',
    blue: 'border-blue-500 bg-blue-600/20 text-blue-200',
    purple: 'border-purple-500 bg-purple-600/20 text-purple-200',
  };
  const inactiveClasses = 'border-gray-700 bg-dark-800 text-gray-300 hover:border-gray-500 hover:text-gray-100';
  const disabledClasses = 'opacity-50 cursor-not-allowed';
  const enabledClasses = 'cursor-pointer';

  el.disabled = disabled;
  el.className = `rounded-md border px-2 py-1.5 text-xs transition ${active ? (activeClasses[tone] || activeClasses.blue) : inactiveClasses} ${disabled ? disabledClasses : enabledClasses}`;
}

function renderRuntimeControls() {
  const summaryEl = document.getElementById('runtime-control-summary');
  const state = buildRuntimeControlState({
    runtimeSettings,
    runtimeSystemStatus,
    runtimeControlPending,
  });
  const {
    tradingEnabled,
    autonomyMode,
    schedulerRunning,
    schedulerEnabled,
    agentRunning,
  } = state;
  const headerSummaryEl = document.getElementById('header-runtime-summary');
  const autonomyLabel = formatAutonomyModeLabel(autonomyMode);

  const schedulerMismatch = state.schedulerMismatchMessage
    ? `<div class="text-yellow-300">${state.schedulerMismatchMessage}</div>`
    : '';

  if (summaryEl) {
    summaryEl.innerHTML = `
      <div>실행 상태: 에이전트 <span class="${agentRunning ? 'text-green-300' : 'text-yellow-300'}">${agentRunning ? '동작' : '중지'}</span> · 스케줄러 <span class="${schedulerRunning ? 'text-green-300' : 'text-yellow-300'}">${schedulerRunning ? '동작' : '중지'}</span></div>
      <div>주문 설정: <span class="${tradingEnabled ? 'text-green-300' : 'text-red-300'}">${tradingEnabled ? 'ON' : 'OFF'}</span> · ${escapeHtml(autonomyLabel)}</div>
      <div>스케줄러 설정: ${schedulerEnabled ? '활성' : '비활성'}</div>
      ${schedulerMismatch}
      ${runtimeControlPending ? '<div class="text-blue-300">변경 적용 중...</div>' : ''}
    `;
  }
  if (headerSummaryEl) {
    headerSummaryEl.innerHTML = `실행: <span class="${agentRunning ? 'text-green-300' : 'text-yellow-300'}">${agentRunning ? '에이전트 동작' : '에이전트 중지'}</span> · <span class="${schedulerRunning ? 'text-green-300' : 'text-yellow-300'}">${schedulerRunning ? '스케줄러 동작' : '스케줄러 중지'}</span>${runtimeControlPending ? ' · <span class="text-blue-300">적용 중...</span>' : ''}`;
  }

  Object.entries(state.buttonStates).forEach(([id, options]) => setControlButtonState(id, options));
  updateHeaderActionButtonState('header-trigger-cycle', { disabled: state.headerTriggerDisabled });
  renderSettingGuidance();
}

function renderSettingGuidance() {
  const copy = buildRuntimeSettingCopy({ runtimeSettings, runtimeSystemStatus });
  const tradingLabelEl = document.getElementById('set-trading-label');
  const tradingHelpEl = document.getElementById('set-trading-help');
  const tradingTipEl = document.getElementById('set-trading-tip');
  const modeLabelEl = document.getElementById('set-mode-label');
  const modeHelpEl = document.getElementById('set-mode-help');
  const modeTipEl = document.getElementById('set-mode-tip');

  if (tradingLabelEl) tradingLabelEl.textContent = copy.tradingLabel;
  if (tradingHelpEl) tradingHelpEl.textContent = copy.tradingHelp;
  if (tradingTipEl) tradingTipEl.title = copy.tradingTitle;
  if (modeLabelEl) modeLabelEl.textContent = copy.modeLabel;
  if (modeHelpEl) modeHelpEl.textContent = copy.modeHelp;
  if (modeTipEl) modeTipEl.title = copy.modeTitle;
}

function applyControlButtonState(ids, options) {
  ids.forEach((id) => setControlButtonState(id, options));
}

function updateHeaderActionButtonState(id, { disabled = false } = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  const disabledClasses = 'opacity-50 cursor-not-allowed';
  const enabledClasses = 'cursor-pointer hover:border-blue-400 hover:bg-blue-600/30';
  el.disabled = disabled;
  el.className = `rounded-md border border-blue-500 bg-blue-600/20 px-2.5 py-1.5 text-xs font-medium text-blue-200 transition ${disabled ? disabledClasses : enabledClasses}`;
}

async function setTradingEnabled(enabled) {
  if (runtimeControlPending) return;
  runtimeControlPending = true;
  renderRuntimeControls();
  try {
    const ok = await updateSetting('TRADING_ENABLED', enabled);
    if (ok) setStatus('runtime', `매매 ${enabled ? 'ON' : 'OFF'} 적용`);
  } finally {
    runtimeControlPending = false;
    renderRuntimeControls();
  }
}

async function setAutonomyMode(mode) {
  if (runtimeControlPending) return;
  runtimeControlPending = true;
  renderRuntimeControls();
  try {
    const ok = await updateSetting('AUTONOMY_MODE', mode);
    if (ok) setStatus('runtime', `운영 모드 ${mode} 적용`);
  } finally {
    runtimeControlPending = false;
    renderRuntimeControls();
  }
}

async function setSchedulerRunning(shouldRun) {
  if (runtimeControlPending) return;
  runtimeControlPending = true;
  renderRuntimeControls();
  try {
    const endpoint = shouldRun ? 'start' : 'stop';
    const resp = await fetch(`${API}/scheduler/${endpoint}`, { method: 'POST' });
    if (!resp.ok) {
      throw new Error(`스케줄러 ${shouldRun ? '시작' : '중지'} 실패`);
    }
    await Promise.all([
      loadSettings(),
      loadSystemStatus(),
    ]);
    setStatus('runtime', `스케줄러 ${shouldRun ? '시작' : '중지'} 완료`);
  } catch (err) {
    console.error('Scheduler control error:', err);
    setStatus('error', err.message);
  } finally {
    runtimeControlPending = false;
    renderRuntimeControls();
  }
}

function getTierProvider(tier, mode = 'primary') {
  const providerEl = document.getElementById(
    mode === 'fallback'
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback' : 'set-llm-tier2-fallback')
      : (tier === 'tier1' ? 'set-llm-tier1-provider' : 'set-llm-tier2-provider')
  );
  if (mode === 'fallback') {
    return providerEl?.value || '';
  }
  return providerEl?.value || 'CLAUDE_CODE';
}

function getTierModelSettingKey(provider, tier, mode = 'primary') {
  if (mode === 'fallback') {
    return tier === 'tier1' ? 'LLM_FALLBACK_MODEL_TIER1' : 'LLM_FALLBACK_MODEL_TIER2';
  }
  if (provider === 'CODEX') {
    return tier === 'tier1' ? 'CODEX_MODEL_TIER1' : 'CODEX_MODEL_TIER2';
  }
  return tier === 'tier1' ? 'CLAUDE_CODE_MODEL_TIER1' : 'CLAUDE_CODE_MODEL_TIER2';
}

function getCatalogProvider(provider) {
  return llmCatalog?.providers?.find((item) => item.id === provider) || null;
}

function renderTierModelSelectors() {
  renderTierModelSelector('tier1', 'primary');
  renderTierModelSelector('tier1', 'fallback');
  renderTierModelSelector('tier2', 'primary');
  renderTierModelSelector('tier2', 'fallback');
}

function renderTierModelSelector(tier, mode = 'primary') {
  if (!runtimeSettings) return;
  const provider = getTierProvider(tier, mode);
  const key = getTierModelSettingKey(provider, tier, mode);
  const currentValue = runtimeSettings[key] || 'DEFAULT';
  const isFallback = mode === 'fallback';
  const hasFallbackProvider = !isFallback || !!provider;
  const selectEl = document.getElementById(
    isFallback
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback-model' : 'set-llm-tier2-fallback-model')
      : (tier === 'tier1' ? 'set-llm-tier1-model' : 'set-llm-tier2-model')
  );
  const sourceEl = document.getElementById(
    isFallback
      ? (tier === 'tier1' ? 'llm-tier1-fallback-model-source' : 'llm-tier2-fallback-model-source')
      : (tier === 'tier1' ? 'llm-tier1-model-source' : 'llm-tier2-model-source')
  );
  const customEl = document.getElementById(
    isFallback
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback-model-custom' : 'set-llm-tier2-fallback-model-custom')
      : (tier === 'tier1' ? 'set-llm-tier1-model-custom' : 'set-llm-tier2-model-custom')
  );
  if (!selectEl) return;

  if (!hasFallbackProvider) {
    selectEl.innerHTML = '<option value="DEFAULT">없음</option>';
    selectEl.value = 'DEFAULT';
    selectEl.disabled = true;
    if (customEl) {
      customEl.value = '';
      customEl.disabled = true;
    }
    if (sourceEl) sourceEl.textContent = 'fallback provider를 먼저 선택하세요';
    return;
  }

  const providerCatalog = getCatalogProvider(provider);
  const entries = providerCatalog?.entries ? [...providerCatalog.entries] : [{ value: 'DEFAULT', label: '기본값 사용' }];
  if (currentValue && !entries.some((item) => item.value === currentValue)) {
    entries.push({
      value: currentValue,
      label: `${currentValue} (custom)`,
      kind: 'custom',
      stability: 'custom',
      source_scope: 'manual',
      source_url: '',
    });
  }

  selectEl.innerHTML = entries.map((item) => {
    const suffix = item.kind === 'snapshot'
      ? ' [고정]'
      : (item.value === 'DEFAULT' ? ' [CLI 기본값]' : '');
    return `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label || item.value)}${suffix}</option>`;
  }).join('');
  selectEl.value = currentValue;
  selectEl.disabled = false;

  if (customEl) {
    customEl.placeholder = provider === 'CODEX'
      ? '예: gpt-5-codex / gpt-5.4'
      : '예: sonnet / claude-sonnet-4-6';
    customEl.value = '';
    customEl.disabled = false;
  }

  if (sourceEl) {
    const selected = entries.find((item) => item.value === currentValue);
    const sourceBits = [];
    if (selected?.source_scope) sourceBits.push(`출처: ${selected.source_scope}`);
    if (selected?.stability) sourceBits.push(`성격: ${selected.stability}`);
    if (providerCatalog?.cli_version) sourceBits.push(`CLI ${providerCatalog.cli_version}`);
    sourceEl.textContent = sourceBits.join(' · ');
  }
}

async function loadLLMCatalog(forceRefresh = false) {
  try {
    const suffix = forceRefresh ? '?force_refresh=true' : '';
    const resp = await fetch(`${API}/llm/catalog${suffix}`);
    const json = await resp.json();
    llmCatalog = json.data;
    renderLLMCatalogMeta();
    renderTierModelSelectors();
  } catch (err) {
    console.error('LLM catalog error:', err);
    const metaEl = document.getElementById('llm-catalog-meta');
    if (metaEl) metaEl.textContent = '공식 모델 목록 조회 실패';
  }
}

function renderLLMCatalogMeta() {
  const metaEl = document.getElementById('llm-catalog-meta');
  if (!metaEl) return;
  if (!llmCatalog) {
    metaEl.textContent = '공식 모델 목록 불러오는 중...';
    return;
  }
  const parts = [];
  if (llmCatalog.fetched_at) {
    parts.push(`동기화 ${formatDateTime(llmCatalog.fetched_at)}`);
  } else {
    parts.push('내장 seed 목록 사용 중');
  }
  if (llmCatalog.stale) parts.push('stale');
  if (llmCatalog.fetch_error) parts.push(`동기화 실패: ${llmCatalog.fetch_error}`);
  metaEl.textContent = parts.join(' · ');
}

async function refreshLLMCatalog() {
  await loadLLMCatalog(true);
  await loadSettings();
  await loadLLMStatus();
}

async function updateTierModelSetting(tier, value, mode = 'primary') {
  const provider = getTierProvider(tier, mode);
  const key = getTierModelSettingKey(provider, tier, mode);
  await updateSetting(key, value || 'DEFAULT');
}

async function applyCustomTierModel(tier, mode = 'primary') {
  const inputEl = document.getElementById(
    mode === 'fallback'
      ? (tier === 'tier1' ? 'set-llm-tier1-fallback-model-custom' : 'set-llm-tier2-fallback-model-custom')
      : (tier === 'tier1' ? 'set-llm-tier1-model-custom' : 'set-llm-tier2-model-custom')
  );
  if (!inputEl) return;
  const value = inputEl.value.trim();
  if (!value) return;
  await updateTierModelSetting(tier, value, mode);
}

// ── LLM Status ──
async function loadLLMStatus() {
  try {
    const resp = await fetch(`${API}/llm/status`);
    const json = await resp.json();
    const s = json.data;
    if (!s) return;
    const t1Model = document.getElementById('llm-tier1-model');
    if (t1Model) {
      const t1FallbackModel = s.tier1.fallback_provider
        ? (s.tier1.fallback_model_mode === 'default' ? '기본값 사용' : s.tier1.fallback_model)
        : '';
      const t2FallbackModel = s.tier2.fallback_provider
        ? (s.tier2.fallback_model_mode === 'default' ? '기본값 사용' : s.tier2.fallback_model)
        : '';
      const t1Fallback = s.tier1.fallback_provider ? ` → ${s.tier1.fallback_provider}${t1FallbackModel ? `(${t1FallbackModel})` : ''}` : '';
      const t2Fallback = s.tier2.fallback_provider ? ` → ${s.tier2.fallback_provider}${t2FallbackModel ? `(${t2FallbackModel})` : ''}` : '';
      const t1ModelLabel = s.tier1.model_mode === 'default' ? '기본값 사용' : s.tier1.model;
      const t2ModelLabel = s.tier2.model_mode === 'default' ? '기본값 사용' : s.tier2.model;
      t1Model.textContent = `T1 ${s.tier1.provider}${t1Fallback} (${t1ModelLabel}) / T2 ${s.tier2.provider}${t2Fallback} (${t2ModelLabel})`;
    }
    const llmSummary = document.getElementById('llm-config-summary');
    if (llmSummary) {
      llmSummary.textContent = `사이클 기본값: T1 ${s.tier1.provider}, T2 ${s.tier2.provider}`;
    }
    const manualSelection = document.getElementById('llm-manual-selection');
    if (manualSelection && s.manual_selection) {
      const provider = s.manual_selection.provider || 'AUTOMATIC';
      const label = provider === 'AUTOMATIC' ? '자동 (기본 tier 설정 사용)' : provider;
      manualSelection.textContent = `현재 수동 작업 선택: ${label}`;
    }
  } catch (err) {
    console.error('LLM status error:', err);
  }
}

async function loadLLMUsage() {
  const panelEl = document.getElementById('llm-usage-panel');
  if (panelEl && !llmUsageSnapshot) {
    panelEl.innerHTML = '<div class="text-gray-500">CLI 상태를 확인하는 중...</div>';
  }

  try {
    const resp = await fetch(`${API}/llm/usage`);
    if (!resp.ok) {
      throw new Error('LLM 사용량 조회 실패');
    }
    const json = await resp.json();
    llmUsageSnapshot = json.data;
    renderLLMUsage();
  } catch (err) {
    console.error('LLM usage error:', err);
    if (panelEl) {
      panelEl.innerHTML = `<div class="text-red-400">조회 실패: ${escapeHtml(err.message)}</div>`;
    }
  }
}

// ── System Status ──
async function loadSystemStatus() {
  try {
    const resp = await fetch(`${API}/system/status`);
    const json = await resp.json();
    const s = json.data;
    if (!s) return;
    runtimeSystemStatus = s;
    const brokerProvider = s.broker_provider || 'KIWOOM';
    const mcpBadge = getMcpBadgeState(s);
    const brokerBadgeTone = brokerProvider === 'KIS' ? 'blue' : 'yellow';
    const isHoliday = !!s.market_holiday;
    const marketLabel = s.market_open ? '장:장중' : (isHoliday ? `장:휴장` : '장:장외');
    const marketBadgeTone = s.market_open ? 'green' : (isHoliday ? 'yellow' : 'gray');
    updateBadge('badge-broker', `브로커:${brokerProvider}`, brokerBadgeTone);
    updateBadge('badge-market', marketLabel, marketBadgeTone);
    updateBadge('badge-trading', s.trading_enabled ? '매매:ON' : '매매:OFF', s.trading_enabled ? 'green' : 'red');
    updateBadge('badge-mcp', mcpBadge.label, mcpBadge.tone);
    const statusEl = document.getElementById('sys-status');
    const marketStatusLabel = s.market_open ? '장중' : (isHoliday ? `휴장 (${s.market_holiday})` : '장외');
    const marketColor = s.market_open ? 'bg-green-400' : (isHoliday ? 'bg-yellow-400' : 'bg-gray-500');
    const marketExtra = s.market_open ? '' : ` (다음: ${s.next_market_open || ''})`;
    statusEl.innerHTML = `
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${marketColor}"></span>
        <strong>${marketStatusLabel}</strong>${marketExtra}
      </div>
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${mcpBadge.dotClass}"></span>
        MCP: ${escapeHtml(mcpBadge.detailLabel)}
      </div>
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${s.scheduler_running ? 'bg-green-400' : 'bg-yellow-400'}"></span>
        스케줄러: ${s.scheduler_running ? '동작' : '중지'}
      </div>
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${s.agent_running ? 'bg-green-400' : 'bg-yellow-400'}"></span>
        에이전트: ${s.agent_running ? '동작' : '중지'}
      </div>
      ${s.last_cycle_time ? `<div class="text-gray-600">마지막: ${formatTime(s.last_cycle_time)}</div>` : ''}
      <div class="text-gray-600">SSE: ${s.sse_clients}명</div>`;
    renderRuntimeControls();
    document.querySelectorAll('[data-cycle-trigger="true"]').forEach((btn) => {
      btn.textContent = s.market_open ? '▶ 매매 사이클 실행' : '▶ 장마감 리뷰 실행';
    });
  } catch (err) {
    console.error('Status load error:', err);
  }
}

// ── Report List ──
async function loadReportList() {
  try {
    const resp = await fetch(`${API}/reports?limit=10`);
    const json = await resp.json();
    const listEl = document.getElementById('report-list');
    listEl.innerHTML = '';
    if (json.data && json.data.length) {
      json.data.forEach(r => {
        const btn = document.createElement('button');
        btn.className = 'w-full text-left px-3 py-1 text-xs text-gray-400 hover:bg-dark-700 rounded';
        btn.textContent = r.report_date;
        btn.onclick = () => switchToReport(r.report_date);
        listEl.appendChild(btn);
      });
    } else {
      listEl.innerHTML = '<div class="px-3 text-xs text-gray-600">리포트 없음</div>';
    }
  } catch (err) {
    console.error('Report list error:', err);
  }
}

// ── Actions ──
let triggerPending = false;
async function triggerCycle() {
  if (triggerPending) return;
  triggerPending = true;
  try {
    await fetch(`${API}/agent/trigger`, { method: 'POST' });
  } catch (err) {
    console.error('Trigger error:', err);
  } finally {
    setTimeout(() => { triggerPending = false; }, 3000);
  }
}

async function generateReport() {
  try {
    await fetch(`${API}/reports/generate`, { method: 'POST' });
    loadReportList();
  } catch (err) {
    console.error('Report gen error:', err);
  }
}

// ── Utilities ──
function formatTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ts; }
}

function formatDateTime(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch { return ts; }
}

function formatInteger(value) {
  const numeric = Number(value || 0);
  return numeric.toLocaleString('ko-KR');
}

function formatUsd(value) {
  const numeric = Number(value || 0);
  return `$${numeric.toFixed(2)}`;
}

function renderProviderLinks(links) {
  if (!links.length) return '';
  return `<div class="mt-2 flex flex-wrap gap-2">${links.map((link) => (
    `<a href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer" class="text-[11px] text-blue-300 hover:text-blue-200 underline underline-offset-2">${escapeHtml(link.label)}</a>`
  )).join('')}</div>`;
}

function renderClaudeUsageCard(claude) {
  const authLabel = claude?.auth?.logged_in
    ? `로그인됨${claude.auth.auth_method ? ` (${claude.auth.auth_method})` : ''}`
    : '로그인 확인 필요';
  const authTone = claude?.auth?.logged_in ? 'text-green-300' : 'text-yellow-300';
  const historical = claude?.historical_usage;
  const appUsage = claude?.app_usage;
  const usageCopy = buildClaudeUsageCopy();
  const topModels = (historical?.top_models || []).slice(0, 2).map((item) => item.model).filter(Boolean);
  const links = [
    { label: 'Claude status line', url: claude?.official?.docs_url || '' },
    { label: 'Claude 사용량 한도', url: claude?.official?.usage_limit_docs_url || '' },
  ].filter((item) => item.url);

  return `
    <div class="rounded-md border border-purple-900/60 bg-purple-950/20 p-2">
      <div class="flex items-center justify-between gap-2">
        <div class="text-gray-100 font-medium">Claude Code</div>
        <div class="text-[11px] ${claude?.available ? 'text-green-300' : 'text-red-300'}">${claude?.available ? 'CLI 감지' : 'CLI 없음'}</div>
      </div>
      <div class="mt-1 ${authTone}">${escapeHtml(authLabel)}</div>
      <div class="mt-1 text-gray-400">${escapeHtml(usageCopy.supportedLabel)}</div>
      <div class="mt-1 text-yellow-200">${escapeHtml(claude?.official?.availability_reason || '실시간 잔여 quota는 현재 미수집')}</div>
      <div class="mt-2 text-gray-400">
        ${escapeHtml(usageCopy.appUsageLabel)} ${formatInteger(appUsage?.total_calls)}회 · 입력 ${formatInteger(appUsage?.total_input_tokens)} · 출력 ${formatInteger(appUsage?.total_output_tokens)}
      </div>
      <div class="text-gray-500">${escapeHtml(usageCopy.appCostLabel)} ${formatUsd(appUsage?.total_cost_usd)}</div>
      ${historical?.available ? `
        <div class="mt-2 text-gray-400">${escapeHtml(usageCopy.historyLabel)} ${formatInteger(historical.total_sessions)}회 · 메시지 ${formatInteger(historical.total_messages)}건</div>
        <div class="text-gray-500">최근 모델: ${topModels.length ? escapeHtml(topModels.join(', ')) : '기록 없음'}</div>
      ` : '<div class="mt-2 text-gray-500">로컬 stats-cache가 없어 히스토리 사용량은 비어 있습니다.</div>'}
      ${renderProviderLinks(links)}
    </div>
  `;
}

function renderCodexUsageCard(codex) {
  const authLabel = buildCodexAuthLabel(codex);
  const usageCopy = buildCodexUsageCopy(codex);
  const links = [
    { label: 'Codex CLI 문서', url: codex?.official?.cli_docs_url || '' },
    { label: 'Codex 사용량 정책', url: codex?.official?.docs_url || '' },
  ].filter((item) => item.url);

  return `
    <div class="rounded-md border border-blue-900/60 bg-blue-950/20 p-2">
      <div class="flex items-center justify-between gap-2">
        <div class="text-gray-100 font-medium">Codex</div>
        <div class="text-[11px] ${codex?.available ? 'text-green-300' : 'text-red-300'}">${codex?.available ? 'CLI 감지' : 'CLI 없음'}</div>
      </div>
      <div class="mt-1 ${codex?.auth?.logged_in ? 'text-green-300' : 'text-yellow-300'}">${escapeHtml(authLabel)}</div>
      <div class="mt-1 text-gray-400">${escapeHtml(usageCopy.supportedLabel)}</div>
      <div class="mt-1 text-yellow-200">${escapeHtml(usageCopy.detail)}</div>
      <div class="mt-2 text-gray-500">${escapeHtml(usageCopy.unsupportedLabel)}</div>
      ${codex?.auth?.raw_status ? `<div class="mt-1 text-gray-600 break-all">${escapeHtml(codex.auth.raw_status)}</div>` : ''}
      ${renderProviderLinks(links)}
    </div>
  `;
}

function renderLLMUsage() {
  const panelEl = document.getElementById('llm-usage-panel');
  if (!panelEl) return;
  if (!llmUsageSnapshot) {
    panelEl.innerHTML = '<div class="text-gray-500">사용량 정보가 없습니다.</div>';
    return;
  }

  panelEl.innerHTML = `
    <div class="space-y-2">
      ${renderClaudeUsageCard(llmUsageSnapshot.claude_code)}
      ${renderCodexUsageCard(llmUsageSnapshot.codex)}
      <div class="text-[11px] text-gray-600">마지막 갱신: ${formatDateTime(llmUsageSnapshot.updated_at)}</div>
    </div>
  `;
}

function formatDetail(detail) {
  if (!detail) return '';
  try {
    const obj = typeof detail === 'string' ? JSON.parse(detail) : detail;
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(detail);
  }
}

function getTypeColor(type) {
  const map = {
    CYCLE: 'blue', SCAN: 'cyan', SCREENING: 'purple',
    TIER1_ANALYSIS: 'yellow', TIER2_REVIEW: 'green',
    STRATEGY_EVAL: 'blue', RISK_CHECK: 'yellow',
    RISK_TUNING: 'purple',
    DECISION: 'green', EVENT: 'gray', REPORT: 'purple',
    LLM_CALL: 'cyan', ORDER: 'red', DAILY_PLAN: 'purple',
    TRADE_RESULT: 'green', RISK_GATE: 'red',
  };
  return map[type] || 'gray';
}

function getTypeDotColor(type) {
  const map = {
    CYCLE: 'blue', SCAN: 'cyan', SCREENING: 'purple',
    TIER1_ANALYSIS: 'yellow', TIER2_REVIEW: 'green',
    STRATEGY_EVAL: 'blue', RISK_CHECK: 'yellow',
    RISK_TUNING: 'purple',
    DECISION: 'green', EVENT: 'gray', REPORT: 'purple',
    LLM_CALL: 'cyan', ORDER: 'red', DAILY_PLAN: 'purple',
    TRADE_RESULT: 'green', RISK_GATE: 'red',
  };
  return map[type] || 'gray';
}

function formatLLMConversation(detail) {
  let obj = detail;
  try {
    if (typeof detail === 'string') obj = JSON.parse(detail);
  } catch { return `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${escapeHtml(String(detail))}</pre>`; }
  const sys = obj.llm_system_prompt || '';
  const prompt = obj.llm_prompt || '';
  const response = obj.llm_response || '';
  const model = obj.llm_model || '';
  let html = '';
  if (model) html += `<div class="llm-model-tag">${escapeHtml(model)}</div>`;

  // System prompt: collapsed by default, show first 2 lines
  if (sys) {
    const sysId = 'sys-' + Math.random().toString(36).substr(2, 6);
    const lines = sys.split('\n');
    const preview = lines.slice(0, 2).join('\n');
    const hasMore = lines.length > 2;
    html += `<div class="llm-msg llm-system">
      <div class="llm-role">SYSTEM</div>
      <div class="llm-body" style="max-height:none">
        <span>${escapeHtml(preview)}${hasMore ? '...' : ''}</span>
        ${hasMore ? `
          <div id="${sysId}" style="display:none"><br>${escapeHtml(lines.slice(2).join('\n'))}</div>
          <button onclick="event.stopPropagation();var el=document.getElementById('${sysId}');var show=el.style.display==='none';el.style.display=show?'':'none';this.textContent=show?'접기':'시스템 프롬프트 전체 보기'" class="text-purple-400 hover:text-purple-300 text-xs mt-1 block">시스템 프롬프트 전체 보기</button>
        ` : ''}
      </div>
    </div>`;
  }

  if (prompt) html += `<div class="llm-msg llm-user"><div class="llm-role">PROMPT</div><div class="llm-body">${escapeHtml(prompt)}</div></div>`;

  // Response: try JSON formatting
  if (response) {
    let formattedResponse = escapeHtml(response);
    try {
      const parsed = JSON.parse(response);
      formattedResponse = '<pre class="whitespace-pre-wrap break-all">' + escapeHtml(JSON.stringify(parsed, null, 2)) + '</pre>';
    } catch {
      // not JSON, use plain text
    }
    html += `<div class="llm-msg llm-assistant"><div class="llm-role">RESPONSE</div><div class="llm-body">${formattedResponse}</div></div>`;
  }

  return `<div class="llm-conversation">${html}</div>`;
}

function getPhaseIcon(phase) {
  return { START: '▶', PROGRESS: '◆', COMPLETE: '✓', ERROR: '✗' }[phase] || '•';
}

function updateBadge(id, text, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  const colors = {
    gray: 'bg-gray-800 text-gray-300',
    green: 'bg-green-900/50 text-green-300',
    red: 'bg-red-900/50 text-red-300',
    yellow: 'bg-yellow-900/50 text-yellow-300',
    purple: 'bg-purple-900/50 text-purple-300',
    blue: 'bg-blue-900/50 text-blue-300',
  };
  el.className = `px-2 py-0.5 rounded text-xs font-medium ${colors[color] || colors.blue}`;
}

function setStatus(state, text) {
  const el = document.getElementById('status-text');
  if (el) el.textContent = text;
}

// Auto-scroll detection
document.getElementById('chat-container').addEventListener('scroll', function() {
  const el = this;
  autoScroll = (el.scrollHeight - el.scrollTop - el.clientHeight) < 50;
});

Object.assign(window, {
  applyCustomTierModel,
  askQuestion,
  clearChat,
  generateReport,
  loadLLMUsage,
  loadTodayActivities,
  refreshLLMCatalog,
  refreshRuntimePanels,
  reconcilePendingTrades,
  setAutonomyMode,
  setSchedulerRunning,
  setTradingEnabled,
  switchView,
  togglePaneCollapse,
  toggleSidebarSection,
  triggerCycle,
  updateSetting,
  updateTierModelSetting,
});
