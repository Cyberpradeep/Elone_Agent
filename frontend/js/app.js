/**
 * Elone SOP Governance Hub — application shell.
 * Auth gate, hash router, role-aware nav, view lifecycle, theme, API health,
 * nav badges, keyboard shortcuts, and the global `data-action` click delegation.
 */

import { api, AUTH_REQUIRED_EVENT } from './api.js';
import {
  initAuth, isAuthenticated, isHumanUser, hasCapability, canAccessView,
  clearSession, renderLoginHtml, mountLoginView, renderSidebarUserHtml,
} from './auth.js';
import { initChartTooltip } from './charts.js';
import {
  actions, registerActions, icon, esc, store, toast, skeleton, errorState,
  closeModal, isModalOpen, trapFocus, debounce,
} from './ui.js';

import overview from './views/overview.js';
import playbooks from './views/playbooks.js';
import review from './views/review.js';
import reviewTask from './views/review-task.js';
import catalog from './views/catalog.js';
import ingestion from './views/ingestion.js';
import tools from './views/tools.js';
import telemetry from './views/telemetry.js';
import audit from './views/audit.js';
import security from './views/security.js';
import settings from './views/settings.js';

const VIEWS = [overview, playbooks, review, reviewTask, catalog, ingestion, tools, telemetry, audit, security, settings];
const GROUPS = [
  ['Governance', ['overview', 'playbooks', 'review', 'catalog']],
  ['Ingestion & Operations', ['ingestion', 'tools']],
  ['Telemetry & Security', ['telemetry', 'audit', 'security']],
  ['System', ['settings']],
];

const state = {
  route: null,
  params: [],        // extra path segments, e.g. #/review/RT-123 -> ['RT-123']
  query: '',
  badges: { playbooks: null, pending: null },
  token: 0,          // guards against out-of-order renders
  data: null,
  abort: null,       // AbortController for the mounted view
  timer: null,
  healthTimer: null,
  badgeTimer: null,
};

const $ = id => document.getElementById(id);
const viewById = id => VIEWS.find(v => v.id === id);

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

function currentTheme() { return document.documentElement.getAttribute('data-theme') || 'dark'; }

function paintThemeButton() {
  const glyph = icon(currentTheme() === 'dark' ? 'sun' : 'moon');
  const btn = $('theme-toggle');
  if (btn) btn.innerHTML = glyph;
  const loginBtn = $('login-theme-toggle');
  if (loginBtn) loginBtn.innerHTML = glyph;
}

registerActions({
  'toggle-theme': () => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    store.set('theme', next);
    paintThemeButton();
  },
  'toggle-nav': () => document.body.classList.toggle('nav-open'),
  'retry-view': () => loadView(),
  'run-scan': () => {
    toast('Batch scanning is disabled (C1). Use individual document Ingest so Agent A3–A6 governance and HITL review execute.', 'warning', 7000);
  },
  'logout': async () => {
    await api.logout().catch(() => {});
    clearSession();
    closeModal();
    toast('Signed out.', 'info', 3000);
    showLogin();
  },
});

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function buildNav() {
  $('nav-menu').innerHTML = GROUPS.map(([label, ids]) => {
    const allowed = ids.filter(id => canAccessView(id));
    if (!allowed.length) return '';
    return `
      <span class="nav-category-label">${esc(label)}</span>
      ${allowed.map(id => {
        const v = viewById(id);
        return `<a href="#/${v.id}" class="nav-item" data-route="${v.id}">
          ${icon(v.icon)}<span>${esc(v.label)}</span>
          ${v.badge ? `<span class="nav-badge-count ${v.badge === 'pending' ? 'attention' : ''}" data-badge="${v.badge}" hidden></span>` : ''}
        </a>`;
      }).join('')}
    `;
  }).join('');
  $('nav-toggle').innerHTML = icon('menu');
  const cta = $('header-cta');
  if (cta) cta.hidden = !hasCapability('can_upload');
  const userHost = $('sidebar-user');
  if (userHost) userHost.innerHTML = renderSidebarUserHtml();
  paintThemeButton();
}

