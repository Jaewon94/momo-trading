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
  buildMarketSessionViewModel,
  buildRuntimeOperationsViewModel,
  buildRuntimeSettingCopy,
  formatAutonomyModeLabel,
  formatRiskAppetiteLabel,
  getMcpBadgeState,
} from './runtime_state.js';
import { SETTINGS_TABS, normalizeSettingsTab } from './settings_modal_state.js';
import { resolveDirectSettingChange } from './settings_action_state.js';
import { applySettingsToForm } from './settings_form_state.js';
import {
  getStandaloneModelSelectorState,
  getTierProviderElementId,
  resolveTierModelState,
  getTierModelSettingKey,
} from './settings_llm_state.js';
import {
  buildProviderModelEntries,
  buildProviderModelSourceText,
  getCatalogProvider,
  getProviderModelPlaceholder,
} from './settings_llm_catalog_state.js';
import {
  buildClaudeUsageCopy,
  buildCodexAuthLabel,
  buildCodexUsageCopy,
} from './llm_usage_state.js';
import {
  buildPortfolioQuickStatsModel,
  buildTradePanelState,
  buildTradeSummaryCounts,
} from './trade_state.js';
import { buildTradeCenterState } from './trade_center_state.js';
import {
  buildManualTradeSupportViewModel,
  buildManualTradeSymbolMap,
  buildPendingOrderAction,
  getImmediateSellAction,
} from './manual_trade_action_state.js';
import {
  buildActivityIdentityLabel,
  formatActivityHeadline,
  normalizeActivitySymbol,
  resolveActivityStockMeta,
} from './activity_state.js';
import { buildEventRadarState, buildTradeStageLabel } from './event_radar_state.js';
import { bindDetailToggleHandlers, buildDetailToggleMarkup } from './detail_toggle.js';
import { buildStrategyInsightsViewModel } from './strategy_insights_state.js';
import { buildCatalogErrorCopy, buildCatalogMetaText } from './llm_catalog_state.js';
import { buildPositionDetailState, groupPositionTimeline } from './position_detail_state.js';
import { buildReportActivityInsights } from './report_activity_state.js';
import { buildReportArchiveCardState } from './report_archive_state.js';
import { buildReportPerformanceState } from './report_performance_state.js';
import {
  buildNewsOverviewCards,
  buildNewsOverviewSourcePills,
  buildTradeBaselineNotice,
  buildReportNewsStripModel,
  buildManualNewsFetchState,
  describeManualNewsFetchResult,
  pickNewsDisplayFields,
} from './news_overview_state.js';
import { buildNewsArchiveCountSummary, buildNewsArchiveState } from './news_archive_state.js';
import { buildNewsPerformanceCards, buildNewsRolloutPolicy } from './news_performance_state.js';
import { buildObservabilityDashboardState } from './observability_state.js';
import { buildPerformanceDashboardState } from './performance_page_state.js';
import { buildReportNewsRationale } from './report_news_state.js';
import { buildTradeCardViewModel } from './trade_history_state.js';
import { resolveTradeExecutionState } from './trade_status_state.js';

const API = '/api/v1/admin';
let currentView = 'live';
let activityCount = 0;
let autoScroll = true;
let accountPollTimer = null;
let runtimeSettings = null;
let runtimeSystemStatus = null;
let newsOverviewSnapshot = null;
let llmUsageSnapshot = null;
let llmCatalog = null;
let runtimeControlPending = false;
let activeSettingsTab = 'operating';
let activePositionSymbol = null;
let activePositionDetailState = null;
let activePositionDetailPayload = null;
let activePositionTimelineFilter = 'all';
let positionTimelineLoadingMore = false;
let activeEventRadarFilter = 'all';
let activeEventRadarSymbol = '';
let eventRadarExpanded = false;
let activeTradeCenterTab = 'pending';
let activeTradeCenterSort = 'latest';
let activeTradeCenterQuery = '';
let tradeCenterVisibleCount = 20;
let latestAccountSnapshot = null;
let latestEventRadarState = null;
let newsArchiveFilters = null;
let activeNewsArchiveItem = null;
let lastManualNewsFetchState = null;
const TRADE_CENTER_PAGE_SIZE = 20;
const EVENT_RADAR_PANEL_KEY = 'momo:event-radar:expanded';
const knownStockNames = {};
const knownStockMeta = {};
let paneLayout = {
  leftWidth: PANE_DEFAULT_WIDTH.left,
  rightWidth: PANE_DEFAULT_WIDTH.right,
  leftCollapsed: false,
  rightCollapsed: false,
};
let activePaneResize = null;

// Stock card tracking: key = "cycleId:symbol" → { element, headerEl, bodyEl, stepsEl, activities[], outcome }
let stockCards = {};
let taskCards = {};
let taskCardSequence = {};
let latestTaskCardKeyByDescriptor = {};
let lastActivityGroupKey = null;

// Sidebar section state
const sidebarState = {
  account: false,
  holdings: false,
  pending: false,
  trades: false,
  settings: false,
  system: false,
};

const FETCH_TIMEOUT_MS = 12000;

