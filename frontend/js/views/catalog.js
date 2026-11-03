/**
 * Catalog — what downstream agents can retrieve. Published-SOP counts per
 * clearance tier plus a search probe that behaves exactly like an agent query
 * (tenant isolation + clearance gating, every query audited).
 */

import { api } from '../api.js';
import { esc, icon, fmt, store, busy, tierBadge, registerActions, emptyState, jsonBlock } from '../ui.js';

const TIERS = [
  ['L0', 'Public', 'Anyone, any agent'],
  ['L1', 'Internal', 'Staff-level agents'],
  ['L2', 'Confidential', 'Restricted agents'],
  ['L3', 'Restricted', 'Security-cleared only'],
];

function resultsHtml(res) {
  const results = res.results || [];
  const caller = `<span class="tiny muted">Searched as tenant <b>${esc(res.caller_tenant)}</b> at clearance ${tierBadge(res.caller_clearance)}</span>`;
  if (!results.length) {
    return `<div class="panel-pad">${caller}${emptyState({ icon: 'search', title: 'No SOPs visible', text: 'Nothing matched, or matching SOPs sit above this clearance tier or belong to another tenant.' })}</div>`;
  }
  return `
    <div class="panel-pad stack-sm">${caller}</div>
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>SOP</th><th>Tier</th><th>Department</th><th class="num">Steps</th><th class="num">Relevance</th><th>Citation</th></tr></thead>
        <tbody>
          ${results.map(r => `
            <tr>
              <td style="max-width:360px">
                <div class="strong">${esc(r.title)}</div>
                <div class="cell-sub mono">${esc(r.sop_id)} · v${esc(r.version)}</div>
                ${r.purpose ? `<div class="cell-sub">${esc(r.purpose)}</div>` : ''}
                ${(r.matched_terms || []).length ? `<div class="row" style="margin-top:6px;gap:4px">${r.matched_terms.map(t => `<span class="badge-tag">${esc(t)}</span>`).join('')}</div>` : ''}
              </td>
              <td>${tierBadge(r.classification_level)}</td>
              <td>${esc(r.department || '—')}</td>
              <td class="num">${esc(r.step_count)}</td>
              <td class="num mono">${Number(r.relevance_score).toFixed(2)}</td>
              <td><span class="row" style="gap:4px;flex-wrap:nowrap"><code class="tiny">${esc(r.citation)}</code><button class="btn btn-ghost btn-icon-only btn-sm" data-action="copy" data-copy="${esc(r.citation)}" data-msg="Citation copied" aria-label="Copy citation">${icon('copy')}</button></span></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

registerActions({
  'catalog-search': async el => {
    const v = id => document.getElementById(id).value.trim();
    const form = {
      query: v('cat-query'), tenant_id: v('cat-tenant'), agent_id: v('cat-agent'),
      agent_persona: v('cat-persona') || undefined, department: v('cat-dept') || undefined,
      clearance_level: v('cat-clearance'), limit: Number(v('cat-limit')) || 10,
    };
    store.set('catalog-form', form);
    const out = document.getElementById('cat-results');
    const done = busy(el);
    try {
      out.innerHTML = resultsHtml(await api.searchDownstream(form));
    } catch (err) {
      out.innerHTML = `<div class="panel-pad"><div class="callout danger">${icon('alert')}<div>${esc(err.message)}</div></div></div>`;
    } finally { done(); }
  },
});

export default {
  id: 'catalog',
  label: 'Agent catalog',
  icon: 'search',
  title: 'Downstream agent catalog',
  subtitle: 'Published SOPs as downstream agents see them, gated by tenant and clearance tier.',

  load: () => api.getDownstreamStats(),

  render(stats) {
    const tiers = stats.by_tier || {};
    const f = { query: '', tenant_id: 'tn_northwind', agent_id: 'dashboard_probe', agent_persona: '', department: '', clearance_level: 'L1', limit: 10, ...store.get('catalog-form', {}) };
    return `
      <div class="view-stack">
        <div class="panel panel-flush">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('database')}Published SOPs by clearance tier</div>
              <div class="panel-subtitle">An agent can only retrieve SOPs at or below its own clearance, within its own tenant.</div>
            </div>
            <span class="badge-tag">${fmt.num(stats.total_published || 0)} published</span>
          </div>
          <div class="tier-grid">
            ${TIERS.map(([t, name, desc]) => `
              <div class="tier-card">
                <div class="row-between">${tierBadge(t)}<span class="tiny muted">${esc(name)}</span></div>
                <div class="tc-count">${fmt.num(tiers[t] || 0)}</div>
                <div class="tc-desc">${esc(desc)}</div>
              </div>`).join('')}
            <div class="tier-card">
              <div class="row-between"><span class="tier status-neutral">AUDIT</span><span class="tiny muted">Queries logged</span></div>
              <div class="tc-count">${fmt.num(stats.audit_queries_count || 0)}</div>
              <div class="tc-desc">Every search is recorded</div>
            </div>
          </div>
        </div>

        <div class="panel panel-flush">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('flask')}Simulate an agent query</div>
              <div class="panel-subtitle">Searches are added to the retrieval audit trail, exactly like a real agent's.</div>
            </div>
          </div>
          <div class="panel-pad stack">
            <div class="form-grid">
              <div class="field" style="grid-column:1/-1"><label for="cat-query">Query</label><input id="cat-query" class="input" value="${esc(f.query)}" placeholder="e.g. reset a locked account"></div>
              <div class="field"><label for="cat-tenant">Tenant</label><input id="cat-tenant" class="input" value="${esc(f.tenant_id)}"></div>
              <div class="field"><label for="cat-agent">Agent ID</label><input id="cat-agent" class="input" value="${esc(f.agent_id)}"></div>
              <div class="field"><label for="cat-persona">Persona <span class="muted" style="text-transform:none">(optional)</span></label><input id="cat-persona" class="input" value="${esc(f.agent_persona)}" placeholder="e.g. l1_support"></div>
              <div class="field"><label for="cat-dept">Department <span class="muted" style="text-transform:none">(optional)</span></label><input id="cat-dept" class="input" value="${esc(f.department)}"></div>
              <div class="field"><label for="cat-clearance">Clearance</label>
                <select id="cat-clearance" class="select">${TIERS.map(([t, n]) => `<option value="${t}" ${f.clearance_level === t ? 'selected' : ''}>${t} — ${n}</option>`).join('')}</select></div>
              <div class="field"><label for="cat-limit">Max results</label><input id="cat-limit" class="input" type="number" min="1" max="50" value="${esc(f.limit)}"></div>
            </div>
            <div><button class="btn btn-primary" data-action="catalog-search">${icon('search')}Search</button></div>
          </div>
          <div id="cat-results"></div>
        </div>
      </div>`;
  },

  mount(root, _d, ctx) {
    root.querySelectorAll('#cat-query, #cat-tenant, #cat-agent, #cat-persona, #cat-dept, #cat-limit').forEach(i =>
      i.addEventListener('keydown', e => { if (e.key === 'Enter') root.querySelector('[data-action="catalog-search"]').click(); }, { signal: ctx.signal }));
  },
};
