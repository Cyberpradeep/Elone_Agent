/**
 * Elone Agent — Verified OKF Playbook Repository View
 * Searchable, filterable list and deep inspection modal with step execution visualizer
 */

export function renderPlaybooks(data, state) {
  const playbooks = data.playbooks || [];
  const query = (state.searchQuery || '').toLowerCase();

  const filtered = playbooks.filter(p => {
    if (!query) return true;
    return (
      (p.sop_id && p.sop_id.toLowerCase().includes(query)) ||
      (p.title && p.title.toLowerCase().includes(query)) ||
      (p.category && p.category.toLowerCase().includes(query)) ||
      (p.platform && p.platform.toLowerCase().includes(query))
    );
  });

  return `
    <div class="playbooks-view">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
              Open Knowledge Format (OKF) Playbooks
            </div>
            <div class="panel-subtitle">
              Verified, deterministic, execution-ready IT SOP playbooks compiled Just-In-Time from human documentation.
            </div>
          </div>
          <div style="display: flex; gap: 10px; align-items: center;">
            <div class="search-wrapper">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              <input type="text" id="playbook-search-input" class="search-input" placeholder="Search by ID, title, category..." value="${state.searchQuery || ''}">
            </div>
          </div>
        </div>

        <!-- Playbooks Data Table -->
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>SOP Identifier</th>
                <th>Playbook Title</th>
                <th>Category</th>
                <th>Platform / Shell</th>
                <th>Confidence</th>
                <th>Steps</th>
                <th>HMAC Signature</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.length === 0 ? `
                <tr>
                  <td colspan="8" style="text-align: center; padding: 36px; color: var(--text-muted);">
                    No verified playbooks found matching criteria.
                  </td>
                </tr>
              ` : filtered.map(p => `
                <tr>
                  <td>
                    <span style="font-family: var(--font-mono); font-weight: 700; color: #818cf8;">${p.sop_id}</span>
                  </td>
                  <td>
                    <div style="font-weight: 600; color: var(--text-primary);">${p.title}</div>
                    <div style="font-size: 11px; color: var(--text-muted);">${p.description ? p.description.slice(0, 75) + '...' : ''}</div>
                  </td>
                  <td>
                    <span class="badge-tag">${p.category}</span>
                  </td>
                  <td>
                    <div style="font-size: 12px; font-weight: 600;">${p.platform}</div>
                    <div style="font-size: 10px; color: var(--text-muted); font-family: var(--font-mono);">${p.target_os}</div>
                  </td>
                  <td>
                    <span class="status-pill ${p.confidence_score >= 0.9 ? 'status-success' : 'status-warning'}">
                      ${Math.round(p.confidence_score * 100)}% (${p.confidence_level})
                    </span>
                  </td>
                  <td>
                    <strong style="color: var(--text-primary);">${p.steps_count}</strong> steps
                  </td>
                  <td>
                    <span class="status-pill ${p.integrity_valid ? 'status-success' : 'status-warning'}" style="font-size: 10px;">
                      ${p.integrity_valid ? 'VERIFIED' : 'TAMPERED/ALERT'}
                    </span>
                  </td>
                  <td>
                    <button class="btn btn-sm btn-secondary" onclick="window.inspectPlaybook('${p.sop_id}')">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                      Inspect
                    </button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}
