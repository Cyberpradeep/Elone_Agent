/**
 * Elone Agent — Audit Logs & Reasoning Traces View
 */

export function renderAudit(data, state) {
  const logs = data.logs || [];
  const selectedLog = state.selectedLog || (logs[0] ? logs[0].filename : null);
  const logContent = state.activeLogContent || '';

  return `
    <div class="audit-view">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Execution Traces & CoT Audit Logs
            </div>
            <div class="panel-subtitle">
              Inspect comprehensive internal reasoning traces, dual-layer validation passes, and security checks from <code style="color: #a5b4fc;">knowledge_base/logs/debug/</code>.
            </div>
          </div>
          <span class="badge-tag">${logs.length} Debug Logs Available</span>
        </div>

        <div style="display: grid; grid-template-columns: 320px 1fr; gap: 20px;">
          <!-- Left: Logs List -->
          <div>
            <label style="display: block; font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
              Select Execution Log File:
            </label>
            <div style="background: var(--bg-secondary); border: 1px solid var(--card-border); border-radius: var(--radius-md); max-height: 520px; overflow-y: auto; padding: 6px;">
              ${logs.length === 0 ? `
                <div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px;">No logs found.</div>
              ` : logs.map(l => `
                <div 
                  class="log-item ${l.filename === selectedLog ? 'active' : ''}" 
                  onclick="window.loadLogFile('${l.filename}')"
                  style="padding: 10px 12px; border-radius: var(--radius-sm); cursor: pointer; margin-bottom: 4px; transition: var(--transition); background: ${l.filename === selectedLog ? 'rgba(99, 102, 241, 0.15)' : 'transparent'}; border: 1px solid ${l.filename === selectedLog ? 'rgba(99, 102, 241, 0.3)' : 'transparent'};"
                >
                  <div style="font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: ${l.filename === selectedLog ? '#a5b4fc' : 'var(--text-primary)'}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    ${l.filename}
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-muted); margin-top: 4px;">
                    <span>${l.size_kb} KB</span>
                    <span>${l.modified_at ? l.modified_at.split('T')[0] : ''}</span>
                  </div>
                </div>
              `).join('')}
            </div>
          </div>

          <!-- Right: Log Content Viewer -->
          <div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-size: 12px; font-weight: 600; color: var(--text-secondary); font-family: var(--font-mono);">
                ${selectedLog || 'No log selected'}
              </span>
              <button class="btn btn-sm btn-outline" onclick="window.copyActiveLog()">Copy Raw Log</button>
            </div>

            <div style="background: #07090e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: var(--radius-md); padding: 16px; height: 490px; overflow-y: auto; font-family: var(--font-mono); font-size: 11px; line-height: 1.6; color: #cbd5e1; white-space: pre-wrap;">
              ${logContent || '<div style="color: var(--text-muted); text-align: center; padding-top: 150px;">Select a log file on the left to inspect full reasoning trace.</div>'}
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
