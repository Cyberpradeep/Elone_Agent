/**
 * Playbooks — searchable library of published, HMAC-signed OKF playbooks,
 * with a deep inspector (steps, details, rulebook, raw source) and integrity check.
 */

import { api } from '../api.js';
import {
  esc, icon, fmt, pill, store, toast, busy, openModal, closeModal, registerActions, bindTabs,
  emptyState, jsonBlock,
} from '../ui.js';

let copyCounts = {};   // sop_id -> how many playbook files carry it (the same id can sit in two category folders)
let currentFilters = { query: '', category: 'all', sort: 'title', layout: store.get('pb-layout', 'cards') };

const confidenceTone = s => (s >= 0.9 ? 'success' : s >= 0.7 ? 'warning' : 'danger');
const pct = s => `${Math.round((Number(s) || 0) * 100)}%`;

function integrityPill(p) {
  const ok = p.integrity?.is_valid;
  return pill(ok ? 'VERIFIED' : 'FAILED CHECK', ok ? 'success' : 'danger', { title: p.integrity?.reason || '' });
}

function matches(p, q) {
  if (!q) return true;
  const hay = [p.sop_id, p.title, p.category, p.platform, p.description, p.target_os].join(' ').toLowerCase();
  return q.toLowerCase().split(/\s+/).every(term => hay.includes(term));
}

function applyFilters(list) {
  const { query, category, sort } = currentFilters;
  const out = list.filter(p => matches(p, query) && (category === 'all' || p.category === category));
  const by = {
    title: (a, b) => String(a.title).localeCompare(String(b.title)),
    steps: (a, b) => (b.step_count || 0) - (a.step_count || 0),
    confidence: (a, b) => (b.confidence_score || 0) - (a.confidence_score || 0),
    category: (a, b) => String(a.category).localeCompare(String(b.category)) || String(a.title).localeCompare(String(b.title)),
  };
  return out.sort(by[sort] || by.title);
}

function cardHtml(p) {
  return `
    <article class="pb-card" tabindex="0" role="button" data-action="inspect-sop" data-id="${esc(p.sop_id)}" aria-label="Inspect ${esc(p.title)}">
      <div class="pb-card-top">
        <span class="id-cell">${esc(p.sop_id)}</span>
        <span class="row" style="gap:6px;flex-wrap:nowrap">${integrityPill(p)}<button class="btn btn-ghost btn-icon-only btn-sm pb-del" data-action="delete-sop" data-id="${esc(p.sop_id)}" data-title="${esc(p.title)}" aria-label="Delete ${esc(p.title)}" title="Delete playbook">${icon('trash')}</button></span>
      </div>
      <div class="stack-sm">
        <h4>${esc(p.title)}</h4>
        <p>${esc(p.description || 'No description provided.')}</p>
      </div>
      <div class="row">
        <span class="badge-tag">${esc(p.category)}</span>
        <span class="badge-tag">${esc(p.platform)} · ${esc(p.target_os)}</span>
      </div>
      <div class="pb-card-foot">
        <span><b class="text-success">${esc(pct(p.confidence_score))}</b> confidence</span>
        <span>${esc(p.step_count)} step${p.step_count === 1 ? '' : 's'}</span>
      </div>
    </article>`;
}

