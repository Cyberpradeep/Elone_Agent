/**
 * Elone SOP Governance Hub — shared UI helpers.
 * Escaping, icons, formatters, toasts, modal host, and the data-action registry.
 * Views build HTML strings with these helpers and never use inline event handlers;
 * interactivity is wired through `data-action` attributes (see registerActions).
 */

// ---------------------------------------------------------------------------
// Escaping
// ---------------------------------------------------------------------------

const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

/** Escape any value for safe use in HTML text or double-quoted attributes. */
export function esc(value) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/[&<>"']/g, ch => ESC_MAP[ch]);
}

// ---------------------------------------------------------------------------
// Icons (24x24, stroke styled by CSS)
// ---------------------------------------------------------------------------

const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  review: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  search: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  tool: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  refresh: '<path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  sun: '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  play: '<polygon points="5 3 19 12 5 21 5 3"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  flask: '<path d="M9 3h6"/><path d="M10 3v6L4.5 19a2 2 0 0 0 1.8 3h11.4a2 2 0 0 0 1.8-3L14 9V3"/><path d="M7.5 15h9"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  grid: '<rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  arrowup: '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
  arrowdown: '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
};

export function icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name] || ''}</svg>`;
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

const nf = new Intl.NumberFormat('en-US');

export const fmt = {
  num(n) { return typeof n === 'number' && isFinite(n) ? nf.format(n) : '—'; },
  usd(n, digits = 4) { return `$${Number(n || 0).toFixed(digits)}`; },
  inr(n) { return `₹${Number(n || 0).toFixed(2)}`; },
  pct(n, digits = 0) { return typeof n === 'number' && isFinite(n) ? `${n.toFixed(digits)}%` : '—'; },
  bytes(n) {
    if (typeof n !== 'number' || !isFinite(n)) return '—';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  },
  date(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return esc(String(iso).replace('T', ' ').split('.')[0]);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  },
  rel(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return '';
    const diff = (d.getTime() - Date.now()) / 1000;
    const abs = Math.abs(diff);
    const unit = abs < 60 ? [Math.round(abs), 's'] : abs < 3600 ? [Math.round(abs / 60), 'm'] : abs < 86400 ? [Math.round(abs / 3600), 'h'] : [Math.round(abs / 86400), 'd'];
    return diff < 0 ? `${unit[0]}${unit[1]} ago` : `in ${unit[0]}${unit[1]}`;
  },
  words(s) { return String(s ?? '').replace(/_/g, ' '); },
};

/** Numbers that the backend may send as the string "unlimited". */
export function isUnlimited(v) { return typeof v === 'string' && v.toLowerCase() === 'unlimited'; }

// ---------------------------------------------------------------------------
// Small renderers
// ---------------------------------------------------------------------------

export function pill(text, tone = 'neutral', { dot = true, title = '' } = {}) {
  return `<span class="status-pill status-${tone}${dot ? '' : ' no-dot'}"${title ? ` title="${esc(title)}"` : ''}>${esc(text)}</span>`;
}

const JOB_TONES = {
  published: 'success', approved: 'success',
  quarantined: 'danger', rejected: 'danger', failed: 'danger', blocked: 'danger', duplicate: 'danger',
  awaiting_review: 'warning', changes_requested: 'warning', correcting: 'warning',
  deactivated: 'neutral', archived: 'neutral', soft_deleted: 'neutral',
};
export function jobTone(state) { return JOB_TONES[state] || 'info'; }
export function jobPill(state) { return pill(fmt.words(state || 'unknown').toUpperCase(), jobTone(state)); }

export function tierBadge(level) {
  const l = ['L0', 'L1', 'L2', 'L3'].includes(level) ? level : 'L1';
  return `<span class="tier tier-${l}">${esc(level || l)}</span>`;
}

export function emptyState({ icon: ic = 'inbox', title = 'Nothing here yet', text = '', action = '' } = {}) {
  return `<div class="empty-state">${icon(ic)}<div class="empty-title">${esc(title)}</div>${text ? `<div class="empty-text">${esc(text)}</div>` : ''}${action}</div>`;
}

export function errorState(message, retryAction = 'retry-view') {
  return `
    <div class="error-state" role="alert">
      <h3>Couldn't load this view</h3>
      <p>${esc(message)}</p>
      <div class="row" style="justify-content:center">
        <button class="btn btn-primary" data-action="${esc(retryAction)}">${icon('refresh')}Try again</button>
      </div>
      <p class="tiny muted" style="margin:14px 0 0">Make sure the backend is running: <code>python server.py</code> (port 8000).</p>
    </div>`;
}

export function skeleton() {
  return `
    <div class="skeleton" aria-busy="true" aria-label="Loading">
      <div class="skel-kpis"><div class="skel"></div><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>
      <div class="skel skel-panel"></div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Misc utilities
// ---------------------------------------------------------------------------

