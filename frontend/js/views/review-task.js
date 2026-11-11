/**
 * Review task page — #/review/<task_id>
 * Everything a reviewer needs on one screen: the SOP's content with the evidence behind each
 * step, its classification and quality, the job history, and the decision form.
 * The decision itself is submitted by the shared `submit-decision` action in review.js.
 */

import { api } from '../api.js';
import {
  esc, icon, fmt, pill, jobPill, tierBadge, store, bindTabs, registerActions, emptyState, jsonBlock, prettyJson, busy, toast, confirmDialog,
} from '../ui.js';
import { classificationCard, qualityCard, timelineHtml, taskStatus, taskStatusPill } from './review.js';

// ---------------------------------------------------------------------------
// Evidence helpers
// ---------------------------------------------------------------------------

const lineRange = r => (Array.isArray(r) && r.length >= 2 ? (r[0] === r[1] ? `line ${r[0]}` : `lines ${r[0]}–${r[1]}`) : '');

function evidencePill(item) {
  if (typeof item?.verified !== 'boolean') return '';
  if (item.verified && item.evidence_source === 'visual_inspection') {
    return pill('FOUND IN SCREENSHOT', 'success');
  }
  return item.verified ? pill('FOUND IN DOCUMENT', 'success') : pill('NOT FOUND IN DOCUMENT', 'danger');
}

function quoteBlock(item) {
  if (!item?.quote) return '';
  const where = lineRange(item.source_lines);
  const loc = (item?.verified && item?.evidence_source === 'visual_inspection')
    ? `From ${item.image_ref || 'embedded screenshot'} · high-confidence visual inspection`
    : (where ? `${where} of the source document` : '');
  return `<blockquote class="quote ${item.verified === false ? 'quote-bad' : ''}">“${esc(item.quote)}”${loc ? `<div class="tiny muted" style="margin-top:4px">${esc(loc)}</div>` : ''}</blockquote>`;
}

function stepCard(s, i) {
  const input = s.input && s.input !== '{}' ? String(s.input) : '';
  return `
    <article class="sop-step-card ${s.verified ? 'step-ok' : 'step-bad'}">
      <div class="step-card-header">
        <div class="row" style="gap:8px">
          <span class="step-badge-number">Step ${esc(s.n ?? i + 1)}</span>
          ${s.actor ? `<span class="step-type-pill">${esc(s.actor)}</span>` : ''}
          ${s.risk && s.risk !== 'low' ? pill(`${s.risk} risk`, 'warning') : ''}
        </div>
        ${evidencePill(s)}
      </div>
      <div class="step-description strong">${esc(s.action)}</div>
      ${input ? `<div class="code-snippet-box"><code>${esc(input)}</code><button class="copy-btn" data-action="copy" data-copy="${esc(input)}" data-msg="Command copied">Copy</button></div>` : ''}
      ${quoteBlock(s)}
      ${(s.expected_outcome || s.warning) ? `
        <div class="step-meta-row">
          ${s.expected_outcome ? `<div class="step-meta-item"><span>Parse</span><em>${esc(s.expected_outcome)}</em></div>` : ''}
          ${s.warning ? `<div class="step-meta-item"><span>Fallback</span><code>${esc(s.warning)}</code></div>` : ''}
        </div>` : ''}
    </article>`;
}

/** One-line description of the many shapes the canonical SOP uses for list items. */
function text(v) {
  if (typeof v === 'string') return v;
  if (v === null || typeof v !== 'object') return String(v ?? '');
  if (v.role) return v.responsibility ? `${v.role} — ${v.responsibility}` : v.role;
  if (v.condition) return v.action ? `${v.condition} ${v.action}` : v.condition;
  return v.text ?? v.value ?? v.name ?? v.message ?? prettyJson(v);
}

/** Header metadata is {status, value, source_lines}; status "missing" means a default was filled in. */
function metaCell(label, v) {
  const value = v !== null && typeof v === 'object' ? v.value : v;
  const missing = v !== null && typeof v === 'object' && v.status === 'missing';
  return `<div class="meta-item"><div class="meta-label">${esc(label)}</div><div class="meta-value">${esc(value || '—')} ${missing ? pill('DEFAULT', 'warning', { dot: false, title: 'Not stated in the document; filled in with a default.' }) : ''}</div></div>`;
}

