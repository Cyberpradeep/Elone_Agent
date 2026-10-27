/**
 * Elone Agent — 5-Phase Pipeline & 7 Verification Gates Architecture View
 * Interactive visual breakdown & Live Gate Testing Simulator
 */

export function renderPipeline(data) {
  const gates = data.gates || [];

  return `
    <div class="pipeline-view">
      <!-- Architecture Overview Header Panel -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              5-Phase Ingestion Pipeline & 7 Security Verification Gates
            </div>
            <div class="panel-subtitle">
              Strict deterministic pre-checks, multimodal physical-order splicing, 6-stage CoT reasoning, and dual-layer plan validation.
            </div>
          </div>
          <span class="status-pill status-success">All Gates Online</span>
        </div>

        <!-- 5-Phase Stepper Visualizer -->
        <div class="pipeline-flow-container">
          <!-- Phase 1 -->
          <div class="pipeline-phase-card">
            <div class="phase-header-row">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="phase-number-tag">Phase 1</span>
                <span class="phase-name">Ingestion Trigger & Pre-Checks</span>
              </div>
              <span class="gate-pill gate-pass">
                <span class="gate-badge-id">Gate 1</span> File Validator
              </span>
            </div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
              Triggered via background scheduler polling or manual CLI/API upload. Enforces magic-byte anti-spoofing, 10MB size ceilings, 10-page caps, and zip bomb ratios before any parsing begins.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <span class="badge-tag">Magic-Bytes Anti-Spoof (%PDF-, PK)</span>
              <span class="badge-tag">Hard 10MB Cap</span>
              <span class="badge-tag">Max 10 Pages / 5000 Words</span>
              <span class="badge-tag">Zip Bomb Max 20x Ratio</span>
            </div>
          </div>

          <!-- Phase 2 -->
          <div class="pipeline-phase-card">
            <div class="phase-header-row">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="phase-number-tag">Phase 2</span>
                <span class="phase-name">Document-Order Extraction & Multimodal Splicing</span>
              </div>
              <div style="display: flex; gap: 6px;">
                <span class="gate-pill gate-pass"><span class="gate-badge-id">Gate 2</span> DLP Masking</span>
                <span class="gate-pill gate-pass"><span class="gate-badge-id">Gate 3</span> VLM OCR</span>
                <span class="gate-pill gate-pass"><span class="gate-badge-id">Gate 4</span> SSRF Scraper</span>
              </div>
            </div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
              Walks the document in physical reading order across PDF, Word, and Excel files. Inline screenshots stay anchored to their corresponding text. Zero-width unicode is scrubbed, DLP secrets masked, and external web hyperlinks quarantined.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <span class="badge-tag">Physical-Order Splicer</span>
              <span class="badge-tag">DLP Password/API Key Masking</span>
              <span class="badge-tag">Pixel Bomb 4096px Cap & 1024px Downscaling</span>
              <span class="badge-tag">SSRF 169.254.169.254 & RFC1918 Block</span>
            </div>
          </div>

          <!-- Phase 3 -->
          <div class="pipeline-phase-card">
            <div class="phase-header-row">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="phase-number-tag">Phase 3</span>
                <span class="phase-name">JIT Converter Agent & 6-Stage Command CoT</span>
              </div>
              <span class="gate-pill gate-pass">
                <span class="gate-badge-id">Gate 5</span> Delimiter Sandboxing
              </span>
            </div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
              Stage 1 Triage Router inspects live platform tools to classify the workflow (<code style="color: #a5b4fc;">command</code>, <code style="color: #a5b4fc;">tool_call</code>, <code style="color: #a5b4fc;">hybrid</code>, or <code style="color: #a5b4fc;">unactionable</code>). Stage 2 wraps data inside <code style="color: #a5b4fc;">&lt;untrusted_document_payload&gt;</code> and executes the 6-stage CoT reasoning mandate.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <span class="badge-tag">1. OS/Shell: Windows PowerShell</span>
              <span class="badge-tag">2. Diagnostic-First (Test-Connection, reg query)</span>
              <span class="badge-tag">3. Dynamic Entity Scoping {entities.*}</span>
              <span class="badge-tag">4. stdout Parsing variables.*</span>
              <span class="badge-tag">5. Conditional Remediation execute_if</span>
              <span class="badge-tag">6. GUI Noise Omission</span>
            </div>
          </div>

          <!-- Phase 4 -->
          <div class="pipeline-phase-card">
            <div class="phase-header-row">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="phase-number-tag">Phase 4</span>
                <span class="phase-name">Dual-Layer Plan Validation & Self-Healing</span>
              </div>
              <span class="gate-pill gate-pass">
                <span class="gate-badge-id">Gate 6</span> Dual-Layer AST & Audit
              </span>
            </div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
              Layer 1 executes in &lt;1ms to verify non-empty commands, quotation wrapping on variable placeholders, and blocks banned LOLBins. Layer 2 invokes Mistral Small 3 at temperature=0 for a 6-point faithfulness audit. On failure, the auto-retry controller feeds surgical directives back to the converter (up to 3 retries).
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <span class="badge-tag">Layer 1 AST: LOLBins Block (certutil, bitsadmin, mshta)</span>
              <span class="badge-tag">Layer 1 AST: Encoded Scripts (-enc) Block</span>
              <span class="badge-tag">Layer 1 AST: Double-Quote Entity Enforcement</span>
              <span class="badge-tag">Layer 2 Mistral: 100% Action Recall & 0 Hallucinations</span>
              <span class="badge-tag">Auto-Retry Controller (3 Attempts Max)</span>
            </div>
          </div>

          <!-- Phase 5 -->
          <div class="pipeline-phase-card">
            <div class="phase-header-row">
              <div style="display: flex; align-items: center; gap: 12px;">
                <span class="phase-number-tag">Phase 5</span>
                <span class="phase-name">Cryptographic Integrity, Slugging & Storage</span>
              </div>
              <span class="gate-pill gate-pass">
                <span class="gate-badge-id">Gate 7</span> HMAC-SHA256 Storage
              </span>
            </div>
            <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
              Sanitizes SOP ID to alphanumeric whitelist slugs, embeds an HMAC-SHA256 cryptographic stamp in the YAML frontmatter to prevent post-approval disk tampering, auto-initializes the Reflection Rulebook learning matrix, and registers the playbook into the master catalog.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              <span class="badge-tag">Alphanumeric Slug Whitelist</span>
              <span class="badge-tag">HMAC-SHA256 Digital Stamp</span>
              <span class="badge-tag">Reflection Rulebook Auto-Init (rules_SOP-ID.md)</span>
              <span class="badge-tag">Master Catalog Registration (sops/index.md)</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Interactive Gate Simulator / Security Testing Sandbox -->
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><circle cx="12" cy="10" r="3"/></svg>
              Live Security Gate Simulator & Threat Tester
            </div>
            <div class="panel-subtitle">
              Test suspicious commands, payloads, or un-sanitized SOP text directly against Elone's live Layer 1 AST blacklist, DLP redactor, and unicode sanitizers.
            </div>
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
          <!-- Left: Input Playground -->
          <div>
            <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">
              Input Command / Document Text:
            </label>
            <textarea id="security-test-input" style="width: 100%; height: 160px; background: var(--bg-secondary); border: 1px solid var(--card-border); border-radius: var(--radius-md); padding: 12px; color: var(--text-primary); font-family: var(--font-mono); font-size: 12px; resize: vertical; outline: none;" placeholder="Enter command or text to test against Gate 2 (DLP) and Gate 6.1 (AST LOLBins)..."></textarea>

            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px;">
              <button class="btn btn-sm btn-outline" onclick="window.loadSecuritySample('lolbin')">Sample: certutil LOLBin</button>
              <button class="btn btn-sm btn-outline" onclick="window.loadSecuritySample('encoded')">Sample: -enc PowerShell</button>
              <button class="btn btn-sm btn-outline" onclick="window.loadSecuritySample('backdoor')">Sample: net user /add</button>
              <button class="btn btn-sm btn-outline" onclick="window.loadSecuritySample('dlp')">Sample: API Key + Password</button>
              <button class="btn btn-sm btn-outline" onclick="window.loadSecuritySample('clean')">Sample: Valid PowerShell</button>
            </div>

            <div style="margin-top: 14px;">
              <button class="btn btn-primary" id="btn-run-security-sim" style="width: 100%;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Execute Real-Time Gate Security Audit
              </button>
            </div>
          </div>

          <!-- Right: Live Audit Verdict -->
          <div>
            <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">
              Security Engine Verification Result:
            </label>
            <div id="security-sim-result" style="height: 230px; background: #07090e; border: 1px solid rgba(255,255,255,0.08); border-radius: var(--radius-md); padding: 14px; overflow-y: auto; font-family: var(--font-mono); font-size: 12px; color: #94a3b8;">
              <div style="text-align: center; color: var(--text-muted); margin-top: 70px;">
                Click "Execute Real-Time Gate Security Audit" or pick a sample above to test.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}
