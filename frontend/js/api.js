/**
 * Elone SOP Governance Hub — API client.
 * One request layer for every backend endpoint (see backend/api/routes_*.py).
 */

export const API_BASE = (window.location.port === '8000')
  ? window.location.origin
  : 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(message, { status = 0, data = {} } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.failures = Array.isArray(data.failures) ? data.failures : Array.isArray(data.errors) ? data.errors : [];
    this.code = data.error_code || null;
  }
}

/**
 * @param {string} path
 * @param {{method?:string, json?:object, form?:FormData, as?:'json'|'text', soft?:boolean}} opts
 *   soft: resolve with the JSON body (plus `_http`) for non-2xx responses that carry a
 *         pipeline status (e.g. quarantined, duplicate) instead of throwing.
 */
async function request(path, { method = 'GET', json, form, as = 'json', soft = false } = {}) {
  const init = { method, headers: {} };
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
    if (soft && data && (data.status || data.success === false)) return { ...data, _http: res.status };
    const message = data.error || data.reason || data.message || `${method} ${path} failed (${res.status} ${res.statusText})`;
    throw new ApiError(message, { status: res.status, data });
  }
  return data;
}

const id = encodeURIComponent;

export const api = {
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
  ingestSingle: (filename, { sopId, tenantId, uploadedBy } = {}) => request('/api/uploads/ingest', {
    method: 'POST',
    soft: true,
    json: {
      filename,
      ...(sopId ? { sop_id: sopId } : {}),
      ...(tenantId ? { tenant_id: tenantId } : {}),
      ...(uploadedBy ? { uploaded_by: uploadedBy } : {}),
    },
  }),
  runScan: () => request('/api/uploads/scan', { method: 'POST' }),
  planPreview: filename => request('/api/plan-preview', { method: 'POST', json: { filename } }),

  // --- Playbooks -----------------------------------------------------------
  listSops: () => request('/api/sops'),
  getSop: sopId => request(`/api/sops/${id(sopId)}`),
  verifySop: sopId => request(`/api/sops/${id(sopId)}/verify`, { method: 'POST' }),
  /** Moves the playbook (+ canonical JSON, rulebook) to knowledge_base/_trash and unpublishes it. */
  deleteSop: (sopId, { actor, reason }) => request(`/api/sops/${id(sopId)}`, { method: 'DELETE', json: { actor, reason } }),

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
  saveDraftSteps: (sopId, { actor, steps }) => request(`/api/governance/drafts/${id(sopId)}/steps`, { method: 'PUT', json: { actor, steps } }),
  /** Saves hand-edited canonical JSON into the draft (system-managed fields are refused by the server). */
  saveDraftCanonical: (sopId, { actor, canonical }) => request(`/api/governance/drafts/${id(sopId)}/canonical`, { method: 'PUT', json: { actor, canonical } }),
  getCanonical: sopId => request(`/api/governance/sops/${id(sopId)}/canonical`),
  updateCanonical: (sopId, canonical) => request(`/api/governance/sops/${id(sopId)}/canonical`, { method: 'PUT', json: canonical }),
  syncPlaybook: (sopId, canonical) => request(`/api/governance/sops/${id(sopId)}/sync-playbook`, { method: 'POST', json: { canonical_sop: canonical } }),
  searchDownstream: payload => request('/api/governance/downstream/search', { method: 'POST', json: payload }),
  getDownstreamStats: tenantId => request(`/api/governance/downstream/stats${tenantId ? `?tenant_id=${id(tenantId)}` : ''}`),

  // --- Configuration -------------------------------------------------------
  getConfig: () => request('/api/config'),
  updateConfig: config => request('/api/config', { method: 'POST', json: config }),
};