function itemList(arr) {
  if (!Array.isArray(arr) || !arr.length) return '<span class="muted small">None recorded.</span>';
  return `<ul class="stack-sm" style="margin-left:18px">${arr.map(x => `<li>${esc(text(x))}${typeof x === 'object' && x ? ` ${evidencePill(x)}` : ''}${typeof x === 'object' && x?.quote ? quoteBlock(x) : ''}</li>`).join('')}</ul>`;
}

function section(title, body) {
  return `<div class="result-card"><h5>${esc(title)}</h5>${body}</div>`;
}

function documentTab(c) {
  const src = c.source || {};
  const block = item => (item ? `<p>${esc(text(item))}</p>${quoteBlock(item)}` : '<span class="muted small">Not stated.</span>');
  return `
    <div class="stack">
      <div class="meta-grid">
        ${metaCell('Department', c.department)}
        ${metaCell('Owner', c.owner)}
        ${metaCell('Document version', c.version_label)}
        ${metaCell('Review date', c.review_date)}
        <div class="meta-item"><div class="meta-label">Source file</div><div class="meta-value mono">${esc(src.filename || '—')}</div></div>
        <div class="meta-item"><div class="meta-label">Size / type</div><div class="meta-value">${esc(src.size ? fmt.bytes(src.size) : '—')} · ${esc(src.detected_type || '—')}</div></div>
      </div>
      ${section('Purpose', block(c.purpose))}
      ${section('Scope', block(c.scope))}
      ${section('Preconditions', itemList(c.preconditions))}
      ${section('Roles', itemList(c.roles))}
      ${section('Exceptions & escalation', itemList(c.exceptions))}
      ${section('Notes', itemList(c.notes))}
      ${(c.references || []).length ? section('References', itemList(c.references)) : ''}
    </div>`;
}

// ---------------------------------------------------------------------------
// Decision card (always visible beside the content)
// ---------------------------------------------------------------------------

function decisionCard(task, c) {
  if (task.status !== 'pending') {
    const approved = taskStatus(task.status).tone === 'success';
    return `
      <div class="panel">
        <div class="panel-header"><div class="panel-title">${icon('check')}Decision recorded</div>${taskStatusPill(task.status)}</div>
        <div class="kv-list">
          <div><span class="k">Reviewer</span><span class="v">${esc(task.reviewer || '—')}</span></div>
          <div><span class="k">Decided</span><span class="v">${fmt.date(task.completed_at)}</span></div>
        </div>
        ${task.notes ? `<div class="field-label" style="margin-top:12px">Notes</div><p class="secondary small" style="margin-top:4px">${esc(task.notes)}</p>` : ''}
      </div>`;
  }
  const q = c?.quality; const cl = c?.classification;
  return `
    <form id="decision-form" class="panel stack" data-page="true" data-task="${esc(task.task_id)}" data-sop="${esc(task.sop_id)}" novalidate>
      <div class="panel-title">${icon('review')}Your decision</div>
      <div class="callout">${icon('info')}<div><b>Separation of duties.</b> You must be a different person from the uploader (<b>${esc(task.uploaded_by)}</b>) and the last editor. Automated approvals are rejected.</div></div>

      <div class="field">
        <label for="dec-reviewer">Your name or ID</label>
        <input id="dec-reviewer" class="input" value="${esc(store.get('reviewer', ''))}" placeholder="e.g. security.reviewer@company.com" autocomplete="username">
      </div>

      <div class="field">
        <span class="field-label">Decision</span>
        <div class="radio-cards" role="radiogroup" aria-label="Decision" style="grid-template-columns:1fr">
          <label class="radio-card approve"><input type="radio" name="decision" value="approve" checked><span class="rc-body"><span class="rc-title">Approve</span><span class="rc-desc">Passes the 6 publication gates</span></span></label>
          <label class="radio-card changes"><input type="radio" name="decision" value="changes_requested"><span class="rc-body"><span class="rc-title">Request changes</span><span class="rc-desc">Send back for correction</span></span></label>
          <label class="radio-card reject"><input type="radio" name="decision" value="reject"><span class="rc-body"><span class="rc-title">Reject</span><span class="rc-desc">Do not publish</span></span></label>
        </div>
      </div>

      <div class="field">
        <label for="dec-notes">Notes <span id="dec-notes-req" class="muted" style="text-transform:none;font-weight:500">(optional)</span></label>
        <textarea id="dec-notes" class="textarea" rows="3" placeholder="What did you check? What needs to change?"></textarea>
      </div>

      <label class="row" style="gap:10px;flex-wrap:nowrap;align-items:flex-start;cursor:pointer">
        <span class="switch"><input type="checkbox" id="dec-classif" ${cl?.level ? '' : 'checked'}><span></span></span>
        <span class="small secondary">I confirm the confidentiality tier${cl?.level ? ` <b>${esc(cl.level)}</b>` : ''} is correct (publication gate 6).</span>
      </label>

      <div id="dec-error" class="field-error" role="alert"></div>
      <button type="button" class="btn btn-primary" data-action="submit-decision" data-quality='${esc(JSON.stringify(q || {}))}'>${icon('check')}Submit decision</button>
    </form>`;
}

