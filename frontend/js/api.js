/**
 * Elone SOP Governance Hub — API client.
 * One request layer for every backend endpoint (see backend/api/routes_*.py).
 * Sends HttpOnly cookie credentials + double-submit X-CSRF-Token header automatically.
 */

export const API_BASE = (window.location.port === '8000')
  ? window.location.origin
  : 'http://127.0.0.1:8000';

export const AUTH_REQUIRED_EVENT = 'elone:auth-required';

export function readCsrfCookie() {
  const m = /(?:^|;\s*)elone_csrf=([^;]+)/.exec(document.cookie || '');
  if (!m) return '';
  try { return decodeURIComponent(m[1]); } catch { return m[1]; }
}

export class ApiError extends Error {
  constructor(message, { status = 0, data = {} } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.failures = Array.isArray(data.failures) ? data.failures : Array.isArray(data.errors) ? data.errors : [];
    this.code = data.error_code || null;
    this.retryAfter = data.retry_after ?? null;
  }
}

/**
 * @param {string} path
 * @param {{method?:string, json?:object, form?:FormData, as?:'json'|'text', soft?:boolean}} opts
 *   soft: resolve with the JSON body (plus `_http`) for non-2xx responses that carry a
 *         pipeline status (e.g. quarantined, duplicate) instead of throwing.
 */
async function request(path, { method = 'GET', json, form, as = 'json', soft = false } = {}) {
  const upperMethod = String(method || 'GET').toUpperCase();
  const init = { method: upperMethod, credentials: 'include', headers: {} };

  if (!['GET', 'HEAD', 'OPTIONS'].includes(upperMethod)) {
    const csrf = readCsrfCookie();
    if (csrf) init.headers['X-CSRF-Token'] = csrf;
  }

  if (json !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(`Cannot reach the API at ${API_BASE}. Is the backend running?`, { status: 0 });
  }

  if (as === 'text' && res.ok) return res.text();

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && path !== '/api/auth/login' && path !== '/api/auth/me') {
      window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT, { detail: { path, data } }));
    }
    if (soft && res.status !== 401 && data && (data.status || data.success === false)) {
      return { ...data, _http: res.status };
    }
    const message = data.error || data.reason || data.message || `${upperMethod} ${path} failed (${res.status} ${res.statusText})`;
    throw new ApiError(message, { status: res.status, data });
  }
  return data;
}

const id = encodeURIComponent;

export const api = {
  // --- Authentication ------------------------------------------------------
  login: (username, password) => request('/api/auth/login', { method: 'POST', json: { username, password } }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  getMe: () => request('/api/auth/me'),
  listUsers: () => request('/api/auth/users'),
  createUser: payload => request('/api/auth/users', { method: 'POST', json: payload }),
  updateUser: (sub, payload) => request(`/api/auth/users/${id(sub)}`, { method: 'PATCH', json: payload }),
  issueAgentToken: (sub, ttlMinutes) => request(`/api/auth/users/${id(sub)}/token`, {
    method: 'POST',
    json: ttlMinutes ? { ttl_minutes: ttlMinutes } : {},
  }),

  // --- Telemetry & diagnostics ---------------------------------------------
  getHealth: () => request('/api/health'),
  getOverview: () => request('/api/overview'),
  getScheduler: () => request('/api/scheduler'),
  getTools: () => request('/api/tools'),
  getTelemetry: () => request('/api/telemetry'),
  listLogs: () => request('/api/logs'),
  getLog: filename => request(`/api/logs/${id(filename)}`, { as: 'text' }),
  testSecurity: (payload, type = 'all') => request('/api/security/test', { method: 'POST', json: { payload, type } }),

  // --- Ingestion -----------------------------------------------------------
  listUploads: () => request('/api/uploads'),
  uploadFile(file) {
    const form = new FormData();
    form.append('file', file);
    return request('/api/uploads/upload', { method: 'POST', form });
  },
  /** Resolves with the pipeline body even for 400/403/409 outcomes (check `.status`). */
  ingestSingle: (filename, { sopId, reingest } = {}) => request('/api/uploads/ingest', {
    method: 'POST',
    soft: true,
    json: {
      filename,
      ...(sopId ? { sop_id: sopId } : {}),
      ...(reingest ? { reingest: true } : {}),
    },
  }),
  /** Ask a running ingestion to stop. It ends at its next checkpoint; nothing is saved. */
  cancelIngest: filename => request('/api/uploads/ingest/cancel', { method: 'POST', json: { filename } }),
  runScan: () => request('/api/uploads/scan', { method: 'POST' }),
  planPreview: filename => request('/api/plan-preview', { method: 'POST', json: { filename } }),

  // --- Playbooks -----------------------------------------------------------
  listSops: () => request('/api/sops'),
  getSop: sopId => request(`/api/sops/${id(sopId)}`),
  verifySop: sopId => request(`/api/sops/${id(sopId)}/verify`, { method: 'POST' }),
  /** Moves the playbook (+ canonical JSON, rulebook) to knowledge_base/_trash and unpublishes it. */
  deleteSop: (sopId, { reason = '' } = {}) => request(`/api/sops/${id(sopId)}`, { method: 'DELETE', json: { reason } }),

  // --- Governance ----------------------------------------------------------
  getGovernanceJobs: () => request('/api/governance/jobs'),
  getJob: jobId => request(`/api/governance/jobs/${id(jobId)}`),
  getReviewTasks: () => request('/api/governance/review-tasks'),
  getIncidents: () => request('/api/governance/incidents'),
  recordDecision: (taskId, payload) => request(`/api/governance/review-tasks/${id(taskId)}/decision`, { method: 'POST', json: payload }),
  publishSop: (sopId, payload = {}) => request(`/api/governance/sops/${id(sopId)}/publish`, { method: 'POST', json: payload }),
  /** The editable (OKF) steps of an unapproved draft, and whether they can still be edited. */
  getDraft: sopId => request(`/api/governance/drafts/${id(sopId)}`),
  /** Saves a reviewer's step edits into the draft only (nothing is published). */
  saveDraftSteps: (sopId, { steps }) => request(`/api/governance/drafts/${id(sopId)}/steps`, { method: 'PUT', json: { steps } }),
  /** Saves hand-edited canonical JSON into the draft (system-managed fields are refused by the server). */
  saveDraftCanonical: (sopId, { canonical }) => request(`/api/governance/drafts/${id(sopId)}/canonical`, { method: 'PUT', json: { canonical } }),
  getCanonical: sopId => request(`/api/governance/sops/${id(sopId)}/canonical`),
  updateCanonical: (sopId, canonical) => request(`/api/governance/sops/${id(sopId)}/canonical`, { method: 'PUT', json: canonical }),
  syncPlaybook: (sopId, canonical) => request(`/api/governance/sops/${id(sopId)}/sync-playbook`, { method: 'POST', json: { canonical_sop: canonical } }),
  searchDownstream: ({ query = '', department, limit = 10 } = {}) => request('/api/governance/downstream/search', {
    method: 'POST',
    json: { query, ...(department ? { department } : {}), limit },
  }),
  getDownstreamStats: () => request('/api/governance/downstream/stats'),

  // --- Configuration -------------------------------------------------------
  getConfig: () => request('/api/config'),
  updateConfig: config => request('/api/config', { method: 'POST', json: config }),
};
