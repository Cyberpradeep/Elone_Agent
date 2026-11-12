/**
 * Review — Option A human-in-the-loop governance:
 * Security Reviewers decide L0–L3 review tasks (with SoD); Process Owners revise
 * changes_requested drafts and publish approved SOPs; Admins/Security Reviewers inspect
 * quarantine incidents; Process Owners/Admins edit published canonical JSON.
 */

import { api } from '../api.js';
import { hasCapability } from '../auth.js';
import {
  esc, icon, fmt, pill, jobPill, jobTone, tierBadge, toast, busy, openModal, closeModal,
  confirmDialog, registerActions, bindTabs, emptyState, jsonBlock, prettyJson,
} from '../ui.js';

let activeTab = 'tasks';

export function showJobsTab() { activeTab = 'jobs'; }

// The ledger stores a task's status as the decision word: pending, approve, changes_requested, reject, superseded.
const TASK_STATUS = {
  pending: ['PENDING', 'warning'],
  approve: ['APPROVED', 'success'], approved: ['APPROVED', 'success'],
  changes_requested: ['CHANGES REQUESTED', 'warning'],
  reject: ['REJECTED', 'danger'], rejected: ['REJECTED', 'danger'],
  superseded: ['SUPERSEDED', 'neutral'],
};
export function taskStatus(status) {
  const [label, tone] = TASK_STATUS[status] || [String(status).toUpperCase(), 'neutral'];
  return { label, tone };
}
export function taskStatusPill(status) {
  const { label, tone } = taskStatus(status);
  return pill(label, tone);
}

/** Job lifecycle transitions as a vertical timeline (shared by the history dialog and the review page). */
export function timelineHtml(hist = []) {
  if (!hist.length) return emptyState({ icon: 'clock', title: 'No transitions recorded' });
  return `<ol class="timeline">${hist.map(h => `
    <li class="tone-${jobTone(h.to_state) === 'info' ? '' : jobTone(h.to_state)}">
      <div class="tl-head">${h.from_state ? `<span class="muted">${esc(fmt.words(h.from_state))}</span><span class="muted">→</span>` : ''}${jobPill(h.to_state)}</div>
      <div class="tl-meta">${fmt.date(h.timestamp)} · ${esc(h.actor || 'system')}</div>
      ${h.reason ? `<div class="tl-reason">${esc(h.reason)}</div>` : ''}
    </li>`).join('')}</ol>`;
}

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------