registerActions({
  'rt-unverified': el => {
    const on = el.classList.toggle('active');
    document.getElementById('rt-steps')?.classList.toggle('only-unverified', on);
  },
});

// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Inline step editor (Steps tab). Edits go to the draft only; nothing is published.
// ---------------------------------------------------------------------------

let editDirty = false;

function editCard(s, i, canonicalStep) {
  const isTool = s.step_type === 'tool_call';
  const ev = canonicalStep && typeof canonicalStep.verified === 'boolean'
    ? (canonicalStep.verified
        ? pill(canonicalStep.evidence_source === 'visual_inspection' ? 'QUOTE FOUND (SCREENSHOT)' : 'QUOTE FOUND', 'success')
        : pill('QUOTE NOT FOUND', 'danger'))
    : '';
  return `
    <article class="sop-step-card edit-card" data-ref="${s.step_number ?? ''}" data-type="${esc(s.step_type || 'command')}">
      <div class="step-card-header">
        <div class="row" style="gap:8px">
          <span class="step-badge-number" data-num>Step ${i + 1}</span>
          <span class="step-type-pill">${esc((s.step_type || 'command').replace('_', ' '))}</span>
          ${s.shell ? `<span class="mono tiny muted">${esc(s.shell)}</span>` : ''}
          ${ev}
        </div>
        <div class="row" style="gap:4px">
          <button type="button" class="btn btn-ghost btn-icon-only btn-sm" data-action="rt-step-up" aria-label="Move step up" title="Move up">${icon('arrowup')}</button>
          <button type="button" class="btn btn-ghost btn-icon-only btn-sm" data-action="rt-step-down" aria-label="Move step down" title="Move down">${icon('arrowdown')}</button>
          <button type="button" class="btn btn-ghost btn-icon-only btn-sm pb-del" data-action="rt-step-del" aria-label="Delete step" title="Delete step">${icon('trash')}</button>
        </div>
      </div>
      <div class="stack">
        <div class="field"><label>What this step does</label>
          <textarea class="textarea" rows="2" data-f="sop_step_description">${esc(s.sop_step_description || '')}</textarea></div>
        ${isTool
          ? `<div class="field"><label>Tool inputs (JSON) · <span class="mono" style="text-transform:none">${esc([s.platform, s.function_name].filter(Boolean).join('.'))}</span></label>
              <textarea class="textarea code" rows="3" spellcheck="false" data-f="comm_inputs">${esc(prettyJson(s.comm_inputs || {}))}</textarea></div>`
          : `<div class="field"><label>Command</label>
              <textarea class="textarea code" rows="2" spellcheck="false" data-f="command">${esc(s.command || '')}</textarea></div>`}
        <div class="field"><label>Source quote</label>
          <textarea class="textarea" rows="2" data-f="source_quote">${esc(s.source_quote || '')}</textarea>
          <span class="field-hint">Copy it word-for-word from the document. It is checked against the document when you save.</span></div>
        <div class="form-grid">
          <div class="field"><label>Parse instruction</label><textarea class="textarea" rows="4" data-f="parse_instruction">${esc(s.parse_instruction || '')}</textarea></div>
          <div class="field"><label>Fallback command</label><textarea class="textarea code" rows="4" spellcheck="false" data-f="fallback_command">${esc(s.fallback_command || '')}</textarea></div>
        </div>
        ${s.execute_if ? `<div class="tiny muted">Runs only if <code>${esc(s.execute_if)}</code> (not editable here)</div>` : ''}
      </div>
    </article>`;
}

