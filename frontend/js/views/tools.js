/**
 * Elone Agent — Registered IT Tool Platforms Catalog View
 */

export function renderTools(data) {
  const platforms = data.platforms || [];

  return `
    <div class="tools-view">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
              Registered IT Tool Platforms Catalog
            </div>
            <div class="panel-subtitle">
              Dynamic tool capabilities inspected by the Stage 1 Triage Router for automated step binding.
            </div>
          </div>
          <span class="status-pill status-info">${platforms.length} Platforms Registered</span>
        </div>

        <div class="tools-grid">
          ${platforms.map(p => `
            <div class="tool-card">
              <div class="tool-card-head">
                <span class="tool-platform-name">${p.platform ? p.platform.toUpperCase() : 'PLATFORM'}</span>
                <span class="badge-tag">${(p.functions || []).length} Functions</span>
              </div>
              <div style="font-size: 13px; font-weight: 600; color: #818cf8; margin-bottom: 4px; font-family: var(--font-mono);">${p.tool_name}</div>
              <p class="tool-desc">${p.description || 'No description provided.'}</p>

              <div style="margin-top: auto;">
                <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">Supported Function Calls:</div>
                ${(p.functions || []).map(f => `
                  <div class="tool-func-item">
                    <div class="func-name">
                      <span>${f.function_name}</span>
                      <span style="font-size: 10px; color: var(--text-muted);">${(f.required_inputs || []).length} args</span>
                    </div>
                    <div class="func-desc">${f.description || ''}</div>
                    ${f.required_inputs && f.required_inputs.length > 0 ? `
                      <div class="func-params-row">
                        <span style="color: var(--text-muted);">Required:</span> ${f.required_inputs.map(arg => `<code style="color: #f59e0b; background: rgba(0,0,0,0.3); padding: 1px 4px; border-radius: 3px;">${arg}</code>`).join(' ')}
                      </div>
                    ` : ''}
                  </div>
                `).join('')}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
}