async function fetchJson(url, options = {}, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload?.message || `HTTP ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new Error('요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.');
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

function getManualTradeSymbolMap() {
  return buildManualTradeSymbolMap({
    holdings: latestAccountSnapshot?.holdings || [],
    pendingOrders: latestAccountSnapshot?.pendingOrders || [],
    tradingEnabled: runtimeSettings?.TRADING_ENABLED !== false,
    runtimeSystemStatus,
  });
}

function renderManualActionButton(action, attrs = {}) {
  if (!action) return '';
  const dataAttrs = Object.entries(attrs)
    .map(([key, value]) => `data-${key}="${escapeHtml(String(value ?? ''))}"`)
    .join(' ');
  const titleText = action.reason || action.hint || '';
  const titleAttr = titleText ? `title="${escapeHtml(titleText)}"` : '';
  return `
    <button
      type="button"
      class="rounded-md border px-2 py-1 text-[11px] transition ${action.disabled
        ? 'border-gray-700 bg-dark-800 text-gray-500 cursor-not-allowed'
        : 'border-blue-500/50 bg-blue-500/10 text-blue-200 hover:border-blue-400 hover:text-white'}"
      ${dataAttrs}
      ${titleAttr}
      ${action.disabled ? 'disabled' : ''}
    >
      ${escapeHtml(action.label)}
    </button>
  `;
}

async function loadNewsOverview(force = false) {
  try {
    const json = await fetchJson(`${API}/news/overview?recent_limit=6&performance_days=30`);
    newsOverviewSnapshot = json?.data || null;
    renderSidebarSettingSummaries();
    renderNewsOverviewPanels();
    return newsOverviewSnapshot;
  } catch (err) {
    console.error('News overview load error:', err);
    if (force) {
      setStatus('error', `뉴스 인텔 로드 실패: ${err.message || '알 수 없는 오류'}`);
    }
    renderNewsOverviewPanels(err);
    return null;
  }
}

function renderNewsItemCards(items = [], { emptyLabel = '최근 적재 뉴스가 없습니다.', compact = false } = {}) {
  if (!Array.isArray(items) || !items.length) {
    return `<div class="text-xs text-gray-500">${escapeHtml(emptyLabel)}</div>`;
  }
  return items.map((item) => {
    const display = pickNewsDisplayFields(item);
    const symbols = Array.isArray(item.symbols) ? item.symbols.filter(Boolean) : [];
    const meta = [
      item.source_name || item.source_code || 'SOURCE',
      item.published_at ? formatDateTime(item.published_at) : '',
      symbols.length ? symbols.join(', ') : '',
    ].filter(Boolean).join(' · ');
    const subtitle = display.summary || '';
    const sentiment = item.sentiment_label
      ? `${item.sentiment_label} ${Number(item.sentiment_score || 0).toFixed(2)}`
      : `impact ${Number(item.impact_score || 0).toFixed(2)}`;
    return `
      <article class="news-item-card ${compact ? 'compact' : ''}">
        <div class="news-item-meta">${escapeHtml(meta)}</div>
        <div class="news-item-title">${escapeHtml(display.title || '-')}</div>
        ${subtitle ? `<div class="news-item-subtitle">${escapeHtml(subtitle)}</div>` : ''}
        ${display.hasTranslation && !compact ? `<div class="mt-2 text-[11px] text-slate-500">원문: ${escapeHtml(display.originalTitle)}</div>` : ''}
        <div class="news-item-badges">
          <span class="news-item-badge">${escapeHtml(item.source_tier || 'TIER')}</span>
          <span class="news-item-badge">${escapeHtml(sentiment)}</span>
          <span class="news-item-badge">신뢰 ${Number(item.trust_score || 0).toFixed(2)}</span>
        </div>
      </article>
    `;
  }).join('');
}

function renderNewsOverviewPanels(error = null) {
  const summaryEl = document.getElementById('news-overview-summary');
  const manualFetchEl = document.getElementById('news-manual-fetch-result');
  const performanceEl = document.getElementById('news-performance-cards');
  const rolloutEl = document.getElementById('news-rollout-policy');
  const sourcePillsEl = document.getElementById('news-source-pills');
  const listEl = document.getElementById('news-overview-list');
  if (!summaryEl || !sourcePillsEl || !listEl) return;

  if (error) {
    const message = error?.message || '알 수 없는 오류';
    summaryEl.innerHTML = `<div class="news-overview-card"><div class="news-overview-label">로드 실패</div><div class="news-overview-value text-red-300">ERR</div><div class="news-overview-help">${escapeHtml(message)}</div></div>`;
    if (manualFetchEl) manualFetchEl.innerHTML = '';
    if (performanceEl) performanceEl.innerHTML = '';
    if (rolloutEl) rolloutEl.innerHTML = `<div class="text-xs text-red-300">${escapeHtml(message)}</div>`;
    sourcePillsEl.innerHTML = '';
    listEl.innerHTML = `<div class="text-xs text-red-300">${escapeHtml(message)}</div>`;
    return;
  }

  const overview = newsOverviewSnapshot;
  if (!overview) {
    summaryEl.innerHTML = '<div class="news-overview-card"><div class="news-overview-label">뉴스 인텔</div><div class="news-overview-value">-</div><div class="news-overview-help">데이터를 불러오는 중...</div></div>';
    if (manualFetchEl) manualFetchEl.innerHTML = '';
    if (performanceEl) performanceEl.innerHTML = '';
    if (rolloutEl) rolloutEl.innerHTML = '<div class="text-xs text-gray-500">롤아웃 정책을 불러오는 중...</div>';
    sourcePillsEl.innerHTML = '';
    listEl.innerHTML = '<div class="text-xs text-gray-500">뉴스 인텔 데이터를 불러오는 중...</div>';
    return;
  }

  if (manualFetchEl) {
    if (!lastManualNewsFetchState) {
      manualFetchEl.innerHTML = '';
    } else {
      const toneClass = lastManualNewsFetchState.tone === 'success'
        ? 'border-emerald-700/50 bg-emerald-950/20'
        : (lastManualNewsFetchState.tone === 'muted'
          ? 'border-gray-700 bg-dark-900/50'
          : 'border-amber-700/50 bg-amber-950/20');
      manualFetchEl.innerHTML = `
        <div class="rounded-xl border ${toneClass} p-3">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">마지막 수동 수집 결과</div>
              <div class="mt-1 text-sm font-medium text-white">${escapeHtml(lastManualNewsFetchState.title)}</div>
              <div class="mt-1 text-xs text-gray-300">${escapeHtml(lastManualNewsFetchState.summary)}</div>
            </div>
            <div class="text-[11px] text-gray-500">${escapeHtml(lastManualNewsFetchState.fetchedAtLabel || '')}</div>
          </div>
          <div class="mt-3 grid grid-cols-4 gap-2 text-center text-[11px]">
            ${lastManualNewsFetchState.stats.map((item) => `
              <div class="rounded-lg border border-gray-700 bg-dark-900/55 px-2 py-2">
                <div class="text-gray-500">${escapeHtml(item.label)}</div>
                <div class="mt-1 text-white font-semibold">${escapeHtml(String(item.value))}</div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
  }

  const baselineNotice = buildTradeBaselineNotice(overview);
  const summaryCardsHtml = buildNewsOverviewCards(overview, {
    formatInteger,
    formatDateTime,
  }).map((card) => `
    <div class="news-overview-card">
      <div class="news-overview-label">${escapeHtml(card.label)}</div>
      <div class="news-overview-value">${escapeHtml(card.value)}</div>
      <div class="news-overview-help">${escapeHtml(card.help || '')}</div>
    </div>
  `).join('');

  summaryEl.innerHTML = `
    ${baselineNotice.active ? `
      <div class="col-span-full rounded-2xl border border-amber-700/50 bg-amber-950/20 px-4 py-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-[11px] uppercase tracking-[0.12em] text-amber-300">Trade Baseline</div>
            <div class="mt-1 text-sm font-medium text-white">${escapeHtml(baselineNotice.label || '기준선 리셋 이후 데이터')}</div>
            <div class="mt-1 text-xs text-gray-300">${escapeHtml(baselineNotice.summary)}</div>
          </div>
          <div class="rounded-full border border-amber-700/50 px-2.5 py-1 text-[10px] text-amber-200">${escapeHtml(baselineNotice.effectiveDate || '-')}</div>
        </div>
        ${baselineNotice.details.length ? `
          <div class="mt-2 space-y-1 text-[11px] leading-5 text-gray-400">
            ${baselineNotice.details.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
          </div>
        ` : ''}
      </div>
    ` : ''}
    ${summaryCardsHtml}
  `;

  sourcePillsEl.innerHTML = buildNewsOverviewSourcePills(overview)
    .map((pill) => pill.replaceAll(/>([^<]*)</g, (_match, text) => `>${escapeHtml(text)}<`))
    .join('');

  if (performanceEl) {
    performanceEl.innerHTML = buildNewsPerformanceCards(overview).map((card) => `
      <div class="news-overview-card">
        <div class="news-overview-label">${escapeHtml(card.label)}</div>
        <div class="news-overview-value">${escapeHtml(card.value)}</div>
        <div class="news-overview-help">${escapeHtml(card.help || '')}</div>
      </div>
    `).join('');
  }

  if (rolloutEl) {
    const rollout = buildNewsRolloutPolicy(overview);
    rolloutEl.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Rollout</div>
          <div class="mt-1 text-sm font-medium text-white">${escapeHtml(rollout.status)}</div>
        </div>
        <div class="rounded-full border border-gray-700 bg-dark-800/80 px-2.5 py-1 text-[11px] text-gray-300">${escapeHtml(rollout.status)}</div>
      </div>
      <div class="mt-2 text-sm text-gray-300">${escapeHtml(rollout.reason)}</div>
      <div class="mt-3 space-y-1 text-[11px] leading-5 text-gray-400">
        ${rollout.lines.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
      </div>
      ${rollout.details.length ? `
        <div class="mt-3 space-y-1 rounded-2xl border border-gray-700 bg-dark-900/40 px-3 py-3 text-[11px] leading-5 text-gray-300">
          ${rollout.details.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
        </div>
      ` : ''}
      ${rollout.checks.length ? `
        <div class="mt-3 grid gap-2 md:grid-cols-2">
          ${rollout.checks.map((item) => `
            <div class="rounded-2xl border px-3 py-2 ${item.passed ? 'border-emerald-700/60 bg-emerald-950/20' : 'border-amber-700/60 bg-amber-950/20'}">
              <div class="flex items-center justify-between gap-2">
                <div class="text-[11px] font-medium ${item.passed ? 'text-emerald-300' : 'text-amber-300'}">${escapeHtml(item.label)}</div>
                <div class="text-[10px] ${item.passed ? 'text-emerald-400' : 'text-amber-400'}">${item.passed ? '통과' : '확인 필요'}</div>
              </div>
              <div class="mt-1 text-[11px] text-white">${escapeHtml(item.actual)}</div>
              <div class="mt-1 text-[10px] text-gray-500">기준 ${escapeHtml(item.target)}</div>
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  }

  listEl.innerHTML = renderNewsItemCards(overview.recent_items || [], {
    emptyLabel: '최근 적재 뉴스가 없습니다.',
  });
}

async function fetchDartNews() {
  try {
    setStatus('runtime', 'OpenDART 공시 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/dart?days=1&page_count=50`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('OpenDART', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('OpenDART', json?.data || {}));
  } catch (err) {
    console.error('DART fetch error:', err);
    setStatus('error', `OpenDART 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchYonhapNews() {
  try {
    setStatus('runtime', '연합뉴스TV 경제 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/yonhap?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('연합뉴스TV', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('연합뉴스TV', json?.data || {}));
  } catch (err) {
    console.error('YONHAP fetch error:', err);
    setStatus('error', `연합뉴스TV 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchBloombergNews() {
  try {
    setStatus('runtime', 'Bloomberg 해외 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/bloomberg?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('Bloomberg', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('Bloomberg', json?.data || {}));
  } catch (err) {
    console.error('Bloomberg fetch error:', err);
    setStatus('error', `Bloomberg 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchCnbcNews() {
  try {
    setStatus('runtime', 'CNBC 해외 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/cnbc?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('CNBC', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('CNBC', json?.data || {}));
  } catch (err) {
    console.error('CNBC fetch error:', err);
    setStatus('error', `CNBC 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchNasdaqNews() {
  try {
    setStatus('runtime', 'Nasdaq 해외 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/nasdaq?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('Nasdaq', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('Nasdaq', json?.data || {}));
  } catch (err) {
    console.error('Nasdaq fetch error:', err);
    setStatus('error', `Nasdaq 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchInvestingNews() {
  try {
    setStatus('runtime', 'Investing.com 해외 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/investing?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('Investing.com', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('Investing.com', json?.data || {}));
  } catch (err) {
    console.error('Investing fetch error:', err);
    setStatus('error', `Investing.com 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchSeekingAlphaNews() {
  try {
    setStatus('runtime', 'Seeking Alpha 해외 뉴스 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/seeking-alpha?limit=30`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('Seeking Alpha', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('Seeking Alpha', json?.data || {}));
  } catch (err) {
    console.error('Seeking Alpha fetch error:', err);
    setStatus('error', `Seeking Alpha 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

async function fetchKrxNews() {
  try {
    setStatus('runtime', 'KIND 오늘의공시 수집 중...');
    const json = await fetchJson(`${API}/news/fetch/krx?page_count=50`, { method: 'POST' });
    lastManualNewsFetchState = buildManualNewsFetchState('KIND', json?.data || {}, formatDateTime(new Date().toISOString()));
    await loadNewsOverview(true);
    setStatus('runtime', describeManualNewsFetchResult('KIND', json?.data || {}));
  } catch (err) {
    console.error('KRX fetch error:', err);
    setStatus('error', `KIND 수집 실패: ${err.message || '알 수 없는 오류'}`);
  }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  bindDetailToggleHandlers(document);
  renderSettingsModal();
  loadPaneLayout();
  loadSettings();
  loadNewsOverview();
  loadLLMCatalog();
  loadSystemStatus();
  loadLLMUsage();
  loadReportList();
  loadAccountInfo();
  loadLLMStatus();
  loadEventRadar();
  loadEventRadarPanelState();
  applyEventRadarPanelState();
  connectSSE();
  loadTodayActivities();
  initSidebarSections();
  initWorkspaceLayout();
  setInterval(loadSystemStatus, 15000);
  setInterval(loadEventRadar, 15000);
  setInterval(loadLLMUsage, 60000);
  accountPollTimer = setInterval(loadAccountInfo, 30000);
  document.addEventListener('keydown', handleSettingsModalKeydown);
});

function loadEventRadarPanelState() {
  try {
    const raw = localStorage.getItem(EVENT_RADAR_PANEL_KEY);
    if (raw === null) {
      eventRadarExpanded = false;
      return;
    }
    eventRadarExpanded = raw === 'true';
  } catch {
    eventRadarExpanded = false;
  }
}

function saveEventRadarPanelState() {
  try {
    localStorage.setItem(EVENT_RADAR_PANEL_KEY, eventRadarExpanded ? 'true' : 'false');
  } catch {
    // no-op
  }
}

function applyEventRadarPanelState() {
  const shell = document.getElementById('event-radar-shell');
  const toggle = document.getElementById('event-radar-toggle');
  if (shell) {
    shell.classList.toggle('compact', !eventRadarExpanded);
  }
  if (toggle) {
    toggle.textContent = eventRadarExpanded ? '접기' : '펼치기';
  }
}

function toggleEventRadarPanel() {
  eventRadarExpanded = !eventRadarExpanded;
  saveEventRadarPanelState();
  applyEventRadarPanelState();
}

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

function openSettingsModal(tab = 'operating') {
  const overlay = document.getElementById('settings-modal-overlay');
  if (!overlay) return;
  activeSettingsTab = normalizeSettingsTab(tab);
  renderSettingsModal();
  overlay.classList.add('open');
  document.body.classList.add('overflow-hidden');
}

function closeSettingsModal() {
  const overlay = document.getElementById('settings-modal-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  document.body.classList.remove('overflow-hidden');
}

function closeSettingsModalOnBackdrop(event) {
  if (event.target?.id === 'settings-modal-overlay') {
    closeSettingsModal();
  }
}

function switchSettingsTab(tab) {
  activeSettingsTab = normalizeSettingsTab(tab);
  renderSettingsModal();
}

function renderSettingsModal() {
  SETTINGS_TABS.forEach((tab) => {
    document.getElementById(`settings-tab-${tab}`)?.classList.toggle('active', tab === activeSettingsTab);
    document.getElementById(`settings-panel-${tab}`)?.classList.toggle('active', tab === activeSettingsTab);
  });
}

function handleSettingsModalKeydown(event) {
  if (event.key === 'Escape') {
    const newsArchiveOverlay = document.getElementById('news-archive-detail-overlay');
    if (newsArchiveOverlay?.classList.contains('open')) {
      closeNewsArchiveDetailModal();
      return;
    }
    const positionOverlay = document.getElementById('position-detail-overlay');
    if (positionOverlay?.classList.contains('open')) {
      closePositionDetailModal();
      return;
    }
    closeSettingsModal();
  }
}

function openPositionDetailModalShell() {
  const overlay = document.getElementById('position-detail-overlay');
  if (!overlay) return;
  overlay.classList.add('open');
  document.body.classList.add('overflow-hidden');
}

function closePositionDetailModal() {
  const overlay = document.getElementById('position-detail-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  activePositionSymbol = null;
  activePositionDetailState = null;
  activePositionDetailPayload = null;
  document.body.classList.remove('overflow-hidden');
}

function closePositionDetailModalOnBackdrop(event) {
  if (event.target?.id === 'position-detail-overlay') {
    closePositionDetailModal();
  }
}

function openNewsArchiveDetailModal() {
  const overlay = document.getElementById('news-archive-detail-overlay');
  if (!overlay) return;
  overlay.classList.add('open');
  document.body.classList.add('overflow-hidden');
}

function closeNewsArchiveDetailModal() {
  const overlay = document.getElementById('news-archive-detail-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  activeNewsArchiveItem = null;
  document.body.classList.remove('overflow-hidden');
}

function closeNewsArchiveDetailOnBackdrop(event) {
  if (event.target?.id === 'news-archive-detail-overlay') {
    closeNewsArchiveDetailModal();
  }
}

function renderPositionDetailLoading(symbol) {
  const titleEl = document.getElementById('position-detail-title');
  const summaryEl = document.getElementById('position-detail-summary');
  const recentEventsEl = document.getElementById('position-detail-recent-events');
  const filterEl = document.getElementById('position-detail-timeline-filters');
  const timelineEl = document.getElementById('position-detail-timeline');
  if (titleEl) titleEl.textContent = `${symbol} 불러오는 중`;
  if (summaryEl) summaryEl.innerHTML = '<div class="text-sm text-gray-400">종목 요약을 불러오는 중...</div>';
  if (recentEventsEl) recentEventsEl.innerHTML = '';
  if (filterEl) filterEl.innerHTML = '';
  if (timelineEl) timelineEl.innerHTML = '<div class="text-sm text-gray-500">타임라인을 불러오는 중...</div>';
  positionTimelineLoadingMore = false;
}

function renderPositionDetailError(symbol, message) {
  const titleEl = document.getElementById('position-detail-title');
  const summaryEl = document.getElementById('position-detail-summary');
  const recentEventsEl = document.getElementById('position-detail-recent-events');
  const filterEl = document.getElementById('position-detail-timeline-filters');
  const timelineEl = document.getElementById('position-detail-timeline');
  if (titleEl) titleEl.textContent = `${symbol} 상세`;
  if (summaryEl) summaryEl.innerHTML = `<div class="text-sm text-red-300">${escapeHtml(message)}</div>`;
  if (recentEventsEl) recentEventsEl.innerHTML = '';
  if (filterEl) filterEl.innerHTML = '';
  if (timelineEl) timelineEl.innerHTML = '<div class="text-sm text-gray-500">다시 시도해 주세요.</div>';
  positionTimelineLoadingMore = false;
}

function openSettingsFromPositionDetail(tab) {
  closePositionDetailModal();
  openSettingsModal(tab);
}

function getPositionTimelineToneClass(entry) {
  switch (entry.tone) {
    case 'buy':
      return 'position-timeline-item tone-buy';
    case 'sell':
      return 'position-timeline-item tone-sell';
    case 'analysis':
      return 'position-timeline-item tone-analysis';
    case 'progress':
      return 'position-timeline-item tone-progress';
    case 'news':
      return 'position-timeline-item tone-news';
    case 'pending':
      return 'position-timeline-item tone-pending';
    case 'error':
      return 'position-timeline-item tone-error';
    default:
      return 'position-timeline-item tone-neutral';
  }
}

function renderPositionTimelineFilters(state) {
  const filterEl = document.getElementById('position-detail-timeline-filters');
  if (!filterEl) return;
  filterEl.innerHTML = state.timelineFilters.map((filter) => `
    <button
      type="button"
      class="position-timeline-filter-chip ${filter.key === activePositionTimelineFilter ? 'active' : ''}"
      data-position-timeline-filter="${escapeHtml(filter.key)}"
    >
      <span>${escapeHtml(filter.label)}</span>
      <span class="position-timeline-filter-count">${escapeHtml(String(filter.count))}</span>
    </button>
  `).join('');
}

function renderPositionTimelineGroups(state) {
  const timelineEl = document.getElementById('position-detail-timeline');
  if (!timelineEl) return;

  const groups = groupPositionTimeline(state.timelineEntries, activePositionTimelineFilter);
  if (!groups.length) {
    timelineEl.innerHTML = `
      <div class="rounded-2xl border border-dashed border-gray-700 bg-dark-900/30 px-4 py-5 text-sm text-gray-500">
        ${escapeHtml(state.emptyMessage)}
      </div>
    `;
    return;
  }

  const groupsMarkup = groups.map((group) => `
    <section class="position-timeline-group">
      <div class="position-timeline-date">
        <div class="position-timeline-date-label">${escapeHtml(group.dayLabel)}</div>
        <div class="position-timeline-date-stamp">${escapeHtml(group.dayStamp)}</div>
        ${group.relativeLabel ? `<div class="position-timeline-date-relative">${escapeHtml(group.relativeLabel)}</div>` : ''}
      </div>
      <div class="position-timeline-rail">
        ${group.entries.map((entry, index) => {
          const detailId = `position-timeline-detail-${escapeHtml(state.symbol)}-${escapeHtml(group.dayKey)}-${index}`;
          const detailMarkup = entry.detailLines?.length
            ? `
              ${buildDetailToggleMarkup({ detailId, muted: true })}
              <div id="${detailId}" class="detail-content">
                <div class="detail-content-inner">
                  <div class="mt-2 space-y-1 rounded-xl border border-white/5 bg-black/10 px-3 py-2 text-xs text-gray-400">
                    ${entry.detailLines.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
                  </div>
                </div>
              </div>
            `
            : '';
          return `
            <article class="${getPositionTimelineToneClass(entry)}">
              <div class="position-timeline-node">
                <div class="position-timeline-dot">${escapeHtml(entry.icon)}</div>
                ${index < group.entries.length - 1 ? '<div class="position-timeline-stem"></div>' : '<div class="position-timeline-stem position-timeline-stem-fade"></div>'}
              </div>
              <div class="position-timeline-card">
                <div class="position-timeline-card-topline">
                  <div class="position-timeline-time">${escapeHtml(entry.timeLabel || '--:--')}</div>
                  <div class="position-timeline-badge">${escapeHtml(entry.kindLabel)}</div>
                </div>
                <div class="position-timeline-title-row">
                  <div class="position-timeline-title">${escapeHtml(entry.title || '이벤트')}</div>
                  <div class="position-timeline-chip">${escapeHtml(entry.badge)}</div>
                </div>
                ${entry.summary ? `<div class="position-timeline-summary">${escapeHtml(entry.summary)}</div>` : ''}
                ${entry.meta ? `<div class="position-timeline-meta">${escapeHtml(entry.meta)}</div>` : ''}
                ${detailMarkup}
              </div>
            </article>
          `;
        }).join('')}
      </div>
    </section>
  `).join('');
  const loadMoreMarkup = state.timelinePage.hasMore ? `
    <div class="pt-2 flex justify-center">
      <button
        type="button"
        class="position-timeline-load-more ${positionTimelineLoadingMore ? 'is-loading' : ''}"
        data-position-timeline-load-more="true"
        ${positionTimelineLoadingMore ? 'disabled' : ''}
      >
        ${positionTimelineLoadingMore ? '이전 이력 불러오는 중...' : '이전 이력 더 보기'}
      </button>
    </div>
  ` : '';
  timelineEl.innerHTML = `${groupsMarkup}${loadMoreMarkup}`;
  bindDetailToggleHandlers(document);
}

function syncPositionTimelineView() {
  if (!activePositionDetailState) return;
  renderPositionTimelineFilters(activePositionDetailState);
  renderPositionTimelineGroups(activePositionDetailState);
}

function buildPositionManualActionMarkup(symbol) {
  const action = getImmediateSellAction(symbol, getManualTradeSymbolMap());
  const support = buildManualTradeSupportViewModel(runtimeSystemStatus);
  return `
    <section class="mb-3 rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-3">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Manual Action</div>
          <div class="mt-1 text-[11px] text-gray-500">${escapeHtml(support.summary)}</div>
          <div class="mt-1 text-sm text-gray-300">
            ${escapeHtml(action.disabled ? (action.reason || '즉시 매도 불가') : `${action.quantity || 0}주 전량 시장가 매도 가능`)}
          </div>
          ${action.hint && !action.disabled ? `<div class="mt-1 text-[11px] text-amber-300/90">${escapeHtml(action.hint)}</div>` : `<div class="mt-1 text-[11px] text-gray-500">${escapeHtml(support.detail)}</div>`}
        </div>
        ${renderManualActionButton(action, {
          'manual-action': action.kind,
          symbol,
        })}
      </div>
    </section>
  `;
}

function renderPositionDetailModal(payload) {
  const state = buildPositionDetailState(payload);
  activePositionDetailPayload = payload;
  activePositionDetailState = state;
  activePositionTimelineFilter = 'all';
  positionTimelineLoadingMore = false;
  const titleEl = document.getElementById('position-detail-title');
  const summaryEl = document.getElementById('position-detail-summary');
  const decisionEl = document.getElementById('position-detail-decision');
  const recentEventsEl = document.getElementById('position-detail-recent-events');
  const shortcutEl = document.getElementById('position-detail-settings-shortcut');
  if (titleEl) titleEl.textContent = state.title;
  if (shortcutEl) {
    shortcutEl.textContent = '관련 설정 열기';
    shortcutEl.onclick = () => openSettingsFromPositionDetail(state.settingsShortcutTab);
  }
  if (summaryEl) {
    summaryEl.innerHTML = `
      ${buildPositionManualActionMarkup(state.symbol)}
      ${state.summaryCards.map((card) => `
      <section class="position-summary-card tone-${escapeHtml(card.accent || 'neutral')}">
        <div class="position-summary-card-topline">
          <div>
            <div class="position-summary-card-eyebrow">${escapeHtml(card.eyebrow || card.title)}</div>
            <div class="position-summary-card-title">${escapeHtml(card.title)}</div>
          </div>
        </div>
        <div class="position-summary-card-hero">${escapeHtml(card.hero || '-')}</div>
        <div class="position-summary-card-hero-meta">${escapeHtml(card.heroMeta || '')}</div>
        <div class="position-summary-card-metrics">
          ${card.metrics.map((metric) => `
            <div class="position-summary-metric">
              <div class="position-summary-metric-label">${escapeHtml(metric.label)}</div>
              <div class="position-summary-metric-value">${escapeHtml(metric.value)}</div>
            </div>
          `).join('')}
        </div>
        <div class="position-summary-card-body">
          ${card.body.map((item) => `<div>${escapeHtml(item)}</div>`).join('')}
        </div>
        ${card.caption ? `<div class="position-summary-card-caption">${escapeHtml(card.caption)}</div>` : ''}
      </section>
    `).join('')}
    `;
  }
  if (decisionEl) {
    decisionEl.innerHTML = state.decisionInsight ? `
      <section class="position-decision-shell">
        <div class="position-decision-header">
          <div>
            <div class="position-summary-card-eyebrow">Decision Matrix</div>
            <div class="position-summary-card-title">차트 · 비용 · 뉴스 판단 근거</div>
          </div>
          <div class="position-decision-verdict">
            <div class="position-decision-hero">${escapeHtml(state.decisionInsight.hero)}</div>
            <div class="position-decision-meta">${escapeHtml(state.decisionInsight.heroMeta)}</div>
          </div>
        </div>
        <div class="position-summary-card-metrics mt-0">
          ${state.decisionInsight.metrics.map((metric) => `
            <div class="position-summary-metric">
              <div class="position-summary-metric-label">${escapeHtml(metric.label)}</div>
              <div class="position-summary-metric-value">${escapeHtml(metric.value)}</div>
            </div>
          `).join('')}
        </div>
        <div class="position-decision-grid">
          ${state.decisionInsight.cards.map((card) => `
            <section class="position-summary-card tone-${escapeHtml(card.accent || 'neutral')}">
              <div class="position-summary-card-eyebrow">${escapeHtml(card.title)}</div>
              <div class="position-summary-card-hero">${escapeHtml(card.hero || '-')}</div>
              <div class="position-summary-card-hero-meta">${escapeHtml(card.heroMeta || '')}</div>
              <div class="position-summary-card-metrics">
                ${card.metrics.map((metric) => `
                  <div class="position-summary-metric">
                    <div class="position-summary-metric-label">${escapeHtml(metric.label)}</div>
                    <div class="position-summary-metric-value">${escapeHtml(metric.value)}</div>
                  </div>
                `).join('')}
              </div>
              <div class="position-summary-card-body">
                ${card.body.map((item) => `<div>${escapeHtml(item)}</div>`).join('')}
              </div>
            </section>
          `).join('')}
        </div>
      </section>
    ` : '<div class="text-xs text-gray-500">의사결정 카드 데이터가 아직 없습니다.</div>';
  }
  if (recentEventsEl) {
    recentEventsEl.innerHTML = state.recentEventChips?.length
      ? state.recentEventChips.map((chip) => `
        <div class="position-recent-event-chip tone-${escapeHtml(chip.tone || 'buy')}">
          <div class="position-recent-event-chip-label">${escapeHtml(chip.label)}</div>
          <div class="position-recent-event-chip-meta">${escapeHtml(chip.meta)}</div>
        </div>
      `).join('')
      : '<div class="text-xs text-gray-500">최근 이벤트 없음</div>';
  }
  syncPositionTimelineView();
}

function mergePositionDetailState(baseState, payload) {
  const nextState = buildPositionDetailState(payload);
  return {
    ...nextState,
    timelineEntries: [...baseState.timelineEntries, ...nextState.timelineEntries],
    timelineFilters: nextState.timelineFilters.map((filter) => {
      if (filter.key === 'all') {
        return { ...filter, count: baseState.timelineEntries.length + nextState.timelineEntries.length };
      }
      const combinedCount = [...baseState.timelineEntries, ...nextState.timelineEntries]
        .filter((entry) => filter.key === 'all' || entry.filterKey === filter.key)
        .length;
      return { ...filter, count: combinedCount };
    }),
  };
}

async function fetchPositionDetail(symbol, offset = 0, limit = 20) {
  const resp = await fetch(`${API}/positions/${encodeURIComponent(symbol)}?timeline_offset=${offset}&timeline_limit=${limit}`);
  const json = await resp.json();
  if (!resp.ok || !json?.data) {
    throw new Error(json?.message || `HTTP ${resp.status}`);
  }
  return json.data;
}

async function openPositionDetailModal(symbol) {
  activePositionSymbol = symbol;
  activePositionDetailState = null;
  activePositionDetailPayload = null;
  activePositionTimelineFilter = 'all';
  openPositionDetailModalShell();
  renderPositionDetailLoading(symbol);
  try {
    const data = await fetchPositionDetail(symbol);
    if (activePositionSymbol !== symbol) return;
    renderPositionDetailModal(data);
  } catch (err) {
    if (activePositionSymbol !== symbol) return;
    console.error('position detail error:', err);
    renderPositionDetailError(symbol, err.message || '종목 상세 조회 실패');
  }
}

async function refreshPositionDetailModalIfOpen(symbol = '') {
  if (!activePositionSymbol) return;
  const normalizedActive = String(activePositionSymbol || '').replace(/^A/i, '');
  const normalizedTarget = String(symbol || '').replace(/^A/i, '');
  if (normalizedTarget && normalizedTarget !== normalizedActive) return;
  try {
    const data = await fetchPositionDetail(activePositionSymbol);
    if (data?.symbol === activePositionSymbol) {
      renderPositionDetailModal(data);
    }
  } catch (err) {
    console.error('position detail refresh error:', err);
  }
}

function filterEventRadarCards(cards, filterKey = 'all') {
  if (filterKey === 'all') return cards;
  if (filterKey === 'cooldown') {
    return cards.filter((card) => String(card.state || '').toUpperCase() === 'COOLDOWN');
  }
  return cards.filter((card) => card.tone === filterKey);
}

function buildTradeStageMap(snapshot = null) {
  const data = snapshot || latestAccountSnapshot || {};
  const map = {};
  const ensure = (symbol) => {
    if (!symbol) return;
    if (!map[symbol]) map[symbol] = "미진입";
  };

  const trades = data?.trades || {};
  const pendingOrders = Array.isArray(data?.pendingOrders) ? data.pendingOrders : [];
  const opened = Array.isArray(trades?.opened) ? trades.opened : [];
  const completed = Array.isArray(trades?.completed) ? trades.completed : [];
  const pendingConfirms = Array.isArray(trades?.pending_confirms) ? trades.pending_confirms : [];
  const openPositions = Array.isArray(trades?.open_positions) ? trades.open_positions : [];

  [...opened, ...completed, ...pendingConfirms, ...openPositions].forEach((item) => ensure(item?.stock_symbol));
  pendingOrders.forEach((item) => ensure(item?.symbol));
  Object.keys(map).forEach((symbol) => {
    map[symbol] = buildTradeStageLabel(data, symbol);
  });

  return map;
}

function buildLatestRadarBySymbol() {
  const cards = latestEventRadarState?.cards || [];
  const map = {};
  cards.forEach((card) => {
    const symbol = card?.symbol;
    if (!symbol || map[symbol]) return;
    map[symbol] = card;
  });
  return map;
}

function renderEventRadar(state) {
  const summaryEl = document.getElementById('event-radar-summary');
  const filtersEl = document.getElementById('event-radar-filters');
  const listEl = document.getElementById('event-radar-list');
  if (!summaryEl || !filtersEl || !listEl) return;

  summaryEl.innerHTML = state.summaryPills.map((pill) => `
    <div class="event-radar-summary-pill">
      <div class="event-radar-summary-label">${escapeHtml(pill.label)}</div>
      <div class="event-radar-summary-value">${escapeHtml(pill.value)}</div>
    </div>
  `).join('');

  filtersEl.innerHTML = state.filters.map((filter) => `
    <button
      type="button"
      class="event-radar-filter-chip ${filter.key === activeEventRadarFilter ? 'active' : ''}"
      data-event-radar-filter="${escapeHtml(filter.key)}"
    >
      <span>${escapeHtml(filter.label)}</span>
      <span class="event-radar-filter-count">${escapeHtml(String(filter.count))}</span>
    </button>
  `).join('');

  const tradeStageMap = buildTradeStageMap();
  const visibleCards = filterEventRadarCards(state.cards, activeEventRadarFilter);
  if (activeEventRadarSymbol) {
    visibleCards.sort((a, b) => {
      if (a.symbol === activeEventRadarSymbol && b.symbol !== activeEventRadarSymbol) return -1;
      if (a.symbol !== activeEventRadarSymbol && b.symbol === activeEventRadarSymbol) return 1;
      return 0;
    });
  }
  if (!visibleCards.length) {
    listEl.innerHTML = `<div class="event-radar-empty">${escapeHtml(state.emptyMessage)}</div>`;
    return;
  }

  listEl.innerHTML = visibleCards.map((card) => `
    <article class="event-radar-card tone-${escapeHtml(card.tone)} ${card.symbol === activeEventRadarSymbol ? 'is-focused' : ''}">
      <div>
        <div class="event-radar-eyebrow">${escapeHtml(card.event_type || 'EVENT')}</div>
        <div class="event-radar-title">${escapeHtml(card.title)}</div>
        <div class="event-radar-subtitle">${escapeHtml(card.subtitle)}</div>
        <div class="mt-2">
          <span class="event-radar-trade-badge">거래상태: ${escapeHtml(tradeStageMap[card.symbol] || '미진입')}</span>
        </div>
        <div class="event-radar-meta">
          ${escapeHtml(card.metaLine || card.reason || '')}
          ${card.metaLine && card.reason ? ' · ' : ''}
          ${escapeHtml(card.reason && card.metaLine ? '' : card.reason || '')}
        </div>
      </div>
      <div class="event-radar-side">
        <div class="event-radar-score">${escapeHtml(card.scoreLabel)}</div>
        <div class="event-radar-state">${escapeHtml(card.stateLabel)}</div>
        <div class="text-[11px] text-gray-500">${escapeHtml(card.occurredTimeLabel || '')}</div>
        ${card.cooldownLabel ? `<div class="event-radar-cooldown">${escapeHtml(card.cooldownLabel)}</div>` : ''}
        <button type="button" class="event-radar-link" data-radar-open-trade="${escapeHtml(card.symbol || '')}" data-radar-tone="${escapeHtml(card.tone || '')}">
          거래센터 보기
        </button>
      </div>
    </article>
  `).join('');
}

async function loadEventRadar() {
  const listEl = document.getElementById('event-radar-list');
  if (listEl && !listEl.dataset.loading) {
    listEl.dataset.loading = 'true';
  }
  try {
    const json = await fetchJson(`${API}/events/radar?limit=8`);
    const state = buildEventRadarState(json?.data || {});
    latestEventRadarState = state;
    renderEventRadar(state);
  } catch (err) {
    if (listEl) {
      listEl.innerHTML = `<div class="event-radar-empty">이벤트 레이더 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
    }
  } finally {
    if (listEl) delete listEl.dataset.loading;
  }
}

document.addEventListener('click', (event) => {
  const filterChip = event.target.closest('[data-event-radar-filter]');
  if (filterChip) {
    activeEventRadarFilter = filterChip.dataset.eventRadarFilter || 'all';
    activeEventRadarSymbol = '';
    loadEventRadar();
    return;
  }
});

document.addEventListener('click', (event) => {
  const link = event.target.closest('[data-radar-open-trade]');
  if (!link) return;
  const symbol = link.dataset.radarOpenTrade || '';
  const tone = link.dataset.radarTone || '';
  activeTradeCenterQuery = symbol;
  activeTradeCenterSort = 'latest';
  tradeCenterVisibleCount = TRADE_CENTER_PAGE_SIZE;
  if (tone === 'sell') activeTradeCenterTab = 'positions';
  else if (tone === 'buy') activeTradeCenterTab = 'opened';
  else activeTradeCenterTab = 'pending';
  switchView('trades-center');
});

document.addEventListener('click', (event) => {
  const tabButton = event.target.closest('[data-trade-center-tab]');
  if (!tabButton) return;
  activeTradeCenterTab = tabButton.dataset.tradeCenterTab || 'pending';
  tradeCenterVisibleCount = TRADE_CENTER_PAGE_SIZE;
  loadTradesCenterView();
});

document.addEventListener('click', async (event) => {
  const reconcileButton = event.target.closest('#trade-center-reconcile-button');
  if (!reconcileButton) return;
  await reconcilePendingTrades(reconcileButton);
  await loadAccountInfo();
  if (currentView === 'trades-center') {
    loadTradesCenterView();
  }
});

async function executeManualTradeAction(actionKind, { symbol = '', orderId = '' } = {}) {
  let url = '';
  let pendingMessage = '';
  let confirmMessage = '';

  if (actionKind === 'sell-now') {
    url = `${API}/account/holdings/${encodeURIComponent(symbol)}/sell`;
    pendingMessage = `${symbol} 즉시 매도 주문 접수 중...`;
    confirmMessage = `${symbol} 보유분을 전량 시장가로 매도합니다.\n\n시장가 주문도 일부 체결 후 잔량이 잠시 대기할 수 있습니다. 계속할까요?`;
  } else if (actionKind === 'cancel-buy') {
    url = `${API}/account/pending-orders/${encodeURIComponent(orderId)}/cancel-buy`;
    pendingMessage = `미체결 매수 주문 ${orderId} 취소 중...`;
    confirmMessage = `미체결 매수 주문 ${orderId}를 취소할까요?`;
  } else if (actionKind === 'cancel-and-sell') {
    url = `${API}/account/pending-orders/${encodeURIComponent(orderId)}/cancel-and-sell`;
    pendingMessage = `미체결 매도 주문 ${orderId} 취소 후 즉시 매도 접수 중...`;
    confirmMessage = `기존 매도 주문 ${orderId}를 취소하고 보유 수량을 시장가로 다시 매도할까요?\n\n시장가 재매도도 일부 체결 후 잔량이 잠시 대기할 수 있습니다.`;
  } else {
    return;
  }

  if (!window.confirm(confirmMessage)) {
    return;
  }

  setStatus('runtime', pendingMessage);
  const json = await fetchJson(url, { method: 'POST' });
  setStatus('runtime', json?.message || '주문 요청 완료');
  await loadAccountInfo();
  await refreshPositionDetailModalIfOpen(symbol || json?.data?.symbol || '');
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-manual-action]');
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  if (button.disabled) return;

  const actionKind = button.dataset.manualAction || '';
  const symbol = button.dataset.symbol || '';
  const orderId = button.dataset.orderId || '';

  try {
    await executeManualTradeAction(actionKind, { symbol, orderId });
  } catch (err) {
    console.error('manual trade action error:', err);
    setStatus('error', err.message || '수동 거래 액션 실패');
  }
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-trade-center-open-symbol]');
  if (!button) return;
  const symbol = button.dataset.tradeCenterOpenSymbol;
  if (symbol) openPositionDetailModal(symbol);
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-trade-open-radar]');
  if (!button) return;
  const symbol = button.dataset.tradeOpenRadar || '';
  if (!symbol) return;
  activeEventRadarSymbol = symbol;
  activeEventRadarFilter = 'all';
  eventRadarExpanded = true;
  saveEventRadarPanelState();
  applyEventRadarPanelState();
  switchView('live');
});

document.addEventListener('input', (event) => {
  const input = event.target.closest('#trade-center-search');
  if (!input) return;
  activeTradeCenterQuery = String(input.value || '').trim();
  tradeCenterVisibleCount = TRADE_CENTER_PAGE_SIZE;
  loadTradesCenterView();
});

document.addEventListener('change', (event) => {
  const directSettingChange = resolveDirectSettingChange(event.target);
  if (directSettingChange) {
    updateSetting(directSettingChange.key, directSettingChange.value);
    return;
  }

  const select = event.target.closest('#trade-center-sort');
  if (!select) return;
  activeTradeCenterSort = select.value || 'latest';
  tradeCenterVisibleCount = TRADE_CENTER_PAGE_SIZE;
  loadTradesCenterView();
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('#trade-center-load-more');
  if (!button) return;
  tradeCenterVisibleCount += TRADE_CENTER_PAGE_SIZE;
  loadTradesCenterView();
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-position-timeline-filter]');
  if (!button || !activePositionDetailState) return;
  activePositionTimelineFilter = button.dataset.positionTimelineFilter || 'all';
  syncPositionTimelineView();
});

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-position-timeline-load-more]');
  if (!button || !activePositionDetailState || !activePositionSymbol || positionTimelineLoadingMore) return;
  positionTimelineLoadingMore = true;
  syncPositionTimelineView();
  try {
    const data = await fetchPositionDetail(
      activePositionSymbol,
      activePositionDetailState.timelinePage.nextOffset,
      activePositionDetailState.timelinePage.limit,
    );
    if (!activePositionDetailState || activePositionSymbol !== data.symbol) return;
    activePositionDetailState = mergePositionDetailState(activePositionDetailState, data);
  } catch (err) {
    console.error('position detail pagination error:', err);
    setStatus('warn', err.message || '이전 이력 로드 실패');
  } finally {
    positionTimelineLoadingMore = false;
    syncPositionTimelineView();
  }
});

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
    latestAccountSnapshot = {
      balance: balJson?.data || null,
      holdings: holdJson?.data || [],
      pendingOrders: pendJson?.data || [],
      trades: tradeJson?.data || {},
    };
    primeKnownStockMeta(holdJson.data, tradeJson.data, pendJson.data);
    renderAccountBalance(balJson.data);
    renderAccountHoldings(holdJson.data);
    renderPendingOrders(pendJson.data);
    renderTodayTrades(tradeJson.data);
    renderPortfolioQuickStats(balJson.data, holdJson.data, pendJson.data, tradeJson.data);
    refreshStockCardActions();
    if (currentView === 'trades-center') {
      loadTradesCenterView(latestAccountSnapshot);
    }
  } catch (err) {
    console.error('Account info error:', err);
    const el = document.getElementById('account-info');
    if (el) el.innerHTML = '<div class="text-gray-600">조회 실패</div>';
  }
}

function primeKnownStockMeta(holdings = [], trades = {}, pendingOrders = []) {
  (holdings || []).forEach((holding) => {
    rememberStockMeta(holding.symbol, {
      stockName: holding.name,
      currentPrice: holding.current_price,
      pnlRate: holding.pnl_rate,
      quantity: holding.quantity,
    });
  });

  (pendingOrders || []).forEach((order) => {
    rememberStockMeta(order.symbol, {
      stockName: order.name,
      quantity: order.remaining_qty || order.order_qty,
    });
  });

  [
    ...(trades?.opened || []),
    ...(trades?.completed || []),
    ...(trades?.pending_confirms || []),
    ...(trades?.open_positions || []),
  ].forEach((trade) => {
    rememberStockMeta(trade.stock_symbol, {
      stockName: trade.stock_name,
      quantity: trade.quantity,
    });
  });

  refreshVisibleStockCards();
  refreshVisibleActivityMeta();
}

function refreshVisibleStockCards() {
  Object.values(stockCards).forEach((card) => {
    const meta = resolveActivityStockMeta({
      symbol: card.symbol,
      summary: '',
      detail: null,
      knownNames: knownStockNames,
      knownMeta: knownStockMeta,
    });
    if (meta.stockName) card.stockName = meta.stockName;
    if (meta.summaryText) card.summaryText = meta.summaryText;
    renderCardIdentity(card);
  });
}

function refreshVisibleActivityMeta() {
  document.querySelectorAll('.activity-stock-meta[data-activity-symbol]').forEach((el) => {
    const symbol = el.dataset.activitySymbol;
    if (!symbol) return;
    const meta = resolveActivityStockMeta({
      symbol,
      summary: '',
      detail: null,
      knownNames: knownStockNames,
      knownMeta: knownStockMeta,
    });
    const identityLabel = buildActivityIdentityLabel(meta);
    if (identityLabel) {
      el.textContent = identityLabel;
      el.classList.remove('hidden');
    }
  });

  document.querySelectorAll('.activity-headline[data-activity-symbol]').forEach((el) => {
    const symbol = el.dataset.activitySymbol;
    if (!symbol) return;
    const summary = el.dataset.activitySummary || '';
    const detail = el.dataset.activityDetail || null;
    const meta = resolveActivityStockMeta({
      symbol,
      summary,
      detail,
      knownNames: knownStockNames,
      knownMeta: knownStockMeta,
    });
    el.textContent = formatActivityHeadline(summary, meta);
  });
}

function renderAccountBalance(data) {
  const el = document.getElementById('account-info');
  if (!el || !data) {
    if (el) el.innerHTML = '<div class="account-balance-empty">계좌 미연결</div>';
    return;
  }
  const stats = buildPortfolioQuickStatsModel(data, latestAccountSnapshot?.holdings, latestAccountSnapshot?.pendingOrders, latestAccountSnapshot?.trades);
  const cashRatio = Number.isFinite(stats.cashRatio) ? stats.cashRatio.toFixed(1) : '0.0';
  const stockRatio = Number.isFinite(100 - stats.cashRatio) ? (100 - stats.cashRatio).toFixed(1) : '0.0';
  el.innerHTML = `
    <div class="account-balance-bar">
      <div class="account-balance-bar-fill cash" style="width:${Math.max(0, Math.min(100, stats.cashRatio))}%"></div>
      <div class="account-balance-bar-fill stock" style="width:${Math.max(0, Math.min(100, 100 - stats.cashRatio))}%"></div>
    </div>
    <div class="account-balance-legend">
      <div class="account-balance-legend-item">
        <div class="account-balance-legend-label">
          <span class="account-balance-dot cash"></span>
          현금
        </div>
        <div class="account-balance-legend-value">${formatKRW(stats.cash)}</div>
        <div class="account-balance-legend-meta">${cashRatio}%</div>
      </div>
      <div class="account-balance-legend-item">
        <div class="account-balance-legend-label">
          <span class="account-balance-dot stock"></span>
          주식 평가액
        </div>
        <div class="account-balance-value">${formatKRW(stats.stockValue)}</div>
        <div class="account-balance-legend-meta">${stockRatio}%</div>
      </div>
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
    return `<button type="button" onclick="openPositionDetailModal('${escapeHtml(h.symbol)}')" class="w-full text-left border border-gray-700 rounded p-1.5 space-y-0.5 ${bgTint} hover:border-blue-500/60 transition">
      <div class="flex justify-between items-center">
        <span class="text-gray-200 font-medium truncate" title="${escapeHtml(h.symbol)}">${escapeHtml(h.name)}</span>
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
    </button>`;
  }).join('');
}

function renderPendingOrders(data) {
  const el = document.getElementById('pending-orders-info');
  const countEl = document.getElementById('pending-count');
  if (!el) return;
  if (!data || !data.length) {
    if (countEl) countEl.textContent = '0';
    el.innerHTML = '<div class="text-gray-600 text-xs">미체결 주문 없음</div>';
    return;
  }
  if (countEl) {
    countEl.textContent = `${data.length}`;
  }
  const symbolMap = getManualTradeSymbolMap();
  const support = buildManualTradeSupportViewModel(runtimeSystemStatus);
  el.innerHTML = data.map(o => {
    const sideColor = o.side === '매수' ? 'text-red-400' : 'text-blue-400';
    const borderColor = o.side === '매수' ? 'border-yellow-700/60' : 'border-yellow-700/60';
    const isMarketOrder = Number(o.order_price || 0) <= 0;
    const orderAmt = isMarketOrder ? null : o.order_price * o.remaining_qty;
    const timeStr = o.order_time ? o.order_time.slice(0,2) + ':' + o.order_time.slice(2,4) + ':' + o.order_time.slice(4,6) : '';
    const action = buildPendingOrderAction(o, symbolMap);
    return `<div class="border ${borderColor} bg-yellow-900/10 rounded p-1.5 space-y-0.5">
      <div class="flex justify-between items-center">
        <span class="text-gray-200 font-medium truncate" title="${o.symbol}">${o.name}</span>
        <span class="${sideColor} font-medium text-xs px-1.5 py-0.5 rounded ${o.side === '매수' ? 'bg-red-900/30' : 'bg-blue-900/30'}">${o.side}</span>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>미체결 ${o.remaining_qty}주 / ${o.order_qty}주</span>
        <span>${isMarketOrder ? '시장가' : `${Number(o.order_price).toLocaleString()}원`}</span>
      </div>
      <div class="flex justify-between text-gray-500">
        <span>${isMarketOrder ? '예상금액 계산 대기' : formatKRW(orderAmt)}</span>
        <span>${timeStr}</span>
      </div>
      <div class="flex items-center justify-between gap-2 pt-1">
        <button
          type="button"
          class="text-[11px] text-gray-400 hover:text-gray-200 transition"
          data-trade-center-open-symbol="${escapeHtml(o.symbol || '')}"
        >
          상세 보기
        </button>
        ${renderManualActionButton(action, {
          'manual-action': action.kind,
          'order-id': o.order_id || '',
          symbol: o.symbol || '',
        })}
      </div>
      ${action.disabled ? `<div class="text-[10px] text-gray-500 pt-1">${escapeHtml(support.summary)}</div>` : ''}
    </div>`;
  }).join('');
}

function renderPortfolioQuickStats(balance, holdings, pendingOrders, trades) {
  const el = document.getElementById('portfolio-quick-stats');
  if (!el) return;

  const stats = buildPortfolioQuickStatsModel(balance, holdings, pendingOrders, trades);
  const unrealizedLabel = `${stats.unrealizedPnl >= 0 ? '+' : ''}${formatKRW(stats.unrealizedPnl)}`;
  const unrealizedClass = stats.unrealizedPnl >= 0 ? 'is-positive' : 'is-negative';
  const realizedLabel = `${stats.realizedTodayPnl >= 0 ? '+' : ''}${formatKRW(stats.realizedTodayPnl)}`;
  const realizedClass = stats.realizedTodayPnl >= 0 ? 'is-positive' : 'is-negative';
  const realizedMeta = stats.unmatchedSellExecutions > 0
    ? `매도 체결 ${stats.sellExecutionCount}건 · 손익 반영 대기 ${stats.unmatchedSellExecutions}건`
    : `오늘 청산 ${stats.completedCount}건`;

  el.innerHTML = `
    <div class="portfolio-stat portfolio-stat-hero">
      <div class="portfolio-stat-label">총자산</div>
      <div class="portfolio-stat-value">${formatKRW(stats.totalAsset)}</div>
      <div class="portfolio-stat-meta">현재 계좌 기준 · 현금 ${formatKRW(stats.cash)} · 주식 ${formatKRW(stats.stockValue)}</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">보유 평가손익</div>
      <div class="portfolio-stat-value ${unrealizedClass}">${unrealizedLabel}</div>
      <div class="portfolio-stat-meta">현재 들고 있는 종목 기준 · ${Number.isFinite(stats.unrealizedPnlRate) ? `${stats.unrealizedPnlRate >= 0 ? '+' : ''}${stats.unrealizedPnlRate.toFixed(2)}%` : '-'}</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">당일 실현손익</div>
      <div class="portfolio-stat-value ${realizedClass}">${realizedLabel}</div>
      <div class="portfolio-stat-meta">오늘 청산 완료 기준 · ${realizedMeta}</div>
    </div>
    <div class="portfolio-stat">
      <div class="portfolio-stat-label">포지션 / 미체결</div>
      <div class="portfolio-stat-value">${stats.holdingCount} / ${stats.pendingCount}</div>
      <div class="portfolio-stat-meta">오늘 진입 ${stats.openedCount}건</div>
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
    sellExecutions,
    completed,
    pendingConfirms,
    openPositions,
    todayCount,
    hasContent,
  } = state;
  const holdings = Array.isArray(latestAccountSnapshot?.holdings) ? latestAccountSnapshot.holdings : [];
  const currentHoldingCount = holdings.length
    || new Set(openPositions.map((item) => item.stock_symbol).filter(Boolean)).size;

  if (countEl) countEl.textContent = String(todayCount);

  if (!hasContent) {
    el.innerHTML = '<div class="text-gray-600 text-xs">오늘 거래 없음 · 거래 센터에서 상세 확인</div>';
    return;
  }

  el.innerHTML = `
    <div class="trade-mini-card">
      <div class="flex items-center justify-between">
        <span class="text-gray-400">오늘 진입</span>
        <span class="text-blue-300 font-semibold">${opened.length}건</span>
      </div>
      <div class="flex items-center justify-between mt-1">
        <span class="text-gray-400">매도 체결</span>
        <span class="text-green-300 font-semibold">${sellExecutions.length}건</span>
      </div>
      <div class="flex items-center justify-between mt-1">
        <span class="text-gray-400">전량 매도 완료</span>
        <span class="text-green-300 font-semibold">${completed.length}건</span>
      </div>
      <div class="flex items-center justify-between mt-1">
        <span class="text-gray-400">체결 확인 대기</span>
        <span class="text-yellow-300 font-semibold">${pendingConfirms.length}건</span>
      </div>
      <div class="flex items-center justify-between mt-1">
        <span class="text-gray-400">현재 보유</span>
        <span class="text-purple-300 font-semibold">${currentHoldingCount}종목</span>
      </div>
      <div class="text-[11px] text-gray-500 mt-2">상세 목록은 거래 센터에서 확인</div>
    </div>
  `;
}

async function fetchTradeCenterSnapshot() {
  const [balJson, holdJson, pendJson, tradeJson] = await Promise.all([
    fetchJson(`${API}/account/balance`),
    fetchJson(`${API}/account/holdings`),
    fetchJson(`${API}/account/pending-orders`),
    fetchJson(`${API}/trades`),
  ]);

  return {
    balance: balJson?.data || null,
    holdings: holdJson?.data || [],
    pendingOrders: pendJson?.data || [],
    trades: tradeJson?.data || {},
  };
}

function renderTradeCenterCard(item, kind, radarEvent = null) {
  const radarMeta = radarEvent
    ? `<div class="trade-center-card-meta">신호: ${escapeHtml(radarEvent.subtitle || radarEvent.event_label || radarEvent.event_type || 'EVENT')} · ${escapeHtml(radarEvent.occurredTimeLabel || '')}</div>`
    : '';

  if (kind === 'pending-confirm') {
    return `
      <button type="button" class="trade-center-card tone-pending" data-trade-center-open-symbol="${escapeHtml(item.stock_symbol || '')}">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(item.stock_name || item.stock_symbol || '-')}</div>
          <div class="text-xs text-yellow-300">체결 확인 대기</div>
        </div>
        <div class="trade-center-card-meta">${escapeHtml(item.stock_symbol || '-')} · ${escapeHtml(String(item.quantity || 0))}주</div>
        ${radarMeta}
      </button>
    `;
  }

  if (kind === 'pending-order') {
    const action = buildPendingOrderAction(item, getManualTradeSymbolMap());
    return `
      <div class="trade-center-card tone-pending">
        <button type="button" class="w-full text-left" data-trade-center-open-symbol="${escapeHtml(item.symbol || '')}">
          <div class="flex items-center justify-between gap-2">
            <div class="text-sm font-medium text-white truncate">${escapeHtml(item.name || item.symbol || '-')}</div>
            <div class="text-xs text-yellow-300">${escapeHtml(item.side || '-')}</div>
          </div>
          <div class="trade-center-card-meta">${escapeHtml(item.symbol || '-')} · 미체결 ${escapeHtml(String(item.remaining_qty || 0))}주 / ${escapeHtml(String(item.order_qty || 0))}주</div>
          ${radarMeta}
        </button>
        <div class="mt-3 flex items-center justify-end">
          ${renderManualActionButton(action, {
            'manual-action': action.kind,
            'order-id': item.order_id || '',
            symbol: item.symbol || '',
          })}
        </div>
      </div>
    `;
  }

  if (kind === 'opened') {
    return `
      <button type="button" class="trade-center-card tone-opened" data-trade-center-open-symbol="${escapeHtml(item.stock_symbol || '')}">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(item.stock_name || item.stock_symbol || '-')}</div>
          <div class="text-xs text-blue-300">${escapeHtml(String(item.quantity || 0))}주</div>
        </div>
        <div class="trade-center-card-meta">${escapeHtml(item.stock_symbol || '-')} · 진입가 ${Number(item.entry_price || 0).toLocaleString()}원</div>
        ${radarMeta}
      </button>
    `;
  }

  if (kind === 'sell-executions') {
    return `
      <button type="button" class="trade-center-card tone-completed-win" data-trade-center-open-symbol="${escapeHtml(item.stock_symbol || '')}">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(item.stock_name || item.stock_symbol || '-')}</div>
          <div class="text-xs text-green-300">매도 체결</div>
        </div>
        <div class="trade-center-card-meta">${escapeHtml(item.stock_symbol || '-')} · ${escapeHtml(String(item.quantity || 0))}주</div>
        ${radarMeta}
      </button>
    `;
  }

  if (kind === 'completed') {
    const pnl = Number(item.pnl || 0);
    const tone = pnl >= 0 ? 'tone-completed-win' : 'tone-completed-loss';
    const pnlClass = pnl >= 0 ? 'text-green-300' : 'text-red-300';
    return `
      <button type="button" class="trade-center-card ${tone}" data-trade-center-open-symbol="${escapeHtml(item.stock_symbol || '')}">
        <div class="flex items-center justify-between gap-2">
          <div class="text-sm font-medium text-white truncate">${escapeHtml(item.stock_name || item.stock_symbol || '-')}</div>
          <div class="text-sm font-semibold ${pnlClass}">${pnl >= 0 ? '+' : ''}${formatKRW(pnl)}</div>
        </div>
        <div class="trade-center-card-meta">${escapeHtml(item.stock_symbol || '-')} · ${Number(item.return_pct || 0).toFixed(2)}%</div>
        ${radarMeta}
      </button>
    `;
  }

  return `
    <button type="button" class="trade-center-card tone-position" data-trade-center-open-symbol="${escapeHtml(item.symbol || '')}">
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm font-medium text-white truncate">${escapeHtml(item.name || item.symbol || '-')}</div>
        <div class="text-xs text-purple-300">${escapeHtml(String(item.quantity || 0))}주</div>
      </div>
      <div class="trade-center-card-meta">
        ${escapeHtml(item.symbol || '-')} · 평단 ${Number(item.avgPrice || 0).toLocaleString()}원 · 손익 ${Number(item.pnl || 0) >= 0 ? '+' : ''}${formatKRW(Number(item.pnl || 0))}
      </div>
      ${radarMeta}
    </button>
  `;
}

function buildTradeCenterRows(state, tabKey) {
  const section = state.sections[tabKey];
  if (!section) return [];

  if (tabKey === 'pending') {
    return [
      ...section.pendingConfirms.map((item) => ({
        kind: 'pending-confirm',
        item,
        symbol: item?.stock_symbol || '',
        name: item?.stock_name || item?.stock_symbol || '',
        time: item?.entry_at || item?.created_at || null,
        pnl: 0,
      })),
      ...section.pendingOrders.map((item) => ({
        kind: 'pending-order',
        item,
        symbol: item?.symbol || '',
        name: item?.name || item?.symbol || '',
        time: item?.order_time || null,
        pnl: 0,
      })),
    ];
  }

  if (tabKey === 'opened') {
    return section.map((item) => ({
      kind: 'opened',
      item,
      symbol: item?.stock_symbol || '',
      name: item?.stock_name || item?.stock_symbol || '',
      time: item?.entry_at || item?.created_at || null,
      pnl: 0,
    }));
  }

  if (tabKey === 'sell-executions') {
    return section.map((item) => ({
      kind: 'sell-executions',
      item,
      symbol: item?.stock_symbol || '',
      name: item?.stock_name || item?.stock_symbol || '',
      time: item?.exit_at || item?.updated_at || item?.created_at || null,
      pnl: toNumber(item?.pnl),
    }));
  }

  if (tabKey === 'completed') {
    return section.map((item) => ({
      kind: 'completed',
      item,
      symbol: item?.stock_symbol || '',
      name: item?.stock_name || item?.stock_symbol || '',
      time: item?.exit_at || item?.updated_at || item?.created_at || null,
      pnl: toNumber(item?.pnl),
    }));
  }

  return section.map((item) => ({
    kind: 'positions',
    item,
    symbol: item?.symbol || '',
    name: item?.name || item?.symbol || '',
    time: null,
    pnl: toNumber(item?.pnl),
  }));
}

function compareTradeCenterRows(a, b, sortKey) {
  if (sortKey === 'name') {
    return String(a.name || '').localeCompare(String(b.name || ''), 'ko');
  }
  if (sortKey === 'pnl-desc') {
    return toNumber(b.pnl) - toNumber(a.pnl);
  }
  if (sortKey === 'pnl-asc') {
    return toNumber(a.pnl) - toNumber(b.pnl);
  }
  const parseTime = (value) => {
    if (!value) return 0;
    const text = String(value);
    if (/^\d{6}$/.test(text)) {
      const hh = Number(text.slice(0, 2));
      const mm = Number(text.slice(2, 4));
      const ss = Number(text.slice(4, 6));
      return ((hh * 60 + mm) * 60 + ss) * 1000;
    }
    const ts = new Date(text).getTime();
    return Number.isFinite(ts) ? ts : 0;
  };
  const at = parseTime(a.time);
  const bt = parseTime(b.time);
  return bt - at;
}

function renderTradeCenterSection(state, tabKey) {
  const rawRows = buildTradeCenterRows(state, tabKey);
  const radarBySymbol = buildLatestRadarBySymbol();
  const query = activeTradeCenterQuery.toLowerCase();
  const filteredRows = rawRows.filter((row) => {
    if (!query) return true;
    return [row.symbol, row.name].some((value) => String(value || '').toLowerCase().includes(query));
  });

  filteredRows.sort((a, b) => compareTradeCenterRows(a, b, activeTradeCenterSort));
  const visibleRows = filteredRows.slice(0, tradeCenterVisibleCount);

  const emptyText = (
    tabKey === 'pending'
      ? '대기 중인 거래가 없습니다.'
      : tabKey === 'opened'
        ? '오늘 진입 거래가 없습니다.'
        : tabKey === 'sell-executions'
          ? '오늘 매도 체결이 없습니다.'
        : tabKey === 'completed'
          ? '전량 매도 완료 거래가 없습니다.'
          : '현재 보유 포지션이 없습니다.'
  );

  const listMarkup = visibleRows.length
    ? `<div class="trade-center-list">${visibleRows.map((row) => renderTradeCenterCard(row.item, row.kind, radarBySymbol[row.symbol] || null)).join('')}</div>`
    : `<div class="trade-center-empty">${emptyText}</div>`;

  const loadMoreMarkup = filteredRows.length > visibleRows.length
    ? `
      <div class="pt-2 flex justify-center">
        <button type="button" id="trade-center-load-more" class="trade-center-load-more">
          더 보기 (${visibleRows.length}/${filteredRows.length})
        </button>
      </div>
    `
    : '';

  return {
    html: `${listMarkup}${loadMoreMarkup}`,
    total: filteredRows.length,
    visible: visibleRows.length,
  };
}

async function loadTradesCenterView(snapshot = null) {
  const container = document.getElementById('chat-container');
  if (!container) return;
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">거래 센터 불러오는 중...</div>';
  cleanupStockCards();

  try {
    const data = snapshot || latestAccountSnapshot || await fetchTradeCenterSnapshot();
    latestAccountSnapshot = data;
    const state = buildTradeCenterState(data);
    const tabKeys = state.tabs.map((tab) => tab.key);
    if (!tabKeys.includes(activeTradeCenterTab)) {
      activeTradeCenterTab = state.tabs[0]?.key || 'pending';
    }

    const activeTabLabel = state.tabs.find((tab) => tab.key === activeTradeCenterTab)?.label || '';
    const section = renderTradeCenterSection(state, activeTradeCenterTab);
    container.innerHTML = `
      <div class="mx-2 rounded-xl border border-gray-700 bg-dark-700/80 p-4 chat-bubble">
        <div class="text-lg font-bold text-white">📂 거래 센터</div>
        <div class="text-xs text-gray-500 mt-1">요약은 우측 사이드바, 상세 추적/점검은 여기서 처리합니다.</div>
        <div class="trade-center-kpi-grid mt-3">
          ${state.kpis.map((kpi) => `
            <div class="trade-center-kpi">
              <div class="trade-center-kpi-label">${escapeHtml(kpi.label)}</div>
              <div class="trade-center-kpi-value">${escapeHtml(String(kpi.value))}</div>
            </div>
          `).join('')}
        </div>
        <div class="trade-center-tabs">
          ${state.tabs.map((tab) => `
            <button type="button" class="trade-center-tab ${tab.key === activeTradeCenterTab ? 'active' : ''}" data-trade-center-tab="${escapeHtml(tab.key)}">
              ${escapeHtml(tab.label)} (${escapeHtml(String(tab.count))})
            </button>
          `).join('')}
        </div>
        <div class="trade-center-controls">
          <input id="trade-center-search" class="trade-center-search" placeholder="종목명/코드 검색" value="${escapeHtml(activeTradeCenterQuery)}" />
          <select id="trade-center-sort" class="trade-center-sort">
            <option value="latest" ${activeTradeCenterSort === 'latest' ? 'selected' : ''}>최신순</option>
            <option value="name" ${activeTradeCenterSort === 'name' ? 'selected' : ''}>종목명순</option>
            <option value="pnl-desc" ${activeTradeCenterSort === 'pnl-desc' ? 'selected' : ''}>손익 높은순</option>
            <option value="pnl-asc" ${activeTradeCenterSort === 'pnl-asc' ? 'selected' : ''}>손익 낮은순</option>
          </select>
        </div>
        <div class="trade-center-toolbar">
          <button type="button" id="trade-center-reconcile-button" class="trade-center-action">확인 대기 복구</button>
        </div>
        <div class="text-xs text-gray-500 mt-2">현재 탭: ${escapeHtml(activeTabLabel)} · 표시 ${section.visible}/${section.total}</div>
      </div>
      <div class="mx-2 mt-3">
        ${section.html}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">거래 센터 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

function renderCompactTradeCard(trade, type) {
  const isCompleted = type === 'completed';
  const isPending = type === 'pending';
  const executionState = resolveTradeExecutionState({
    side: trade?.side || 'BUY',
    status: trade?.status || (isPending ? 'PENDING_CONFIRM' : 'CONFIRMED'),
    notes: trade?.notes,
    hasExit: isCompleted,
  });
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
          <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time} · ${escapeHtml(executionState.shortLabel)}</div>
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
          <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time} · ${escapeHtml(executionState.shortLabel)}</div>
        </div>
        <div class="text-right text-yellow-300">
          <div class="font-semibold">${trade.quantity}주</div>
          <div class="text-[11px]">${escapeHtml(executionState.label)}</div>
        </div>
      </div>
    </div>`;
  }

  return `<div class="trade-mini-card opened">
    <div class="flex items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="text-gray-100 font-medium truncate">${trade.stock_name}</div>
        <div class="text-[11px] text-gray-500">${trade.stock_symbol} · ${time} · ${escapeHtml(executionState.shortLabel)}</div>
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

  const normalizedSymbol = normalizeActivitySymbol(data.symbol);
  const activity = normalizedSymbol && normalizedSymbol !== data.symbol
    ? { ...data, symbol: normalizedSymbol }
    : data;
  const symbol = activity.symbol;
  const isCycleActivity = activity.activity_type === 'CYCLE';
  const isDailyPlan = activity.activity_type === 'DAILY_PLAN';
  const isTaskActivity = !symbol && !isCycleActivity;

  // Non-symbol activities → inline (cycle dividers, daily plan, events without symbol)
  if (isCycleActivity) {
    if (isCycleActivity && activity.phase === 'START') {
      const divider = createCycleDivider(activity, true);
      container.appendChild(divider);
    } else if (isCycleActivity && (activity.phase === 'COMPLETE' || activity.phase === 'ERROR')) {
      // Remove matching START divider spinner
      const startKey = `cycle-start-${activity.cycle_id}`;
      const existing = container.querySelector(`[data-cycle-start="${startKey}"]`);
      if (existing) {
        const spinner = existing.querySelector('.progress-spinner');
        if (spinner) spinner.remove();
        existing.querySelector('.cycle-text').textContent += ' → 완료';
      }
      container.appendChild(createCycleDivider(activity, false));
    } else {
      container.appendChild(createBubble(activity));
    }
    lastActivityGroupKey = `cycle:${activity.cycle_id || activity.phase || 'global'}`;
  } else if (isTaskActivity || isDailyPlan) {
    const descriptor = buildTaskCardDescriptor(activity);
    const groupKey = `task:${descriptor.key}`;
    let cardKey = latestTaskCardKeyByDescriptor[descriptor.key];
    if (lastActivityGroupKey !== groupKey || !cardKey || !taskCards[cardKey]) {
      const nextIndex = (taskCardSequence[descriptor.key] || 0) + 1;
      taskCardSequence[descriptor.key] = nextIndex;
      cardKey = `${descriptor.key}:${nextIndex}`;
    }
    let card = taskCards[cardKey];
    if (!card) {
      card = createTaskCard(activity);
      taskCards[cardKey] = card;
      latestTaskCardKeyByDescriptor[descriptor.key] = cardKey;
      container.appendChild(card.element);
    }
    addStepToTaskCard(card, activity);
    lastActivityGroupKey = groupKey;
  } else {
    // Symbol-specific → route to stock card
    const cardKey = `${activity.cycle_id || 'ev'}:${symbol}`;
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
      card = createStockCard(symbol, activity);
      stockCards[cardKey] = card;
      container.appendChild(card.element);
    }
    addStepToCard(card, activity);
    updateCardHeader(card);
    lastActivityGroupKey = `symbol:${cardKey}`;
  }

  activityCount++;
  document.getElementById('activity-count').textContent = `${activityCount}건`;

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

function buildActivityMetaLine(meta = {}) {
  const identityLabel = buildActivityIdentityLabel(meta);
  if (!identityLabel) return '';
  const symbolAttr = meta.symbol ? ` data-activity-symbol="${escapeHtml(normalizeActivitySymbol(meta.symbol))}"` : '';
  return `<div class="activity-stock-meta text-[11px] text-gray-500 mb-0.5"${symbolAttr}>${escapeHtml(identityLabel)}</div>`;
}

function buildActivityHeadlineMarkup(data, meta = {}, className = 'text-sm') {
  const symbolAttr = meta.symbol ? ` data-activity-symbol="${escapeHtml(normalizeActivitySymbol(meta.symbol))}"` : '';
  const summaryAttr = ` data-activity-summary="${escapeHtml(data.summary || '')}"`;
  const detailAttr = data.detail ? ` data-activity-detail="${escapeHtml(data.detail)}"` : '';
  return `<div class="${className} activity-headline"${symbolAttr}${summaryAttr}${detailAttr}>${escapeHtml(formatActivityHeadline(data.summary, meta))}</div>`;
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

function rememberStockMeta(symbol, meta = {}) {
  const normalizedSymbol = normalizeActivitySymbol(symbol);
  if (!normalizedSymbol) return;
  knownStockMeta[normalizedSymbol] = {
    ...(knownStockMeta[normalizedSymbol] || {}),
    ...meta,
  };
  if (knownStockMeta[normalizedSymbol].stockName) {
    rememberStockName(normalizedSymbol, knownStockMeta[normalizedSymbol].stockName);
  }
}

function renderCardIdentity(card) {
  const identityEl = card.headerEl.querySelector('.stock-identity');
  if (!identityEl) return;
  identityEl.innerHTML = `
    ${escapeHtml(card.stockName)} <span class="text-gray-500 text-xs">${escapeHtml(card.symbol)}</span>
  `;
  identityEl.title = `${card.stockName} (${card.symbol})`;

  const metaEl = card.headerEl.querySelector('.stock-meta');
  if (!metaEl) return;
  metaEl.textContent = card.summaryText || '';
  metaEl.classList.toggle('hidden', !card.summaryText);
}

function updateCardManualActions(card) {
  if (!card?.actionsEl) return;
  if (card.outcome !== 'sell') {
    card.actionsEl.innerHTML = '';
    card.actionsEl.classList.add('hidden');
    return;
  }

  const action = getImmediateSellAction(card.symbol, getManualTradeSymbolMap());
  card.actionsEl.innerHTML = `
    <div class="flex items-center justify-between gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-2 py-2">
      <div class="space-y-1">
        <div class="text-[11px] text-gray-400">
          ${escapeHtml(action.disabled ? (action.reason || '즉시 매도 불가') : `${action.quantity || 0}주 전량 시장가 매도`)}
        </div>
        ${action.hint && !action.disabled ? `<div class="text-[10px] text-amber-300/80">${escapeHtml(action.hint)}</div>` : ''}
      </div>
      ${renderManualActionButton(action, {
        'manual-action': action.kind,
        symbol: card.symbol || '',
      })}
    </div>
  `;
  card.actionsEl.classList.remove('hidden');
}

function refreshStockCardActions() {
  Object.values(stockCards || {}).forEach((card) => {
    updateCardManualActions(card);
  });
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
    knownMeta: knownStockMeta,
  });
  const stockName = meta.stockName;
  const normalizedSymbol = meta.symbol;
  rememberStockMeta(normalizedSymbol, { stockName });

  // Header
  const header = document.createElement('div');
  header.className = 'stock-card-header';
  header.innerHTML = `
    <span class="text-sm">📊</span>
    <span class="flex-1 min-w-0">
      <span class="stock-identity text-sm font-medium text-white block truncate">
        ${escapeHtml(stockName)} <span class="text-gray-500 text-xs">${escapeHtml(normalizedSymbol)}</span>
      </span>
      <span class="stock-meta text-[11px] text-gray-500 block truncate ${meta.summaryText ? '' : 'hidden'}">${escapeHtml(meta.summaryText || '')}</span>
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

  const actions = document.createElement('div');
  actions.className = 'hidden mb-2';

  const steps = document.createElement('div');
  steps.className = 'stock-card-steps';
  body.appendChild(actions);
  body.appendChild(steps);

  el.appendChild(header);
  el.appendChild(body);

  const card = {
    element: el,
    headerEl: header,
    bodyEl: body,
    actionsEl: actions,
    stepsEl: steps,
    activities: [],
    symbol: normalizedSymbol,
    stockName: stockName,
    summaryText: meta.summaryText || '',
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
  const stockMeta = resolveActivityStockMeta({
    symbol: card.symbol,
    summary: data.summary,
    detail: data.detail,
    knownNames: knownStockNames,
    knownMeta: knownStockMeta,
  });
  if (stockMeta.stockName && stockMeta.stockName !== card.stockName) {
    card.stockName = stockMeta.stockName;
  }
  if (stockMeta.summaryText) {
    card.summaryText = stockMeta.summaryText;
  }
  rememberStockMeta(card.symbol, { stockName: stockMeta.stockName });
  renderCardIdentity(card);

  card.activities.push(data);

  const progressKey = getProgressKey(data);

  // START → compact progress indicator
  if (data.phase === 'START') {
    const step = document.createElement('div');
    step.className = 'stock-step';
    step.setAttribute('data-progress-key', progressKey);
    const time = formatTime(data.created_at);
    const label = formatActivityHeadline((data.summary || '').replace(/시작$/, '').trim(), stockMeta);
    step.innerHTML = `
      <span class="text-xs text-gray-600 shrink-0 w-14">${time}</span>
      <span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px"></span>
      <span class="text-xs text-gray-400 activity-headline"
        data-activity-symbol="${escapeHtml(stockMeta.symbol || card.symbol)}"
        data-activity-summary="${escapeHtml(data.summary || '')}"
        ${data.detail ? `data-activity-detail="${escapeHtml(data.detail)}"` : ''}>${escapeHtml(label)}...</span>
    `;
    card.stepsEl.appendChild(step);
    return;
  }

  // COMPLETE/ERROR → remove matching START spinner
  if (data.phase === 'COMPLETE' || data.phase === 'ERROR') {
    const existing = findProgressStep(card.stepsEl, progressKey);
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
      ${buildActivityMetaLine(stockMeta)}
      ${buildActivityHeadlineMarkup(data, stockMeta, 'text-xs')}`;

  // Meta line
  const metaParts = [];
  if (data.llm_provider) metaParts.push(`<span class="text-${typeColor}-400">${data.llm_provider}</span>`);
  if (elapsed) metaParts.push(elapsed);
  if (data.confidence != null) {
    const pct = Math.round(data.confidence * 100);
    metaParts.push(`신뢰도 ${pct}%`);
  }
  if (metaParts.length) {
    html += `<div class="text-xs text-gray-600 mt-0.5">${metaParts.join(' · ')}</div>`;
  }

  // Detail (expandable)
  if (data.detail) {
    const detailId = 'sd-' + Math.random().toString(36).substr(2, 6);
    const isLLMCall = data.activity_type === 'LLM_CALL';
    html += `
      ${buildDetailToggleMarkup({ detailId, isLLMCall })}
      <div id="${detailId}" class="detail-content mt-1 text-xs bg-dark-900/50 rounded p-2 text-gray-400">
        <div class="detail-content-inner">
          ${isLLMCall ? formatLLMConversation(data.detail) : `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${formatDetail(data.detail)}</pre>`}
        </div>
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
  const latestActivity = acts[acts.length - 1];
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
  card.element.className = `stock-card outcome-${outcome} tone-${resolveActivityTone(latestActivity?.activity_type, latestActivity?.summary)}`;
  updateCardManualActions(card);
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
  const stockMeta = resolveActivityStockMeta({
    symbol: data.symbol,
    summary: data.summary,
    detail: data.detail,
    knownNames: knownStockNames,
    knownMeta: knownStockMeta,
  });
  if (stockMeta.symbol) {
    rememberStockMeta(stockMeta.symbol, { stockName: stockMeta.stockName });
  }

  let html = `
    <div class="flex items-start gap-2 px-3 py-1.5 rounded-lg hover:bg-dark-700/50 transition group">
      <span class="text-xs text-gray-500 mt-0.5 shrink-0 w-14">${time}</span>
      <div class="flex-1 min-w-0">
        ${buildActivityMetaLine(stockMeta)}
        ${buildActivityHeadlineMarkup(data, stockMeta, 'text-sm whitespace-pre-wrap')}`;

  const metaParts = [];
  if (data.llm_provider) metaParts.push(`<span class="text-${typeColor}-400">${data.llm_provider}</span>`);
  if (data.execution_time_ms) metaParts.push(`${(data.execution_time_ms / 1000).toFixed(1)}초`);
  if (data.confidence != null) {
    const pct = Math.round(data.confidence * 100);
    metaParts.push(`신뢰도 ${pct}%`);
  }
  if (metaParts.length) {
    html += `<div class="flex items-center gap-3 mt-0.5 text-xs text-gray-500">${metaParts.join(' | ')}</div>`;
  }

  if (data.detail) {
    const detailId = 'detail-' + (data.id || Math.random().toString(36).substr(2, 6));
    const isLLMCall = data.activity_type === 'LLM_CALL';
    html += `
      ${buildDetailToggleMarkup({ detailId, isLLMCall, muted: true })}
      <div id="${detailId}" class="detail-content mt-1 text-xs bg-dark-900 rounded p-2 text-gray-400">
        <div class="detail-content-inner">
          ${isLLMCall ? formatLLMConversation(data.detail) : `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${formatDetail(data.detail)}</pre>`}
        </div>
      </div>`;
  }

  if (data.error_message) {
    html += `<div class="text-xs text-red-400 mt-1">${escapeHtml(data.error_message)}</div>`;
  }

  html += `</div></div>`;
  div.innerHTML = html;
  return div;
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
  } else if (view === 'reports') {
    loadReportsArchive();
  } else if (view === 'performance') {
    loadPerformanceView();
  } else if (view === 'observability') {
    loadObservabilityView();
  } else if (view === 'errors') {
    loadErrorObservabilityView();
  } else if (view === 'news-archive') {
    loadNewsArchiveView();
  } else if (view === 'trades-center') {
    loadTradesCenterView();
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
    const json = await fetchJson(`${API}/activities?limit=2000`);
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
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
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
  taskCards = {};
  taskCardSequence = {};
  latestTaskCardKeyByDescriptor = {};
  lastActivityGroupKey = null;
}

function buildTaskCardDescriptor(data) {
  const summary = String(data?.summary || '');
  const type = String(data?.activity_type || '').toUpperCase();

  if (type === 'REPORT') {
    return { key: 'report', title: '일일 리포트 작업', icon: '📝' };
  }
  if (/뉴스|공시|수집|poll/i.test(summary)) {
    return { key: 'news', title: '뉴스 수집/해석', icon: '🛰️' };
  }
  if (type === 'QA') {
    return { key: 'qa', title: 'Q&A 작업', icon: '💬' };
  }
  if (type === 'DAILY_PLAN') {
    return { key: 'daily-plan', title: '일일 계획 작업', icon: '📅' };
  }
  if (type === 'LLM_CALL') {
    return { key: 'llm', title: '공용 LLM 작업', icon: '🤖' };
  }
  if (type === 'EVENT') {
    return { key: 'event', title: '운영 이벤트', icon: '📣' };
  }
  if (type === 'SCHEDULE' || type === 'TRADING_RULE' || type === 'HOLDINGS_CHECK') {
    return { key: 'operations', title: '운영 스케줄 작업', icon: '⚙️' };
  }
  return { key: `task-${type || 'misc'}`, title: type || '기타 작업', icon: '📌' };
}

function parseActivityDetailObject(detail) {
  if (!detail) return null;
  if (typeof detail === 'object') return detail;
  try {
    return JSON.parse(detail);
  } catch {
    return null;
  }
}

function getTaskProgressKey(data) {
  const detail = parseActivityDetailObject(data?.detail);
  const detailKey = detail?.task_key || detail?.source_code || detail?.report_date || detail?.mode;
  const normalizedSummary = String(data?.summary || '')
    .replace(/시작$/, '')
    .replace(/완료.*$/, '완료')
    .trim();
  return `${String(data?.activity_type || 'TASK').toUpperCase()}:${detailKey || normalizedSummary || 'global'}`;
}

function findProgressStep(container, progressKey) {
  if (!container || !progressKey) return null;
  return Array.from(container.querySelectorAll('[data-progress-key]')).find(
    (element) => element.getAttribute('data-progress-key') === progressKey,
  ) || null;
}

function resolveActivityTone(activityType, summary = '') {
  const type = String(activityType || '').toUpperCase();
  const text = String(summary || '');

  if (type === 'TIER1_ANALYSIS' || type === 'MARKET_SCAN' || /스캔|1차 분석|실시간 이벤트/.test(text)) return 'scan';
  if (type === 'TIER2_REVIEW') return 'review';
  if (type === 'STRATEGY_EVAL') return 'strategy';
  if (type === 'ORDER' || type === 'DECISION' || /주문|체결|매수|매도/.test(text)) return 'order';
  if (type === 'LLM_CALL') return 'llm';
  if (type === 'REPORT') return 'report';
  if (type === 'DAILY_PLAN') return 'plan';
  if (type === 'EVENT') return 'event';
  if (type === 'SCHEDULE' || type === 'TRADING_RULE' || type === 'HOLDINGS_CHECK') return 'operations';
  if (/뉴스|공시|수집|poll/i.test(text)) return 'news';
  return 'operations';
}

function resolveTaskDescriptorTone(descriptorKey) {
  if (descriptorKey === 'news') return 'news';
  if (descriptorKey === 'report') return 'report';
  if (descriptorKey === 'daily-plan') return 'plan';
  if (descriptorKey === 'llm') return 'llm';
  if (descriptorKey === 'event') return 'event';
  return 'operations';
}

function buildTaskHeaderMeta(card, latest, detail) {
  if (!latest) return '';

  if (card.descriptor?.key === 'news') {
    const summary = detail?.summary;
    if (summary && (summary.created != null || summary.duplicates != null || summary.skipped != null)) {
      return `최근 실행 · 신규 ${summary.created || 0}건 · 중복 ${summary.duplicates || 0}건 · 스킵 ${summary.skipped || 0}건`;
    }
  }

  if (card.descriptor?.key === 'report' && detail?.report_date) {
    return `${detail.report_date} · ${latest.summary || '리포트 갱신'}`;
  }

  if (card.descriptor?.key === 'operations' && detail?.mode) {
    return `${detail.mode} · ${latest.summary || '운영 상태 갱신'}`;
  }

  return latest.summary || '';
}

function buildTaskStepHeadline(card, data, detail) {
  if (card.descriptor?.key === 'news') {
    const summary = detail?.summary;
    if (summary && (summary.created != null || summary.duplicates != null || summary.skipped != null)) {
      return `뉴스 자동 수집 완료 · 신규 ${summary.created || 0}건 · 중복 ${summary.duplicates || 0}건 · 스킵 ${summary.skipped || 0}건`;
    }
  }

  if (card.descriptor?.key === 'report' && detail?.report_date) {
    return `${detail.report_date} 리포트 · ${data.summary || '리포트 작업'}`;
  }

  return data.summary || data.activity_type || '작업';
}

function createTaskCard(firstActivity) {
  const descriptor = buildTaskCardDescriptor(firstActivity);
  const el = document.createElement('div');
  el.className = 'stock-card task-card outcome-progress';

  const header = document.createElement('div');
  header.className = 'stock-card-header';
  header.innerHTML = `
    <span class="task-icon-badge">${descriptor.icon}</span>
    <span class="flex-1 min-w-0">
      <span class="flex items-center gap-2 min-w-0">
        <span class="text-sm font-medium text-white block truncate">${escapeHtml(descriptor.title)}</span>
        <span class="task-count task-meta-chip hidden"></span>
      </span>
      <span class="task-meta text-[11px] text-gray-500 block truncate mt-1 hidden"></span>
    </span>
    <span class="stock-outcome text-xs px-2 py-0.5 rounded bg-purple-900/40 text-purple-300">
      <span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px;margin-right:4px"></span>진행 중
    </span>
    <span class="stock-elapsed text-xs text-gray-600"></span>
    <span class="stock-expand text-gray-500 text-xs transition-transform" style="transform:rotate(-90deg)">▼</span>
  `;

  const body = document.createElement('div');
  body.className = 'stock-card-body';

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
    descriptor,
    outcome: 'progress',
    isOpen: false,
    totalElapsed: 0,
    startTime: Date.now(),
    liveTimer: null,
  };

  header.onclick = () => toggleCardBody(card);
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

function addStepToTaskCard(card, data) {
  card.activities.push(data);
  const progressKey = getTaskProgressKey(data);
  const detail = parseActivityDetailObject(data.detail);

  if (data.phase === 'START') {
    const step = document.createElement('div');
    step.className = 'stock-step';
    step.setAttribute('data-progress-key', progressKey);
    step.innerHTML = `
      <span class="text-xs text-gray-600 shrink-0 w-14">${formatTime(data.created_at)}</span>
      <span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px"></span>
      <span class="text-xs text-gray-400">${escapeHtml(buildTaskStepHeadline(card, data, detail))}...</span>
    `;
    card.stepsEl.appendChild(step);
    updateTaskCardHeader(card);
    return;
  }

  if (data.phase === 'COMPLETE' || data.phase === 'ERROR') {
    const existing = findProgressStep(card.stepsEl, progressKey);
    if (existing) existing.remove();
  }

  const step = document.createElement('div');
  step.className = 'stock-step';
  const dotColor = getTypeDotColor(data.activity_type);
  let html = `
    <span class="text-xs text-gray-600 shrink-0 w-14">${formatTime(data.created_at)}</span>
    <span class="shrink-0 w-2 h-2 rounded-full bg-${dotColor}-400 mt-1.5"></span>
    <div class="flex-1 min-w-0">
      <div class="text-xs text-gray-500 mb-0.5">${escapeHtml(data.activity_type || 'TASK')}</div>
      <div class="text-xs text-gray-200 whitespace-pre-wrap">${escapeHtml(buildTaskStepHeadline(card, data, detail))}</div>
  `;
  const metaParts = [];
  if (data.llm_provider) metaParts.push(data.llm_provider);
  if (data.execution_time_ms) metaParts.push(`${(data.execution_time_ms / 1000).toFixed(1)}초`);
  if (metaParts.length) {
    html += `<div class="text-xs text-gray-600 mt-0.5">${escapeHtml(metaParts.join(' · '))}</div>`;
  }
  if (data.detail) {
    const detailId = 'task-detail-' + (data.id || Math.random().toString(36).slice(2, 8));
    const isLLMCall = data.activity_type === 'LLM_CALL';
    html += `
      ${buildDetailToggleMarkup({ detailId, isLLMCall })}
      <div id="${detailId}" class="detail-content mt-1 text-xs bg-dark-900/50 rounded p-2 text-gray-400">
        <div class="detail-content-inner">
          ${isLLMCall ? formatLLMConversation(data.detail) : `<pre class="whitespace-pre-wrap break-all max-h-96 overflow-y-auto">${formatDetail(data.detail)}</pre>`}
        </div>
      </div>`;
  }
  if (data.error_message) {
    html += `<div class="text-xs text-red-400 mt-0.5">${escapeHtml(data.error_message)}</div>`;
  }
  html += '</div>';
  step.innerHTML = html;
  card.stepsEl.appendChild(step);
  updateTaskCardHeader(card);
}

function updateTaskCardHeader(card) {
  const latest = card.activities[card.activities.length - 1];
  const detail = parseActivityDetailObject(latest?.detail);
  const metaEl = card.headerEl.querySelector('.task-meta');
  if (metaEl) {
    const metaText = buildTaskHeaderMeta(card, latest, detail);
    metaEl.textContent = metaText;
    metaEl.classList.toggle('hidden', !metaText);
  }

  const countEl = card.headerEl.querySelector('.task-count');
  if (countEl) {
    const visibleSteps = card.stepsEl ? card.stepsEl.children.length : 0;
    countEl.textContent = `${visibleSteps}개 단계`;
    countEl.classList.toggle('hidden', visibleSteps === 0);
  }

  let outcome = 'progress';
  let outcomeText = '<span class="progress-spinner" style="width:10px;height:10px;border-width:1.5px;margin-right:4px"></span>진행 중';
  let outcomeBg = 'bg-purple-900/40 text-purple-300';
  if (latest?.phase === 'ERROR' || latest?.error_message) {
    outcome = 'error';
    outcomeText = '❌ 오류';
    outcomeBg = 'bg-yellow-900/40 text-yellow-300';
  } else if (latest?.phase === 'SKIP') {
    outcome = 'hold';
    outcomeText = '⏭ 스킵';
    outcomeBg = 'bg-gray-700/60 text-gray-400';
  } else if (latest?.phase === 'COMPLETE' || latest?.phase === 'PROGRESS') {
    outcome = 'hold';
    if (card.descriptor?.key === 'news' && detail?.summary) {
      outcomeText = `🛰 신규 ${detail.summary.created || 0}건`;
    } else if (card.descriptor?.key === 'report') {
      outcomeText = '📝 리포트 갱신';
    } else {
      outcomeText = '✓ 업데이트';
    }
    outcomeBg = 'bg-blue-900/40 text-blue-200';
  }

  card.outcome = outcome;
  card.totalElapsed = card.activities.reduce((sum, activity) => sum + (activity.execution_time_ms || 0), 0);
  const outcomeEl = card.headerEl.querySelector('.stock-outcome');
  if (outcomeEl) {
    outcomeEl.className = `stock-outcome text-xs px-2 py-0.5 rounded ${outcomeBg}`;
    outcomeEl.innerHTML = outcomeText;
  }
  if (outcome !== 'progress' && card.liveTimer) {
    clearInterval(card.liveTimer);
    card.liveTimer = null;
  }
  const elapsedEl = card.headerEl.querySelector('.stock-elapsed');
  if (elapsedEl && outcome !== 'progress' && card.totalElapsed > 0) {
    elapsedEl.textContent = `${(card.totalElapsed / 1000).toFixed(1)}초`;
  }
  card.element.className = `stock-card task-card outcome-${outcome}`;
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
    let report = null;
    let reportDate = dateStr;

    if (dateStr === 'today') {
      reportDate = getKstDateString();
      const todayJson = await fetchJson(`${API}/reports/${reportDate}`);
      report = todayJson?.data || null;

      if (!report) {
        const latestJson = await fetchJson(`${API}/reports/latest`);
        report = latestJson?.data || null;
      }
    } else {
      const targetUrl = dateStr ? `${API}/reports/${dateStr}` : `${API}/reports/latest`;
      const json = await fetchJson(targetUrl);
      report = json?.data || null;
      reportDate = report?.report_date || reportDate;
    }

    if (!report) {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">해당 날짜의 리포트가 없습니다</div>';
      if (dateStr && dateStr !== 'today') await loadDateActivities(dateStr, container);
      return;
    }

    let tradeSnapshot = null;
    if (report.report_date) {
      try {
        const tradesJson = await fetchJson(`${API}/trades?target_date=${report.report_date}`);
        tradeSnapshot = tradesJson?.data || null;
      } catch (error) {
        console.warn('Trade snapshot fallback load failed:', error);
      }
    }

    let newsOverview = newsOverviewSnapshot;
    try {
      const overviewJson = await fetchJson(`${API}/news/overview?recent_limit=4&performance_days=30`);
      newsOverview = overviewJson?.data || newsOverview;
      if (newsOverview) {
        newsOverviewSnapshot = newsOverview;
        renderSidebarSettingSummaries();
        renderNewsOverviewPanels();
      }
    } catch (error) {
      console.warn('News overview load failed:', error);
    }

    let dateActivities = [];
    if (report.report_date) {
      dateActivities = await fetchDateActivities(report.report_date);
    }

    const reportView = applyReportMetricsFallback(report, tradeSnapshot);
    const activityInsights = buildReportActivityInsights(dateActivities);
    container.innerHTML = '';
    container.appendChild(
      createReportCard(reportView, {
        requestedDate: dateStr,
        resolvedDate: reportDate,
        usingTradeFallback: Boolean(reportView?._fallback_metrics),
        newsOverview,
        activityInsights,
        tradeSnapshot,
      })
    );
    if (report.report_date) {
      await loadTradeHistory(report.report_date, container, tradeSnapshot);
      renderDateActivities(report.report_date, container, dateActivities);
    }
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">리포트 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

async function fetchDateActivities(dateStr) {
  try {
    const json = await fetchJson(`${API}/activities?target_date=${dateStr}&limit=500`);
    return Array.isArray(json?.data) ? json.data : [];
  } catch (err) {
    console.error('Activities load error:', err);
    return [];
  }
}

function renderDateActivities(dateStr, container, activities = []) {
  if (!Array.isArray(activities) || !activities.length) {
    return;
  }

  const section = document.createElement('div');
  section.className = 'mt-4 border-t border-gray-800';
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'w-full text-center text-gray-500 hover:text-gray-300 text-xs py-3 flex items-center justify-center gap-2 transition';
  toggleBtn.innerHTML = `<span class="activity-toggle-icon">▶</span> ${dateStr} 활동 로그 (${activities.length}건)`;
  const logContainer = document.createElement('div');
  logContainer.className = 'hidden';
  logContainer.style.maxHeight = '600px';
  logContainer.style.overflowY = 'auto';
  activities.forEach((activity) => logContainer.appendChild(createBubble(activity)));
  toggleBtn.onclick = () => {
    const isHidden = logContainer.classList.contains('hidden');
    logContainer.classList.toggle('hidden');
    toggleBtn.querySelector('.activity-toggle-icon').innerHTML = isHidden ? '▼' : '▶';
  };
  section.appendChild(toggleBtn);
  section.appendChild(logContainer);
  container.appendChild(section);
}

async function loadDateActivities(dateStr, container) {
  try {
    const activities = await fetchDateActivities(dateStr);
    renderDateActivities(dateStr, container, activities);
  } catch (err) {
    console.error('Activities load error:', err);
  }
}

function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function normalizeReportSummaryMetrics(report) {
  if (!report) return report;
  const buyCountRaw = toNumber(report.buy_count);
  const sellCountRaw = toNumber(report.sell_count);
  const openCountRaw = toNumber(report.open_position_count);
  const totalOrders = toNumber(report.total_orders);
  const unrealizedPnl = toNumber(report.unrealized_pnl);

  let buyCount = buyCountRaw;
  let sellCount = sellCountRaw;
  let openCount = openCountRaw;

  const metricsAreZero = buyCountRaw === 0 && sellCountRaw === 0 && openCountRaw === 0;
  if (metricsAreZero && totalOrders > 0) {
    // 집계값이 누락된 과거 리포트 방어: 최소한 주문 건수는 매수 건수로 노출
    buyCount = Math.max(buyCount, totalOrders);
  }
  if (openCount === 0 && unrealizedPnl !== 0) {
    // 미실현 손익이 존재하면 최소 1개 이상의 보유 포지션이 있다고 간주
    openCount = 1;
  }

  return {
    ...report,
    buy_count: buyCount,
    sell_count: sellCount,
    open_position_count: openCount,
  };
}

function applyReportMetricsFallback(report, tradeSnapshot) {
  if (!report || !tradeSnapshot) return report;

  const opened = Array.isArray(tradeSnapshot.opened) ? tradeSnapshot.opened : [];
  const completed = Array.isArray(tradeSnapshot.completed) ? tradeSnapshot.completed : [];
  const openPositions = Array.isArray(tradeSnapshot.open_positions) ? tradeSnapshot.open_positions : [];

  const buyCount = opened.length;
  const sellCount = completed.length;
  const winCount = completed.filter((t) => Boolean(t?.is_win)).length;
  const lossCount = completed.length - winCount;
  const totalPnl = completed.reduce((sum, item) => sum + toNumber(item?.pnl), 0);
  const openPositionCount = new Set(
    openPositions
      .map((item) => item?.stock_symbol)
      .filter(Boolean)
  ).size;

  const reportLooksEmpty = (
    toNumber(report.buy_count) === 0
    && toNumber(report.sell_count) === 0
    && toNumber(report.total_pnl) === 0
    && toNumber(report.open_position_count) === 0
  );

  const tradeHasData = buyCount > 0 || sellCount > 0 || openPositionCount > 0;
  if (!reportLooksEmpty || !tradeHasData) {
    return report;
  }

  return {
    ...report,
    buy_count: buyCount,
    sell_count: sellCount,
    win_count: winCount,
    loss_count: lossCount,
    total_pnl: totalPnl,
    open_position_count: openPositionCount,
    total_orders: buyCount + sellCount,
    _fallback_metrics: true,
  };
}

function createReportCard(report, context = {}) {
  const normalizedReport = normalizeReportSummaryMetrics(report);
  const div = document.createElement('div');
  div.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble';
  const winCount = toNumber(normalizedReport.win_count);
  const lossCount = toNumber(normalizedReport.loss_count);
  const totalPnl = toNumber(normalizedReport.total_pnl);
  const unrealizedPnl = toNumber(normalizedReport.unrealized_pnl);
  const totalCycles = toNumber(normalizedReport.total_cycles);
  const totalAnalyses = toNumber(normalizedReport.total_analyses);
  const buyCount = toNumber(normalizedReport.buy_count);
  const sellCount = toNumber(normalizedReport.sell_count);
  const openCount = toNumber(normalizedReport.open_position_count);
  const reportDate = normalizedReport.report_date || context.resolvedDate || '-';
  const requestedDate = context.requestedDate === 'today' ? getKstDateString() : (context.requestedDate || reportDate);
  const isFallbackReport = context.requestedDate === 'today' && reportDate !== requestedDate;
  const activityInsights = context.activityInsights || null;
  const newsOverview = context.newsOverview || null;
  const tradeSnapshot = context.tradeSnapshot || null;
  const reportPerformance = buildReportPerformanceState(normalizedReport);
  const newsPerformance = newsOverview?.performance || {};
  const newsSettings = newsOverview?.settings || {};
  const newsStorage = newsOverview?.storage || {};
  const newsStrip = newsOverview ? buildReportNewsStripModel(newsOverview) : null;
  const newsSourcePills = newsOverview ? buildNewsOverviewSourcePills(newsOverview).slice(0, 6) : [];
  const newsPerformanceCards = newsOverview ? buildNewsPerformanceCards(newsOverview) : [];
  const newsRolloutPolicy = newsOverview ? buildNewsRolloutPolicy(newsOverview) : null;
  const newsRationale = buildReportNewsRationale({ trades: tradeSnapshot, activityInsights });
  const newsStatusToneClass = newsStrip?.statusLabel === 'SUCCESS'
    ? 'tone-success'
    : newsStrip?.statusLabel === 'ERROR'
      ? 'tone-error'
      : newsStrip?.statusLabel === 'EMPTY'
        ? 'tone-empty'
        : 'tone-idle';
  const winRate = (winCount + lossCount) > 0
    ? ((winCount / (winCount + lossCount)) * 100).toFixed(1)
    : '-';
  const realizedPnlColor = totalPnl >= 0 ? 'text-green-400' : 'text-red-400';
  const unrealizedPnlColor = unrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400';
  let topPicks = '';
  try {
    const picks = JSON.parse(normalizedReport.top_picks || '[]');
    topPicks = picks.map(p => typeof p === 'string' ? p : `${p.name || ''}(${p.symbol || ''})`).filter(Boolean).join(', ');
  } catch(e) {}

  div.innerHTML = `
    <div class="flex items-start justify-between gap-3 mb-4">
      <div>
        <div class="text-lg font-bold text-white">📋 ${reportDate} 일일 리포트</div>
        <div class="text-xs ${isFallbackReport ? 'text-yellow-400' : 'text-gray-500'} mt-1">
          ${isFallbackReport ? `오늘(${requestedDate}) 리포트가 없어 최신 리포트(${reportDate})를 표시 중` : `조회 기준일: ${requestedDate}`}
        </div>
        ${context.usingTradeFallback ? '<div class="text-xs text-amber-300 mt-1">집계값 불일치로 오늘 거래 원본 기준 수치를 임시 보정해 표시 중</div>' : ''}
      </div>
      <button onclick="loadReport('${reportDate}')" class="text-[11px] text-gray-400 hover:text-gray-200 transition">다시 불러오기</button>
    </div>
    <div class="grid grid-cols-3 gap-3 mb-3">
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-blue-400">${totalCycles}</div>
        <div class="text-xs text-gray-500">사이클</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-purple-400">${totalAnalyses}</div>
        <div class="text-xs text-gray-500">분석</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-2xl font-bold text-yellow-400">${buyCount}<span class="text-xs text-gray-500">매수</span> / ${sellCount}<span class="text-xs text-gray-500">매도</span></div>
        <div class="text-xs text-gray-500">주문 (보유 ${openCount}종목)</div>
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3 mb-4">
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-xl font-bold ${realizedPnlColor}">${totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString()}원</div>
        <div class="text-xs text-gray-500">실현 손익 (승률 ${winRate}%)</div>
      </div>
      <div class="bg-dark-900 rounded-lg p-3 text-center">
        <div class="text-xl font-bold ${unrealizedPnlColor}">${unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toLocaleString()}원</div>
        <div class="text-xs text-gray-500">미실현 손익</div>
      </div>
    </div>
    <div class="mb-4 rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <div class="text-sm font-medium text-gray-300">🧪 뉴스 반영 거래 비교</div>
          <div class="text-xs text-gray-500 mt-1">리포트 기준 청산 거래를 뉴스 반영 여부로 나눠 기대값과 손익을 비교합니다.</div>
        </div>
        <div class="text-[11px] text-gray-500">${escapeHtml(reportPerformance.helperLabel)}</div>
      </div>
      ${reportPerformance.ready ? `
        <div class="performance-table">
          ${reportPerformance.rows.map((row) => `
            <div class="performance-table-row">
              <div class="performance-table-cell metric-name">${escapeHtml(row.label)}</div>
              <div class="performance-table-cell">${escapeHtml(row.tradeCount)}</div>
              <div class="performance-table-cell">${escapeHtml(row.expectancy)}</div>
              <div class="performance-table-cell">${escapeHtml(row.profitFactor)}</div>
              <div class="performance-table-cell">${escapeHtml(row.totalPnl)}</div>
            </div>
          `).join('')}
        </div>
        <div class="mt-3 flex flex-wrap gap-3 text-[11px] text-gray-400">
          <span>E 차이 ${escapeHtml(reportPerformance.delta.expectancy)}</span>
          <span>PF 차이 ${escapeHtml(reportPerformance.delta.profitFactor)}</span>
          <span>비용차감 ${escapeHtml(reportPerformance.delta.netPnlAfterCost)}</span>
        </div>
      ` : `
        <div class="rounded-2xl border border-dashed border-gray-700 bg-dark-900/30 px-4 py-5 text-sm text-gray-500">${escapeHtml(reportPerformance.emptyLabel)}</div>
      `}
    </div>
    ${newsOverview && newsStrip ? `
    <details class="report-news-strip ${newsStatusToneClass} mb-4">
      <summary class="report-news-strip-summary">
        <div class="min-w-0">
          <div class="report-news-strip-eyebrow">🛰 뉴스 인텔</div>
          <div class="report-news-strip-title">${escapeHtml(newsStrip.statusLabel)} · ${escapeHtml(newsStrip.pollLabel)}</div>
          <div class="report-news-strip-meta">${escapeHtml(newsStrip.pollAtLabel)} · ${escapeHtml(newsStrip.message)}</div>
        </div>
        <div class="report-news-strip-stat-row">
          <div class="report-news-strip-stat">
            <span class="report-news-strip-stat-label">최근 24시간</span>
            <strong>${escapeHtml(newsStrip.recentCountLabel)}</strong>
          </div>
          <div class="report-news-strip-stat">
            <span class="report-news-strip-stat-label">소스</span>
            <strong>${escapeHtml(newsStrip.sourceSummary)}</strong>
          </div>
          <div class="report-news-strip-stat">
            <span class="report-news-strip-stat-label">설정</span>
            <strong>${escapeHtml(newsSettings.include_foreign ? '해외 포함' : '국내 중심')}</strong>
          </div>
        </div>
      </summary>
      <div class="report-news-strip-body">
        <div class="flex items-start justify-between gap-3 mb-3">
          <div>
            <div class="text-xs text-gray-400">${escapeHtml(newsStrip.settingSummary)}</div>
            <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(newsStrip.impactSummary || '뉴스 영향 집계 없음')}</div>
            <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(newsStrip.rolloutSummary || '롤아웃 판정 대기')}</div>
            <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(newsStrip.periodicSummary || '주간/월간 집계 대기')}</div>
            ${newsStorage.ready === false ? `<div class="text-[11px] text-amber-300 mt-1">저장소 준비 필요 · ${escapeHtml(newsStorage.message || 'news_items 테이블이 아직 없습니다.')}</div>` : ''}
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button type="button" onclick="fetchBloombergNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">Bloomberg 수동 수집</button>
            <button type="button" onclick="fetchCnbcNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">CNBC 수동 수집</button>
            <button type="button" onclick="fetchNasdaqNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">Nasdaq 수동 수집</button>
            <button type="button" onclick="fetchInvestingNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">Investing 수동 수집</button>
            <button type="button" onclick="fetchSeekingAlphaNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">Seeking Alpha 수동 수집</button>
            <button type="button" onclick="fetchYonhapNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">연합뉴스TV 수동 수집</button>
            <button type="button" onclick="fetchKrxNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">KIND 수동 수집</button>
            <button type="button" onclick="fetchDartNews()" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">DART 수동 수집</button>
          </div>
        </div>
        <div class="news-source-pill-row mb-3">
          ${newsSourcePills.join('')}
        </div>
        <div class="news-overview-grid mb-3">
          ${newsPerformanceCards.map((card) => `
            <div class="news-overview-card">
              <div class="news-overview-label">${escapeHtml(card.label)}</div>
              <div class="news-overview-value">${escapeHtml(card.value)}</div>
              <div class="news-overview-help">${escapeHtml(card.help || '')}</div>
            </div>
          `).join('')}
          <div class="news-overview-card">
            <div class="news-overview-label">뉴스 게이트</div>
            <div class="news-overview-value">${escapeHtml(String(newsPerformance.news_gate_blocks || 0))}</div>
            <div class="news-overview-help">부정 뉴스 압력으로 진입을 막은 횟수</div>
          </div>
          <div class="news-overview-card">
            <div class="news-overview-label">재검증</div>
            <div class="news-overview-value">${escapeHtml(String(newsPerformance.news_rechecks || 0))}</div>
            <div class="news-overview-help">신규 뉴스 도착 후 다시 본 종목 수</div>
          </div>
        </div>
        ${newsRolloutPolicy ? `
        <div class="rounded-2xl border border-gray-700/80 bg-dark-900/40 px-4 py-3 mb-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">Shadow / Rollout</div>
              <div class="mt-1 text-sm font-medium text-white">${escapeHtml(newsRolloutPolicy.status)}</div>
            </div>
            <div class="text-[11px] text-gray-400">${escapeHtml(newsRolloutPolicy.reason)}</div>
          </div>
          <div class="mt-2 space-y-1 text-[11px] text-gray-400">
            ${newsRolloutPolicy.lines.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
          </div>
        </div>` : ''}
        <div>
          <div class="text-xs font-medium text-gray-400 mb-2">최근 적재 뉴스</div>
          <div class="news-item-list">
            ${renderNewsItemCards(newsStrip.recentItems, { emptyLabel: '최근 적재 뉴스가 없습니다.', compact: true })}
          </div>
        </div>
      </div>
    </details>` : ''}
    ${activityInsights ? `
    <div class="mb-4">
      <div class="flex items-start justify-between gap-3 mb-2">
        <div>
          <div class="text-sm font-medium text-gray-300">🚫 오늘 안 산 이유</div>
          <div class="text-xs text-gray-500 mt-1">리스크·비용·뉴스 게이트로 보류된 후보와 뉴스 재검증 흐름을 바로 확인합니다.</div>
        </div>
        <div class="text-[11px] text-gray-500">차단 ${escapeHtml(String(activityInsights.blockedCount || 0))}건 · 재검증 ${escapeHtml(String(activityInsights.recheckCount || 0))}종목</div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${activityInsights.cards.map((card) => `
          <div class="bg-dark-900 rounded-lg p-3 text-center">
            <div class="text-lg font-bold text-amber-300">${escapeHtml(String(card.count || 0))}</div>
            <div class="text-xs text-gray-500">${escapeHtml(card.label)}</div>
          </div>
        `).join('')}
      </div>
      ${activityInsights.items?.length ? `
      <div class="mt-3 space-y-2">
        ${activityInsights.items.map((item) => `
          <div class="rounded-lg border border-gray-700 bg-dark-900/70 px-3 py-2">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm text-gray-200">${escapeHtml(item.title || item.symbol || '후보 종목')}</div>
                <div class="text-xs text-gray-500 mt-1">${escapeHtml(item.reason || '')}</div>
              </div>
              <div class="text-[11px] rounded-full border border-gray-600 px-2 py-1 text-gray-300">${escapeHtml(item.label || '차단')}</div>
            </div>
          </div>
        `).join('')}
      </div>` : '<div class="mt-3 rounded-lg border border-dashed border-gray-700 bg-dark-900/40 px-3 py-3 text-xs text-gray-500">차단 또는 재검증 기록이 없습니다.</div>'}
    </div>` : ''}
    ${newsRationale.hasContent ? `
    <div class="mb-4">
      <div class="flex items-start justify-between gap-3 mb-2">
        <div>
          <div class="text-sm font-medium text-gray-300">🏷 매수/보류 근거 태그</div>
          <div class="text-xs text-gray-500 mt-1">뉴스 위험도, 다중 소스 확인, 차단 사유를 리포트 기준으로 묶었습니다.</div>
        </div>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <div class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-3">
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">왜 샀나</div>
          <div class="mt-3 space-y-2">
            ${newsRationale.buyTags.length
              ? newsRationale.buyTags.map((item) => `
                <div class="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <div class="text-sm text-emerald-200">${escapeHtml(item.label)}</div>
                    <div class="text-[11px] text-emerald-100/80">${escapeHtml(String(item.count))}건</div>
                  </div>
                  ${item.detail ? `<div class="mt-1 text-[11px] text-gray-400">${escapeHtml(item.detail)}</div>` : ''}
                </div>
              `).join('')
              : '<div class="text-xs text-gray-500">뉴스 근거가 기록된 매수 내역이 아직 없습니다.</div>'}
          </div>
        </div>
        <div class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-3">
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">왜 안 샀나</div>
          <div class="mt-3 space-y-2">
            ${newsRationale.blockTags.length
              ? newsRationale.blockTags.map((item) => `
                <div class="rounded-xl border border-rose-500/20 bg-rose-500/5 px-3 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <div class="text-sm text-rose-200">${escapeHtml(item.label)}</div>
                    <div class="text-[11px] text-rose-100/80">${escapeHtml(String(item.count))}건</div>
                  </div>
                  ${item.detail ? `<div class="mt-1 text-[11px] text-gray-400">${escapeHtml(item.detail)}</div>` : ''}
                </div>
              `).join('')
              : '<div class="text-xs text-gray-500">보류 근거 태그가 아직 없습니다.</div>'}
          </div>
        </div>
      </div>
    </div>` : ''}
    ${normalizedReport.market_summary ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📝 오늘 리뷰</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(normalizedReport.market_summary)}</div>
    </div>` : ''}
    ${normalizedReport.performance_review ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📊 포트폴리오 진단</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(normalizedReport.performance_review)}</div>
    </div>` : ''}
    ${normalizedReport.lessons_learned ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">🔮 내일 전망</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(normalizedReport.lessons_learned)}</div>
    </div>` : ''}
    ${normalizedReport.next_day_plan ? `
    <div class="mb-3">
      <div class="text-sm font-medium text-gray-300 mb-1">📈 액션 플랜</div>
      <div class="text-sm text-gray-400 bg-dark-900 rounded p-3 whitespace-pre-wrap">${escapeHtml(normalizedReport.next_day_plan)}</div>
    </div>` : ''}
    ${topPicks ? `
    <div class="mb-2">
      <div class="text-sm font-medium text-gray-300 mb-1">🎯 관심 종목</div>
      <div class="text-xs text-gray-400 bg-dark-900 rounded p-2">${escapeHtml(topPicks)}</div>
    </div>` : ''}`;
  return div;
}

function renderMetricRows(rows = [], emptyLabel = '데이터가 아직 없습니다.') {
  if (!rows.length) {
    return `<div class="rounded-2xl border border-dashed border-gray-700 bg-dark-900/30 px-4 py-5 text-sm text-gray-500">${escapeHtml(emptyLabel)}</div>`;
  }
  return `
    <div class="performance-table">
      ${rows.map((row) => `
        <div class="performance-table-row">
          <div class="performance-table-cell metric-name">${escapeHtml(row.label)}</div>
          <div class="performance-table-cell">${escapeHtml(row.tradeCount)}</div>
          <div class="performance-table-cell">${escapeHtml(row.expectancy)}</div>
          <div class="performance-table-cell">${escapeHtml(row.profitFactor)}</div>
          <div class="performance-table-cell">${escapeHtml(row.totalPnl)}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderPeriodRows(rows = [], emptyLabel = '집계 대기 중입니다.') {
  if (!rows.length) {
    return `<div class="rounded-2xl border border-dashed border-gray-700 bg-dark-900/30 px-4 py-5 text-sm text-gray-500">${escapeHtml(emptyLabel)}</div>`;
  }
  return `
    <div class="performance-table">
      ${rows.map((row) => `
        <div class="performance-table-row compact">
          <div class="performance-table-cell metric-name">${escapeHtml(row.periodLabel)}</div>
          <div class="performance-table-cell">${escapeHtml(row.expectancy)}</div>
          <div class="performance-table-cell">${escapeHtml(row.profitFactor)}</div>
          <div class="performance-table-cell">${escapeHtml(row.totalPnl)}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderObservabilityChartCard(card, strokeClass) {
  const path = card?.line?.path || '';
  if (!path) {
    return '<div class="observability-chart-empty">데이터 수집 중...</div>';
  }
  return `
    <svg viewBox="0 0 360 96" class="observability-chart-svg" preserveAspectRatio="none">
      <path d="${escapeHtml(path)}" class="observability-chart-path ${strokeClass}" />
    </svg>
    <div class="observability-chart-meta">
      <span>min ${escapeHtml(String(card.line.min ?? '-'))}${escapeHtml(card.unit || '')}</span>
      <span>max ${escapeHtml(String(card.line.max ?? '-'))}${escapeHtml(card.unit || '')}</span>
      <span>last ${escapeHtml(String(card.line.last ?? '-'))}${escapeHtml(card.unit || '')}</span>
    </div>
  `;
}

function createObservabilityDashboard(observabilityState) {
  const div = document.createElement('div');
  div.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble';
  const obs = observabilityState;
  const selectedObservabilityHours = Number(window.performanceObservabilityHours || 24);
  div.innerHTML = `
    <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <div class="text-lg font-bold text-white">⚙️ 시스템 관측</div>
          <div class="text-sm text-gray-400 mt-1">프로그램 리소스와 뉴스/LLM 파이프라인 상태를 최적화 관점에서 확인합니다.</div>
          <div class="mt-2 text-[11px] text-gray-500">${escapeHtml(obs.machine.host)} · ${escapeHtml(obs.machine.runtime)} · ${escapeHtml(obs.machine.platform)} · 최근 ${escapeHtml(obs.machine.latestCollectedAt)} · ${escapeHtml(String(obs.window.hours || 24))}h / ${escapeHtml(obs.window.resolution || 'raw')}</div>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" onclick="loadObservabilityView(24)" class="rounded-full border px-3 py-1 text-[11px] transition ${selectedObservabilityHours === 24 ? 'border-blue-400 text-white' : 'border-gray-600 text-gray-300 hover:border-blue-400 hover:text-white'}">24시간</button>
          <button type="button" onclick="loadObservabilityView(168)" class="rounded-full border px-3 py-1 text-[11px] transition ${selectedObservabilityHours === 168 ? 'border-blue-400 text-white' : 'border-gray-600 text-gray-300 hover:border-blue-400 hover:text-white'}">7일</button>
        </div>
      </div>
      <div class="news-overview-grid mb-4">
        ${obs.summaryCards.map((card) => `
          <div class="news-overview-card">
            <div class="news-overview-label">${escapeHtml(card.label)}</div>
            <div class="news-overview-value">${escapeHtml(card.value)}</div>
            <div class="news-overview-help">${escapeHtml(card.help)}</div>
          </div>
        `).join('')}
      </div>
      <div class="grid gap-4 xl:grid-cols-2 mb-4">
        ${obs.resourceCharts.map((card, index) => `
          <div class="rounded-2xl border border-gray-700 bg-dark-950/50 px-4 py-4">
            <div class="flex items-center justify-between gap-2">
              <div class="text-sm text-white font-medium">${escapeHtml(card.label)}</div>
              <div class="text-[11px] text-gray-500">${escapeHtml(card.unit || 'ratio')}</div>
            </div>
            <div class="observability-chart-shell mt-3">
              ${renderObservabilityChartCard(card, ['stroke-blue-400','stroke-emerald-400','stroke-amber-400','stroke-fuchsia-400'][index] || 'stroke-blue-400')}
            </div>
          </div>
        `).join('')}
      </div>
      <div class="grid gap-4 xl:grid-cols-2 mb-4">
        ${obs.trendCharts.map((card, index) => `
          <div class="rounded-2xl border border-gray-700 bg-dark-950/40 px-4 py-4">
            <div class="flex items-center justify-between gap-2">
              <div>
                <div class="text-sm text-white font-medium">${escapeHtml(card.label)}</div>
                <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(card.meta || '')}</div>
              </div>
              <div class="text-[11px] text-gray-500">${escapeHtml(card.unit || 'count')}</div>
            </div>
            <div class="observability-chart-shell mt-3">
              ${renderObservabilityChartCard(card, ['stroke-cyan-400','stroke-lime-400','stroke-rose-400','stroke-orange-400'][index] || 'stroke-cyan-400')}
            </div>
          </div>
        `).join('')}
      </div>
      <div class="grid gap-4 xl:grid-cols-[1.05fr,0.95fr]">
        <section class="rounded-2xl border border-gray-700 bg-dark-950/40 px-4 py-4">
          <div class="flex items-center justify-between gap-3 mb-3">
            <div>
              <div class="text-xs uppercase tracking-[0.12em] text-gray-500">LLM Breakdown</div>
              <div class="text-sm text-gray-400 mt-1">프로바이더별 호출량, 지연, fallback 비율</div>
            </div>
            <div class="performance-table-head compact">
              <span>성공률</span><span>평균</span><span>p95</span>
            </div>
          </div>
          ${obs.providerRows.length ? `
            <div class="performance-table">
              ${obs.providerRows.map((row) => `
                <div class="performance-table-row compact">
                  <div class="performance-table-cell metric-name">${escapeHtml(row.provider)} · ${escapeHtml(row.calls)} · FB ${escapeHtml(row.fallbackRate)}</div>
                  <div class="performance-table-cell">${escapeHtml(row.successRate)}</div>
                  <div class="performance-table-cell">${escapeHtml(row.avgLatency)}</div>
                  <div class="performance-table-cell">${escapeHtml(row.p95Latency)}</div>
                </div>
              `).join('')}
            </div>
          ` : '<div class="text-xs text-gray-500">최근 LLM 호출 메트릭이 없습니다.</div>'}
        </section>
        <section class="rounded-2xl border border-gray-700 bg-dark-950/40 px-4 py-4">
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">News Poll Pipeline</div>
          <div class="grid grid-cols-2 gap-3 text-sm mt-3">
            ${obs.newsRows.map((row) => `
              <div>
                <div class="text-gray-500">${escapeHtml(row.label)}</div>
                <div class="text-white font-semibold mt-1">${escapeHtml(row.value)}</div>
              </div>
            `).join('')}
          </div>
          <div class="mt-4 flex flex-wrap gap-2">
            ${obs.statusRows.map((row) => `<span class="news-item-badge">${escapeHtml(row.status)} ${escapeHtml(row.count)}</span>`).join('')}
          </div>
        </section>
      </div>
      <section class="rounded-2xl border border-gray-700 bg-dark-950/40 px-4 py-4 mt-4">
        <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Maintenance</div>
        <div class="grid grid-cols-2 xl:grid-cols-3 gap-3 text-sm mt-3">
          ${obs.maintenanceRows.map((row) => `
            <div>
              <div class="text-gray-500">${escapeHtml(row.label)}</div>
              <div class="text-white font-semibold mt-1">${escapeHtml(row.value)}</div>
            </div>
          `).join('')}
        </div>
      </section>
      <section class="rounded-2xl border border-gray-700 bg-dark-950/40 px-4 py-4 mt-4">
        <div class="text-xs uppercase tracking-[0.12em] text-gray-500">LLM Recommendation</div>
        <div class="news-overview-grid mt-3">
          ${obs.recommendationCards.map((card) => `
            <div class="news-overview-card">
              <div class="news-overview-label">${escapeHtml(card.label)}</div>
              <div class="news-overview-value text-base">${escapeHtml(card.value)}</div>
              <div class="news-overview-help">${escapeHtml(card.help)}</div>
            </div>
          `).join('')}
        </div>
      </section>
      <div class="mt-4 flex justify-end">
        <button type="button" onclick="loadErrorObservabilityView(${selectedObservabilityHours})" class="rounded-full border border-rose-500/40 px-3 py-1 text-[11px] text-rose-200 hover:border-rose-300 hover:text-white transition">
          에러 관측 페이지 열기
        </button>
      </div>
    </section>
  `;
  return div;
}

function renderErrorObservabilityPanels(obs) {
  return `
    <div class="grid gap-4 xl:grid-cols-2 mt-4">
      <section class="rounded-2xl border border-rose-900/40 bg-rose-950/10 px-4 py-4">
        <div class="text-xs uppercase tracking-[0.12em] text-rose-300">Recent Errors</div>
        <div class="mt-3 space-y-2">
          ${obs.recentErrors.length ? obs.recentErrors.map((row) => `
            <div class="rounded-xl border border-rose-900/30 bg-dark-900/45 px-3 py-3">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm text-white font-medium">${escapeHtml(row.title)}</div>
                  <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(row.meta)}</div>
                </div>
                <div class="text-[11px] text-gray-500">${escapeHtml(row.occurredAt)}</div>
              </div>
              <div class="text-xs text-gray-300 mt-2">${escapeHtml(row.detail)}</div>
            </div>
          `).join('') : '<div class="text-xs text-gray-500">최근 에러가 없습니다.</div>'}
        </div>
      </section>
      <section class="rounded-2xl border border-amber-900/40 bg-amber-950/10 px-4 py-4">
        <div class="text-xs uppercase tracking-[0.12em] text-amber-300">Repeated Incidents</div>
        <div class="mt-3 space-y-2">
          ${obs.incidentRows.length ? obs.incidentRows.map((row) => `
            <div class="rounded-xl border border-amber-900/30 bg-dark-900/45 px-3 py-3">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm text-white font-medium">${escapeHtml(row.title)}</div>
                  <div class="text-[11px] text-gray-500 mt-1">${escapeHtml(row.meta)}</div>
                </div>
                <div class="text-[11px] text-gray-500">${escapeHtml(row.lastSeenAt)}</div>
              </div>
              <div class="text-xs text-gray-300 mt-2">${escapeHtml(row.detail)}</div>
              ${row.ownerNote ? `<div class="text-[11px] text-amber-200 mt-2">메모 · ${escapeHtml(row.ownerNote)}</div>` : ''}
              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onclick="updateIncidentStatus('${escapeHtml(row.fingerprint)}', 'OPEN')"
                  class="rounded-full border px-2 py-1 text-[11px] transition ${row.status === 'OPEN' ? 'border-amber-300 text-white' : 'border-gray-600 text-gray-300 hover:border-amber-300 hover:text-white'}"
                >
                  OPEN
                </button>
                <button
                  type="button"
                  onclick="updateIncidentStatus('${escapeHtml(row.fingerprint)}', 'RESOLVED')"
                  class="rounded-full border px-2 py-1 text-[11px] transition ${row.status === 'RESOLVED' ? 'border-emerald-300 text-white' : 'border-gray-600 text-gray-300 hover:border-emerald-300 hover:text-white'}"
                >
                  RESOLVED
                </button>
                <button
                  type="button"
                  onclick="updateIncidentStatus('${escapeHtml(row.fingerprint)}', 'MUTED')"
                  class="rounded-full border px-2 py-1 text-[11px] transition ${row.status === 'MUTED' ? 'border-sky-300 text-white' : 'border-gray-600 text-gray-300 hover:border-sky-300 hover:text-white'}"
                >
                  MUTED
                </button>
                <button
                  type="button"
                  onclick="editIncidentNote('${escapeHtml(row.fingerprint)}', '${escapeHtml(encodeURIComponent(row.ownerNote || ''))}')"
                  class="rounded-full border border-gray-600 px-2 py-1 text-[11px] text-gray-300 hover:border-amber-300 hover:text-white transition"
                >
                  메모
                </button>
              </div>
            </div>
          `).join('') : '<div class="text-xs text-gray-500">누적 incident가 없습니다.</div>'}
        </div>
      </section>
    </div>
  `;
}

function createErrorObservabilityDashboard(observabilityState) {
  const div = document.createElement('div');
  div.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble';
  const obs = observabilityState;
  const selectedObservabilityHours = Number(window.performanceObservabilityHours || 24);
  const recentCount = Array.isArray(obs.recentErrors) ? obs.recentErrors.length : 0;
  const incidentCount = Array.isArray(obs.incidentRows) ? obs.incidentRows.length : 0;

  div.innerHTML = `
    <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
      <div class="flex items-start justify-between gap-3 mb-3">
        <div>
          <div class="text-lg font-bold text-white">🚨 에러 관측</div>
          <div class="text-sm text-gray-400 mt-1">장중에 쌓인 예외와 반복 incident를 저녁 점검 관점에서 따로 봅니다.</div>
          <div class="mt-2 text-[11px] text-gray-500">${escapeHtml(obs.machine.host)} · 최근 ${escapeHtml(obs.machine.latestCollectedAt)} · ${escapeHtml(String(obs.window.hours || 24))}h / ${escapeHtml(obs.window.resolution || 'raw')}</div>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" onclick="loadErrorObservabilityView(24)" class="rounded-full border px-3 py-1 text-[11px] transition ${selectedObservabilityHours === 24 ? 'border-rose-400 text-white' : 'border-gray-600 text-gray-300 hover:border-rose-400 hover:text-white'}">24시간</button>
          <button type="button" onclick="loadErrorObservabilityView(168)" class="rounded-full border px-3 py-1 text-[11px] transition ${selectedObservabilityHours === 168 ? 'border-rose-400 text-white' : 'border-gray-600 text-gray-300 hover:border-rose-400 hover:text-white'}">7일</button>
        </div>
      </div>
      <div class="news-overview-grid mb-4">
        <div class="news-overview-card">
          <div class="news-overview-label">최근 에러</div>
          <div class="news-overview-value">${escapeHtml(String(recentCount))}</div>
          <div class="news-overview-help">현재 창에서 보여주는 최근 개별 예외 수</div>
        </div>
        <div class="news-overview-card">
          <div class="news-overview-label">반복 incident</div>
          <div class="news-overview-value">${escapeHtml(String(incidentCount))}</div>
          <div class="news-overview-help">fingerprint로 묶인 누적 문제 수</div>
        </div>
        <div class="news-overview-card">
          <div class="news-overview-label">머신 정보</div>
          <div class="news-overview-value text-base">${escapeHtml(obs.machine.host)}</div>
          <div class="news-overview-help">${escapeHtml(obs.machine.runtime)} · ${escapeHtml(obs.machine.platform)}</div>
        </div>
      </div>
      ${renderErrorObservabilityPanels(obs)}
      <div class="mt-4 flex justify-end">
        <button type="button" onclick="loadObservabilityView(${selectedObservabilityHours})" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">
          시스템 관측으로 돌아가기
        </button>
      </div>
    </section>
  `;
  return div;
}

function createPerformanceDashboard(state) {
  const div = document.createElement('div');
  div.className = 'bg-dark-700 rounded-xl p-5 border border-gray-600 mx-2 chat-bubble';

  div.innerHTML = `
    <div class="flex items-start justify-between gap-3 mb-4">
      <div>
        <div class="text-lg font-bold text-white">📈 성과 분석</div>
        <div class="text-xs text-gray-500 mt-1">뉴스 전략, Shadow, 주간/월간 성과를 한 화면에서 비교합니다.</div>
      </div>
      <div class="flex items-center gap-2">
        <button type="button" onclick="loadPerformanceView()" class="text-[11px] text-gray-400 hover:text-gray-200 transition">새로고침</button>
        <button type="button" onclick="openSettingsModal('news')" class="rounded-full border border-gray-600 px-3 py-1 text-[11px] text-gray-200 hover:border-blue-400 hover:text-white transition">뉴스 설정 열기</button>
      </div>
    </div>
    ${state.baseline.active ? `
      <section class="rounded-2xl border border-amber-700/50 bg-amber-950/20 px-4 py-4 mb-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.12em] text-amber-300">Trade Baseline</div>
            <div class="mt-1 text-sm font-medium text-white">${escapeHtml(state.baseline.label)}</div>
            <div class="mt-1 text-sm text-gray-300">${escapeHtml(state.baseline.summary)}</div>
          </div>
          <div class="rounded-full border border-amber-700/50 px-3 py-1 text-[11px] text-amber-200">${escapeHtml(state.baseline.effectiveDate || '-')}</div>
        </div>
        ${state.baseline.details.length ? `
          <div class="mt-3 space-y-1 text-[11px] leading-5 text-gray-400">
            ${state.baseline.details.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
          </div>
        ` : ''}
      </section>
    ` : ''}
    <section class="rounded-2xl border border-sky-800/50 bg-sky-950/20 px-4 py-4 mb-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-xs uppercase tracking-[0.12em] text-sky-300">Current Account</div>
          <div class="mt-1 text-sm text-gray-300">닫힌 거래 성과와 별개로 현재 계좌 기준 상태를 함께 봅니다.</div>
          ${state.helperLabel ? `<div class="mt-2 text-[11px] text-sky-200">${escapeHtml(state.helperLabel)}</div>` : ''}
          ${state.currentAccount.warning ? `<div class="mt-2 text-[11px] text-amber-300">${escapeHtml(state.currentAccount.warning)}</div>` : ''}
        </div>
        <div class="text-[11px] text-sky-200">${state.currentAccount.synced ? '브로커 동기화 완료' : '브로커 동기화 실패'}</div>
      </div>
      <div class="news-overview-grid mt-4">
        <div class="news-overview-card">
          <div class="news-overview-label">현재 미실현 손익</div>
          <div class="news-overview-value">${escapeHtml(state.currentAccount.unrealizedPnl)}</div>
          <div class="news-overview-help">${escapeHtml(state.currentAccount.unrealizedPnlRate)}</div>
        </div>
        <div class="news-overview-card">
          <div class="news-overview-label">현재 보유</div>
          <div class="news-overview-value">${escapeHtml(state.currentAccount.holdingCount)}</div>
          <div class="news-overview-help">브로커 보유 종목 수</div>
        </div>
        <div class="news-overview-card">
          <div class="news-overview-label">미체결 주문</div>
          <div class="news-overview-value">${escapeHtml(state.currentAccount.pendingOrderCount)}</div>
          <div class="news-overview-help">현재 남아 있는 주문</div>
        </div>
        <div class="news-overview-card">
          <div class="news-overview-label">총자산</div>
          <div class="news-overview-value">${escapeHtml(state.currentAccount.totalAsset)}</div>
          <div class="news-overview-help">현재 계좌 스냅샷</div>
        </div>
      </div>
    </section>
    <div class="news-overview-grid mb-4">
      ${state.summaryCards.map((card) => `
        <div class="news-overview-card">
          <div class="news-overview-label">${escapeHtml(card.label)}</div>
          <div class="news-overview-value">${escapeHtml(card.value)}</div>
        </div>
      `).join('')}
    </div>
    <div class="grid gap-4 xl:grid-cols-[1.2fr,0.8fr] mb-4">
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Shadow / Rollout</div>
        <div class="mt-2 text-xl font-semibold text-white">${escapeHtml(state.rollout.status)}</div>
        <div class="mt-1 text-sm text-gray-400">${escapeHtml(state.rollout.reason)}</div>
        ${state.rollout.details.length ? `
          <div class="mt-3 space-y-1 rounded-2xl border border-gray-700 bg-dark-950/40 px-3 py-3 text-[11px] leading-5 text-gray-300">
            ${state.rollout.details.map((line) => `<div>${escapeHtml(line)}</div>`).join('')}
          </div>
        ` : ''}
        <div class="mt-3 grid grid-cols-2 gap-3 text-sm">
          ${state.shadowSummaryRows.map((item) => `
            <div>
              <div class="text-gray-500">${escapeHtml(item.label)}</div>
              <div class="mt-1 font-semibold text-white">${escapeHtml(item.value)}</div>
            </div>
          `).join('')}
        </div>
        ${state.rollout.checks.length ? `
          <div class="mt-3 grid gap-2">
            ${state.rollout.checks.map((item) => `
              <div class="rounded-2xl border px-3 py-2 ${item.passed ? 'border-emerald-700/50 bg-emerald-950/20' : 'border-amber-700/50 bg-amber-950/20'}">
                <div class="flex items-center justify-between gap-2">
                  <div class="text-[11px] font-medium ${item.passed ? 'text-emerald-300' : 'text-amber-300'}">${escapeHtml(item.label)}</div>
                  <div class="text-[10px] ${item.passed ? 'text-emerald-400' : 'text-amber-400'}">${item.passed ? '통과' : '확인 필요'}</div>
                </div>
                <div class="mt-1 text-[11px] text-white">${escapeHtml(item.actual)}</div>
                <div class="mt-1 text-[10px] text-gray-500">기준 ${escapeHtml(item.target)}</div>
              </div>
            `).join('')}
          </div>
        ` : ''}
      </section>
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="text-xs uppercase tracking-[0.12em] text-gray-500">News Ops</div>
        <div class="mt-3 grid grid-cols-2 gap-3 text-sm">
          <div><div class="text-gray-500">뉴스 게이트</div><div class="text-white font-semibold mt-1">${escapeHtml(state.newsOps.newsGateBlocks)}</div></div>
          <div><div class="text-gray-500">재검증</div><div class="text-white font-semibold mt-1">${escapeHtml(state.newsOps.newsRechecks)}</div></div>
          <div><div class="text-gray-500">평균 부정 압력</div><div class="text-white font-semibold mt-1">${escapeHtml(state.newsOps.avgNegativePressure)}</div></div>
          <div><div class="text-gray-500">Shadow 차단율</div><div class="text-white font-semibold mt-1">${escapeHtml(state.newsOps.shadowBlockRate)}</div></div>
        </div>
      </section>
    </div>
    <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4 mb-4">
      <div class="flex items-center justify-between gap-3 mb-3">
        <div>
          <div class="text-xs uppercase tracking-[0.12em] text-gray-500">News vs Plain</div>
          <div class="text-sm text-gray-400 mt-1">뉴스 메타가 남은 거래와 일반 거래의 실제 성과 비교</div>
        </div>
        <div class="grid grid-cols-3 gap-3 text-right text-[11px] text-gray-500">
          <span>E 차이 ${escapeHtml(state.comparisonDelta.expectancy)}</span>
          <span>PF 차이 ${escapeHtml(state.comparisonDelta.profitFactor)}</span>
          <span>비용차감 ${escapeHtml(state.comparisonDelta.netPnlAfterCost)}</span>
        </div>
      </div>
      ${renderMetricRows(state.comparisonRows, '비교할 거래 표본이 아직 없습니다.')}
    </section>
    <div class="grid gap-4 xl:grid-cols-2 mb-4">
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div>
            <div class="text-xs uppercase tracking-[0.12em] text-gray-500">By Horizon</div>
            <div class="text-sm text-gray-400 mt-1">단기/중기/장기 성과 비교</div>
          </div>
          <div class="performance-table-head">
            <span>건수</span><span>E</span><span>PF</span><span>손익</span>
          </div>
        </div>
        ${renderMetricRows(state.byHorizonRows, '호라이즌 집계가 아직 없습니다.')}
      </section>
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div>
            <div class="text-xs uppercase tracking-[0.12em] text-gray-500">By Strategy</div>
            <div class="text-sm text-gray-400 mt-1">전략별 기대값과 손익 비교</div>
          </div>
          <div class="performance-table-head">
            <span>건수</span><span>E</span><span>PF</span><span>손익</span>
          </div>
        </div>
        ${renderMetricRows(state.byStrategyRows, '전략 집계가 아직 없습니다.')}
      </section>
    </div>
    <div class="grid gap-4 xl:grid-cols-2">
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div>
            <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Weekly</div>
            <div class="text-sm text-gray-400 mt-1">최근 주간 성과</div>
          </div>
          <div class="performance-table-head compact">
            <span>E</span><span>PF</span><span>손익</span>
          </div>
        </div>
        ${renderPeriodRows(state.weeklyRows, '주간 집계 대기 중입니다.')}
      </section>
      <section class="rounded-2xl border border-gray-700 bg-dark-900/40 px-4 py-4">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div>
            <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Monthly</div>
            <div class="text-sm text-gray-400 mt-1">최근 월간 성과</div>
          </div>
          <div class="performance-table-head compact">
            <span>E</span><span>PF</span><span>손익</span>
          </div>
        </div>
        ${renderPeriodRows(state.monthlyRows, '월간 집계 대기 중입니다.')}
      </section>
    </div>
  `;

  return div;
}

async function loadPerformanceView(observabilityHours = null) {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">성과 분석 불러오는 중...</div>';
  cleanupStockCards();

  try {
    const [summaryJson, weeklyJson, monthlyJson, overviewJson] = await Promise.all([
      fetchJson(`${API}/performance/summary?days=30`),
      fetchJson(`${API}/performance/periodic?period=weekly&size=6`),
      fetchJson(`${API}/performance/periodic?period=monthly&size=6`),
      fetchJson(`${API}/news/overview?recent_limit=4&performance_days=30`),
    ]);
    const state = buildPerformanceDashboardState({
      summary: summaryJson?.data || {},
      weekly: weeklyJson?.data || {},
      monthly: monthlyJson?.data || {},
      newsOverview: overviewJson?.data || {},
    });
    if (overviewJson?.data) {
      newsOverviewSnapshot = overviewJson.data;
      renderSidebarSettingSummaries();
      renderNewsOverviewPanels();
    }
    container.innerHTML = '';
    container.appendChild(createPerformanceDashboard(state));
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">성과 분석 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

async function loadObservabilityView(observabilityHours = null) {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">시스템 관측 불러오는 중...</div>';
  cleanupStockCards();
  const resolvedObservabilityHours = Number(observabilityHours || window.performanceObservabilityHours || 24);
  window.performanceObservabilityHours = resolvedObservabilityHours;
  const observabilityPoints = resolvedObservabilityHours > 48 ? 168 : 120;

  try {
    const observabilityJson = await fetchJson(`${API}/observability/overview?hours=${resolvedObservabilityHours}&points=${observabilityPoints}`);
    const observabilityState = observabilityJson?.data
      ? buildObservabilityDashboardState(observabilityJson.data)
      : null;
    container.innerHTML = '';
    if (!observabilityState) {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">관측 데이터가 아직 없습니다.</div>';
      return;
    }
    container.appendChild(createObservabilityDashboard(observabilityState));
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">시스템 관측 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

async function loadErrorObservabilityView(observabilityHours = null) {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">에러 관측 불러오는 중...</div>';
  cleanupStockCards();
  const resolvedObservabilityHours = Number(observabilityHours || window.performanceObservabilityHours || 24);
  window.performanceObservabilityHours = resolvedObservabilityHours;
  const observabilityPoints = resolvedObservabilityHours > 48 ? 168 : 120;

  try {
    const observabilityJson = await fetchJson(`${API}/observability/overview?hours=${resolvedObservabilityHours}&points=${observabilityPoints}`);
    const observabilityState = observabilityJson?.data
      ? buildObservabilityDashboardState(observabilityJson.data)
      : null;
    container.innerHTML = '';
    if (!observabilityState) {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">에러 관측 데이터가 아직 없습니다.</div>';
      return;
    }
    container.appendChild(createErrorObservabilityDashboard(observabilityState));
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">에러 관측 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

async function updateIncidentStatus(fingerprint, status) {
  try {
    setStatus('runtime', `incident 상태를 ${status}로 변경 중...`);
    const json = await fetchJson(`${API}/observability/incidents/${encodeURIComponent(fingerprint)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    setStatus('runtime', json?.message || `incident 상태가 ${status}로 변경되었습니다.`);
    await loadErrorObservabilityView(window.performanceObservabilityHours || 24);
  } catch (err) {
    setStatus('error', err.message || 'incident 상태 변경 실패');
  }
}

async function editIncidentNote(fingerprint, currentNoteEncoded = '') {
  const currentNote = currentNoteEncoded ? decodeURIComponent(currentNoteEncoded) : '';
  const nextNote = window.prompt('incident 메모를 입력하세요. 비우면 메모를 제거합니다.', currentNote || '');
  if (nextNote === null) return;

  try {
    setStatus('runtime', 'incident 메모 저장 중...');
    const json = await fetchJson(`${API}/observability/incidents/${encodeURIComponent(fingerprint)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_note: nextNote }),
    });
    setStatus('runtime', json?.message || 'incident 메모가 저장되었습니다.');
    await loadErrorObservabilityView(window.performanceObservabilityHours || 24);
  } catch (err) {
    setStatus('error', err.message || 'incident 메모 저장 실패');
  }
}

async function loadReportsArchive() {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">과거 리포트 불러오는 중...</div>';
  cleanupStockCards();
  try {
    const json = await fetchJson(`${API}/reports?limit=90`);
    const reports = json?.data || [];
    if (!reports.length) {
      container.innerHTML = '<div class="text-center text-gray-500 text-sm py-8">저장된 리포트가 없습니다</div>';
      return;
    }

    const listMarkup = reports.map((rawReport) => {
      const report = normalizeReportSummaryMetrics(rawReport);
      const archiveState = buildReportArchiveCardState(report);
      return `
      <button
        type="button"
        class="w-full rounded-xl border border-gray-700 bg-dark-900/50 p-4 text-left hover:border-blue-500/60 hover:bg-dark-900 transition"
        data-archive-report-date="${escapeHtml(archiveState.dateLabel)}"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="text-sm font-medium text-white">${escapeHtml(archiveState.dateLabel)}</div>
          <div class="text-xs text-gray-500">상세 보기</div>
        </div>
        <div class="mt-2 text-xs text-gray-400">
          ${escapeHtml(archiveState.summaryLabel)}
        </div>
        <div class="mt-3 rounded-xl border border-gray-700/70 bg-dark-800/70 px-3 py-2">
          <div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">뉴스 비교</div>
          <div class="mt-1 text-xs text-gray-300">${escapeHtml(archiveState.comparison.headline)}</div>
          <div class="mt-1 text-[11px] ${archiveState.comparison.ready ? 'text-emerald-300' : 'text-gray-500'}">${escapeHtml(archiveState.comparison.deltaLabel)}</div>
        </div>
      </button>
    `;
    }).join('');

    container.innerHTML = `
      <div class="mx-2 rounded-xl border border-gray-700 bg-dark-700/80 p-4 chat-bubble">
        <div class="text-lg font-bold text-white">🗂 과거 리포트 아카이브</div>
        <div class="text-xs text-gray-500 mt-1">날짜를 눌러 해당 리포트를 중앙 화면에서 확인합니다.</div>
      </div>
      <div class="mx-2 mt-3 grid gap-2">${listMarkup}</div>
    `;

    container.querySelectorAll('[data-archive-report-date]').forEach((button) => {
      button.addEventListener('click', () => {
        const date = button.dataset.archiveReportDate;
        if (date) switchToReport(date);
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">리포트 아카이브 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

function formatDateInputValue(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
}

function createDefaultNewsArchiveFilters() {
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - 6);
  return {
    published_from: formatDateInputValue(from),
    published_to: formatDateInputValue(today),
    source_code: '',
    symbol: '',
    sentiment_label: '',
    query: '',
  };
}

function getNewsArchiveFilters() {
  if (!newsArchiveFilters) {
    newsArchiveFilters = createDefaultNewsArchiveFilters();
  }
  return { ...newsArchiveFilters };
}

function buildNewsArchiveQuery(filters) {
  const params = new URLSearchParams();
  Object.entries(filters || {}).forEach(([key, value]) => {
    if (value != null && String(value).trim()) {
      params.set(key, String(value).trim());
    }
  });
  params.set('limit', '200');
  return params.toString();
}

function renderNewsArchiveView(state) {
  const countSummary = buildNewsArchiveCountSummary({
    filteredCount: state.totalCount,
    overallCount: state.overallCount,
  });
  const sourceOptions = [
    '<option value="">전체 소스</option>',
    ...state.sourceOptions.map((item) => (
      `<option value="${escapeHtml(item.code)}" ${state.filters.source_code === item.code ? 'selected' : ''}>${escapeHtml(item.code)} · ${escapeHtml(item.name)}</option>`
    )),
  ].join('');
  const sentimentOptions = state.sentimentOptions.map((item) => (
    `<option value="${escapeHtml(item.value)}" ${state.filters.sentiment_label === item.value ? 'selected' : ''}>${escapeHtml(item.label)}</option>`
  )).join('');

  const groupMarkup = state.groups.map((group) => {
    const itemsMarkup = group.items.map((item) => `
      <article class="rounded-xl border border-gray-700 bg-dark-900/55 p-4">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
              <span>${escapeHtml(item.timeLabel)}</span>
              <span>${escapeHtml(item.sourceCode)}</span>
              <span>${escapeHtml(item.regionLabel)}</span>
              <span class="rounded-full border px-2 py-0.5 ${item.sentimentToneClass}">${escapeHtml(item.sentimentLabel)}</span>
            </div>
            <div class="mt-2 text-sm font-semibold text-white leading-6">${escapeHtml(item.title)}</div>
            ${item.summary ? `<div class="mt-2 text-xs leading-5 text-gray-300">${escapeHtml(item.summary)}</div>` : ''}
            ${item.hasTranslation && item.originalTitle ? `<div class="mt-2 text-[11px] text-gray-500">원문: ${escapeHtml(item.originalTitle)}</div>` : ''}
          </div>
          ${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="shrink-0 rounded-lg border border-gray-700 px-3 py-1.5 text-[11px] text-gray-300 hover:border-blue-500/50 hover:text-white">원문</a>` : ''}
        </div>
        <div class="mt-3 flex flex-wrap gap-2 text-[11px] text-gray-400">
          <span class="rounded-full border border-gray-700 px-2 py-1">심볼 ${escapeHtml(item.symbolLabel)}</span>
          ${item.sectorLabel ? `<span class="rounded-full border border-gray-700 px-2 py-1">섹터 ${escapeHtml(item.sectorLabel)}</span>` : ''}
          <span class="rounded-full border border-gray-700 px-2 py-1">${escapeHtml(item.impactLabel)}</span>
          <span class="rounded-full border border-gray-700 px-2 py-1">${escapeHtml(item.trustLabel)}</span>
        </div>
        <div class="mt-3 flex justify-end">
          <button type="button" data-news-archive-detail-id="${escapeHtml(item.id)}" class="rounded-lg border border-gray-700 px-3 py-1.5 text-[11px] text-gray-300 hover:border-blue-500/50 hover:text-white">상세 보기</button>
        </div>
      </article>
    `).join('');

    return `
      <section class="mx-2 mt-4 rounded-2xl border border-gray-700 bg-dark-800/70 p-4 chat-bubble">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-base font-semibold text-white">${escapeHtml(group.dateLabel)}</div>
            <div class="text-[11px] text-gray-500">${escapeHtml(group.dateKey)} · ${group.count}건</div>
          </div>
        </div>
        <div class="mt-3 grid gap-3">${itemsMarkup}</div>
      </section>
    `;
  }).join('');

  return `
    <section class="mx-2 rounded-2xl border border-gray-700 bg-dark-700/80 p-5 chat-bubble">
      <div class="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div class="text-lg font-bold text-white">🗞 뉴스 아카이브</div>
          <div class="mt-1 text-xs text-gray-400">날짜별로 적재된 뉴스를 모아서 보고, 소스/종목/감성 기준으로 바로 좁혀볼 수 있습니다.</div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center text-xs">
          <div class="rounded-xl border border-gray-700 bg-dark-900/60 px-3 py-2">
            <div class="text-gray-500">현재 결과</div>
            <div class="mt-1 text-sm font-semibold text-white">${countSummary.filteredLabel}</div>
          </div>
          <div class="rounded-xl border border-gray-700 bg-dark-900/60 px-3 py-2">
            <div class="text-gray-500">전체 적재</div>
            <div class="mt-1 text-sm font-semibold text-white">${countSummary.overallLabel}</div>
          </div>
          <div class="rounded-xl border border-gray-700 bg-dark-900/60 px-3 py-2">
            <div class="text-gray-500">날짜 그룹</div>
            <div class="mt-1 text-sm font-semibold text-white">${state.groupCount}</div>
          </div>
        </div>
      </div>
      <div class="mt-3 text-xs text-gray-500">${escapeHtml(countSummary.helper)}</div>
      <form id="news-archive-filter-form" class="mt-4 grid gap-3 xl:grid-cols-6">
        <label class="text-xs text-gray-400">
          시작일
          <input type="date" name="published_from" value="${escapeHtml(state.filters.published_from)}" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200" />
        </label>
        <label class="text-xs text-gray-400">
          종료일
          <input type="date" name="published_to" value="${escapeHtml(state.filters.published_to)}" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200" />
        </label>
        <label class="text-xs text-gray-400">
          소스
          <select name="source_code" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200">${sourceOptions}</select>
        </label>
        <label class="text-xs text-gray-400">
          심볼
          <input type="text" name="symbol" value="${escapeHtml(state.filters.symbol)}" placeholder="005930" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200" />
        </label>
        <label class="text-xs text-gray-400">
          감성
          <select name="sentiment_label" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200">${sentimentOptions}</select>
        </label>
        <label class="text-xs text-gray-400">
          검색
          <input type="text" name="query" value="${escapeHtml(state.filters.query)}" placeholder="제목/요약 검색" class="mt-1 w-full rounded-lg border border-gray-700 bg-dark-900 px-3 py-2 text-sm text-gray-200" />
        </label>
        <div class="xl:col-span-6 flex flex-wrap gap-2">
          <button type="submit" class="rounded-lg border border-blue-500/50 bg-blue-500/10 px-4 py-2 text-sm text-blue-200 hover:bg-blue-500/15">필터 적용</button>
          <button type="button" id="news-archive-reset" class="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:border-gray-500">최근 7일로 초기화</button>
        </div>
      </form>
      ${state.sourceSummary.length ? `
        <div class="mt-4">
          <div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">소스별 건수</div>
          <div class="mt-2 flex flex-wrap gap-2">
            ${state.sourceSummary.map((item) => `
              <div class="rounded-full border border-gray-700 bg-dark-900/60 px-3 py-1.5 text-[11px] text-gray-300">
                <strong class="text-white">${escapeHtml(item.code)}</strong>
                <span class="ml-1 text-gray-500">${item.count}건</span>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}
    </section>
    ${state.emptyMessage
      ? `<div class="mx-2 mt-4 rounded-xl border border-gray-700 bg-dark-800/70 px-4 py-8 text-center text-sm text-gray-400 chat-bubble">${escapeHtml(state.emptyMessage)}</div>`
      : groupMarkup}
  `;
}

function renderNewsArchiveDetailModal(item) {
  const titleEl = document.getElementById('news-archive-detail-title');
  const bodyEl = document.getElementById('news-archive-detail-body');
  if (!titleEl || !bodyEl) return;
  if (!item) {
    titleEl.textContent = '뉴스 상세';
    bodyEl.innerHTML = '<div class="rounded-xl border border-gray-700 bg-dark-900/60 p-4 text-sm text-gray-400">표시할 뉴스가 없습니다.</div>';
    return;
  }
  const sectorLabels = Array.isArray(item.metadata?.matched_sector_labels)
    ? item.metadata.matched_sector_labels.filter(Boolean).join(', ')
    : '';
  const matchedNames = Array.isArray(item.metadata?.matched_stock_names)
    ? item.metadata.matched_stock_names.filter(Boolean).join(', ')
    : '';
  titleEl.textContent = item.title || '뉴스 상세';
  bodyEl.innerHTML = `
    <section class="rounded-xl border border-gray-700 bg-dark-900/60 p-4">
      <div class="flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
        <span>${escapeHtml(item.timeLabel)}</span>
        <span>${escapeHtml(item.sourceCode)}</span>
        <span>${escapeHtml(item.regionLabel)}</span>
        <span class="rounded-full border px-2 py-0.5 ${item.sentimentToneClass}">${escapeHtml(item.sentimentLabel)}</span>
      </div>
      <div class="mt-3 text-base font-semibold text-white leading-7">${escapeHtml(item.title)}</div>
      ${item.summary ? `<div class="mt-3 text-sm leading-6 text-gray-300">${escapeHtml(item.summary)}</div>` : ''}
      ${item.hasTranslation && item.originalTitle ? `<div class="mt-4 rounded-xl border border-gray-700 bg-dark-800/70 p-3 text-xs text-gray-400"><div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">원문 제목</div><div class="mt-1 text-gray-300">${escapeHtml(item.originalTitle)}</div>${item.originalSummary ? `<div class="mt-2 text-gray-500">${escapeHtml(item.originalSummary)}</div>` : ''}</div>` : ''}
      <div class="mt-4 grid gap-2 md:grid-cols-2 text-xs text-gray-300">
        <div class="rounded-xl border border-gray-700 bg-dark-800/60 p-3">심볼: ${escapeHtml(item.symbolLabel)}</div>
        <div class="rounded-xl border border-gray-700 bg-dark-800/60 p-3">섹터: ${escapeHtml(item.sectorLabel || sectorLabels || '-')}</div>
        <div class="rounded-xl border border-gray-700 bg-dark-800/60 p-3">${escapeHtml(item.impactLabel)}</div>
        <div class="rounded-xl border border-gray-700 bg-dark-800/60 p-3">${escapeHtml(item.trustLabel)}</div>
      </div>
      ${(matchedNames || sectorLabels) ? `
        <div class="mt-4 rounded-xl border border-gray-700 bg-dark-800/60 p-3 text-xs text-gray-400">
          ${matchedNames ? `<div>매칭 종목명: <span class="text-gray-200">${escapeHtml(matchedNames)}</span></div>` : ''}
          ${sectorLabels ? `<div class="${matchedNames ? 'mt-2' : ''}">매칭 업종: <span class="text-gray-200">${escapeHtml(sectorLabels)}</span></div>` : ''}
        </div>
      ` : ''}
      ${item.url ? `<div class="mt-4"><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" class="inline-flex rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-xs text-blue-200 hover:bg-blue-500/15">원문 링크 열기</a></div>` : ''}
    </section>
  `;
}

async function loadNewsArchiveView(nextFilters = null) {
  const container = document.getElementById('chat-container');
  container.innerHTML = '<div class="text-center text-gray-500 text-sm py-4">뉴스 아카이브 불러오는 중...</div>';
  cleanupStockCards();
  newsArchiveFilters = {
    ...getNewsArchiveFilters(),
    ...(nextFilters || {}),
  };

  try {
    const query = buildNewsArchiveQuery(newsArchiveFilters);
    const [itemsJson, sourcesJson, overviewJson] = await Promise.all([
      fetchJson(`${API}/news/items?${query}`),
      fetchJson(`${API}/news/sources`),
      fetchJson(`${API}/news/overview?recent_limit=1&performance_days=30`),
    ]);
    const state = buildNewsArchiveState(itemsJson?.data || [], {
      filters: newsArchiveFilters,
      catalog: sourcesJson?.data?.sources || [],
    });
    state.overallCount = Number(overviewJson?.data?.ingestion?.total_count || 0);
    container.innerHTML = renderNewsArchiveView(state);

    const form = document.getElementById('news-archive-filter-form');
    if (form) {
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const formData = new FormData(form);
        loadNewsArchiveView(Object.fromEntries(formData.entries()));
      });
    }
    const resetButton = document.getElementById('news-archive-reset');
    if (resetButton) {
      resetButton.addEventListener('click', () => {
        loadNewsArchiveView(createDefaultNewsArchiveFilters());
      });
    }
    const itemMap = new Map();
    state.groups.forEach((group) => {
      group.items.forEach((item) => {
        itemMap.set(String(item.id), item);
      });
    });
    container.querySelectorAll('[data-news-archive-detail-id]').forEach((button) => {
      button.addEventListener('click', () => {
        const itemId = String(button.dataset.newsArchiveDetailId || '');
        activeNewsArchiveItem = itemMap.get(itemId) || null;
        renderNewsArchiveDetailModal(activeNewsArchiveItem);
        openNewsArchiveDetailModal();
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="text-center text-red-400 text-sm py-8">뉴스 아카이브 로드 실패: ${escapeHtml(err.message || '알 수 없는 오류')}</div>`;
  }
}

// ── Trade History ──
async function loadTradeHistory(dateStr, container, prefetched = null) {
  try {
    const json = prefetched ? { data: prefetched } : await fetchJson(`${API}/trades?target_date=${dateStr}`);
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
  const tradeCardState = buildTradeCardViewModel(t, type);
  const executionState = resolveTradeExecutionState({
    side: t?.side || 'BUY',
    status: t?.status || (type === 'pending' ? 'PENDING_CONFIRM' : 'CONFIRMED'),
    notes: t?.notes,
    hasExit: type === 'completed',
  });
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
      <div class="text-[11px] text-gray-400 mt-1">${escapeHtml(tradeCardState.executionStateLabel)}</div>
      ${tradeCardState.fillStatusLabel ? `<div class="text-[11px] text-amber-300 mt-1">${escapeHtml(tradeCardState.fillStatusLabel)}</div>` : ''}
      ${t.ai_confidence ? `<div class="text-xs text-gray-600 mt-1">신뢰도 ${(t.ai_confidence*100).toFixed(0)}% · ${t.strategy_type || ''}</div>` : ''}
    </div>`;
  }

  if (type === 'pending') {
    const conf = t.ai_confidence ? `신뢰도 ${(t.ai_confidence*100).toFixed(0)}%` : '';
    return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 border-yellow-500">
      <div class="flex justify-between items-center">
        <span class="text-sm text-white font-medium">${t.stock_name}<span class="text-gray-500 text-xs ml-1">${t.stock_symbol}</span></span>
        <span class="text-xs text-yellow-400">${escapeHtml(tradeCardState.executionStateLabel)} · ${t.quantity}주 @${t.entry_price.toLocaleString()}원</span>
      </div>
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>${time}${tradeCardState.fillStatusLabel ? ` · ${escapeHtml(tradeCardState.fillStatusLabel)}` : ''}</span>
        <span>${conf}</span>
      </div>
    </div>`;
  }

  // opened (매수)
  const conf = t.ai_confidence ? `신뢰도 ${(t.ai_confidence*100).toFixed(0)}%` : '';
  return `<div class="bg-dark-900 rounded-lg p-3 mb-2 border-l-2 border-red-500">
    <div class="flex justify-between items-center">
      <span class="text-sm text-white font-medium">${t.stock_name}<span class="text-gray-500 text-xs ml-1">${t.stock_symbol}</span></span>
      <span class="text-xs text-red-400">${escapeHtml(tradeCardState.executionStateLabel)} · ${t.quantity}주 @${t.entry_price.toLocaleString()}원</span>
    </div>
    <div class="flex justify-between text-xs text-gray-500 mt-1">
      <span>${time} · ${t.strategy_type || ''}</span>
      <span>${conf}</span>
    </div>
  </div>`;
}

async function reconcilePendingTrades(triggerButton = null) {
  const button = triggerButton || document.getElementById('trade-center-reconcile-button') || document.getElementById('reconcile-pending-trades');
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

async function resetOperationalBaseline(triggerButton = null) {
  const button = triggerButton || document.getElementById('reset-operational-baseline-button');
  const originalText = button?.textContent || 'DB 초기화';
  const confirmed = window.confirm(
    '운영 DB를 초기화하고 현재 브로커 상태를 기준선으로 다시 시작합니다.\n\n'
    + '설정은 유지되지만 거래 이력, 리포트, 활동 로그, 뉴스 적재 이력은 삭제됩니다.\n'
    + '초기화 직후 현재 잔고/보유/미체결을 다시 읽어와 새 기준선을 만듭니다.\n'
    + '과거 실현손익과 예전 리포트는 복원되지 않습니다.\n'
    + '계속할까요?'
  );
  if (!confirmed) return;

  try {
    if (button) {
      button.disabled = true;
      button.textContent = '초기화 중...';
    }
    const json = await fetchJson(`${API}/system/reset-operational-baseline`, { method: 'POST' }, 30000);
    await Promise.all([
      loadSettings(),
      loadAccountInfo(),
      loadNewsOverview(true),
      loadSystemStatus(),
      loadLLMUsage(),
    ]);
    if (currentView === 'performance') {
      await loadPerformanceView();
    }
    if (currentView === 'report') {
      await loadReportsArchive();
    }
    const snapshot = json?.data?.broker_snapshot || {};
    const statusMessage = snapshot?.synced
      ? `${json?.message || '운영 DB 초기화 완료'} · 잔고/보유/미체결 재동기화 완료`
      : (json?.message || '운영 DB 초기화 완료');
    setStatus('runtime', statusMessage);
  } catch (err) {
    console.error('Operational baseline reset error:', err);
    setStatus('error', err.message || '운영 DB 초기화 실패');
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalText;
    }
  }
}

async function backupOperationalDatabase(triggerButton = null) {
  const button = triggerButton || document.getElementById('backup-operational-db-button');
  const originalText = button?.textContent || 'DB 백업';

  try {
    if (button) {
      button.disabled = true;
      button.textContent = '백업 중...';
    }
    const json = await fetchJson(`${API}/system/backup-operational-db`, { method: 'POST' }, 30000);
    const relativePath = json?.data?.relative_path || json?.data?.filename || 'runtime/backups/db';
    setStatus('runtime', json?.message || `운영 DB 백업 완료 · ${relativePath}`);
  } catch (err) {
    console.error('Operational DB backup error:', err);
    setStatus('error', err.message || '운영 DB 백업 실패');
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
    applySettingsToForm(s);
    renderTierModelSelectors();
    renderStandaloneModelSelectors();
    updateBadge('badge-trading', s.TRADING_ENABLED ? '매매:ON' : '매매:OFF', s.TRADING_ENABLED ? 'green' : 'red');
    updateBadge('badge-mode', formatAutonomyModeLabel(s.AUTONOMY_MODE), 'purple');
    renderSettingGuidance();
    renderSidebarSettingSummaries();
    renderNewsOverviewPanels();
    renderStrategyInsightsPanel();
    renderRuntimeControls();
    refreshStockCardActions();
    if (latestAccountSnapshot) {
      renderPendingOrders(latestAccountSnapshot.pendingOrders || []);
      if (currentView === 'trades-center') {
        loadTradesCenterView(latestAccountSnapshot);
      }
      if (activePositionDetailPayload) {
        renderPositionDetailModal(activePositionDetailPayload);
      }
    }
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
      loadNewsOverview(),
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
    loadNewsOverview(),
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
  const readinessEl = document.getElementById('runtime-readiness-panel');
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
    sellAutomationReady,
    sellAutomationLabel,
    sellAutomationHelp,
  } = state;
  const autonomyLabel = formatAutonomyModeLabel(autonomyMode);

  const schedulerMismatch = state.schedulerMismatchMessage
    ? `<div class="text-yellow-300">${state.schedulerMismatchMessage}</div>`
    : '';

  if (summaryEl) {
    summaryEl.innerHTML = `
      <div>실행 상태: 에이전트 <span class="${agentRunning ? 'text-green-300' : 'text-yellow-300'}">${agentRunning ? '동작' : '중지'}</span> · 스케줄러 <span class="${schedulerRunning ? 'text-green-300' : 'text-yellow-300'}">${schedulerRunning ? '동작' : '중지'}</span></div>
      <div>주문 설정: <span class="${tradingEnabled ? 'text-green-300' : 'text-red-300'}">${tradingEnabled ? 'ON' : 'OFF'}</span> · ${escapeHtml(autonomyLabel)}</div>
      ${runtimeControlPending ? '<div class="text-blue-300">변경 적용 중...</div>' : ''}
    `;
  }
  if (readinessEl) {
    readinessEl.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-[11px] uppercase tracking-[0.12em] text-gray-500">Operation Readiness</div>
          <div class="mt-1 text-sm font-medium ${sellAutomationReady ? 'text-green-200' : 'text-yellow-200'}">${escapeHtml(sellAutomationLabel)}</div>
        </div>
        <div class="rounded-full border ${sellAutomationReady ? 'border-green-500/30 bg-green-500/10 text-green-200' : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200'} px-2.5 py-1 text-[11px]">
          ${sellAutomationReady ? 'LIVE READY' : 'CHECK NEEDED'}
        </div>
      </div>
      <div class="mt-2 text-[11px] leading-5 text-gray-400">${escapeHtml(sellAutomationHelp)}</div>
      <div class="mt-3 grid gap-2 md:grid-cols-3">
        <div class="rounded-lg border border-gray-800 bg-dark-800/70 px-3 py-2">
          <div class="text-[10px] uppercase tracking-[0.12em] text-gray-500">실주문</div>
          <div class="mt-1 text-sm font-medium ${tradingEnabled ? 'text-green-200' : 'text-red-200'}">${tradingEnabled ? 'ON' : 'OFF'}</div>
        </div>
        <div class="rounded-lg border border-gray-800 bg-dark-800/70 px-3 py-2">
          <div class="text-[10px] uppercase tracking-[0.12em] text-gray-500">주문 방식</div>
          <div class="mt-1 text-sm font-medium text-gray-100">${escapeHtml(autonomyLabel)}</div>
        </div>
        <div class="rounded-lg border border-gray-800 bg-dark-800/70 px-3 py-2">
          <div class="text-[10px] uppercase tracking-[0.12em] text-gray-500">스케줄러</div>
          <div class="mt-1 text-sm font-medium ${schedulerRunning ? 'text-green-200' : 'text-yellow-200'}">${schedulerRunning ? '동작' : '중지'}</div>
        </div>
      </div>
      ${schedulerMismatch ? `<div class="mt-3">${schedulerMismatch}</div>` : ''}
      <div class="mt-3 text-[11px] text-gray-500">헤더는 현재 상태만, 왼쪽은 운영 제어와 해석만 보여줍니다.</div>
    `;
  }

  Object.entries(state.buttonStates).forEach(([id, options]) => setControlButtonState(id, options));
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

function renderSidebarSettingSummaries() {
  const riskSummaryEl = document.getElementById('left-risk-summary');
  if (riskSummaryEl) {
    const riskLabel = formatRiskAppetiteLabel(runtimeSettings?.RISK_APPETITE || 'MODERATE');
    riskSummaryEl.textContent = `현재 ${riskLabel} · 눌러서 전략 설정 열기`;
  }
  const llmSummaryEl = document.getElementById('left-llm-summary');
  if (llmSummaryEl && runtimeSettings) {
    const tier1Provider = runtimeSettings.LLM_PROVIDER_TIER1 || runtimeSettings.LLM_PROVIDER || 'CLAUDE_CODE';
    const tier2Provider = runtimeSettings.LLM_PROVIDER_TIER2 || runtimeSettings.LLM_PROVIDER || 'CLAUDE_CODE';
    llmSummaryEl.textContent = `T1 ${tier1Provider} · T2 ${tier2Provider}`;
  }
  const newsSummaryEl = document.getElementById('left-news-summary');
  if (newsSummaryEl) {
    const provider = runtimeSettings?.NEWS_LLM_PROVIDER || 'CLAUDE_CODE';
    const includeForeign = runtimeSettings?.NEWS_INCLUDE_FOREIGN ? '해외 포함' : '국내 중심';
    const domesticMedia = runtimeSettings?.NEWS_DOMESTIC_MEDIA_ENABLED ? '국내 미디어 ON' : '국내 미디어 OFF';
    const recent24h = newsOverviewSnapshot?.ingestion?.recent_24h_count;
    const recentText = newsOverviewSnapshot?.storage?.ready === false
      ? '저장소 준비 필요'
      : (Number.isFinite(Number(recent24h)) ? `24h ${formatInteger(recent24h)}건` : '수집 전');
    newsSummaryEl.textContent = `${provider} · ${includeForeign} · ${domesticMedia} · ${recentText}`;
  }
}

function renderStrategyInsightsPanel() {
  const panelEl = document.getElementById('strategy-insights-panel');
  if (!panelEl) return;

  const viewModel = buildStrategyInsightsViewModel(runtimeSettings || {});
  const selected = viewModel.selected;

  if (!selected) {
    panelEl.innerHTML = '<div class="text-xs text-gray-500">전략 인사이트를 불러오지 못했습니다.</div>';
    return;
  }

  const optionMarkup = (viewModel.options || []).map((option) => `
    <div class="flex h-full flex-col rounded-xl border ${option.isSelected ? 'border-blue-500/60 bg-blue-500/10 shadow-[0_0_0_1px_rgba(59,130,246,0.08)]' : 'border-gray-800 bg-dark-800/60'} p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <div class="text-sm font-semibold text-white">${escapeHtml(option.label)}</div>
            <span class="text-[11px] font-medium tracking-[0.08em] text-gray-500">${escapeHtml(option.key)}</span>
          </div>
          <div class="mt-2 text-xs leading-5 text-gray-400">${escapeHtml(option.headline || '')}</div>
        </div>
        ${option.isSelected ? '<div class="shrink-0 rounded-full border border-blue-500/40 bg-blue-500/10 px-2.5 py-1 text-[11px] font-medium text-blue-200">현재 적용</div>' : ''}
      </div>
      <div class="mt-3 text-sm leading-6 text-gray-200">${escapeHtml(option.description || '')}</div>
      <div class="mt-auto pt-4 text-[11px] leading-5 text-gray-500">${escapeHtml(option.effectSummary || '')}</div>
    </div>
  `).join('');

  const contextMarkup = (viewModel.context || []).map((item) => `
    <div class="rounded-lg border border-gray-800 bg-dark-800/60 p-3">
      <div class="text-xs font-medium text-gray-400">${escapeHtml(item.label)}</div>
      <div class="mt-1 text-sm font-medium text-white">${escapeHtml(item.value || '')}</div>
      <div class="mt-1 text-xs leading-5 text-gray-500">${escapeHtml(item.description || '')}</div>
    </div>
  `).join('');

  panelEl.innerHTML = `
    <div class="flex items-start justify-between gap-3">
      <div>
        <div class="text-xs uppercase tracking-[0.12em] text-gray-500">Strategy Insight</div>
        <div class="mt-1 text-base font-semibold text-white">${escapeHtml(selected.label)} <span class="text-xs font-medium text-gray-500">${escapeHtml(selected.key)}</span></div>
        <div class="mt-1 text-sm text-blue-200">${escapeHtml(selected.headline || '')}</div>
      </div>
      <div class="rounded-full border border-blue-500/40 bg-blue-500/10 px-3 py-1 text-xs text-blue-200">현재 적용</div>
    </div>
    <div class="mt-4 rounded-lg border border-gray-800 bg-dark-800/70 p-3">
      <div class="text-xs font-medium text-gray-400">의미</div>
      <div class="mt-1 text-sm text-gray-200">${escapeHtml(selected.description || '')}</div>
    </div>
    <div class="mt-3 rounded-lg border border-gray-800 bg-dark-800/70 p-3">
      <div class="text-xs font-medium text-gray-400">실제 영향</div>
      <ul class="mt-2 space-y-1 text-sm text-gray-200">
        ${(selected.system_effects || []).map((item) => `<li>• ${escapeHtml(item)}</li>`).join('')}
      </ul>
    </div>
    ${optionMarkup ? `
      <div class="mt-3">
        <div class="text-xs font-medium text-gray-400">성향별 비교</div>
        <div class="mt-2 grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          ${optionMarkup}
        </div>
      </div>
    ` : ''}
    <div class="mt-3 rounded-lg border border-gray-800 bg-dark-800/70 p-3">
      <div class="text-xs font-medium text-gray-400">코드 기준 가이드</div>
      <div class="mt-1 whitespace-pre-wrap text-xs leading-5 text-gray-400">${escapeHtml(selected.guideline || '')}</div>
    </div>
    ${contextMarkup ? `
      <div class="mt-3">
        <div class="text-xs font-medium text-gray-400">현재 함께 작동하는 전략 입력</div>
        <div class="mt-2 grid gap-3 md:grid-cols-3">
          ${contextMarkup}
        </div>
      </div>
    ` : ''}
    ${viewModel.notes?.length ? `
      <div class="mt-3 rounded-lg border border-gray-800 bg-dark-800/70 p-3">
        <div class="text-xs font-medium text-gray-400">운용 메모</div>
        <ul class="mt-2 space-y-1 text-xs text-gray-400">
          ${viewModel.notes.map((item) => `<li>• ${escapeHtml(item)}</li>`).join('')}
        </ul>
      </div>
    ` : ''}
  `;
}

function applyControlButtonState(ids, options) {
  ids.forEach((id) => setControlButtonState(id, options));
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

async function applyRuntimePreset(preset) {
  if (runtimeControlPending) return;
  runtimeControlPending = true;
  renderRuntimeControls();

  const applySetting = async (key, value) => {
    const ok = await updateSetting(key, value);
    if (!ok) throw new Error(`${key} 적용 실패`);
  };

  const applyScheduler = async (shouldRun) => {
    const endpoint = shouldRun ? 'start' : 'stop';
    const resp = await fetch(`${API}/scheduler/${endpoint}`, { method: 'POST' });
    if (!resp.ok) {
      throw new Error(`스케줄러 ${shouldRun ? '시작' : '중지'} 실패`);
    }
  };

  try {
    if (preset === 'live-auto') {
      await applySetting('TRADING_ENABLED', true);
      await applySetting('AUTONOMY_MODE', 'AUTONOMOUS');
      await applySetting('SCHEDULER_ENABLED', true);
      await applyScheduler(true);
      setStatus('runtime', '자동 운영 시작 프리셋 적용 완료');
    } else if (preset === 'safe-review') {
      await applySetting('TRADING_ENABLED', false);
      await applySetting('AUTONOMY_MODE', 'SEMI_AUTO');
      await applySetting('SCHEDULER_ENABLED', false);
      await applyScheduler(false);
      setStatus('runtime', '안전 모드 프리셋 적용 완료');
    }
    await Promise.all([
      loadSettings(),
      loadSystemStatus(),
    ]);
  } catch (err) {
    console.error('Runtime preset error:', err);
    setStatus('error', err.message || '운영 프리셋 적용 실패');
  } finally {
    runtimeControlPending = false;
    renderRuntimeControls();
  }
}

function getTierProvider(tier, mode = 'primary') {
  const providerEl = document.getElementById(getTierProviderElementId(tier, mode));
  if (mode === 'fallback') {
    return providerEl?.value || '';
  }
  return providerEl?.value || 'CLAUDE_CODE';
}

function renderProviderModelSelector({
  provider,
  currentValue = 'DEFAULT',
  selectEl,
  sourceEl,
  customEl,
  disabledMessage = '',
  defaultSuffix = '[기본값]',
}) {
  if (!selectEl) return;

  if (!provider) {
    selectEl.innerHTML = '<option value="DEFAULT">없음</option>';
    selectEl.value = 'DEFAULT';
    selectEl.disabled = true;
    if (customEl) {
      customEl.value = '';
      customEl.disabled = true;
    }
    if (sourceEl) sourceEl.textContent = disabledMessage;
    return;
  }

  const providerCatalog = getCatalogProvider(llmCatalog, provider);
  const entries = buildProviderModelEntries(providerCatalog, currentValue, defaultSuffix);

  selectEl.innerHTML = entries.map((item) => {
    return `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label || item.value)}${item.suffix || ''}</option>`;
  }).join('');
  selectEl.value = currentValue;
  selectEl.disabled = false;

  if (customEl) {
    customEl.placeholder = getProviderModelPlaceholder(provider);
    customEl.value = '';
    customEl.disabled = false;
  }

  if (sourceEl) {
    sourceEl.textContent = buildProviderModelSourceText(providerCatalog, entries, currentValue);
  }
}

function renderTierModelSelectors() {
  renderTierModelSelector('tier1', 'primary');
  renderTierModelSelector('tier1', 'fallback');
  renderTierModelSelector('tier2', 'primary');
  renderTierModelSelector('tier2', 'fallback');
}

function renderStandaloneModelSelectors() {
  renderStandaloneModelSelector('manual');
  renderStandaloneModelSelector('manual', 'fallback');
  renderStandaloneModelSelector('news');
  renderStandaloneModelSelector('news', 'fallback');
}

function renderTierModelSelector(tier, mode = 'primary') {
  if (!runtimeSettings) return;
  const state = resolveTierModelState({
    runtimeSettings,
    tier,
    mode,
    provider: getTierProvider(tier, mode),
  });
  const selectEl = document.getElementById(state.selectId);
  const sourceEl = document.getElementById(state.sourceId);
  const customEl = document.getElementById(state.customId);
  if (!selectEl) return;

  if (!state.hasProvider) {
    renderProviderModelSelector({
      provider: '',
      currentValue: 'DEFAULT',
      selectEl,
      sourceEl,
      customEl,
      disabledMessage: 'fallback provider를 먼저 선택하세요',
    });
    return;
  }

  renderProviderModelSelector({
    provider: state.provider,
    currentValue: state.currentValue,
    selectEl,
    sourceEl,
    customEl,
    defaultSuffix: '[CLI 기본값]',
  });
}

function renderStandaloneModelSelector(kind, mode = 'primary') {
  if (!runtimeSettings) return;
  const providerElementId = mode === 'fallback'
    ? `set-${kind}-llm-fallback-provider`
    : `set-${kind}-llm-provider`;
  const state = getStandaloneModelSelectorState(
    kind,
    runtimeSettings,
    document.getElementById(providerElementId)?.value || '',
    mode,
  );
  const selectEl = document.getElementById(state.selectId);
  const sourceEl = document.getElementById(state.sourceId);
  const customEl = document.getElementById(state.customId);
  if (!selectEl) return;

  if (!state.hasProvider) {
    renderProviderModelSelector({
      provider: '',
      currentValue: 'DEFAULT',
      selectEl,
      sourceEl,
      customEl,
      disabledMessage: 'fallback provider를 먼저 선택하세요',
    });
    return;
  }

  renderProviderModelSelector({
    provider: state.provider,
    currentValue: state.currentValue,
    selectEl,
    sourceEl,
    customEl,
    defaultSuffix: '[provider 기본값]',
  });
}

async function loadLLMCatalog(forceRefresh = false) {
  try {
    const suffix = forceRefresh ? '?force_refresh=true' : '';
    const resp = await fetch(`${API}/llm/catalog${suffix}`);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const json = await resp.json();
    if (!json?.data) {
      throw new Error(json?.message || '카탈로그 응답이 비어 있습니다.');
    }
    llmCatalog = json.data;
    renderLLMCatalogMeta();
    renderTierModelSelectors();
    renderStandaloneModelSelectors();
    if (forceRefresh && json.message) {
      setStatus('warn', json.message);
    }
  } catch (err) {
    console.error('LLM catalog error:', err);
    const metaEl = document.getElementById('llm-catalog-meta');
    if (metaEl) metaEl.textContent = buildCatalogErrorCopy(err);
    setStatus('error', buildCatalogErrorCopy(err));
  }
}

function renderLLMCatalogMeta() {
  const metaEl = document.getElementById('llm-catalog-meta');
  if (!metaEl) return;
  metaEl.textContent = buildCatalogMetaText(llmCatalog);
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
    const leftLlmSummary = document.getElementById('left-llm-summary');
    if (leftLlmSummary) {
      leftLlmSummary.textContent = `T1 ${s.tier1.provider} · T2 ${s.tier2.provider}`;
    }
    const manualSelection = document.getElementById('llm-manual-selection');
    if (manualSelection && s.manual_selection) {
      const provider = s.manual_selection.provider || 'CLAUDE_CODE';
      const model = s.manual_selection.model || 'DEFAULT';
      const fallbackProvider = s.manual_selection.fallback_provider || '';
      const fallbackModel = s.manual_selection.fallback_model || 'DEFAULT';
      const modelLabel = model === 'DEFAULT' ? '기본값' : model;
      const fallbackLabel = fallbackProvider
        ? ` → ${fallbackProvider} (${fallbackModel === 'DEFAULT' ? '기본값' : fallbackModel})`
        : '';
      const label = `${provider} (${modelLabel})${fallbackLabel}`;
      manualSelection.textContent = `현재 리포트·수동 작업 선택: ${label}`;
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
    const marketSession = buildMarketSessionViewModel(s);
    updateBadge('badge-broker', `브로커:${brokerProvider}`, brokerBadgeTone);
    updateBadge('badge-market', marketSession.badgeLabel, marketSession.tone);
    updateBadge('badge-trading', s.trading_enabled ? '매매:ON' : '매매:OFF', s.trading_enabled ? 'green' : 'red');
    updateBadge('badge-mcp', mcpBadge.label, mcpBadge.tone);
    const statusEl = document.getElementById('sys-status');
    const operationItems = buildRuntimeOperationsViewModel(s);
    const operationsHtml = operationItems.map((item) => `
      <div class="rounded-lg border ${item.tone === 'red' ? 'border-red-500/30 bg-red-500/10 text-red-100' : item.tone === 'yellow' ? 'border-yellow-500/30 bg-yellow-500/10 text-yellow-100' : 'border-green-500/30 bg-green-500/10 text-green-100'} px-2.5 py-2">
        <div class="flex items-center gap-1.5">
          <span class="status-dot w-1.5 h-1.5 rounded-full ${item.dotClass}"></span>
          <strong>${escapeHtml(item.title)}:</strong> ${escapeHtml(item.label)}
        </div>
        <div class="mt-1 text-[11px] leading-4 opacity-90">${escapeHtml(item.message)}</div>
        ${item.meta ? `<div class="mt-1 text-[10px] text-gray-300">${escapeHtml(item.meta)}</div>` : ''}
      </div>
    `).join('');
    statusEl.innerHTML = `
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${marketSession.dotClass}"></span>
        <strong>${escapeHtml(marketSession.detailLabel)}</strong> (${escapeHtml(marketSession.extra)})
      </div>
      <div class="text-[11px] text-gray-400">${escapeHtml(marketSession.note)}</div>
      <div class="flex items-center gap-1.5">
        <span class="status-dot w-1.5 h-1.5 rounded-full ${mcpBadge.dotClass}"></span>
        MCP: ${escapeHtml(mcpBadge.detailLabel)}
      </div>
      ${operationsHtml}`;
    renderRuntimeControls();
    document.querySelectorAll('[data-cycle-trigger="true"]').forEach((btn) => {
      btn.textContent = marketSession.sessionCode === 'KRX_NXT'
        ? '▶ 매매 사이클 실행'
        : marketSession.sessionCode !== 'CLOSED'
          ? '▶ 장외 세션 점검 실행'
          : '▶ 장마감 리뷰 실행';
    });
  } catch (err) {
    console.error('Status load error:', err);
  }
}

// ── Report List ──
async function loadReportList() {
  try {
    const json = await fetchJson(`${API}/reports?limit=100`);
    const countEl = document.getElementById('report-archive-count');
    const count = Array.isArray(json?.data) ? json.data.length : 0;
    if (countEl) countEl.textContent = `(${count})`;
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

function getKstDateString() {
  try {
    const formatter = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
    return formatter.format(new Date());
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
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
  askQuestion,
  clearChat,
  fetchBloombergNews,
  fetchCnbcNews,
  fetchInvestingNews,
  fetchNasdaqNews,
  fetchSeekingAlphaNews,
  fetchDartNews,
  fetchYonhapNews,
  fetchKrxNews,
  backupOperationalDatabase,
  generateReport,
  loadLLMUsage,
  loadNewsOverview,
  loadObservabilityView,
  loadPerformanceView,
  loadErrorObservabilityView,
  loadTodayActivities,
  loadEventRadar,
  refreshLLMCatalog,
  refreshRuntimePanels,
  reconcilePendingTrades,
  resetOperationalBaseline,
  applyRuntimePreset,
  setAutonomyMode,
  setSchedulerRunning,
  setTradingEnabled,
  switchView,
  switchSettingsTab,
  toggleEventRadarPanel,
  togglePaneCollapse,
  toggleSidebarSection,
  triggerCycle,
  updateSetting,
  updateTierModelSetting,
  updateIncidentStatus,
  editIncidentNote,
  openSettingsModal,
  closeSettingsModal,
  closeSettingsModalOnBackdrop,
  openPositionDetailModal,
  closePositionDetailModal,
  closePositionDetailModalOnBackdrop,
  openNewsArchiveDetailModal,
  closeNewsArchiveDetailModal,
  closeNewsArchiveDetailOnBackdrop,
});