function tableHtml(list) {
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>SOP</th><th>Category</th><th>Platform</th><th>Confidence</th><th class="num">Steps</th><th>Integrity</th><th></th></tr></thead>
        <tbody>
          ${list.map(p => `
            <tr>
              <td><div class="id-cell">${esc(p.sop_id)}</div><div class="strong">${esc(p.title)}</div></td>
              <td><span class="badge-tag">${esc(p.category)}</span></td>
              <td><div>${esc(p.platform)}</div><div class="cell-sub mono">${esc(p.target_os)}</div></td>
              <td>${pill(`${pct(p.confidence_score)} ${p.confidence_level || ''}`.trim(), confidenceTone(p.confidence_score))}</td>
              <td class="num">${esc(p.step_count)}</td>
              <td>${integrityPill(p)}</td>
              <td><div class="row-actions"><button class="btn btn-sm btn-secondary" data-action="inspect-sop" data-id="${esc(p.sop_id)}">${icon('eye')}Inspect</button><button class="btn btn-sm btn-danger-ghost" data-action="delete-sop" data-id="${esc(p.sop_id)}" data-title="${esc(p.title)}" aria-label="Delete ${esc(p.title)}">${icon('trash')}Delete</button></div></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function resultsHtml(all) {
  const list = applyFilters(all);
  if (!all.length) {
    return emptyState({ icon: 'book', title: 'No published playbooks yet', text: 'Playbooks appear here once an SOP is approved and published.', action: '<a class="btn btn-primary" href="#/ingestion">Ingest an SOP</a>' });
  }
  if (!list.length) {
    return emptyState({ icon: 'search', title: 'No playbooks match', text: 'Try a different search term or clear the category filter.', action: '<button class="btn btn-outline" data-action="pb-clear">Clear filters</button>' });
  }
  return currentFilters.layout === 'table'
    ? `<div class="panel panel-flush">${tableHtml(list)}</div>`
    : `<div class="cards-grid">${list.map(cardHtml).join('')}</div>`;
}

// ---------------------------------------------------------------------------
// Inspector modal
// ---------------------------------------------------------------------------

export function stepHtml(s, idx) {
  const isTool = s.step_type === 'tool_call';
  const parse = s.output_parse_instruction || s.parse_instruction;
  return `
    <div class="sop-step-card">
      <div class="step-card-header">
        <div class="row" style="gap:8px">
          <span class="step-badge-number">Step ${esc(s.step_number || idx + 1)}</span>
          <span class="step-type-pill">${esc((s.step_type || 'command').replace('_', ' '))}</span>
          ${s.shell ? `<span class="mono tiny muted">${esc(s.shell)}</span>` : ''}
        </div>
        ${s.timeout_seconds ? `<span class="tiny muted">timeout ${esc(s.timeout_seconds)}s</span>` : ''}
      </div>
      <div class="step-description">${esc(s.sop_step_description || '')}</div>
      ${isTool ? `<div class="step-meta-row"><div class="step-meta-item"><span>Tool</span><code>${esc([s.platform, s.function_name].filter(Boolean).join('.'))}</code></div></div>` : ''}
      ${s.command ? `<div class="code-snippet-box"><code>${esc(s.command)}</code><button class="copy-btn" data-action="copy" data-copy="${esc(s.command)}" data-msg="Command copied">Copy</button></div>` : ''}
      ${s.fallback_command ? `<div class="tiny strong text-warning" style="margin-top:8px">FALLBACK</div><div class="code-snippet-box"><code>${esc(s.fallback_command)}</code></div>` : ''}
      ${(s.execute_if || parse || (s.comm_inputs && Object.keys(s.comm_inputs).length)) ? `
        <div class="step-meta-row">
          ${s.execute_if ? `<div class="step-meta-item"><span>Only if</span><code>${esc(s.execute_if)}</code></div>` : ''}
          ${parse ? `<div class="step-meta-item"><span>Parse</span><em>${esc(parse)}</em></div>` : ''}
          ${s.comm_inputs && Object.keys(s.comm_inputs).length ? `<div class="step-meta-item"><span>Inputs</span><code>${esc(JSON.stringify(s.comm_inputs))}</code></div>` : ''}
        </div>` : ''}
    </div>`;
}

function inspectorHtml(d) {
  const fm = d.frontmatter || {};
  const steps = d.steps || [];
  const ents = fm.required_entities || [];
  const rb = d.rulebook || {};
  const integ = d.integrity || {};
  return `
    <div class="stack">
      <div class="meta-grid">
        <div class="meta-item"><div class="meta-label">Category</div><div class="meta-value">${esc(fm.category || '—')}</div></div>
        <div class="meta-item"><div class="meta-label">Platform / OS</div><div class="meta-value mono">${esc(fm.platform || 'system')} / ${esc(fm.target_os || 'windows')}</div></div>
        <div class="meta-item"><div class="meta-label">Confidence</div><div class="meta-value">${esc(pct(fm.confidence_score))} <span class="muted">${esc(fm.confidence_level || '')}</span></div></div>
        <div class="meta-item"><div class="meta-label">HMAC signature</div><div class="meta-value" id="sop-integrity">${pill(integ.is_valid ? 'AUTHENTIC' : 'FAILED CHECK', integ.is_valid ? 'success' : 'danger', { title: integ.reason || '' })}</div></div>
      </div>

      <div class="tabs in-modal" role="tablist">
        <button class="tab active" role="tab" data-tab="steps">Steps <span class="tab-count">${steps.length}</span></button>
        <button class="tab" role="tab" data-tab="details" >Details</button>
        <button class="tab" role="tab" data-tab="rulebook">Rulebook ${rb.exists ? '' : '<span class="tab-count">none</span>'}</button>
        <button class="tab" role="tab" data-tab="raw">Raw file</button>
      </div>
      <div>
        <div class="tab-panel" data-panel="steps"><div class="stack">${steps.length ? steps.map(stepHtml).join('') : emptyState({ icon: 'list', title: 'No steps recorded' })}</div></div>
        <div class="tab-panel" data-panel="details" hidden>
          <div class="stack">
            <div><div class="field-label">Description</div><p class="secondary" style="margin-top:4px">${esc(fm.description || 'No description provided.')}</p></div>
            ${ents.length ? `<div><div class="field-label">Required entities</div><div class="row" style="margin-top:6px">${ents.map(e => `<code class="badge-tag">{{entities.${esc(e)}}}</code>`).join('')}</div></div>` : ''}
            <div><div class="field-label">File</div><code>${esc(d.file_path)}</code></div>
            <div><div class="field-label">Front matter</div>${jsonBlock(fm)}</div>
          </div>
        </div>
        <div class="tab-panel" data-panel="rulebook" hidden>
          ${rb.exists ? `<div class="stack-sm"><code>${esc(rb.path)}</code><pre class="code-block">${esc(rb.content)}</pre></div>` : emptyState({ icon: 'book', title: 'No rulebook yet', text: 'A reflection rulebook is created when the playbook is first written.' })}
        </div>
        <div class="tab-panel" data-panel="raw" hidden><pre class="code-block" style="max-height:420px">${esc(d.raw_content)}</pre></div>
      </div>
    </div>`;
}

registerActions({
  'inspect-sop': async el => {
    const id = el.dataset.id;
    let d;
    try { d = await api.getSop(id); } catch (err) { toast(`Couldn't open ${id}: ${err.message}`, 'error'); return; }
    openModal({
      title: `${d.frontmatter?.title || id}`,
      size: 'lg',
      body: inspectorHtml(d),
      footer: `
        <button class="btn btn-danger-ghost" data-action="delete-sop" data-id="${esc(id)}" data-title="${esc(d.frontmatter?.title || id)}" style="margin-right:auto">${icon('trash')}Delete…</button>
        <button class="btn btn-outline" data-action="edit-canonical" data-id="${esc(id)}">${icon('edit')}Canonical JSON</button>
        <button class="btn btn-secondary" data-action="verify-sop" data-id="${esc(id)}">${icon('shield')}Re-verify HMAC</button>
        <button class="btn btn-primary" data-action="close-modal">Close</button>`,
      onMount: root => bindTabs(root),
    });
  },

  'verify-sop': async el => {
    const done = busy(el);
    try {
      const r = await api.verifySop(el.dataset.id);
      const holder = document.getElementById('sop-integrity');
      if (holder) holder.innerHTML = pill(r.is_valid ? 'AUTHENTIC' : 'TAMPERED OR CORRUPT', r.is_valid ? 'success' : 'danger', { title: r.reason || '' });
      toast(r.is_valid ? 'HMAC stamp is authentic — the playbook is untampered.' : `Integrity alert: ${r.reason || 'signature mismatch'}`, r.is_valid ? 'success' : 'error', 6000);
    } finally { done(); }
  },

  'delete-sop': el => {
    const id = el.dataset.id;
    const title = el.dataset.title || id;
    const copies = copyCounts[id] || 1;
    openModal({
      title: 'Delete playbook',
      size: 'md',
      body: `
        <form id="del-form" class="stack" data-id="${esc(id)}" novalidate>
          <div class="meta-item"><div class="meta-label">Playbook</div><div class="meta-value">${esc(title)} <span class="mono muted">${esc(id)}</span></div></div>
          ${copies > 1 ? `<div class="callout warn">${icon('alert')}<div><b>${copies} playbook files share this id</b> (in different category folders). All of them will be removed.</div></div>` : ''}
          <div class="callout danger">${icon('trash')}<div>
            <b>This takes the playbook out of use.</b>
            <ul>
              <li>The playbook and its canonical JSON and rulebook are moved to <code>knowledge_base/_trash/</code> — they are <b>not erased</b>.</li>
              <li>It is removed from the downstream agent catalog straight away, so agents can no longer retrieve it.</li>
              <li>Its lifecycle job is marked <b>soft-deleted</b>, and the category index pages are refreshed.</li>
            </ul>
          </div></div>
          <div class="form-grid">
            <div class="field"><label for="del-actor">Your name or ID</label><input id="del-actor" class="input" value="${esc(store.get('reviewer', ''))}" placeholder="who is deleting this" autocomplete="username"></div>
            <div class="field"><label for="del-reason">Reason <span class="muted" style="text-transform:none">(optional)</span></label><input id="del-reason" class="input" placeholder="e.g. superseded by v2"></div>
          </div>
          <div class="field">
            <label for="del-confirm">Type <span class="mono" style="text-transform:none">${esc(id)}</span> to confirm</label>
            <input id="del-confirm" class="input mono" autocomplete="off" spellcheck="false" placeholder="${esc(id)}">
          </div>
          <div id="del-error" class="field-error" role="alert"></div>
        </form>`,
      footer: `<button class="btn btn-outline" data-action="close-modal">Cancel</button>
               <button class="btn btn-danger" id="del-go" data-action="confirm-delete-sop" disabled>${icon('trash')}Delete playbook</button>`,
      onMount: root => {
        const actor = root.querySelector('#del-actor'), typed = root.querySelector('#del-confirm'), go = root.querySelector('#del-go');
        const sync = () => { go.disabled = !(actor.value.trim() && typed.value.trim() === id); };
        actor.addEventListener('input', sync); typed.addEventListener('input', sync); sync();
        (actor.value ? typed : actor).focus();
      },
    });
  },

  'confirm-delete-sop': async (el, _e, ctx) => {
    const form = document.getElementById('del-form');
    const id = form.dataset.id;
    const actor = form.querySelector('#del-actor').value.trim();
    const reason = form.querySelector('#del-reason').value.trim();
    const err = document.getElementById('del-error');
    err.textContent = '';
    if (form.querySelector('#del-confirm').value.trim() !== id) { err.textContent = `Type ${id} exactly to confirm.`; return; }
    const done = busy(el);
    try {
      const r = await api.deleteSop(id, { actor, reason });
      store.set('reviewer', actor);
      closeModal();
      toast(`Deleted ${r.sop_id}. Files moved to ${r.trash_dir}.`, 'success', 7000);
      (r.warnings || []).forEach(w => toast(w, 'warning', 8000));
      await ctx.reload();
      ctx.refreshBadges();
    } catch (e) {
      err.textContent = e.message;
    } finally { done(); }
  },

  'pb-clear': () => {
    currentFilters = { ...currentFilters, query: '', category: 'all' };
    const g = document.getElementById('global-search'); if (g) g.value = '';
    document.dispatchEvent(new CustomEvent('elone:filters'));
  },
});

