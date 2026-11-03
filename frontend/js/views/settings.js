/**
 * Settings — the live pipeline configuration (hot-reloaded by the server).
 * A form is generated from the config's own shape, so new settings appear
 * automatically; a raw JSON tab is available for anything the form can't express.
 */

import { api } from '../api.js';
import { esc, icon, toast, busy, registerActions, bindTabs, prettyJson } from '../ui.js';

let original = null;       // last config saved/loaded
const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const prettyKey = k => String(k).replace(/_/g, ' ');

function kindOf(v) {
  if (typeof v === 'boolean') return 'boolean';
  if (typeof v === 'number') return 'number';
  if (typeof v === 'string') return 'string';
  if (Array.isArray(v) && v.every(x => typeof x === 'string')) return 'list:string';
  if (Array.isArray(v) && v.every(x => typeof x === 'number')) return 'list:number';
  return 'json';
}

function control(path, value) {
  const kind = kindOf(value);
  const attrs = `data-path='${esc(JSON.stringify(path))}' data-kind="${kind}" aria-label="${esc(path.join(' › '))}"`;
  if (kind === 'boolean') return `<span class="switch"><input type="checkbox" ${attrs} ${value ? 'checked' : ''}><span></span></span>`;
  if (kind === 'number') return `<input class="input mono" type="number" step="any" ${attrs} value="${esc(value)}">`;
  if (kind === 'string') return `<input class="input" type="text" ${attrs} value="${esc(value)}">`;
  if (kind.startsWith('list')) return `<input class="input mono" type="text" ${attrs} value="${esc(value.join(', '))}" placeholder="comma, separated, values">`;
  return `<textarea class="textarea code" rows="4" spellcheck="false" ${attrs}>${esc(prettyJson(value))}</textarea>`;
}

function rows(obj, path = []) {
  return Object.entries(obj).map(([k, v]) => {
    const p = [...path, k];
    if (isObj(v)) {
      return `<div class="cfg-row" style="grid-template-columns:1fr"><div class="cfg-name" style="text-transform:capitalize">${esc(prettyKey(k))}</div></div><div class="cfg-sub">${rows(v, p)}</div>`;
    }
    return `
      <div class="cfg-row" data-row='${esc(JSON.stringify(p))}'>
        <div><div class="cfg-name" style="text-transform:capitalize">${esc(prettyKey(k))}</div><div class="cfg-path">${esc(p.join('.'))}</div></div>
        <div>${control(p, v)}</div>
      </div>`;
  }).join('');
}

function formHtml(cfg) {
  const top = Object.entries(cfg);
  const scalars = Object.fromEntries(top.filter(([, v]) => !isObj(v)));
  const sections = top.filter(([, v]) => isObj(v));
  return `
    <div class="stack">
      ${Object.keys(scalars).length ? `<section class="cfg-section"><h4>General</h4>${rows(scalars)}</section>` : ''}
      ${sections.map(([k, v]) => `<section class="cfg-section"><h4>${esc(prettyKey(k))}</h4>${rows(v, [k])}</section>`).join('')}
    </div>`;
}

function setIn(target, path, value) {
  let o = target;
  path.slice(0, -1).forEach(k => { o = o[k]; });
  o[path[path.length - 1]] = value;
}
function getIn(target, path) { return path.reduce((o, k) => (o == null ? o : o[k]), target); }

/** Read every field back into a copy of the original config. Throws on bad input. */
function collect(root) {
  const out = JSON.parse(JSON.stringify(original));
  root.querySelectorAll('[data-path]').forEach(el => {
    const path = JSON.parse(el.dataset.path);
    const kind = el.dataset.kind;
    let v;
    if (kind === 'boolean') v = el.checked;
    else if (kind === 'number') {
      v = Number(el.value);
      if (el.value === '' || Number.isNaN(v)) throw new Error(`"${path.join('.')}" must be a number.`);
    }
    else if (kind === 'string') v = el.value;
    else if (kind === 'list:string') v = el.value.split(',').map(s => s.trim()).filter(Boolean);
    else if (kind === 'list:number') {
      v = el.value.split(',').map(s => s.trim()).filter(Boolean).map(Number);
      if (v.some(Number.isNaN)) throw new Error(`"${path.join('.')}" must be a list of numbers.`);
    }
    else { try { v = JSON.parse(el.value); } catch { throw new Error(`"${path.join('.')}" is not valid JSON.`); } }
    setIn(out, path, v);
  });
  return out;
}

