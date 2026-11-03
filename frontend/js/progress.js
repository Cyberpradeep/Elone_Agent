/**
 * Live ingestion progress.
 *
 * `POST /api/uploads/ingest` only answers when the whole pipeline is finished, so while it runs
 * we watch two read-only endpoints instead:
 *   - /api/governance/jobs  -> the job's current lifecycle state and its transition history
 *   - /api/telemetry        -> every LLM call made since we started (triage, draft, validate…)
 * The job is found by diffing the job list against a snapshot taken just before the request.
 */

import { api } from './api.js';
import { esc, icon, fmt, openModal, registerActions, toast } from './ui.js';

const STAGES = [
  { id: 'read', label: 'Validate & read the document', hint: 'File checks and text extraction', states: ['received', 'extracting'] },
  { id: 'scan', label: 'Scan for secrets', hint: 'Passwords, API keys and private keys', states: ['scanning'] },
  { id: 'structure', label: 'Structure the playbook with the LLM', hint: 'Usually the slowest step', states: ['structuring'] },
  { id: 'assess', label: 'Check quality & confidentiality', hint: 'Quote traceability, completeness, tier', states: ['assessing', 'correcting'] },
  { id: 'review', label: 'Create the review task', hint: 'A human must approve before publishing', states: ['awaiting_review'] },
];

/** Where the job sits: the active stage index, and why it stopped if it did. */
export function locate(state) {
  if (!state) return { index: 0, halted: null };
  if (['awaiting_review', 'approved', 'published'].includes(state)) return { index: STAGES.length, halted: null };
  if (state === 'quarantined') return { index: 1, halted: 'Quarantined — secrets found' };
  if (state === 'rejected') return { index: 2, halted: 'Not actionable as an automated procedure' };
  if (state === 'duplicate') return { index: 0, halted: 'Duplicate of an existing job' };
  if (['failed', 'blocked'].includes(state)) return { index: -1, halted: `Job ${fmt.words(state)}` };
  const i = STAGES.findIndex(s => s.states.includes(state));
  return { index: i === -1 ? 0 : i, halted: null };
}

const CALL_LABELS = {
  vlm_image_analysis: 'Read a screenshot (vision model)',
  triage_router: 'Classify the SOP (triage)',
  execution_planning: 'Draft the playbook steps',
  planning_validation: 'Validate the draft against the SOP',
};

const secs = ms => (ms < 10000 ? `${(ms / 1000).toFixed(1)} s` : ms < 60000 ? `${Math.round(ms / 1000)} s` : `${Math.floor(ms / 60000)}m ${String(Math.round((ms % 60000) / 1000)).padStart(2, '0')}s`);