function tasksTable(tasks) {
  const canEditDraft = hasCapability('can_edit_draft');
  const sorted = [...tasks].sort((a, b) => {
    if ((a.status === 'pending') !== (b.status === 'pending')) return a.status === 'pending' ? -1 : 1;
    return String(a.due_date).localeCompare(String(b.due_date));
  });
  if (!sorted.length) return emptyState({ icon: 'review', title: 'No review tasks', text: 'A task is created automatically when an ingested SOP reaches "awaiting review" within your tenant and clearance.' });
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>Task</th><th>SOP</th><th>Tier &amp; role</th><th>Due</th><th>Status</th><th></th></tr></thead>
        <tbody>
          ${sorted.map(t => `
            <tr>
              <td><span class="id-cell">${esc(t.task_id)}</span></td>
              <td><div class="mono strong">${esc(t.sop_id)}</div><div class="cell-sub">v${esc(t.version)} · uploaded by ${esc(t.uploaded_by)}</div></td>
              <td>
                <div class="row" style="gap:6px">${t.sop_tier ? tierBadge(t.sop_tier) : ''}<span>${esc(t.assigned_role)}</span></div>
                ${t.status === 'pending' && t.eligible_for_me === false ? '<div class="cell-sub muted">Requires Security Reviewer / SoD check</div>' : ''}
              </td>
              <td class="nowrap"><div class="mono tiny">${fmt.date(t.due_date)}</div><div class="cell-sub">${t.status === 'pending' ? fmt.rel(t.due_date) : ''} ${t.is_overdue ? pill('OVERDUE', 'danger', { dot: false }) : ''}</div></td>
              <td>${taskStatusPill(t.status)}
                  ${t.reviewer ? `<div class="cell-sub">by ${esc(t.reviewer)}</div>` : ''}</td>
              <td>
                <div class="row-actions">
                  ${t.status === 'pending'
                    ? `<a class="btn btn-sm ${t.eligible_for_me === false ? 'btn-outline' : 'btn-primary'}" href="#/review/${esc(t.task_id)}">${t.eligible_for_me === false ? 'Inspect' : 'Review'}</a>`
                    : (t.status === 'changes_requested' && canEditDraft)
                    ? `<a class="btn btn-sm btn-primary" href="#/review/${esc(t.task_id)}">${icon('edit')}Revise &amp; resubmit</a>`
                    : `<a class="btn btn-sm btn-outline" href="#/review/${esc(t.task_id)}">View</a>`}
                  <button class="btn btn-sm btn-ghost" data-action="job-history" data-id="${esc(t.job_id)}">History</button>
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function jobsTable(jobs) {
  const canPublish = hasCapability('can_publish');
  const canEditDraft = hasCapability('can_edit_draft');
  const sorted = [...jobs].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
  if (!sorted.length) return emptyState({ icon: 'file', title: 'No lifecycle jobs', text: 'Jobs appear here as soon as a document is ingested.' });
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>SOP</th><th>Job</th><th>Tenant</th><th>State</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          ${sorted.map(j => `
            <tr>
              <td><div class="id-cell">${esc(j.sop_id)}</div><div class="cell-sub">v${esc(j.version)} · ${esc(j.uploaded_by)}</div></td>
              <td class="mono tiny">${esc(j.job_id)}</td>
              <td class="secondary">${esc(j.tenant_id)}</td>
              <td>${jobPill(j.current_state)}</td>
              <td class="nowrap"><div class="mono tiny">${fmt.date(j.updated_at)}</div><div class="cell-sub">${fmt.rel(j.updated_at)}</div></td>
              <td>
                <div class="row-actions">
                  ${j.current_state === 'approved' && canPublish ? `<button class="btn btn-sm btn-success" data-action="publish-sop" data-id="${esc(j.sop_id)}">${icon('upload')}Publish</button>` : ''}
                  ${j.current_state === 'changes_requested' && canEditDraft && j.review_task?.task_id ? `<a class="btn btn-sm btn-primary" href="#/review/${esc(j.review_task.task_id)}">${icon('edit')}Revise &amp; resubmit</a>` : ''}
                  <button class="btn btn-sm btn-outline" data-action="job-history" data-id="${esc(j.job_id)}">History</button>
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function incidentsTable(incidents) {
  if (!incidents.length) return emptyState({ icon: 'lock', title: 'No quarantine incidents', text: 'Documents containing passwords, API keys or private keys are halted here before any AI call is made.' });
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>Incident</th><th>SOP</th><th>Job</th><th class="num">Secrets</th><th>Types</th><th>When</th></tr></thead>
        <tbody>
          ${incidents.map(i => `
            <tr>
              <td><span class="id-cell text-danger">${esc(i.incident_id)}</span></td>
              <td class="mono">${esc(i.sop_id)}</td>
              <td class="mono tiny">${esc(i.job_id)}</td>
              <td class="num strong">${esc(i.secrets_count)}</td>
              <td>${(i.secret_types || []).map(t => `<span class="badge-tag">${esc(fmt.words(t))}</span>`).join(' ')}</td>
              <td class="nowrap tiny mono">${fmt.date(i.timestamp)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

// ---------------------------------------------------------------------------
// Canonical summaries
// ---------------------------------------------------------------------------

export function classificationCard(c) {
  if (!c) return '';
  return `
    <div class="result-card">
      <h5>Confidentiality ${tierBadge(c.level)}</h5>
      <div class="kv-list">
        <div><span class="k">Score</span><span class="v mono">${esc(c.score)}/100</span></div>
        <div><span class="k">Rule tier / AI suggestion</span><span class="v mono">${esc(c.rule_level || '—')} / ${esc(c.ai_suggested_level || '—')}</span></div>
        <div><span class="k">Confirmed by a human</span><span class="v">${c.confirmed ? pill('YES', 'success') : pill('NOT YET', 'warning')}</span></div>
      </div>
      ${(c.evidence_categories || []).length ? `<div class="row" style="margin-top:8px">${c.evidence_categories.map(e => `<span class="badge-tag">${esc(fmt.words(e))}</span>`).join('')}</div>` : ''}
    </div>`;
}

export function qualityCard(q) {
  if (!q) return '';
  const tone = q.status === 'Ready' ? 'success' : q.status === 'Needs attention' ? 'warning' : 'danger';
  return `
    <div class="result-card">
      <h5>Quality ${pill(String(q.status || '—').toUpperCase(), tone)}</h5>
      <div class="kv-list">
        <div><span class="k">Quality score</span><span class="v mono">${esc(q.quality_score)}</span></div>
        <div><span class="k">Completeness</span><span class="v mono">${esc(q.completeness)}%</span></div>
        <div><span class="k">Quote traceability</span><span class="v mono">${esc(q.traceability)}%</span></div>
        <div><span class="k">Blocking issues</span><span class="v mono">${esc(q.blocking_issues_count)}</span></div>
      </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

registerActions({
  'submit-decision': async (el, _e, ctx) => {
    const form = document.getElementById('decision-form');
    const err = document.getElementById('dec-error');
    err.innerHTML = '';
    const decisionEl = form.querySelector('input[name="decision"]:checked');
    const decision = decisionEl ? decisionEl.value : 'approve';
    const notes = form.querySelector('#dec-notes').value.trim();
    const confirmed = form.querySelector('#dec-classif').checked;

    if (decision !== 'approve' && !notes) { err.textContent = 'Add a note explaining the decision.'; form.querySelector('#dec-notes').focus(); return; }
    if (decision === 'approve' && !confirmed) { err.textContent = 'Confirm the confidentiality tier to approve.'; return; }

    let quality = {};
    try { quality = JSON.parse(el.dataset.quality || '{}'); } catch { /* ignore */ }
    // Reviewer identity and actor_type=human are derived strictly from the server token.
    const payload = {
      decision, notes, confirmed_classification: confirmed,
      ...(typeof quality.traceability === 'number' ? { traceability_pct: quality.traceability } : {}),
      ...(typeof quality.completeness === 'number' ? { completeness_pct: quality.completeness } : {}),
      ...(typeof quality.schema_valid === 'boolean' ? { schema_valid: quality.schema_valid } : {}),
      ...(typeof quality.blocking_issues_count === 'number' ? { open_blocking_issues_count: quality.blocking_issues_count } : {}),
    };

    const done = busy(el);
    try {
      const res = await api.recordDecision(form.dataset.task, payload);
      closeModal();
      toast(`Decision recorded: ${fmt.words(res.decision)}. Job is now ${fmt.words(res.job_state)}.`, 'success', 5500);
      if (res.decision === 'approve') activeTab = 'jobs';
      ctx.refreshBadges();
      if (form.dataset.page === 'true') { location.hash = '#/review'; return; }
      await ctx.reload();
    } catch (e) {
      const list = e.failures?.length ? `<ul style="margin:6px 0 0 18px">${e.failures.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : '';
      const m = /from '([a-z_]+)' to '([a-z_]+)'/.exec(e.message || '');
      const text = m
        ? `${esc(`This SOP can't move from “${fmt.words(m[1])}” to “${fmt.words(m[2])}” right now. It may already have been decided, or changed by someone else. Reload the page to see its latest status.`)}<div class="tiny muted" style="margin-top:4px">${esc(e.message)}</div>`
        : esc(e.message);
      err.innerHTML = `<div class="callout danger">${icon('alert')}<div>${text}${list}</div></div>`;
    } finally { done(); }
  },

  'publish-sop': async (el, _e, ctx) => {
    const id = el.dataset.id;
    const ok = await confirmDialog({
      title: `Publish ${id}?`,
      message: 'This writes the playbook to the knowledge base and makes it retrievable by downstream agents at its clearance tier.',
      confirmLabel: 'Publish',
      tone: 'success',
    });
    if (!ok) return;
    try {
      const res = await api.publishSop(id);
      toast(`Published ${res.sop_id} v${res.version} — ${res.citation}`, 'success', 7000);
      await ctx.reload();
    } catch (e) {
      const extra = e.failures?.length ? ` — ${e.failures.join('; ')}` : '';
      toast(`Publish failed: ${e.message}${extra}`, 'error', 8000);
    }
  },

  'job-history': async el => {
    let job;
    try { job = await api.getJob(el.dataset.id); } catch (e) { toast(`Couldn't load job: ${e.message}`, 'error'); return; }
    const hist = job.history || [];
    openModal({
      title: `${job.sop_id} — job history`,
      size: 'md',
      body: `
        <div class="stack">
          <div class="row">${jobPill(job.current_state)}<span class="mono tiny muted">${esc(job.job_id)}</span><span class="tiny muted">tenant ${esc(job.tenant_id)} · v${esc(job.version)}</span></div>
          ${timelineHtml(hist)}
          ${job.approval_decision ? `<details class="accordion"><summary>Approval decision</summary><div class="acc-body">${jsonBlock(job.approval_decision)}</div></details>` : ''}
          ${job.gate_results ? `<details class="accordion"><summary>Publication gate results</summary><div class="acc-body">${jsonBlock(job.gate_results)}</div></details>` : ''}
          ${job.incident ? `<details class="accordion" open><summary>Quarantine incident</summary><div class="acc-body">${jsonBlock(job.incident)}</div></details>` : ''}
        </div>`,
      footer: '<button class="btn btn-primary" data-action="close-modal">Close</button>',
    });
  },

  'edit-canonical': async el => {
    const id = el.dataset.id;
    let canonical;
    try { canonical = await api.getCanonical(id); } catch (e) { toast(`Canonical SOP not available: ${e.message}`, 'error'); return; }
    const isDraft = canonical.lifecycle?.state !== 'published';
    const steps = canonical.steps || [];
    const hasEditCap = hasCapability('can_edit_canonical');
    const canEdit = hasEditCap && !isDraft;

    openModal({
      title: `Canonical SOP — ${id}`,
      size: 'lg',
      body: `
        <div class="stack" data-sop="${esc(id)}" data-draft="${isDraft}">
          ${isDraft ? `<div class="callout warn">${icon('lock')}<div><b>Draft canonical JSON is read-only here.</b> Unapproved drafts cannot bypass review to write directly into the knowledge base. Process Owners revise drafts inside the Review queue task before Security Reviewer approval and publication.</div></div>` : ''}
          ${!isDraft && !hasEditCap ? `<div class="callout">${icon('lock')}<div><b>Read-only view.</b> Direct canonical JSON edits are restricted to Process Owners and Admins.</div></div>` : ''}
          <div class="tabs in-modal" role="tablist">
            <button class="tab active" role="tab" data-tab="summary">Summary</button>
            <button class="tab" role="tab" data-tab="steps">Steps <span class="tab-count">${steps.length}</span></button>
            <button class="tab" role="tab" data-tab="json">${canEdit ? 'JSON editor' : 'JSON'}</button>
          </div>
          <div>
            <div class="tab-panel" data-panel="summary">
              <div class="stack">
                <div class="meta-grid">
                  <div class="meta-item"><div class="meta-label">Title</div><div class="meta-value">${esc(canonical.title || id)}</div></div>
                  <div class="meta-item"><div class="meta-label">Version</div><div class="meta-value mono">v${esc(canonical.version ?? 1)}</div></div>
                  <div class="meta-item"><div class="meta-label">Lifecycle</div><div class="meta-value">${jobPill(canonical.lifecycle?.state)}</div></div>
                  <div class="meta-item"><div class="meta-label">Tenant</div><div class="meta-value mono">${esc(canonical.tenant_id || '—')}</div></div>
                </div>
                <div class="grid-2" style="gap:12px">${classificationCard(canonical.classification)}${qualityCard(canonical.quality)}</div>
                ${(canonical.transformations || []).length ? `<details class="accordion"><summary>Cleaning log <span class="tab-count">${canonical.transformations.length}</span></summary><div class="acc-body">${jsonBlock(canonical.transformations)}</div></details>` : ''}
              </div>
            </div>
            <div class="tab-panel" data-panel="steps" hidden>
              <div class="stack">${steps.length ? steps.map((s, i) => `
                <div class="sop-step-card">
                  <div class="step-card-header"><span class="step-badge-number">Step ${esc(s.step_number ?? s.number ?? i + 1)}</span>${s.action_type || s.step_type ? `<span class="step-type-pill">${esc(s.action_type || s.step_type)}</span>` : ''}</div>
                  <div class="step-description">${esc(s.description || s.sop_step_description || s.text || prettyJson(s))}</div>
                  ${s.source_quote || s.quote ? `<div class="tiny muted" style="margin-top:6px">“${esc(s.source_quote || s.quote)}”</div>` : ''}
                </div>`).join('') : emptyState({ icon: 'list', title: 'No steps in this SOP' })}</div>
            </div>
            <div class="tab-panel" data-panel="json" hidden>
              <div class="stack-sm">
                <textarea id="canon-json" class="textarea code" spellcheck="false" style="min-height:380px" ${canEdit ? '' : 'readonly'}>${esc(prettyJson(canonical))}</textarea>
                ${canEdit ? `<div class="row-between"><span id="canon-status" class="tiny"></span><button type="button" class="btn btn-sm btn-ghost" data-action="canon-format">Format JSON</button></div>` : ''}
              </div>
            </div>
          </div>
        </div>`,
      footer: canEdit ? `
        <button class="btn btn-outline" data-action="close-modal">Close</button>
        <button class="btn btn-secondary" data-action="canon-sync">Sync playbook only</button>
        <button class="btn btn-primary" data-action="canon-save">Save &amp; sync</button>` : '<button class="btn btn-primary" data-action="close-modal">Close</button>',
      onMount: root => {
        bindTabs(root);
        if (!canEdit) return;
        const ta = root.querySelector('#canon-json');
        const status = root.querySelector('#canon-status');
        const check = () => {
          try { JSON.parse(ta.value); status.textContent = '✓ Valid JSON'; status.className = 'tiny text-success'; }
          catch (e) { status.textContent = `✕ ${e.message}`; status.className = 'tiny text-danger'; }
        };
        ta.addEventListener('input', check);
        check();
      },
    });
  },

  'canon-format': () => {
    const ta = document.getElementById('canon-json');
    try { ta.value = prettyJson(JSON.parse(ta.value)); ta.dispatchEvent(new Event('input')); } catch (e) { toast(`Invalid JSON: ${e.message}`, 'error'); }
  },

  'canon-save': async el => saveCanonical(el, 'save'),
  'canon-sync': async el => saveCanonical(el, 'sync'),
});

async function saveCanonical(btn, mode) {
  const wrap = document.querySelector('#modal-body [data-sop]');
  const id = wrap?.dataset.sop;
  if (!id || wrap.dataset.draft === 'true' || !hasCapability('can_edit_canonical')) {
    toast('Only published canonical SOPs may be edited here.', 'error');
    return;
  }
  let parsed;
  try { parsed = JSON.parse(document.getElementById('canon-json').value); }
  catch (e) { toast(`Invalid JSON: ${e.message}`, 'error'); return; }

  const done = busy(btn);
  try {
    if (mode === 'save') {
      const r = await api.updateCanonical(id, parsed);
      toast(`Saved and synced — ${r.path || id}`, 'success', 5000);
    } else {
      const r = await api.syncPlaybook(id, parsed);
      toast(`Playbook synced — ${r.playbook_path || id}`, 'success', 5000);
    }
    closeModal();
  } catch (e) {
    toast(`Failed: ${e.message}`, 'error', 7000);
  } finally { done(); }
}

// ---------------------------------------------------------------------------

export default {
  id: 'review',
  label: 'Review queue',
  icon: 'review',
  badge: 'pending',
  title: 'Review & publish',
  subtitle: 'Security Reviewer gatekeeping (L0–L3 with SoD) and Process Owner publication to downstream agents.',
  refreshMs: 15000,

  async load(ctx) {
    const canIncidents = hasCapability('can_view_incidents');
    const [jobs, tasks, incidents] = await Promise.all([
      api.getGovernanceJobs(),
      api.getReviewTasks(),
      canIncidents ? api.getIncidents() : Promise.resolve({ incidents: [] }),
    ]);
    const pending = (tasks.tasks || []).filter(t => t.status === 'pending').length;
    ctx.setBadges({ pending });
    return { jobs: jobs.jobs || [], tasks: tasks.tasks || [], incidents: incidents.incidents || [], pending };
  },

  render({ jobs, tasks, incidents, pending }) {
    const canIncidents = hasCapability('can_view_incidents');
    if (!canIncidents && activeTab === 'incidents') activeTab = 'tasks';

    const approved = jobs.filter(j => j.current_state === 'approved').length;
    const changesRequested = jobs.filter(j => j.current_state === 'changes_requested').length;
    const canPublish = hasCapability('can_publish');
    const canEditDraft = hasCapability('can_edit_draft');
    const tab = (id, label, count, cls = '') => `<button class="tab ${activeTab === id ? 'active' : ''}" role="tab" data-tab="${id}" aria-selected="${activeTab === id}">${label}<span class="tab-count ${cls}">${count}</span></button>`;
    return `
      <div class="view-stack">
        ${approved ? `<div class="callout success">${icon('check')}<div>${canPublish
          ? `<b>${approved} approved SOP${approved > 1 ? 's are' : ' is'} ready to publish.</b> Open the <button class="chip" data-action="goto-jobs" style="padding:1px 9px">Lifecycle jobs</button> tab to publish.`
          : `<b>${approved} SOP${approved > 1 ? 's are' : ' is'} approved</b> and waiting for a Process Owner to publish.`}</div></div>` : ''}
        ${changesRequested && canEditDraft ? `<div class="callout warn">${icon('alert')}<div><b>${changesRequested} SOP${changesRequested > 1 ? 's have' : ' has'} changes requested.</b> Open the task to edit steps or JSON and resubmit for security review.</div></div>` : ''}
        <div class="panel panel-flush">
          <div class="tabs" role="tablist" style="padding:0 12px">
            ${tab('tasks', 'Review tasks', pending, pending ? 'attention' : '')}
            ${tab('jobs', 'Lifecycle jobs', jobs.length, approved ? 'attention' : '')}
            ${canIncidents ? tab('incidents', 'Quarantine incidents', incidents.length, incidents.length ? 'danger' : '') : ''}
          </div>
          <div>
            <div class="tab-panel" data-panel="tasks" ${activeTab === 'tasks' ? '' : 'hidden'}>${tasksTable(tasks)}</div>
            <div class="tab-panel" data-panel="jobs" ${activeTab === 'jobs' ? '' : 'hidden'}>${jobsTable(jobs)}</div>
            ${canIncidents ? `<div class="tab-panel" data-panel="incidents" ${activeTab === 'incidents' ? '' : 'hidden'}>${incidentsTable(incidents)}</div>` : ''}
          </div>
        </div>
      </div>`;
  },

  mount(root) {
    bindTabs(root, tab => { activeTab = tab; });
  },
};

registerActions({
  'goto-jobs': () => {
    activeTab = 'jobs';
    document.querySelector('.tab[data-tab="jobs"]')?.click();
  },
});