function dirtyPaths(root) {
  const dirty = [];
  root.querySelectorAll('[data-path]').forEach(el => {
    const path = JSON.parse(el.dataset.path);
    const row = el.closest('.cfg-row');
    let changed;
    try {
      const probe = JSON.parse(JSON.stringify(original));
      const kind = el.dataset.kind;
      const cur = kind === 'boolean' ? el.checked
        : kind === 'number' ? Number(el.value)
        : kind === 'string' ? el.value
        : kind.startsWith('list') ? el.value.split(',').map(s => s.trim()).filter(Boolean).map(s => (kind === 'list:number' ? Number(s) : s))
        : JSON.parse(el.value);
      changed = JSON.stringify(cur) !== JSON.stringify(getIn(probe, path));
    } catch { changed = true; }
    row?.classList.toggle('dirty', changed);
    if (changed) dirty.push(path.join('.'));
  });
  return dirty;
}

async function persist(btn, cfg, ctx) {
  const done = busy(btn);
  try {
    const res = await api.updateConfig(cfg);
    original = res.config || cfg;
    toast('Configuration saved and hot-reloaded.', 'success');
    await ctx.reload();
  } catch (e) {
    toast(`Save failed: ${e.message}`, 'error', 7000);
  } finally { done(); }
}

registerActions({
  'cfg-save': (el, _e, ctx) => {
    try { persist(el, collect(document.getElementById('cfg-form')), ctx); }
    catch (e) { toast(e.message, 'error', 6000); }
  },
  'cfg-discard': (_el, _e, ctx) => ctx.reload(),
  'cfg-json-save': (el, _e, ctx) => {
    let parsed;
    try { parsed = JSON.parse(document.getElementById('cfg-json').value); } catch (e) { document.getElementById('cfg-json-status').textContent = `✕ ${e.message}`; return; }
    persist(el, parsed, ctx);
  },
});

export default {
  id: 'settings',
  label: 'Settings',
  icon: 'settings',
  title: 'Pipeline settings',
  subtitle: 'Limits, allowed file types and model routing. Changes apply immediately.',

  async load() {
    original = await api.getConfig();
    return original;
  },

  render(cfg) {
    return `
      <div class="view-stack">
        <div class="callout warn">${icon('alert')}<div>These settings are persisted and <b>hot-reloaded into the running server</b>. Lowering file limits or changing model providers affects the next document processed.</div></div>
        <div class="panel panel-flush">
          <div class="tabs" role="tablist" style="padding:0 12px">
            <button class="tab active" role="tab" data-tab="form">Form</button>
            <button class="tab" role="tab" data-tab="json">Raw JSON</button>
          </div>
          <div class="tab-panel panel-pad" data-panel="form" style="padding-top:18px">
            <div id="cfg-form">${formHtml(cfg)}</div>
            <div class="savebar" id="cfg-savebar" style="margin-top:16px">
              <span id="cfg-dirty" class="small muted">No unsaved changes</span>
              <div class="row"><button class="btn btn-outline" data-action="cfg-discard">Discard</button><button class="btn btn-primary" data-action="cfg-save" id="cfg-save" disabled>Save changes</button></div>
            </div>
          </div>
          <div class="tab-panel panel-pad" data-panel="json" hidden style="padding-top:18px">
            <textarea id="cfg-json" class="textarea code" spellcheck="false" style="min-height:460px">${esc(prettyJson(cfg))}</textarea>
            <div class="row-between" style="margin-top:10px"><span id="cfg-json-status" class="tiny"></span><button class="btn btn-primary" data-action="cfg-json-save">Save JSON</button></div>
          </div>
        </div>
      </div>`;
  },

  mount(root, _cfg, ctx) {
    bindTabs(root);
    const form = root.querySelector('#cfg-form');
    const label = root.querySelector('#cfg-dirty');
    const save = root.querySelector('#cfg-save');
    const refresh = () => {
      const d = dirtyPaths(form);
      label.textContent = d.length ? `${d.length} unsaved change${d.length > 1 ? 's' : ''}` : 'No unsaved changes';
      label.className = `small ${d.length ? 'text-warning strong' : 'muted'}`;
      save.disabled = !d.length;
    };
    form.addEventListener('input', refresh, { signal: ctx.signal });
    form.addEventListener('change', refresh, { signal: ctx.signal });

    const ta = root.querySelector('#cfg-json');
    const status = root.querySelector('#cfg-json-status');
    ta.addEventListener('input', () => {
      try { JSON.parse(ta.value); status.textContent = '✓ Valid JSON'; status.className = 'tiny text-success'; }
      catch (e) { status.textContent = `✕ ${e.message}`; status.className = 'tiny text-danger'; }
    }, { signal: ctx.signal });
  },
};
