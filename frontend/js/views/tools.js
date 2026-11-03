/**
 * Tools — the registered platform tool catalog the LLM may bind steps to.
 * Searchable; each function expands to show its required inputs and response shapes.
 */

import { api } from '../api.js';
import { esc, icon, fmt, emptyState, jsonBlock } from '../ui.js';

function matches(fn, q) {
  return !q || `${fn.function_name} ${fn.description}`.toLowerCase().includes(q);
}

function platformHtml(p, q) {
  const all = p.functions || [];
  const platformHit = !q || `${p.tool_name} ${p.platform} ${p.description}`.toLowerCase().includes(q);
  const funcs = platformHit ? all : all.filter(f => matches(f, q));
  if (!funcs.length) return '';
  return `
    <article class="tool-card">
      <div class="tool-card-head">
        <span class="tool-platform-name">${esc(String(p.platform || 'platform').toUpperCase())}</span>
        <span class="badge-tag">${funcs.length}${funcs.length !== all.length ? ` of ${all.length}` : ''} function${all.length === 1 ? '' : 's'}</span>
      </div>
      <div class="tool-name">${esc(p.tool_name)}</div>
      <p class="tool-desc">${esc(p.description || 'No description provided.')}</p>
      <div class="tool-funcs">
        ${funcs.map(f => `
          <details class="func-item" ${q && funcs.length <= 4 ? 'open' : ''}>
            <summary>
              <span class="func-name">${esc(f.function_name)}</span>
              <span class="tiny muted">${(f.required_inputs || []).length} input${(f.required_inputs || []).length === 1 ? '' : 's'}</span>
            </summary>
            <div class="func-body">
              <div>${esc(f.description || '')}</div>
              <div>
                <div class="field-label" style="margin-bottom:4px">Required inputs</div>
                ${(f.required_inputs || []).length ? f.required_inputs.map(a => `<span class="param">${esc(a)}</span>`).join('') : '<span class="muted">none</span>'}
              </div>
              ${f.response_schema ? `<div><div class="field-label" style="margin-bottom:4px">Response shapes</div>${jsonBlock(f.response_schema)}</div>` : ''}
            </div>
          </details>`).join('')}
      </div>
    </article>`;
}

export default {
  id: 'tools',
  label: 'Tool catalog',
  icon: 'tool',
  title: 'Platform tool catalog',
  subtitle: 'Registered tools and functions the converter can bind SOP steps to.',

  load: () => api.getTools(),

  render(data) {
    const platforms = data.platforms || [];
    return `
      <div class="view-stack">
        <div class="toolbar">
          <div class="search-wrapper">
            ${icon('search')}
            <input id="tool-search" type="search" class="search-input" style="width:300px" placeholder="Filter tools and functions…" aria-label="Filter tools">
          </div>
          <span class="spacer"></span>
          <span class="badge-tag">${platforms.length} platforms</span>
          <span class="badge-tag">${fmt.num(data.total_functions ?? platforms.reduce((n, p) => n + (p.functions || []).length, 0))} functions</span>
        </div>
        <div class="callout">${icon('info')}<div>This is the static catalog served by <code>/api/tools</code>. When the live <code>tools.platforms</code> schemas are available, the LLM uses those instead, so the two can differ.</div></div>
        <div id="tools-grid" class="tools-grid">${platforms.map(p => platformHtml(p, '')).join('')}</div>
      </div>`;
  },

  mount(root, data, ctx) {
    const platforms = data.platforms || [];
    const grid = root.querySelector('#tools-grid');
    root.querySelector('#tool-search').addEventListener('input', e => {
      const q = e.target.value.trim().toLowerCase();
      const html = platforms.map(p => platformHtml(p, q)).join('');
      grid.innerHTML = html || emptyState({ icon: 'search', title: 'No tools match', text: `Nothing matches “${q}”.` });
    }, { signal: ctx.signal });
  },
};
