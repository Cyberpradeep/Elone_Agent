/**
 * Elone Agent — SOP Governance Hub API Client Layer
 * Handles all async communication with backend endpoints
 */

const API_BASE = (window.location.port === '8000')
  ? window.location.origin
  : 'http://127.0.0.1:8000';

export const api = {
  async getOverview() {
    const res = await fetch(`${API_BASE}/api/overview`);
    if (!res.ok) throw new Error(`Overview fetch failed: ${res.statusText}`);
    return await res.json();
  },

  async listSops() {
    const res = await fetch(`${API_BASE}/api/sops`);
    if (!res.ok) throw new Error(`SOP list fetch failed: ${res.statusText}`);
    return await res.json();
  },

  async getSop(sopId) {
    const res = await fetch(`${API_BASE}/api/sops/${encodeURIComponent(sopId)}`);
    if (!res.ok) throw new Error(`Failed to fetch SOP ${sopId}`);
    return await res.json();
  },

  async verifySop(sopId) {
    const res = await fetch(`${API_BASE}/api/sops/${encodeURIComponent(sopId)}/verify`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`Failed to verify SOP ${sopId}`);
    return await res.json();
  },

  async listUploads() {
    const res = await fetch(`${API_BASE}/api/uploads`);
    if (!res.ok) throw new Error(`Uploads fetch failed: ${res.statusText}`);
    return await res.json();
  },

  async ingestSingle(filename, overrideSopId = null) {
    const res = await fetch(`${API_BASE}/api/uploads/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, override_sop_id: overrideSopId })
    });
    const data = await res.json();
    if (!res.ok && !data.error && !data.reason) {
      throw new Error(`Ingestion failed with status ${res.status}`);
    }
    return data;
  },

  async runScan() {
    const res = await fetch(`${API_BASE}/api/uploads/scan`, { method: 'POST' });
    if (!res.ok) throw new Error(`Scan cycle failed`);
    return await res.json();
  },

  async uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/api/uploads/upload`, {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Upload failed');
    return data;
  },

  async planPreview(filename) {
    const res = await fetch(`${API_BASE}/api/plan-preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Plan preview failed');
    return data;
  },

  async getScheduler() {
    const res = await fetch(`${API_BASE}/api/scheduler`);
    if (!res.ok) throw new Error(`Scheduler state failed`);
    return await res.json();
  },

  async getTools() {
    const res = await fetch(`${API_BASE}/api/tools`);
    if (!res.ok) throw new Error(`Tool catalog failed`);
    return await res.json();
  },

  async getTelemetry() {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    if (!res.ok) throw new Error(`Telemetry failed`);
    return await res.json();
  },

  async listLogs() {
    const res = await fetch(`${API_BASE}/api/logs`);
    if (!res.ok) throw new Error(`Logs list failed`);
    return await res.json();
  },

  async getLog(filename) {
    const res = await fetch(`${API_BASE}/api/logs/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error(`Log fetch failed`);
    return await res.json();
  },

  async testSecurity(payload, type = 'all') {
    const res = await fetch(`${API_BASE}/api/security/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload, type })
    });
    if (!res.ok) throw new Error(`Security test failed`);
    return await res.json();
  }
};