function renumberEditCards() {
  const cards = [...document.querySelectorAll('#rt-edit-list .edit-card')];
  cards.forEach((c, i) => {
    c.querySelector('[data-num]').textContent = `Step ${i + 1}`;
    c.querySelector('[data-action="rt-step-up"]').disabled = i === 0;
    c.querySelector('[data-action="rt-step-down"]').disabled = i === cards.length - 1;
  });
}

function collectEditedSteps() {
  return [...document.querySelectorAll('#rt-edit-list .edit-card')].map(card => {
    const g = f => card.querySelector(`[data-f="${f}"]`)?.value ?? '';
    const step = {
      ref: card.dataset.ref ? Number(card.dataset.ref) : null,
      sop_step_description: g('sop_step_description'),
      source_quote: g('source_quote'),
      parse_instruction: g('parse_instruction'),
      fallback_command: g('fallback_command'),
    };
    if (card.dataset.type === 'tool_call') step.comm_inputs = g('comm_inputs'); else step.command = g('command');
    return step;
  });
}

function showEditError(messages) {
  const box = document.getElementById('rt-edit-error');
  const list = [].concat(messages).filter(Boolean);
  box.innerHTML = list.length
    ? `<div class="callout danger">${icon('alert')}<div>${list.length === 1 ? esc(list[0]) : `<b>Fix these before saving:</b><ul>${list.map(m => `<li>${esc(m)}</li>`).join('')}</ul>`}</div></div>` : '';
}