// ---------------------------------------------------------------------------

export default {
  id: 'playbooks',
  label: 'Playbooks',
  icon: 'book',
  badge: 'playbooks',
  title: 'OKF playbooks',
  subtitle: 'Published, signed playbooks compiled from human SOPs.',

  async load(ctx) {
    const data = await api.listSops();
    ctx.setBadges({ playbooks: data.total ?? (data.playbooks || []).length });
    return data;
  },

  render(data, ctx) {
    currentFilters.query = ctx.state.query || '';
    const list = data.playbooks || [];
    copyCounts = list.reduce((m, p) => ({ ...m, [p.sop_id]: (m[p.sop_id] || 0) + 1 }), {});
    const cats = [...new Set(list.map(p => p.category))].sort();
    const failed = list.filter(p => !p.integrity?.is_valid).length;
    if (currentFilters.category !== 'all' && !cats.includes(currentFilters.category)) currentFilters.category = 'all';

    return `
      <div class="view-stack">
        ${failed ? `<div class="callout danger">${icon('alert')}<div><b>${failed} playbook${failed > 1 ? 's' : ''} failed the HMAC integrity check.</b> Don't run ${failed > 1 ? 'them' : 'it'} until the signature is verified — the file may have been edited outside the review process.</div></div>` : ''}
        <div class="toolbar">
          <div class="search-wrapper">
            ${icon('search')}
            <input id="pb-search" type="search" class="search-input" style="width:320px" placeholder="Filter by ID, title, category…" value="${esc(currentFilters.query)}" aria-label="Filter playbooks">
          </div>
          <span class="spacer"></span>
          <select id="pb-sort" class="select" style="width:auto" aria-label="Sort playbooks">
            ${[['title', 'Title'], ['category', 'Category'], ['steps', 'Most steps'], ['confidence', 'Confidence']].map(([v, l]) => `<option value="${v}" ${currentFilters.sort === v ? 'selected' : ''}>Sort: ${l}</option>`).join('')}
          </select>
          <div class="segmented" role="group" aria-label="Layout">
            <button data-layout="cards" class="${currentFilters.layout === 'cards' ? 'active' : ''}" aria-label="Card layout" title="Cards">${icon('grid')}</button>
            <button data-layout="table" class="${currentFilters.layout === 'table' ? 'active' : ''}" aria-label="Table layout" title="Table">${icon('list')}</button>
          </div>
        </div>
        <div class="chips" id="pb-chips" role="group" aria-label="Category">
          <button class="chip ${currentFilters.category === 'all' ? 'active' : ''}" data-cat="all">All <span class="count">${list.length}</span></button>
          ${cats.map(c => `<button class="chip ${currentFilters.category === c ? 'active' : ''}" data-cat="${esc(c)}">${esc(c)} <span class="count">${list.filter(p => p.category === c).length}</span></button>`).join('')}
        </div>
        <div id="pb-results">${resultsHtml(list)}</div>
      </div>`;
  },

  mount(root, data, ctx) {
    const list = data.playbooks || [];
    const results = root.querySelector('#pb-results');
    const search = root.querySelector('#pb-search');
    const paint = () => { results.innerHTML = resultsHtml(list); };
    const opts = { signal: ctx.signal };

    search.addEventListener('input', () => {
      currentFilters.query = search.value;
      const g = document.getElementById('global-search'); if (g && g.value !== search.value) g.value = search.value;
      paint();
    }, opts);

    root.querySelector('#pb-chips').addEventListener('click', e => {
      const chip = e.target.closest('.chip'); if (!chip) return;
      currentFilters.category = chip.dataset.cat;
      root.querySelectorAll('#pb-chips .chip').forEach(c => c.classList.toggle('active', c === chip));
      paint();
    }, opts);

    root.querySelector('#pb-sort').addEventListener('change', e => { currentFilters.sort = e.target.value; paint(); }, opts);

    root.querySelector('.segmented').addEventListener('click', e => {
      const b = e.target.closest('button[data-layout]'); if (!b) return;
      currentFilters.layout = b.dataset.layout; store.set('pb-layout', b.dataset.layout);
      root.querySelectorAll('.segmented button').forEach(x => x.classList.toggle('active', x === b));
      paint();
    }, opts);

    // Cards are role="button": make Enter / Space activate them.
    results.addEventListener('keydown', e => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.pb-card')) { e.preventDefault(); e.target.click(); }
    }, opts);

    // Header search + "clear filters" feed the same list.
    document.addEventListener('elone:query', e => { currentFilters.query = e.detail; search.value = e.detail; paint(); }, opts);
    document.addEventListener('elone:filters', () => {
      search.value = currentFilters.query;
      root.querySelectorAll('#pb-chips .chip').forEach(c => c.classList.toggle('active', c.dataset.cat === currentFilters.category));
      paint();
    }, opts);
  },
};
