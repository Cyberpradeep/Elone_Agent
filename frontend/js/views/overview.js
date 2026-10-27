/**
 * Elone Agent — Overview & Executive Governance Dashboard View
 */

export function renderOverview(data, state, actions) {
  const stats = data.stats || {};
  const telemetry = data.telemetry || {};
  const scheduler = data.scheduler || {};
  const gates = data.gates || [];

  const quotaPct = telemetry.max_daily_calls > 0
    ? Math.round((telemetry.total_calls / telemetry.max_daily_calls) * 100)
    : 0;

  return `
    <div class="overview-view">
      <!-- KPI Bento Grid -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Verified Playbooks</span>
            <div class="kpi-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${stats.total_playbooks || 0}</span>
            <span class="kpi-badge badge-success">OKF Format</span>
          </div>
          <div class="kpi-subtext">Cryptographically signed with HMAC-SHA256</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Ingestion Success Rate</span>
            <div class="kpi-icon-wrap" style="color: var(--success);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${stats.success_rate || 100}%</span>
            <span class="kpi-badge badge-success">${stats.manifest_success || 0} Passed</span>
          </div>
          <div class="kpi-subtext">${stats.manifest_failed || 0} security rejected / quota halted</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Daily Call Quota</span>
            <div class="kpi-icon-wrap" style="color: ${quotaPct > 80 ? 'var(--danger)' : 'var(--accent-secondary)'};">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${telemetry.total_calls || 0} / ${telemetry.max_daily_calls || 50}</span>
            <span class="kpi-badge ${quotaPct > 80 ? 'badge-danger' : 'badge-warning'}">${telemetry.calls_remaining || 0} left</span>
          </div>
          <div class="quota-gauge-wrapper">
            <div class="gauge-track">
              <div class="gauge-fill ${quotaPct > 80 ? 'warning' : ''}" style="width: ${Math.min(quotaPct, 100)}%;"></div>
            </div>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Daily AI Expenditure</span>
            <div class="kpi-icon-wrap" style="color: var(--warning);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">$${Number(telemetry.total_cost_usd || 0).toFixed(4)}</span>
            <span class="kpi-badge badge-warning">~₹${Number(telemetry.total_cost_inr || 0).toFixed(2)}</span>
          </div>
          <div class="kpi-subtext">Total Tokens: ${(telemetry.total_tokens || 0).toLocaleString()}</div>
        </div>
      </div>

      <!-- Quick Action Bar -->
      <div class="panel" style="padding: 16px 20px;">
        <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px;">
          <div>
            <h4 style="font-size: 15px; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;">Governance Operations Control</h4>
            <p style="font-size: 12px; color: var(--text-muted);">Manage real-time SOP document ingestion, run security audits, and trigger pipeline syncs.</p>
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 10px;">
            <button class="btn btn-primary" onclick="window.switchTab('ingestion')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              Upload & Ingest SOP
            </button>
            <button class="btn btn-secondary" id="btn-trigger-scan">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
              Trigger Full Scan Cycle
            </button>
            <button class="btn btn-outline" onclick="window.switchTab('pipeline')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
              Inspect 7 Gates
            </button>
          </div>
        </div>
      </div>

      <!-- Two Column Layout: Pipeline Gates Overview + Provider & Scheduler Status -->
      <div style="display: grid; grid-template-columns: 1.4fr 1fr; gap: 24px;">
        <!-- Left: 7 Active Security Gates -->
        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                7-Gate Ingestion Security Architecture
              </div>
              <div class="panel-subtitle">Multi-layered deterministic & LLM defense enforcing OWASP Top 10 for LLMs</div>
            </div>
            <span class="status-pill status-success">All 7 Active</span>
          </div>

          <div style="display: flex; flex-direction: column; gap: 10px;">
            ${gates.map(gate => `
              <div style="background: var(--bg-secondary); border: 1px solid var(--card-border); border-radius: var(--radius-sm); padding: 12px 16px; display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <span style="font-family: var(--font-mono); font-size: 11px; font-weight: 700; background: rgba(99, 102, 241, 0.15); color: #a5b4fc; padding: 2px 7px; border-radius: 4px; border: 1px solid rgba(99, 102, 241, 0.3);">Gate ${gate.gate_id}</span>
                  <div>
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-primary);">${gate.name}</div>
                    <div style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">${gate.module}</div>
                  </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="status-pill status-success" style="font-size: 10px; padding: 2px 7px;">ENFORCING</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Right: Multi-Model Orchestration & Scheduler Telemetry -->
        <div style="display: flex; flex-direction: column; gap: 24px;">
          <!-- Multi-Model Routing Status -->
          <div class="panel">
            <div class="panel-header">
              <div class="panel-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>
                Multi-Model Orchestration
              </div>
              <span class="status-pill status-info">Active Matrix</span>
            </div>

            <div style="display: flex; flex-direction: column; gap: 12px; font-size: 12px;">
              <div style="background: var(--bg-tertiary); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Planning & Conversion:</span>
                  <div style="font-weight: 700; color: #818cf8; font-family: var(--font-mono);">gemini-2.5-flash</div>
                </div>
                <span class="status-pill status-success" style="font-size: 10px;">Primary</span>
              </div>

              <div style="background: var(--bg-tertiary); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Layer 2 Validation:</span>
                  <div style="font-weight: 700; color: #38bdf8; font-family: var(--font-mono);">mistral-small-latest</div>
                </div>
                <span class="status-pill status-success" style="font-size: 10px;">Audit Head</span>
              </div>

              <div style="background: var(--bg-tertiary); padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--card-border); display: flex; justify-content: space-between; align-items: center;">
                <div>
                  <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Screenshot & VLM OCR:</span>
                  <div style="font-weight: 700; color: #34d399; font-family: var(--font-mono);">llama-3.2-11b-vision / nvidia</div>
                </div>
                <span class="status-pill status-success" style="font-size: 10px;">Vision Head</span>
              </div>
            </div>
          </div>

          <!-- Background Polling Worker Status -->
          <div class="panel">
            <div class="panel-header">
              <div class="panel-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Background Polling Scheduler
              </div>
              <span class="status-pill ${scheduler.running ? 'status-success' : 'status-warning'}">
                ${scheduler.running ? 'WATCHER ACTIVE' : 'STANDBY'}
              </span>
            </div>

            <div style="display: flex; flex-direction: column; gap: 8px; font-size: 12px; color: var(--text-secondary);">
              <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--card-border);">
                <span>Scan Interval:</span>
                <strong style="color: var(--text-primary); font-family: var(--font-mono);">${scheduler.interval_minutes || 10} minutes</strong>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--card-border);">
                <span>Total Runs Executed:</span>
                <strong style="color: var(--text-primary); font-family: var(--font-mono);">${scheduler.total_runs || 0} cycles</strong>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 6px 0;">
                <span>Monitored Target:</span>
                <code style="color: #a5b4fc; font-size: 11px;">knowledge_base/_uploads/</code>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