/** Pure renderer — everything the dialog shows, from plain data. */
export function progressHtml({ file, job, calls, lastActiveIndex = 0, startedAt = Date.now(), stopping = false }) {
  const state = job?.current_state || null;
  const loc = locate(state);
  const index = loc.index;
  const lastReason = job?.history?.[job.history.length - 1]?.reason || '';
  // A job the user stopped ends as "failed" with a reason starting "Cancelled".
  const halted = state === 'failed' && /^Cancelled/.test(lastReason) ? 'Stopped by you' : loc.halted;
  const active = index === -1 ? lastActiveIndex : index;
  const stoppedAt = halted ? active : -1;

  // When each stage was first entered (from the server's own history timestamps).
  const entered = {};
  for (const h of job?.history || []) {
    const i = STAGES.findIndex(s => s.states.includes(h.to_state));
    if (i !== -1 && entered[i] === undefined) entered[i] = new Date(h.timestamp).getTime();
  }
  const doneAt = (i) => {
    for (let k = i + 1; k <= STAGES.length; k++) if (entered[k] !== undefined) return entered[k];
    return null;
  };

  const rows = STAGES.map((s, i) => {
    let status = 'pending';
    if (i < active) status = 'done';
    else if (i === active) status = halted ? 'failed' : (index >= STAGES.length ? 'done' : 'active');
    if (index >= STAGES.length) status = 'done';
    const stoppedHere = halted && i === stoppedAt;
    if (stoppedHere) status = 'failed';

    // Stage 0 happens before the job exists (parsing + secret scan), so time it from the click.
    let timing = '';
    if (status === 'done' && i === 0 && entered[0] !== undefined) timing = secs(Math.max(0, entered[0] - startedAt));
    else if (status === 'done' && entered[i] !== undefined && doneAt(i) !== null) timing = secs(doneAt(i) - entered[i]);
    if (status === 'active') timing = `<span data-run-since="${entered[i] ?? startedAt}">…</span>`;

    const showCalls = i === 2 && calls.length && (status === 'active' || status === 'done' || status === 'failed');
    const callCounts = {};
    const callHtml = showCalls ? `
      <ul class="ip-calls" aria-label="LLM calls so far">
        ${calls.map(c => {
          callCounts[c.caller] = (callCounts[c.caller] || 0) + 1;
          const n = callCounts[c.caller];
          const again = n > 1 ? ` <span class="badge-tag">attempt ${n}</span>` : '';
          return `<li>${icon('check')}<span>${esc(CALL_LABELS[c.caller] || c.caller)}${again}</span><span class="muted mono tiny">${esc(c.model || '')} · ${fmt.num((c.input_tokens || 0) + (c.output_tokens || 0))} tokens</span></li>`;
        }).join('')}
      </ul>` : '';
    const working = i === 2 && status === 'active'
      ? `<div class="ip-working tiny muted">${stopping ? 'Letting the call in progress finish; its result will be discarded…' : calls.length ? 'Waiting on the next model call…' : 'Waiting for the first model call…'}</div>` : '';

    return `
      <li class="ip-stage ip-${status}">
        <span class="ip-mark" aria-hidden="true">${status === 'done' ? icon('check') : status === 'failed' ? icon('x') : status === 'active' ? '<span class="spinner"></span>' : '<span class="ip-dot"></span>'}</span>
        <div class="ip-body">
          <div class="ip-title"><span>${esc(s.label)}</span><span class="ip-time tiny mono">${timing}</span></div>
          <div class="ip-hint tiny muted">${stoppedHere ? esc(halted) : (stopping && status === 'active') ? 'Stopping — no further model calls will be made' : esc(s.hint)}</div>
          ${callHtml}${working}
        </div>
      </li>`;
  }).join('');

  const current = halted ? halted : stopping ? 'Stopping… waiting for the step in progress to finish' : index >= STAGES.length ? 'Finishing up…' : STAGES[Math.max(0, active)].label;
  return `
    <div class="stack">
      <div class="row-between">
        <div><div class="mono strong small">${esc(file)}</div><div class="tiny muted" id="ip-current">${esc(current)}</div></div>
        <div class="ip-elapsed mono"><span id="ip-elapsed">0.0 s</span></div>
      </div>
      <ol class="ip-stages" id="ip-stages">${rows}</ol>
      <div class="tiny muted">Keep this tab open. The result appears here when the pipeline finishes.</div>
    </div>`;
}


// ---------------------------------------------------------------------------
// Stop button
// ---------------------------------------------------------------------------

const FOOTER = {
  run: `<span class="tiny muted" style="margin-right:auto">You can stop this at any time.</span>
        <button class="btn btn-danger-ghost" data-action="ingest-stop">${icon('x')}Stop processing</button>`,
  confirm: `<span class="small" style="margin-right:auto"><b>Stop this ingestion?</b> Nothing will be saved.</span>
            <button class="btn btn-outline" data-action="ingest-stop-no">Keep going</button>
            <button class="btn btn-danger" data-action="ingest-stop-yes">Yes, stop</button>`,
  stopping: `<span class="small muted" style="margin-right:auto"><span class="spinner" style="vertical-align:-3px"></span> Stopping… the step in progress can't be interrupted, but nothing further will run and nothing will be saved.</span>`,
};