function paintNav() {
  document.querySelectorAll('.nav-item').forEach(a => {
    const active = a.dataset.route === (viewById(state.route)?.parent || state.route);
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
}

function paintBadges() {
  document.querySelectorAll('[data-badge]').forEach(el => {
    const n = state.badges[el.dataset.badge];
    el.hidden = n === null || n === undefined || (el.dataset.badge === 'pending' && n === 0);
    el.textContent = n ?? '';
  });
}

function setBadges(patch) { Object.assign(state.badges, patch); paintBadges(); }

async function refreshBadges() {
  if (!isAuthenticated() || !isHumanUser()) return;
  try {
    const { tasks } = await api.getReviewTasks();
    setBadges({ pending: (tasks || []).filter(t => t.status === 'pending').length });
  } catch { /* badge is best-effort */ }
}

// ---------------------------------------------------------------------------
// API health
// ---------------------------------------------------------------------------

async function checkHealth() {
  const t0 = performance.now();
  try {
    await api.getHealth();
    $('api-dot').className = 'status-dot-pulse online';
    $('api-label').textContent = 'API online';
    $('api-latency').textContent = `${Math.round(performance.now() - t0)} ms`;
  } catch {
    $('api-dot').className = 'status-dot-pulse offline';
    $('api-label').textContent = 'API offline';
    $('api-latency').textContent = '';
  }
}

// ---------------------------------------------------------------------------
// Auth transition shell
// ---------------------------------------------------------------------------

function showLogin(initialError = null) {
  clearTimeout(state.timer);
  state.abort?.abort();
  clearInterval(state.badgeTimer);
  state.badgeTimer = null;
  state.token++;
  state.route = null;
  document.body.classList.remove('nav-open');
  closeModal();

  $('app-container').hidden = true;
  const loginHost = $('login-screen');
  loginHost.hidden = false;
  loginHost.innerHTML = renderLoginHtml(initialError);
  paintThemeButton();
  mountLoginView(loginHost, showApp);
}

async function showApp() {
  const loginHost = $('login-screen');
  loginHost.hidden = true;
  loginHost.innerHTML = '';
  $('app-container').hidden = false;

  buildNav();
  checkHealth();
  refreshBadges();
  clearInterval(state.badgeTimer);
  state.badgeTimer = setInterval(refreshBadges, 30000);
  await route();
}

// ---------------------------------------------------------------------------
// Router & view lifecycle
// ---------------------------------------------------------------------------

function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  const [first, second] = parts;
  if (first === 'review' && second) return { id: 'review-task', params: [second] };   // detail page for one task
  const view = viewById(first);
  return { id: view && !view.hidden ? first : 'overview', params: parts.slice(1) };
}

export function navigate(id) { location.hash = `#/${id}`; }

function makeCtx() {
  return {
    state,
    params: state.params,
    query: state.query,
    signal: state.abort.signal,
    navigate,
    setBadges,
    reload: opts => loadView({ silent: true, ...opts }),
    refreshBadges,
  };
}

function schedulePoll(view, token) {
  clearTimeout(state.timer);
  if (!view.refreshMs || !isAuthenticated()) return;
  state.timer = setTimeout(async function tick() {
    if (token !== state.token || !isAuthenticated()) return;
    const typing = document.activeElement?.closest?.('#viewport-container') && /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (document.hidden || isModalOpen() || typing) { state.timer = setTimeout(tick, 4000); return; }
    await loadView({ silent: true });
  }, view.refreshMs);
}

async function loadView({ silent = false } = {}) {
  if (!isAuthenticated() || !isHumanUser()) return;
  const view = viewById(state.route);
  if (!view) return;
  const token = ++state.token;
  const viewport = $('viewport-container');

  if (!silent) {
    state.abort?.abort();
    state.abort = new AbortController();
    viewport.innerHTML = skeleton();
  } else if (!state.abort) {
    state.abort = new AbortController();
  }

  try {
    const data = await view.load(makeCtx());
    if (token !== state.token) return;                 // a newer navigation won
    const scrollTop = silent ? viewport.scrollTop : 0;
    if (silent) { state.abort.abort(); state.abort = new AbortController(); }
    state.data = data;
    viewport.innerHTML = `<div class="view-enter">${view.render(data, makeCtx())}</div>`;
    view.mount?.(viewport, data, makeCtx());
    viewport.scrollTop = scrollTop;
    schedulePoll(view, token);
  } catch (err) {
    if (token !== state.token) return;
    if (err.status === 401) return;                    // handled globally by AUTH_REQUIRED_EVENT
    if (silent) { console.warn(`[${view.id}] background refresh failed:`, err); schedulePoll(view, token); return; }
    viewport.innerHTML = errorState(err.message);
  }
}

async function route() {
  if (!isAuthenticated() || !isHumanUser()) {
    showLogin();
    return;
  }
  clearTimeout(state.timer);
  const { id, params } = parseRoute();
  const view = viewById(id);
  state.route = id;
  state.params = params;
  document.body.classList.remove('nav-open');
  paintNav();

  if (!canAccessView(id)) {
    state.token++;
    state.abort?.abort();
    $('page-title').textContent = 'Access restricted';
    $('page-subtitle').textContent = 'Your signed-in role cannot open this section.';
    document.title = 'Elone SOP Hub';
    $('viewport-container').innerHTML = `
      <div class="error-state" role="alert">
        <h3>${icon('lock')} Access restricted</h3>
        <p>The <b>${esc(view?.label || id)}</b> view is restricted by RBAC policy for your account.</p>
        <div class="row" style="justify-content:center">
          <a class="btn btn-primary" href="#/overview">Return to Overview</a>
        </div>
      </div>`;
    return;
  }

  $('page-title').textContent = view.title;
  $('page-subtitle').textContent = view.subtitle;
  document.title = 'Elone SOP Hub';
  await loadView();
  $('viewport-container').focus({ preventScroll: true });
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

document.addEventListener('click', async e => {
  if (e.target.id === 'global-modal') { closeModal(); return; }   // overlay click
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const handler = actions[el.dataset.action];
  if (!handler) { console.warn(`No handler for data-action="${el.dataset.action}"`); return; }
  if (el.tagName === 'A' && !el.getAttribute('href')?.startsWith('#')) return;
  if (el.tagName === 'A') e.preventDefault();
  try {
    await handler(el, e, makeCtx());
  } catch (err) {
    console.error(err);
    toast(err.message || 'Something went wrong', 'error', 6000);
  }
});

// Forms are driven by custom listeners or data-action buttons; never let the browser navigate on submit.
document.addEventListener('submit', e => e.preventDefault());

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && isModalOpen()) { closeModal(); return; }
  trapFocus(e);
  if (!isAuthenticated() || !isHumanUser()) return;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if ((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
    e.preventDefault();
    $('global-search').focus();
    $('global-search').select();
  }
});

