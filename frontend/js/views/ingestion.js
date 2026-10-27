/**
 * Elone Agent — Ingestion Queue, Upload Manager & Manifest View
 */

export function renderIngestion(data, state) {
  const files = data.files || [];
  const manifest = data.manifest || {};

  return `
    <div class="ingestion-view">
      <!-- File Upload Dropzone -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              Upload New Raw Human SOP Document
            </div>
            <div class="panel-subtitle">
              Strict Gate 1 pre-checks: Allowed formats (.pdf, .docx, .csv, .xlsx, .txt), max 10MB, max 10 pages, anti-spoof magic-bytes.
            </div>
          </div>
          <button class="btn btn-secondary" id="btn-run-full-scan">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            Run Full Ingestion Scan Cycle
          </button>
        </div>

        <div class="dropzone-container" id="sop-dropzone">
          <input type="file" id="sop-file-input" style="display: none;" accept=".pdf,.docx,.csv,.xls,.xlsx,.txt">
          <div class="dropzone-icon">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          </div>
          <div class="dropzone-title">Click to Browse or Drag & Drop SOP File</div>
          <div class="dropzone-subtext">PDF, DOCX, XLSX, CSV, or TXT documents up to 10MB</div>
        </div>
      </div>

      <!-- Ingestion Queue & Processed Manifest Table -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
              Uploads Directory & Processed Manifest
            </div>
            <div class="panel-subtitle">Real-time status tracking from <code style="color: #a5b4fc;">knowledge_base/_uploads/_processed_manifest.json</code></div>
          </div>
        </div>

        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Document File</th>
                <th>File Size</th>
                <th>Gate 1 Pre-Check</th>
                <th>Pipeline Status</th>
                <th>Target Playbook</th>
                <th>Last Modified / Converted</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${files.length === 0 ? `
                <tr>
                  <td colspan="7" style="text-align: center; padding: 36px; color: var(--text-muted);">
                    No upload files found in <code>knowledge_base/_uploads/</code>.
                  </td>
                </tr>
              ` : files.map(file => {
                const info = file.manifest_info || {};
                const isSuccess = file.manifest_status === 'success';
                const isFailed = file.manifest_status === 'failed';

                return `
                  <tr>
                    <td>
                      <div style="font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); font-size: 12px;">${file.filename}</div>
                      <div style="font-size: 11px; color: var(--text-muted);">${file.extension.toUpperCase()} Format</div>
                    </td>
                    <td>
                      <span style="font-family: var(--font-mono);">${file.size_mb} MB</span>
                    </td>
                    <td>
                      <span class="status-pill ${file.gate1_passed ? 'status-success' : 'status-danger'}" style="font-size: 10px;">
                        ${file.gate1_passed ? 'PASSED GATE 1' : 'SECURITY REJECT'}
                      </span>
                      ${file.gate1_error ? `<div style="font-size: 10px; color: var(--danger); margin-top: 4px; max-width: 180px;">${file.gate1_error}</div>` : ''}
                    </td>
                    <td>
                      ${isSuccess ? `
                        <span class="status-pill status-success">CONVERTED</span>
                      ` : isFailed ? `
                        <span class="status-pill status-danger" title="${info.error || ''}">FAILED</span>
                      ` : `
                        <span class="status-pill status-warning">PENDING SCAN</span>
                      `}
                      ${info.error ? `
                        <div style="font-size: 10px; color: #f87171; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px;" title="${info.error}">
                          ${info.error}
                        </div>
                      ` : ''}
                    </td>
                    <td>
                      ${info.sop_id ? `
                        <span style="font-family: var(--font-mono); font-weight: 700; color: #818cf8; font-size: 11px;">${info.sop_id}</span>
                      ` : `
                        <span style="color: var(--text-muted); font-size: 11px;">—</span>
                      `}
                    </td>
                    <td>
                      <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">
                        ${info.converted_at ? info.converted_at.split('T')[0] : file.modified_at.split('T')[0]}
                      </span>
                    </td>
                    <td>
                      <div style="display: flex; gap: 6px;">
                        <button class="btn btn-sm btn-primary" onclick="window.triggerIngest('${file.filename}')" title="Run JIT conversion pipeline">
                          Ingest
                        </button>
                        <button class="btn btn-sm btn-outline" onclick="window.previewPlan('${file.filename}')" title="Dry-run planner without writing to disk">
                          Dry-Run
                        </button>
                      </div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}