let active = null;      // the ingestion this dialog is showing: { file, actor, requestStop }
const setFooter = html => { const f = document.getElementById('modal-footer'); if (f) f.innerHTML = html; };

registerActions({
  'ingest-stop': () => setFooter(FOOTER.confirm),          // first click only asks "are you sure?"
  'ingest-stop-no': () => setFooter(FOOTER.run),
  'ingest-stop-yes': async () => {
    if (!active) return;
    setFooter(FOOTER.stopping);
    active.requestStop();
    try {
      const r = await api.cancelIngest(active.file, active.actor);
      if (r.status === 'not_running') toast('It had already finished.', 'info');
    } catch (err) {
      setFooter(FOOTER.run);
      toast(`Couldn't send the stop request: ${err.message}`, 'error', 6000);
    }
  },
});

/**
 * Open the progress dialog and start watching. Call `finish()` when the ingest request settles.
 * @returns {{stop: () => void, finish: (pauseMs?: number) => Promise<void>}}
 */
export function trackIngest(file, { actor = '' } = {}) {
  const startedAt = Date.now();
  let job = null;
  let calls = [];
  let lastActive = 0;
  let before = new Map();
  let callBase = 0;
  let stopped = false;
  let stopping = false;
  let lastHtml = '';

  const body = () => document.getElementById('modal-body');
  const paint = () => {
    const el = body();
    if (!el || !el.querySelector('#ip-stages')) return;            // the dialog was closed or replaced
    const { index } = locate(job?.current_state);
    if (index >= 0) lastActive = Math.min(index, STAGES.length - 1);
    const html = progressHtml({ file, job, calls, lastActiveIndex: lastActive, startedAt, stopping });
    if (html !== lastHtml) { el.innerHTML = html; lastHtml = html; tick(); }   // re-fill the clocks the template reset
  };
  const tick = () => {
    const now = Date.now();
    const e = document.getElementById('ip-elapsed'); if (e) e.textContent = secs(now - startedAt);
    document.querySelectorAll('[data-run-since]').forEach(n => { n.textContent = secs(Math.max(0, now - Number(n.dataset.runSince))); });
  };

  openModal({ title: 'Ingesting…', size: 'md', body: progressHtml({ file, job: null, calls: [], startedAt }), footer: FOOTER.run });
  active = { file, actor, requestStop() { stopping = true; paint(); } };
  lastHtml = body().innerHTML;
  tick();

  const poll = async () => {
    try {
      const { jobs = [] } = await api.getGovernanceJobs();
      const changed = jobs.filter(j => !before.has(j.job_id) || before.get(j.job_id) !== j.updated_at);
      changed.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
      if (changed[0]) job = changed[0];
    } catch { /* keep the last known state */ }
    try {
      const t = await api.getTelemetry();
      const all = t.today?.call_history || [];
      calls = all.slice(callBase).filter(c => c.caller !== 'test_runner');
    } catch { /* telemetry is optional */ }
    if (!stopped) paint();
  };

  (async () => {
    try {
      const { jobs = [] } = await api.getGovernanceJobs();
      before = new Map(jobs.map(j => [j.job_id, j.updated_at]));
    } catch { /* first poll will treat everything as new; harmless */ }
    try { callBase = ((await api.getTelemetry()).today?.call_history || []).length; } catch { /* ignore */ }
    if (stopped) return;
    await poll();
    const pollTimer = setInterval(() => { if (stopped) clearInterval(pollTimer); else poll(); }, 1000);
    const tickTimer = setInterval(() => { if (stopped) clearInterval(tickTimer); else tick(); }, 250);
    stop.timers = [pollTimer, tickTimer];
  })();

  function stop() { stopped = true; if (active && active.file === file) active = null; (stop.timers || []).forEach(clearInterval); }

  /** Take one last snapshot, show it for a moment, then stop watching. */
  async function finish(pause = 700) {
    await poll();
    tick();
    stop();
    if (pause) await new Promise(r => setTimeout(r, pause));
  }
  return { stop, finish };
}