export function debounce(fn, ms = 200) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export const store = {
  get(key, fallback = null) {
    try { const v = localStorage.getItem(`elone-${key}`); return v === null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(`elone-${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ } },
};

export async function copyText(text, successMsg = 'Copied to clipboard') {
  try {
    await navigator.clipboard.writeText(text);
    toast(successMsg, 'success', 2200);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); toast(successMsg, 'success', 2200); } catch { toast('Copy failed', 'error'); }
    ta.remove();
  }
}

export function downloadText(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Toggle a button's busy state. Returns a function that restores it. */
export function busy(btn, on = true) {
  if (!btn) return () => {};
  btn.classList.toggle('is-loading', on);
  btn.disabled = on;
  return () => busy(btn, false);
}

export function prettyJson(value) {
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

export function jsonBlock(value, extraClass = '') {
  return `<pre class="code-block ${extraClass}">${esc(prettyJson(value))}</pre>`;
}

// ---------------------------------------------------------------------------
// Toasts
// ---------------------------------------------------------------------------

const TOAST_ICON = { success: '✓', error: '✕', warning: '!', info: 'i' };

export function toast(message, type = 'info', duration = 4200) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.setAttribute('role', type === 'error' ? 'alert' : 'status');
  el.innerHTML = '<span class="toast-icon"></span><span class="toast-msg"></span><button class="toast-close" aria-label="Dismiss">✕</button>';
  el.querySelector('.toast-icon').textContent = TOAST_ICON[type] || 'i';
  el.querySelector('.toast-msg').textContent = message;   // textContent: message may contain user data
  const dismiss = () => { el.classList.add('leaving'); setTimeout(() => el.remove(), 260); };
  el.querySelector('.toast-close').addEventListener('click', dismiss);
  container.appendChild(el);
  while (container.children.length > 4) container.firstElementChild.remove();
  if (duration > 0) setTimeout(dismiss, duration);
}

// ---------------------------------------------------------------------------
// Modal host
// ---------------------------------------------------------------------------

let lastFocus = null;
let confirmResolver = null;

function modalEl() { return document.getElementById('global-modal'); }

export function isModalOpen() { return modalEl()?.classList.contains('active') || false; }

/**
 * Open the single global modal.
 * @param {{title:string, body:string, footer?:string, size?:'sm'|'md'|'lg', onMount?:(root:HTMLElement)=>void}} opts
 */
export function openModal({ title, body, footer = '', size = '', onMount } = {}) {
  const host = modalEl();
  if (!host) return;
  if (!isModalOpen()) lastFocus = document.activeElement;
  host.innerHTML = `
    <div class="modal-card ${size ? `modal-${size}` : ''}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div class="modal-header">
        <h3 id="modal-title">${esc(title)}</h3>
        <button class="btn btn-ghost btn-icon-only btn-sm" data-action="close-modal" aria-label="Close dialog">${icon('x')}</button>
      </div>
      <div class="modal-body" id="modal-body">${body}</div>
      <div class="modal-footer" id="modal-footer">${footer}</div>
    </div>`;
  host.classList.add('active');
  const focusTarget = host.querySelector('[autofocus]') || host.querySelector('.modal-body input, .modal-body textarea, .modal-body select') || host.querySelector('.modal-footer .btn-primary, .modal-footer .btn');
  (focusTarget || host.querySelector('.modal-card')).focus?.();
  if (onMount) onMount(host);
  return host;
}

export function closeModal() {
  const host = modalEl();
  if (!host) return;
  host.classList.remove('active');
  host.innerHTML = '';
  if (confirmResolver) { confirmResolver(false); confirmResolver = null; }
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus?.();
  lastFocus = null;
}

/** Promise-based confirmation dialog. Resolves true only if confirmed. */
export function confirmDialog({ title = 'Are you sure?', message = '', confirmLabel = 'Confirm', tone = 'primary', details = '' } = {}) {
  return new Promise(resolve => {
    openModal({
      title,
      size: 'sm',
      body: `<p class="secondary" style="font-size:13.5px">${esc(message)}</p>${details}`,
      footer: `<button class="btn btn-outline" data-action="modal-cancel">Cancel</button>
               <button class="btn btn-${tone}" data-action="modal-confirm" autofocus>${esc(confirmLabel)}</button>`,
    });
    confirmResolver = resolve;
  });
}

export function resolveConfirm(value) {
  const r = confirmResolver;
  confirmResolver = null;
  const host = modalEl();
  if (host) { host.classList.remove('active'); host.innerHTML = ''; }
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus?.();
  lastFocus = null;
  if (r) r(value);
}

/** Keep Tab focus inside the open modal. */
export function trapFocus(e) {
  if (e.key !== 'Tab' || !isModalOpen()) return;
  const nodes = [...modalEl().querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(n => !n.disabled && n.offsetParent !== null);
  if (!nodes.length) return;
  const first = nodes[0], last = nodes[nodes.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

// ---------------------------------------------------------------------------
// data-action registry
// ---------------------------------------------------------------------------

export const actions = {};

/** Register handlers: { 'action-name': (el, event) => void|Promise }. */
export function registerActions(map) { Object.assign(actions, map); }

registerActions({
  'close-modal': () => closeModal(),
  'modal-cancel': () => resolveConfirm(false),
  'modal-confirm': () => resolveConfirm(true),
  'copy': el => copyText(el.dataset.copy ?? '', el.dataset.msg || 'Copied to clipboard'),
});

// ---------------------------------------------------------------------------
// Tabs (shared by views and modals)
// ---------------------------------------------------------------------------

/** Wire `.tab[data-tab]` buttons inside `root` to `.tab-panel[data-panel]` siblings. */
export function bindTabs(root, onChange) {
  root.querySelectorAll('.tabs').forEach(tabs => {
    tabs.addEventListener('click', e => {
      const btn = e.target.closest('.tab[data-tab]');
      if (!btn) return;
      const scope = tabs.parentElement;
      tabs.querySelectorAll('.tab').forEach(t => { t.classList.toggle('active', t === btn); t.setAttribute('aria-selected', t === btn ? 'true' : 'false'); });
      scope.querySelectorAll('.tab-panel').forEach(p => { p.hidden = p.dataset.panel !== btn.dataset.tab; });
      onChange?.(btn.dataset.tab);
    });
  });
}