registerActions({
  'rt-edit-steps': () => {
    document.getElementById('rt-steps-view').hidden = true;
    document.getElementById('rt-edit').hidden = false;
    editDirty = false;
    renumberEditCards();
    document.getElementById('rt-edit').scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  },

  'rt-edit-cancel': async (_el, _e, ctx) => {
    if (editDirty) {
      const ok = await confirmDialog({ title: 'Discard your edits?', message: 'Nothing has been saved yet. Your changes to the steps will be lost.', confirmLabel: 'Discard', tone: 'danger' });
      if (!ok) return;
    }
    editDirty = false;
    await ctx.reload();
  },

  'rt-step-up': el => {
    const card = el.closest('.edit-card'); const prev = card.previousElementSibling;
    if (prev) { prev.before(card); editDirty = true; renumberEditCards(); }
  },
  'rt-step-down': el => {
    const card = el.closest('.edit-card'); const next = card.nextElementSibling;
    if (next) { next.after(card); editDirty = true; renumberEditCards(); }
  },
  'rt-step-del': async el => {
    const card = el.closest('.edit-card');
    const label = card.querySelector('[data-num]').textContent;
    const ok = await confirmDialog({ title: `Delete ${label.toLowerCase()}?`, message: 'It is removed when you save. Later steps are renumbered.', confirmLabel: 'Delete step', tone: 'danger' });
    if (!ok) return;
    card.remove(); editDirty = true; renumberEditCards();
  },
  'rt-add-step': () => {
    const list = document.getElementById('rt-edit-list');
    list.insertAdjacentHTML('beforeend', editCard({ step_number: null, step_type: 'command', shell: 'powershell', sop_step_description: '', command: '' }, list.children.length, null));
    editDirty = true; renumberEditCards();
    list.lastElementChild.querySelector('[data-f="sop_step_description"]').focus();
  },

  'rt-save-steps': async (el, _e, ctx) => {
    showEditError([]);
    const actor = document.getElementById('rt-actor').value.trim();
    if (!actor) { showEditError('Enter your name or ID so the edit can be attributed.'); document.getElementById('rt-actor').focus(); return; }
    const steps = collectEditedSteps();
    const problems = [];
    if (!steps.length) problems.push('An SOP needs at least one step.');
    steps.forEach((s, i) => {
      if (!s.sop_step_description.trim()) problems.push(`Step ${i + 1}: describe what the step does.`);
      if ('command' in s && !s.command.trim()) problems.push(`Step ${i + 1}: a command step needs a command.`);
      if ('comm_inputs' in s) { try { JSON.parse(s.comm_inputs || '{}'); } catch { problems.push(`Step ${i + 1}: the tool inputs are not valid JSON.`); } }
    });
    if (problems.length) { showEditError(problems); return; }

    const sop = document.getElementById('rt-edit').dataset.sop;
    const done = busy(el);
    try {
      const res = await api.saveDraftSteps(sop, { actor, steps });
      store.set('reviewer', actor);
      const cs = res.canonical_draft?.steps || [];
      const found = cs.filter(s => s.verified).length;
      editDirty = false;
      toast(`Steps saved. ${found} of ${cs.length} quotes found in the document. ${actor} can no longer approve this SOP — a different reviewer must.`, 'success', 8000);
      (res.warnings || []).forEach(w => toast(w, 'warning', 9000));
      await ctx.reload();
    } catch (e) {
      showEditError(e.failures?.length ? e.failures : e.message);
    } finally { done(); }
  },
});


// ---------------------------------------------------------------------------
// Inline JSON editor (JSON tab)
// ---------------------------------------------------------------------------

let jsonDirty = false;

function jsonStatus() {
  const ta = document.getElementById('rt-json-text'); const st = document.getElementById('rt-json-status');
  if (!ta || !st) return;
  try { JSON.parse(ta.value); st.textContent = '✓ Valid JSON'; st.className = 'tiny text-success'; }
  catch (e) { st.textContent = `✕ ${e.message}`; st.className = 'tiny text-danger'; }
}

function showJsonError(messages) {
  const box = document.getElementById('rt-json-error');
  const list = [].concat(messages).filter(Boolean);
  box.innerHTML = list.length
    ? `<div class="callout danger">${icon('alert')}<div>${list.length === 1 ? esc(list[0]) : `<b>Fix these before saving:</b><ul>${list.map(m => `<li>${esc(m)}</li>`).join('')}</ul>`}</div></div>` : '';
}

registerActions({
  'rt-json-edit': () => {
    document.getElementById('rt-json-view').hidden = true;
    document.getElementById('rt-json-edit').hidden = false;
    jsonDirty = false; jsonStatus();
    document.getElementById('rt-json-text').focus();
  },

  'rt-json-format': () => {
    const ta = document.getElementById('rt-json-text');
    try { ta.value = prettyJson(JSON.parse(ta.value)); jsonStatus(); } catch (e) { toast(`Invalid JSON: ${e.message}`, 'error'); }
  },

  'rt-json-cancel': async (_el, _e, ctx) => {
    if (jsonDirty) {
      const ok = await confirmDialog({ title: 'Discard your edits?', message: 'Nothing has been saved yet. Your changes to the JSON will be lost.', confirmLabel: 'Discard', tone: 'danger' });
      if (!ok) return;
    }
    jsonDirty = false;
    await ctx.reload();
  },

  'rt-json-save': async (el, _e, ctx) => {
    showJsonError([]);
    const actor = document.getElementById('rt-json-actor').value.trim();
    if (!actor) { showJsonError('Enter your name or ID so the edit can be attributed.'); document.getElementById('rt-json-actor').focus(); return; }
    let canonical;
    try { canonical = JSON.parse(document.getElementById('rt-json-text').value); }
    catch (e) { showJsonError(`This isn't valid JSON yet: ${e.message}`); return; }

    const done = busy(el);
    try {
      const res = await api.saveDraftCanonical(document.getElementById('rt-json-edit').dataset.sop, { actor, canonical });
      store.set('reviewer', actor);
      const cs = res.canonical_draft?.steps || [];
      jsonDirty = false;
      toast(`JSON saved. ${cs.filter(s => s.verified).length} of ${cs.length} step quotes found in the document. ${actor} can no longer approve this SOP — a different reviewer must.`, 'success', 8000);
      (res.warnings || []).forEach(w => toast(w, 'warning', 9000));
      await ctx.reload();
    } catch (e) {
      showJsonError(e.failures?.length ? e.failures : e.message);
    } finally { done(); }
  },
});