// Global search drives the playbook list.
const onSearch = debounce(value => {
  if (!isAuthenticated() || !isHumanUser()) return;
  state.query = value.trim();
  if (state.route !== 'playbooks') navigate('playbooks');
  else document.dispatchEvent(new CustomEvent('elone:query', { detail: state.query }));
}, 180);

$('global-search').addEventListener('input', e => onSearch(e.target.value));
$('global-search').addEventListener('keydown', e => {
  if (e.key === 'Enter') { state.query = e.target.value.trim(); if (state.route !== 'playbooks') navigate('playbooks'); }
  if (e.key === 'Escape') { e.target.value = ''; onSearch(''); e.target.blur(); }
});

window.addEventListener(AUTH_REQUIRED_EVENT, () => {
  const wasAuthed = isAuthenticated();
  clearSession();
  if (wasAuthed) toast('Session expired or invalidated. Please sign in again.', 'warning', 5000);
  showLogin();
});

window.addEventListener('hashchange', () => {
  if (isAuthenticated() && isHumanUser()) route();
});
window.addEventListener('online', checkHealth);
window.addEventListener('offline', checkHealth);

// ---------------------------------------------------------------------------
// Boot (authenticate BEFORE rendering sidebar / polling / protected views)
// ---------------------------------------------------------------------------

async function boot() {
  initChartTooltip();
  checkHealth();
  state.healthTimer = setInterval(checkHealth, 15000);

  const authResult = await initAuth();
  if (!authResult.authenticated) {
    showLogin(authResult.error || null);
    return;
  }
  await showApp();
}

boot();
