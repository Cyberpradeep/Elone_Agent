/**
 * Elone Agent — Multi-Model Telemetry & Cost Accounting View
 */

export function renderTelemetry(data, state) {
  const today = data.today || {};
  const history = data.history || {};
  const selectedDate = state.selectedDate || today.date;
  const currentViewData = history[selectedDate] || today;

  const quotaPct = currentViewData.max_daily_calls > 0
    ? Math.round((currentViewData.total_calls / currentViewData.max_daily_calls) * 100)
    : 0;

  const callHistory = currentViewData.call_history || [];
  const dates = Object.keys(history).sort().reverse();

  return `
    <div class="telemetry-view">
      <!-- Date Selector & Summary Bar -->
      <div class="panel" style="padding: 16px 20px;">
        <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 14px;">
          <div>
            <h4 style="font-size: 15px; font-weight: 700; color: var(--text-primary); margin-bottom: 2px;">Daily Usage & Circuit Breaker Telemetry</h4>
            <p style="font-size: 12px; color: var(--text-muted);">Real-time token counting, cost computation, and call logging across Gemini, Mistral, and Vision models.</p>
          </div>
          <div style="display: flex; align-items: center; gap: 10px;">
            <label style="font-size: 12px; font-weight: 600; color: var(--text-secondary);">Select Date:</label>
            <select id="telemetry-date-select" style="background: var(--bg-tertiary); border: 1px solid var(--card-border); border-radius: var(--radius-sm); padding: 6px 12px; color: var(--text-primary); font-size: 12px; outline: none;">
              ${dates.map(d => `<option value="${d}" ${d === selectedDate ? 'selected' : ''}>${d} ${d === today.date ? '(Today)' : ''}</option>`).join('')}
            </select>
          </div>
        </div>
      </div>

      <!-- Telemetry KPI Cards -->
      <div class="kpi-grid">
        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">API Calls Today</span>
            <div class="kpi-icon-wrap">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${currentViewData.total_calls || 0}</span>
            <span class="kpi-badge ${quotaPct > 80 ? 'badge-danger' : 'badge-success'}">${quotaPct}% Quota</span>
          </div>
          <div class="quota-gauge-wrapper">
            <div class="gauge-track">
              <div class="gauge-fill ${quotaPct > 80 ? 'warning' : ''}" style="width: ${Math.min(quotaPct, 100)}%;"></div>
            </div>
          </div>
          <div class="kpi-subtext" style="margin-top: 6px;">Remaining calls: ${currentViewData.calls_remaining ?? (50 - (currentViewData.total_calls || 0))}</div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Model Distribution</span>
            <div class="kpi-icon-wrap" style="color: #a5b4fc;">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/></svg>
            </div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 4px; font-size: 12px;">
            <div style="display: flex; justify-content: space-between;">
              <span style="color: #818cf8;">Gemini (Planning):</span>
              <strong>${currentViewData.gemini_calls || 0}</strong>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: #38bdf8;">Mistral (Audit):</span>
              <strong>${currentViewData.mistral_calls || 0}</strong>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span style="color: #34d399;">NVIDIA (Vision):</span>
              <strong>${currentViewData.nvidia_vision_calls || 0}</strong>
            </div>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Token Consumption</span>
            <div class="kpi-icon-wrap" style="color: var(--accent-secondary);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">${(currentViewData.total_tokens || 0).toLocaleString()}</span>
          </div>
          <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); margin-top: 6px;">
            <span>In: ${(currentViewData.total_input_tokens || 0).toLocaleString()}</span>
            <span>Out: ${(currentViewData.total_output_tokens || 0).toLocaleString()}</span>
            <span>Img: ${(currentViewData.total_image_tokens || 0).toLocaleString()}</span>
          </div>
        </div>

        <div class="kpi-card">
          <div class="kpi-card-header">
            <span class="kpi-title">Computed Cost</span>
            <div class="kpi-icon-wrap" style="color: var(--warning);">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            </div>
          </div>
          <div class="kpi-value-row">
            <span class="kpi-value">$${Number(currentViewData.total_cost_usd || 0).toFixed(4)}</span>
            <span class="kpi-badge badge-warning">₹${Number(currentViewData.total_cost_inr || 0).toFixed(2)}</span>
          </div>
          <div class="kpi-subtext">Circuit breaker cap: $2.00 / 50 calls</div>
        </div>
      </div>

      <!-- Call History Ledger Table -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Execution Session & Call Ledger (${selectedDate})
            </div>
            <div class="panel-subtitle">Individual API call telemetry with prompt tokens, completion tokens, latency, and costs.</div>
          </div>
          <span class="badge-tag">${callHistory.length} Recorded Calls</span>
        </div>

        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Caller Role</th>
                <th>Provider / Model</th>
                <th>Target SOP ID</th>
                <th>Input Tokens</th>
                <th>Output Tokens</th>
                <th>Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              ${callHistory.length === 0 ? `
                <tr>
                  <td colspan="7" style="text-align: center; padding: 36px; color: var(--text-muted);">
                    No API calls logged for date ${selectedDate}.
                  </td>
                </tr>
              ` : callHistory.slice().reverse().map(call => `
                <tr>
                  <td>
                    <span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${call.timestamp}</span>
                  </td>
                  <td>
                    <span class="badge-tag" style="background: rgba(99, 102, 241, 0.15); color: #c7d2fe;">${call.caller}</span>
                  </td>
                  <td>
                    <div style="font-weight: 600; color: var(--text-primary); font-size: 12px;">${call.provider}</div>
                    <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">${call.model}</div>
                  </td>
                  <td>
                    <span style="font-family: var(--font-mono); font-size: 11px; color: #818cf8;">${call.sop_id || '—'}</span>
                  </td>
                  <td>
                    <span style="font-family: var(--font-mono); font-size: 12px;">${(call.input_tokens || 0).toLocaleString()}</span>
                  </td>
                  <td>
                    <span style="font-family: var(--font-mono); font-size: 12px;">${(call.output_tokens || 0).toLocaleString()}</span>
                  </td>
                  <td>
                    <span style="font-family: var(--font-mono); font-size: 12px; color: var(--warning);">$${Number(call.cost_usd || 0).toFixed(6)}</span>
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