export default {
  id: 'review-task',
  parent: 'review',          // keeps "Review queue" highlighted in the sidebar
  hidden: true,              // reachable only as #/review/<task_id>
  label: 'Review task',
  icon: 'review',
  title: 'Review task',
  subtitle: '',

  async load(ctx) {
    const id = ctx.params?.[0];
    const { tasks = [] } = await api.getReviewTasks();
    const task = tasks.find(t => t.task_id === id);
    if (!task) return { id, task: null };
    const [canonical, job, draft] = await Promise.all([
      api.getCanonical(task.sop_id).catch(() => null),
      api.getJob(task.job_id).catch(() => null),
      task.status === 'pending' ? api.getDraft(task.sop_id).catch(() => null) : Promise.resolve(null),
    ]);
    return { id, task, canonical, job, draft };
  },

  render({ id, task, canonical: c, job, draft }) {
    const back = '<a class="breadcrumb" href="#/review">← Review queue</a>';
    if (!task) {
      return `<div class="view-stack">${back}<div class="panel">${emptyState({ icon: 'review', title: `Review task ${id} not found`, text: 'It may have been decided already, or the server was restarted. Open the review queue to see current tasks.', action: '<a class="btn btn-primary" href="#/review">Back to the queue</a>' })}</div></div>`;
    }

    const steps = c?.steps || [];
    const found = steps.filter(s => s.verified).length;
    const pct = steps.length ? Math.round((found / steps.length) * 100) : 0;
    const gaugeTone = pct >= 90 ? 'success' : pct >= 50 ? 'warning' : 'danger';
    const issues = c?.issues || [];
    const tab = (idTab, label, extra = '') => `<button class="tab ${idTab === 'steps' ? 'active' : ''}" role="tab" data-tab="${idTab}">${label}${extra}</button>`;

    return `
      <div class="view-stack">
        ${back}
        <div class="row-between">
          <div class="stack-sm">
            <div class="row" style="gap:10px">
              <h3 style="font-family:var(--font-heading);font-size:22px;letter-spacing:-0.01em">${esc(c?.title || task.sop_id)}</h3>
              ${c?.classification ? tierBadge(c.classification.level) : ''}
              ${task.status === 'pending' ? pill('PENDING REVIEW', 'warning') : taskStatusPill(task.status)}
            </div>
            <div class="tiny muted"><span class="mono">${esc(task.sop_id)}</span> · v${esc(task.version)} · task <span class="mono">${esc(task.task_id)}</span> · uploaded by ${esc(task.uploaded_by)} · assigned to <b>${esc(task.assigned_role)}</b> · due ${fmt.date(task.due_date)} ${task.is_overdue ? pill('OVERDUE', 'danger', { dot: false }) : ''}</div>
          </div>
        </div>

        ${c ? '' : `<div class="callout warn">${icon('alert')}<div><b>The draft couldn't be loaded</b>, so the SOP content and quality metrics are unavailable. The server will apply its default gate values if you decide now.</div></div>`}
        ${c?.lifecycle?.last_editor ? `<div class="callout warn">${icon('alert')}<div><b>Steps were edited by ${esc(c.lifecycle.last_editor)}</b> (${fmt.date(c.lifecycle.last_edited_at)}). Under separation of duties, ${esc(c.lifecycle.last_editor)} cannot approve this SOP — a different reviewer must decide.</div></div>` : ''}
        ${issues.length ? `<div class="callout danger">${icon('alert')}<div><b>${issues.length} open issue${issues.length > 1 ? 's' : ''} recorded on this SOP.</b> They block approval until resolved — see the Issues tab.</div></div>` : ''}

        <div class="grid-main-side">
          <div class="stack">
            ${c ? `
              <div class="panel">
                <div class="row-between" style="margin-bottom:10px">
                  <div><div class="strong">Evidence check</div><div class="tiny muted">Each step cites a quote from the source document. This checks the quote really is there.</div></div>
                  <div class="strong mono">${found} / ${steps.length} found</div>
                </div>
                <div class="gauge-track" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="Steps with a verified quote"><div class="gauge-fill ${gaugeTone}" style="width:${pct}%"></div></div>
              </div>` : ''}

            <div class="panel panel-flush">
              <div class="tabs" role="tablist" style="padding:0 12px">
                ${tab('steps', 'Steps', ` <span class="tab-count ${found < steps.length ? 'attention' : ''}">${steps.length}</span>`)}
                ${tab('document', 'Document')}
                ${issues.length ? tab('issues', 'Issues', ` <span class="tab-count danger">${issues.length}</span>`) : ''}
                ${tab('history', 'History')}
                ${tab('json', 'JSON')}
              </div>
              <div class="panel-pad" style="padding-top:18px">
                <div class="tab-panel" data-panel="steps">
                  <div id="rt-steps-view">
                    <div class="toolbar" style="margin-bottom:12px">
                      ${steps.length ? `<button class="chip" data-action="rt-unverified">Show only steps without a found quote <span class="count">${steps.length - found}</span></button>` : ''}
                      <span class="spacer"></span>
                      ${draft?.editable
                        ? `<button class="btn btn-sm btn-secondary" data-action="rt-edit-steps">${icon('edit')}Edit steps</button>`
                        : `<span class="tiny muted">${esc(draft ? (draft.editable_reason || '') : (task.status === 'pending' ? "Editing isn't available: the draft file for this SOP wasn't found." : ''))}</span>`}
                    </div>
                    ${steps.length ? `<div class="stack" id="rt-steps">${steps.map(stepCard).join('')}</div>` : emptyState({ icon: 'list', title: 'No steps in this SOP' })}
                  </div>
                  ${draft?.editable ? `
                  <div id="rt-edit" data-sop="${esc(task.sop_id)}" hidden>
                    <div class="callout">${icon('info')}<div><b>Editing steps.</b> Nothing is published until the SOP is approved. When you save, every source quote is checked against the document again and the evidence figures update. Because you will have edited it, <b>a different reviewer must approve it</b>.</div></div>
                    <div class="stack" id="rt-edit-list" style="margin-top:14px">${(draft.steps || []).map((s, i) => editCard(s, i, c?.steps?.[i])).join('')}</div>
                    <div style="margin-top:12px"><button type="button" class="btn btn-outline" data-action="rt-add-step">+ Add step</button></div>
                    <div id="rt-edit-error" style="margin-top:12px" role="alert"></div>
                    <div class="savebar" style="margin-top:16px">
                      <div class="field" style="flex-direction:row;align-items:center;gap:10px"><label for="rt-actor" style="margin:0">Your name or ID</label><input id="rt-actor" class="input" style="width:240px" value="${esc(store.get('reviewer', ''))}" autocomplete="username"></div>
                      <div class="row"><button type="button" class="btn btn-outline" data-action="rt-edit-cancel">Cancel</button><button type="button" class="btn btn-primary" data-action="rt-save-steps">${icon('check')}Save steps</button></div>
                    </div>
                  </div>` : ''}
                </div>
                <div class="tab-panel" data-panel="document" hidden>${c ? documentTab(c) : emptyState({ icon: 'file', title: 'Draft unavailable' })}</div>
                ${issues.length ? `<div class="tab-panel" data-panel="issues" hidden><div class="stack">${issues.map(i => `<div class="callout danger">${icon('alert')}<div>${esc(text(i))}</div></div>`).join('')}</div></div>` : ''}
                <div class="tab-panel" data-panel="history" hidden>
                  <div class="stack">
                    ${job ? `<div class="row">${jobPill(job.current_state)}<span class="mono tiny muted">${esc(job.job_id)}</span></div>` : ''}
                    ${timelineHtml(job?.history || [])}
                    ${(c?.transformations || []).length ? `<details class="accordion"><summary>Text cleaning applied <span class="tab-count">${c.transformations.length}</span></summary><div class="acc-body">${jsonBlock(c.transformations)}</div></details>` : ''}
                  </div>
                </div>
                <div class="tab-panel" data-panel="json" hidden>
                  <div id="rt-json-view" class="stack-sm">
                    <div class="row-between">
                      <span class="tiny muted">The canonical SOP. The tier, quality scores, source and lifecycle are managed by the system and can't be edited.</span>
                      ${draft?.editable && c
                        ? `<button class="btn btn-sm btn-secondary" data-action="rt-json-edit">${icon('edit')}Edit JSON</button>`
                        : `<span class="tiny muted">${esc(draft ? (draft.editable_reason || '') : '')}</span>`}
                    </div>
                    ${c ? jsonBlock(c) : emptyState({ icon: 'file', title: 'Draft unavailable' })}
                  </div>
                  ${draft?.editable && c ? `
                  <div id="rt-json-edit" data-sop="${esc(task.sop_id)}" hidden>
                    <div class="stack-sm">
                      <div class="callout">${icon('info')}<div><b>Editing the JSON.</b> You can change the title, metadata, purpose, scope, preconditions, roles, exceptions, notes and steps. Changing the confidentiality tier, quality, source or lifecycle is refused. Every quote is checked against the document again when you save, and because you will have edited it, <b>a different reviewer must approve it</b>.</div></div>
                      <textarea id="rt-json-text" class="textarea code" spellcheck="false" aria-label="Canonical SOP JSON" style="min-height:480px">${esc(prettyJson(c))}</textarea>
                      <div class="row-between"><span id="rt-json-status" class="tiny"></span><button type="button" class="btn btn-sm btn-ghost" data-action="rt-json-format">Format JSON</button></div>
                      <div id="rt-json-error" role="alert"></div>
                      <div class="savebar">
                        <div class="field" style="flex-direction:row;align-items:center;gap:10px"><label for="rt-json-actor" style="margin:0">Your name or ID</label><input id="rt-json-actor" class="input" style="width:240px" value="${esc(store.get('reviewer', ''))}" autocomplete="username"></div>
                        <div class="row"><button type="button" class="btn btn-outline" data-action="rt-json-cancel">Cancel</button><button type="button" class="btn btn-primary" data-action="rt-json-save">${icon('check')}Save JSON</button></div>
                      </div>
                    </div>
                  </div>` : ''}
                </div>
              </div>
            </div>
          </div>

          <div class="stack sticky-side">
            ${decisionCard(task, c)}
            ${c ? classificationCard(c.classification) + qualityCard(c.quality) : ''}
          </div>
        </div>
      </div>`;
  },

  mount(root, data, ctx) {
    if (data.task) {
      document.getElementById('page-title').textContent = `Review ${data.task.task_id}`;
      document.getElementById('page-subtitle').textContent = data.canonical?.title || data.task.sop_id;
    }
    bindTabs(root);
    editDirty = false; jsonDirty = false;
    root.querySelector('#rt-edit')?.addEventListener('input', () => { editDirty = true; }, { signal: ctx.signal });
    root.querySelector('#rt-json-text')?.addEventListener('input', () => { jsonDirty = true; jsonStatus(); }, { signal: ctx.signal });
    const notesReq = root.querySelector('#dec-notes-req');
    root.querySelector('.radio-cards')?.addEventListener('change', e => {
      notesReq.textContent = e.target.value !== 'approve' ? '(required)' : '(optional)';
    }, { signal: ctx.signal });
  },
};
