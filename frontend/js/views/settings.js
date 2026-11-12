/**
 * Settings — live pipeline configuration (hot-reloaded by the server) and
 * tenant-scoped Users & Service Agents provisioning (Admin only).
 */

import { api } from '../api.js';
import { getUser, hasCapability, formatRoleLabel } from '../auth.js';
import {
  esc, icon, fmt, pill, tierBadge, toast, busy, registerActions,
  bindTabs, prettyJson, openModal, closeModal, confirmDialog, emptyState,
} from '../ui.js';

let original = null;       // last config saved/loaded
let cachedUsers = [];      // last user list loaded
let activeTab = null;      // 'form' | 'json' | 'users'
let userQuery = '';

const PERSONA_MAX_CLEARANCE = {
  public_agent: 'L0',
  general_assistant: 'L1',
  service_desk_agent: 'L1',
  it_support_agent: 'L1',
  devops_engineer: 'L2',
  incident_responder: 'L2',
  security_agent: 'L3',
  compliance_auditor: 'L3',
  admin_agent: 'L3',
};
const CLEARANCE_RANK = { L0: 0, L1: 1, L2: 2, L3: 3 };

const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const prettyKey = k => String(k).replace(/_/g, ' ');

// Must mirror backend/config/settings.py _EDITABLE_SCHEMA
const EDITABLE_CONFIG_PATHS = new Set([
  'file_upload.max_file_size_mb',
  'file_upload.max_page_count',
  'file_upload.max_text_lines',
  'file_upload.max_text_words',
  'file_upload.max_table_rows',
  'images.max_images_per_sop',
  'images.max_image_dimension',
  'images.target_image_dimension',
  'governance.min_passing_score',
  'governance.max_daily_calls',
  'governance.max_calls_per_job',
  'governance.llm_timeout_seconds',
  'governance.llm_max_retries',
  'governance.sop_scan_interval_minutes',
]);

function isEditablePath(path) {
  return EDITABLE_CONFIG_PATHS.has(path.join('.'));
}

// ---------------------------------------------------------------------------
// Pipeline Config Form Helpers
// ---------------------------------------------------------------------------

function kindOf(v) {
  if (typeof v === 'boolean') return 'boolean';
  if (typeof v === 'number') return 'number';
  if (typeof v === 'string') return 'string';
  if (Array.isArray(v) && v.every(x => typeof x === 'string')) return 'list:string';
  if (Array.isArray(v) && v.every(x => typeof x === 'number')) return 'list:number';
  return 'json';
}

function control(path, value, editable = true) {
  const kind = kindOf(value);
  const disAttr = editable ? '' : ' disabled title="Server-managed setting (edit settings.json / .env)"';
  const attrs = `data-path='${esc(JSON.stringify(path))}' data-kind="${kind}" aria-label="${esc(path.join(' › '))}"${disAttr}`;
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
    const editable = isEditablePath(p);
    return `
      <div class="cfg-row" data-row='${esc(JSON.stringify(p))}'>
        <div><div class="cfg-name" style="text-transform:capitalize">${esc(prettyKey(k))}</div><div class="cfg-path">${esc(p.join('.'))}${editable ? '' : ' · read-only'}</div></div>
        <div>${control(p, v, editable)}</div>
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
  for (let i = 0; i < path.length - 1; i++) {
    const k = path[i];
    if (!isObj(o[k])) o[k] = {};
    o = o[k];
  }
  o[path[path.length - 1]] = value;
}
function getIn(target, path) { return path.reduce((o, k) => (o == null ? o : o[k]), target); }

function readControlValue(el, path) {
  const kind = el.dataset.kind;
  if (kind === 'boolean') return el.checked;
  if (kind === 'number') {
    const v = Number(el.value);
    if (el.value === '' || Number.isNaN(v)) throw new Error(`"${path.join('.')}" must be a number.`);
    return v;
  }
  if (kind === 'string') return el.value;
  if (kind === 'list:string') return el.value.split(',').map(s => s.trim()).filter(Boolean);
  if (kind === 'list:number') {
    const v = el.value.split(',').map(s => s.trim()).filter(Boolean).map(Number);
    if (v.some(Number.isNaN)) throw new Error(`"${path.join('.')}" must be a list of numbers.`);
    return v;
  }
  try { return JSON.parse(el.value); }
  catch { throw new Error(`"${path.join('.')}" is not valid JSON.`); }
}

/** Collect only changed editable fields into a minimal patch object for POST /api/config. */
function collect(root) {
  const patch = {};
  root.querySelectorAll('[data-path]').forEach(el => {
    const path = JSON.parse(el.dataset.path);
    if (!isEditablePath(path) || el.disabled) return;
    const v = readControlValue(el, path);
    if (JSON.stringify(v) !== JSON.stringify(getIn(original, path))) {
      setIn(patch, path, v);
    }
  });
  return patch;
}

/** Compute minimal diff between parsed Raw JSON and original so locked unchanged keys aren't sent. */
function collectJsonDiff(parsed, base = original) {
  if (!isObj(parsed)) throw new Error('Configuration JSON must be an object.');
  if (!isObj(base)) return parsed;
  const diff = {};
  for (const [k, v] of Object.entries(parsed)) {
    const prev = base[k];
    if (isObj(v) && isObj(prev)) {
      const sub = collectJsonDiff(v, prev);
      if (Object.keys(sub).length) diff[k] = sub;
    } else if (JSON.stringify(v) !== JSON.stringify(prev)) {
      diff[k] = v;
    }
  }
  return diff;
}

function dirtyPaths(root) {
  const dirty = [];
  root.querySelectorAll('[data-path]').forEach(el => {
    const path = JSON.parse(el.dataset.path);
    if (!isEditablePath(path)) return;
    const row = el.closest('.cfg-row');
    let changed;
    try {
      const cur = readControlValue(el, path);
      changed = JSON.stringify(cur) !== JSON.stringify(getIn(original, path));
    } catch { changed = true; }
    row?.classList.toggle('dirty', changed);
    if (changed) dirty.push(path.join('.'));
  });
  return dirty;
}

async function persist(btn, patch, ctx) {
  if (!patch || !Object.keys(patch).length) {
    toast('No configuration changes to save.', 'info');
    return;
  }
  const done = busy(btn);
  try {
    const res = await api.updateConfig(patch);
    original = res.config || original;
    toast('Configuration saved and hot-reloaded.', 'success');
    await ctx.reload();
  } catch (e) {
    toast(`Save failed: ${e.message}`, 'error', 7000);
  } finally { done(); }
}

// ---------------------------------------------------------------------------
// Users & Service Agents Management (Admin only)
// ---------------------------------------------------------------------------

function filterUsersList(list) {
  const q = userQuery.trim().toLowerCase();
  const sorted = [...list].sort((a, b) => {
    if ((a.actor_type === 'human') !== (b.actor_type === 'human')) return a.actor_type === 'human' ? -1 : 1;
    return String(a.username).localeCompare(String(b.username));
  });
  if (!q) return sorted;
  return sorted.filter(u =>
    [u.username, u.display_name, u.identity, u.agent_id, u.agent_persona, ...(u.roles || [])]
      .filter(Boolean).join(' ').toLowerCase().includes(q)
  );
}

function usersTableHtml(users) {
  const me = getUser() || {};
  const list = filterUsersList(users);
  if (!users.length) {
    return emptyState({ icon: 'users', title: 'No accounts found', text: 'Create a human operator or downstream service agent for this tenant.' });
  }
  if (!list.length) {
    return emptyState({ icon: 'search', title: 'No accounts match your filter' });
  }
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>Account</th><th>Type</th><th>Role</th><th>Clearance</th><th>Status</th><th>Last login</th><th></th></tr></thead>
        <tbody>
          ${list.map(u => {
            const isSelf = u.sub === me.sub;
            const isAgent = u.actor_type === 'agent' || (u.roles || []).includes('agent');
            return `
              <tr>
                <td>
                  <div class="strong">${esc(u.display_name || u.username)} ${isSelf ? pill('YOU', 'info', { dot: false }) : ''}</div>
                  <div class="cell-sub mono">${esc(u.username)}${u.identity && u.identity !== u.username ? ` · ${esc(u.identity)}` : ''}</div>
                </td>
                <td>
                  <div>${pill(isAgent ? 'AGENT' : 'HUMAN', isAgent ? 'neutral' : 'info', { dot: false })}</div>
                  ${u.agent_persona ? `<div class="cell-sub mono">${esc(u.agent_persona)}</div>` : ''}
                  ${u.agent_id && !u.agent_persona ? `<div class="cell-sub mono">${esc(u.agent_id)}</div>` : ''}
                </td>
                <td>${(u.roles || []).map(r => `<span class="role-pill">${esc(formatRoleLabel(r))}</span>`).join(' ')}</td>
                <td>${tierBadge(u.clearance || 'L1')}</td>
                <td>${u.disabled ? pill('DISABLED', 'danger') : pill('ACTIVE', 'success')}</td>
                <td class="nowrap">
                  <div class="mono tiny">${u.last_login_at ? fmt.date(u.last_login_at) : 'Never'}</div>
                  ${u.last_login_at ? `<div class="cell-sub">${fmt.rel(u.last_login_at)}</div>` : ''}
                </td>
                <td>
                  <div class="row-actions">
                    <button class="btn btn-sm btn-outline" data-action="usr-edit" data-sub="${esc(u.sub)}">${icon('edit')}Edit</button>
                    ${isAgent ? `<button class="btn btn-sm btn-secondary" data-action="usr-token" data-sub="${esc(u.sub)}" ${u.disabled ? 'disabled title="Re-enable agent before minting a token"' : ''}>${icon('lock')}Mint token</button>` : ''}
                    <button class="btn btn-sm ${u.disabled ? 'btn-secondary' : 'btn-danger-ghost'}" data-action="usr-toggle" data-sub="${esc(u.sub)}" ${isSelf && !u.disabled ? 'disabled title="Admins cannot disable their own active account"' : ''}>${u.disabled ? 'Enable' : 'Disable'}</button>
                  </div>
                </td>
              </tr>`;
          }).join('')}
        </tbody>
      </table>
    </div>`;
}

function usersTabHtml(users, tenantId) {
  const humans = users.filter(u => u.actor_type === 'human').length;
  const agents = users.filter(u => u.actor_type !== 'human').length;
  return `
    <div class="stack">
      <div class="callout">${icon('shield')}<div><b>Option A roles for tenant <code class="mono">${esc(tenantId || 'default')}</code>:</b> <b>Process Owner</b> uploads/edits drafts &amp; publishes · <b>Security Reviewer</b> decides L0–L3 reviews (promote clearance to <code>L3</code> to approve restricted SOPs) · <b>Admin</b> manages config, telemetry, logs, users &amp; deletion · <b>Agent</b> reads published playbooks via minted tokens.</div></div>
      <div class="toolbar">
        <div class="search-wrapper">
          ${icon('search')}
          <input id="usr-search" type="search" class="search-input" style="width:280px" placeholder="Filter by username, identity, role…" value="${esc(userQuery)}" aria-label="Filter users">
        </div>
        <span class="tiny muted">${humans} human · ${agents} agent</span>
        <span class="spacer"></span>
        <button class="btn btn-sm btn-secondary" data-action="usr-new" data-kind="agent">${icon('plus')}New service agent</button>
        <button class="btn btn-sm btn-primary" data-action="usr-new" data-kind="human">${icon('plus')}New user</button>
      </div>
      <div id="usr-table-host">${usersTableHtml(users)}</div>
    </div>`;
}

function personaOptionsHtml(selected = '') {
  const entries = Object.entries(PERSONA_MAX_CLEARANCE);
  return `<option value="" ${!selected ? 'selected' : ''}>(No fixed persona — use custom clearance)</option>`
    + entries.map(([p, maxClr]) => `<option value="${esc(p)}" ${selected === p ? 'selected' : ''}>${esc(p)} (max ${maxClr})</option>`).join('');
}

function syncPersonaClearance(personaSelect, clrSelect, hintEl, clampOnChange = false) {
  const p = personaSelect?.value || '';
  const maxClr = p ? (PERSONA_MAX_CLEARANCE[p] || 'L3') : 'L3';
  const maxRank = CLEARANCE_RANK[maxClr] ?? 3;
  [...(clrSelect?.options || [])].forEach(opt => {
    opt.disabled = (CLEARANCE_RANK[opt.value] ?? 0) > maxRank;
  });
  if (clampOnChange || (CLEARANCE_RANK[clrSelect.value] ?? 0) > maxRank) {
    clrSelect.value = maxClr;
  }
  if (hintEl) {
    hintEl.textContent = p
      ? `Persona "${p}" caps clearance at ${maxClr}.`
      : 'Agent tokens can retrieve published SOPs up to the assigned clearance tier.';
  }
}

function openCreateAccountModal(kind, ctx) {
  const isAgent = kind === 'agent';
  openModal({
    title: isAgent ? 'New service agent' : 'New human user',
    size: 'md',
    body: `
      <form id="usr-create-form" class="stack" data-kind="${esc(kind)}" novalidate>
        <div class="form-grid">
          <div class="field">
            <label for="usr-c-username">Username</label>
            <input id="usr-c-username" class="input mono" placeholder="${isAgent ? 'svc.devops.bot' : 'carol.sec'}" autocomplete="off" required autofocus>
            <span class="field-hint">2–64 chars (letters, digits, <code>. _ - @</code>).</span>
          </div>
          <div class="field">
            <label for="usr-c-display">Display name <span class="muted" style="text-transform:none">(optional)</span></label>
            <input id="usr-c-display" class="input" placeholder="${isAgent ? 'DevOps Automation Agent' : 'Carol Security'}">
          </div>
        </div>
        <div class="field">
          <label for="usr-c-identity">Identity <span class="muted" style="text-transform:none">(optional — used for audit logs &amp; SoD)</span></label>
          <input id="usr-c-identity" class="input mono" placeholder="${isAgent ? 'svc.devops.bot@corp.example' : 'carol@corp.example (defaults to username)'}">
        </div>
        ${isAgent ? `
          <div class="form-grid">
            <div class="field">
              <label for="usr-c-persona">Agent persona</label>
              <select id="usr-c-persona" class="select">${personaOptionsHtml('general_assistant')}</select>
            </div>
            <div class="field">
              <label for="usr-c-clearance">Clearance tier</label>
              <select id="usr-c-clearance" class="select">
                ${['L0', 'L1', 'L2', 'L3'].map(l => `<option value="${l}" ${l === 'L1' ? 'selected' : ''}>${l}</option>`).join('')}
              </select>
              <span id="usr-c-clr-hint" class="field-hint"></span>
            </div>
          </div>
          <div class="field">
            <label for="usr-c-agentid">Agent ID <span class="muted" style="text-transform:none">(optional)</span></label>
            <input id="usr-c-agentid" class="input mono" placeholder="Defaults to agent_&lt;username&gt;">
          </div>
        ` : `
          <div class="form-grid">
            <div class="field">
              <label for="usr-c-role">Option A role</label>
              <select id="usr-c-role" class="select">
                <option value="process_owner">Process Owner (Author &amp; Publisher)</option>
                <option value="security_reviewer">Security Reviewer (L0–L3 Gatekeeper)</option>
                <option value="admin">Admin (Platform &amp; Tenant Ops)</option>
              </select>
            </div>
            <div class="field">
              <label for="usr-c-clearance">Clearance tier</label>
              <select id="usr-c-clearance" class="select">
                <option value="L0">L0 (Public)</option>
                <option value="L1" selected>L1 (Internal)</option>
                <option value="L2">L2 (Confidential)</option>
                <option value="L3">L3 (Restricted)</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label for="usr-c-password">Initial password</label>
            <input id="usr-c-password" class="input" type="password" autocomplete="new-password" placeholder="Minimum 8 characters" required>
          </div>
        `}
        <div id="usr-c-err" class="field-error" role="alert"></div>
      </form>`,
    footer: `<button class="btn btn-outline" data-action="close-modal">Cancel</button>
             <button class="btn btn-primary" data-action="usr-create-save">${icon('plus')}${isAgent ? 'Create agent' : 'Create user'}</button>`,
    onMount: root => {
      if (isAgent) {
        const ps = root.querySelector('#usr-c-persona');
        const cs = root.querySelector('#usr-c-clearance');
        const hint = root.querySelector('#usr-c-clr-hint');
        syncPersonaClearance(ps, cs, hint, true);
        ps.addEventListener('change', () => syncPersonaClearance(ps, cs, hint, true));
      }
    },
  });
  // keep linter happy if ctx used inside action
  void ctx;
}

function openEditAccountModal(u) {
  const me = getUser() || {};
  const isSelf = u.sub === me.sub;
  const isAgent = u.actor_type === 'agent' || (u.roles || []).includes('agent');
  const currentRole = (u.roles || [])[0] || 'process_owner';
  const isSelfAdmin = isSelf && (u.roles || []).includes('admin');

  openModal({
    title: `Edit ${isAgent ? 'agent' : 'user'} — ${u.username}`,
    size: 'md',
    body: `
      <form id="usr-edit-form" class="stack" data-sub="${esc(u.sub)}" data-agent="${isAgent ? '1' : '0'}" novalidate>
        <div class="meta-grid">
          <div class="meta-item"><div class="meta-label">Username</div><div class="meta-value mono">${esc(u.username)}</div></div>
          <div class="meta-item"><div class="meta-label">Identity</div><div class="meta-value mono">${esc(u.identity)}</div></div>
          <div class="meta-item"><div class="meta-label">Tenant</div><div class="meta-value mono">${esc(u.tenant_id)}</div></div>
        </div>
        <div class="field">
          <label for="usr-e-display">Display name</label>
          <input id="usr-e-display" class="input" value="${esc(u.display_name || '')}">
        </div>
        ${isAgent ? `
          <div class="form-grid">
            <div class="field">
              <label for="usr-e-persona">Agent persona</label>
              <select id="usr-e-persona" class="select">${personaOptionsHtml(u.agent_persona || '')}</select>
            </div>
            <div class="field">
              <label for="usr-e-clearance">Clearance tier</label>
              <select id="usr-e-clearance" class="select">
                ${['L0', 'L1', 'L2', 'L3'].map(l => `<option value="${l}" ${u.clearance === l ? 'selected' : ''}>${l}</option>`).join('')}
              </select>
              <span id="usr-e-clr-hint" class="field-hint"></span>
            </div>
          </div>
        ` : `
          <div class="form-grid">
            <div class="field">
              <label for="usr-e-role">Option A role</label>
              <select id="usr-e-role" class="select" ${isSelfAdmin ? 'disabled title="Admins cannot remove their own admin role"' : ''}>
                <option value="process_owner" ${currentRole === 'process_owner' ? 'selected' : ''}>Process Owner (Author &amp; Publisher)</option>
                <option value="security_reviewer" ${currentRole === 'security_reviewer' ? 'selected' : ''}>Security Reviewer (L0–L3 Gatekeeper)</option>
                <option value="admin" ${currentRole === 'admin' ? 'selected' : ''}>Admin (Platform &amp; Tenant Ops)</option>
              </select>
              ${isSelfAdmin ? '<span class="field-hint">You cannot remove your own Admin role.</span>' : ''}
            </div>
            <div class="field">
              <label for="usr-e-clearance">Clearance tier</label>
              <select id="usr-e-clearance" class="select">
                <option value="L0" ${u.clearance === 'L0' ? 'selected' : ''}>L0 (Public)</option>
                <option value="L1" ${u.clearance === 'L1' ? 'selected' : ''}>L1 (Internal)</option>
                <option value="L2" ${u.clearance === 'L2' ? 'selected' : ''}>L2 (Confidential)</option>
                <option value="L3" ${u.clearance === 'L3' ? 'selected' : ''}>L3 (Restricted)</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label for="usr-e-password">Reset password <span class="muted" style="text-transform:none">(optional — leave blank to keep current)</span></label>
            <input id="usr-e-password" class="input" type="password" autocomplete="new-password" placeholder="Minimum 8 characters">
          </div>
        `}
        <div id="usr-e-err" class="field-error" role="alert"></div>
      </form>`,
    footer: `<button class="btn btn-outline" data-action="close-modal">Cancel</button>
             <button class="btn btn-primary" data-action="usr-edit-save">${icon('check')}Save changes</button>`,
    onMount: root => {
      if (isAgent) {
        const ps = root.querySelector('#usr-e-persona');
        const cs = root.querySelector('#usr-e-clearance');
        const hint = root.querySelector('#usr-e-clr-hint');
        syncPersonaClearance(ps, cs, hint, false);
        ps.addEventListener('change', () => syncPersonaClearance(ps, cs, hint, true));
      }
    },
  });
}

function openMintTokenModal(u) {
  openModal({
    title: `Mint service token — ${u.username}`,
    size: 'md',
    body: `
      <div id="tok-body" class="stack" data-sub="${esc(u.sub)}">
        <div class="meta-grid">
          <div class="meta-item"><div class="meta-label">Identity</div><div class="meta-value mono">${esc(u.identity)}</div></div>
          <div class="meta-item"><div class="meta-label">Agent ID</div><div class="meta-value mono">${esc(u.agent_id || '—')}</div></div>
          <div class="meta-item"><div class="meta-label">Persona</div><div class="meta-value mono">${esc(u.agent_persona || '—')}</div></div>
          <div class="meta-item"><div class="meta-label">Clearance</div><div class="meta-value">${tierBadge(u.clearance || 'L1')}</div></div>
        </div>
        <div class="callout">${icon('info')}<div>Mints a scoped Bearer JWT valid only for downstream read &amp; search endpoints within tenant <code>${esc(u.tenant_id)}</code> up to clearance <b>${esc(u.clearance)}</b>.</div></div>
        <div class="field">
          <label for="tok-ttl">Token lifetime (TTL)</label>
          <select id="tok-ttl" class="select">
            <option value="15">15 minutes</option>
            <option value="60">1 hour (60 min)</option>
            <option value="480" selected>8 hours (480 min)</option>
            <option value="1440">24 hours (1 day)</option>
            <option value="10080">7 days (10080 min)</option>
          </select>
        </div>
        <div id="tok-err" class="field-error" role="alert"></div>
      </div>`,
    footer: `<button class="btn btn-outline" data-action="close-modal">Cancel</button>
             <button class="btn btn-primary" data-action="usr-token-go">${icon('lock')}Mint bearer token</button>`,
  });
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

registerActions({
  'cfg-save': (el, _e, ctx) => {
    try { persist(el, collect(document.getElementById('cfg-form')), ctx); }
    catch (e) { toast(e.message, 'error', 6000); }
  },
  'cfg-discard': (_el, _e, ctx) => ctx.reload(),
  'cfg-json-save': (el, _e, ctx) => {
    let parsed;
    try { parsed = JSON.parse(document.getElementById('cfg-json').value); } catch (e) { document.getElementById('cfg-json-status').textContent = `✕ ${e.message}`; return; }
    try { persist(el, collectJsonDiff(parsed, original), ctx); }
    catch (e) { toast(e.message, 'error', 6000); }
  },

  'usr-new': (el, _e, ctx) => openCreateAccountModal(el.dataset.kind || 'human', ctx),

  'usr-create-save': async (el, _e, ctx) => {
    const form = document.getElementById('usr-create-form');
    const err = document.getElementById('usr-c-err');
    err.textContent = '';
    const isAgent = form.dataset.kind === 'agent';
    const username = form.querySelector('#usr-c-username').value.trim();
    const displayName = form.querySelector('#usr-c-display').value.trim();
    const identity = form.querySelector('#usr-c-identity').value.trim();
    const clearance = form.querySelector('#usr-c-clearance').value;

    if (!username) { err.textContent = 'Username is required.'; return; }

    const payload = {
      username,
      clearance,
      ...(displayName ? { display_name: displayName } : {}),
      ...(identity ? { identity } : {}),
    };

    if (isAgent) {
      payload.roles = ['agent'];
      const persona = form.querySelector('#usr-c-persona').value;
      const agentId = form.querySelector('#usr-c-agentid').value.trim();
      if (persona) payload.agent_persona = persona;
      if (agentId) payload.agent_id = agentId;
    } else {
      const role = form.querySelector('#usr-c-role').value;
      const password = form.querySelector('#usr-c-password').value;
      if (password.length < 8) { err.textContent = 'Password must be at least 8 characters.'; return; }
      payload.roles = [role];
      payload.password = password;
    }

    const done = busy(el);
    try {
      const res = await api.createUser(payload);
      closeModal();
      toast(`Created ${isAgent ? 'service agent' : 'user'} ${res.user?.username || username}.`, 'success', 5000);
      await ctx.reload();
    } catch (e) {
      err.textContent = e.message;
    } finally { done(); }
  },

  'usr-edit': el => {
    const u = cachedUsers.find(x => x.sub === el.dataset.sub);
    if (!u) { toast('User record not loaded.', 'error'); return; }
    openEditAccountModal(u);
  },

  'usr-edit-save': async (el, _e, ctx) => {
    const form = document.getElementById('usr-edit-form');
    const err = document.getElementById('usr-e-err');
    err.textContent = '';
    const sub = form.dataset.sub;
    const isAgent = form.dataset.agent === '1';
    const me = getUser() || {};

    const payload = {
      display_name: form.querySelector('#usr-e-display').value.trim(),
      clearance: form.querySelector('#usr-e-clearance').value,
    };

    if (isAgent) {
      payload.agent_persona = form.querySelector('#usr-e-persona').value || '';
    } else {
      const roleEl = form.querySelector('#usr-e-role');
      if (roleEl && !roleEl.disabled) payload.roles = [roleEl.value];
      const pw = form.querySelector('#usr-e-password').value;
      if (pw) {
        if (pw.length < 8) { err.textContent = 'New password must be at least 8 characters.'; return; }
        payload.password = pw;
      }
    }

    const done = busy(el);
    try {
      const res = await api.updateUser(sub, payload);
      closeModal();
      const extra = sub === me.sub ? ' Sign out and back in to refresh your own session claims if changed.' : '';
      toast(`Updated ${res.user?.username || sub}.${extra}`, 'success', 6000);
      await ctx.reload();
    } catch (e) {
      err.textContent = e.message;
    } finally { done(); }
  },

  'usr-toggle': async (el, _e, ctx) => {
    const u = cachedUsers.find(x => x.sub === el.dataset.sub);
    if (!u) return;
    const disabling = !u.disabled;
    const ok = await confirmDialog({
      title: `${disabling ? 'Disable' : 'Enable'} ${u.username}?`,
      message: disabling
        ? `Disabling ${u.username} immediately invalidates existing sessions and tokens.`
        : `Re-enabling ${u.username} allows authentication again.`,
      confirmLabel: disabling ? 'Disable account' : 'Enable account',
      tone: disabling ? 'danger' : 'primary',
    });
    if (!ok) return;
    try {
      await api.updateUser(u.sub, { disabled: disabling });
      toast(`${u.username} is now ${disabling ? 'disabled' : 'active'}.`, 'success');
      await ctx.reload();
    } catch (e) {
      toast(`Failed: ${e.message}`, 'error', 7000);
    }
  },

  'usr-token': el => {
    const u = cachedUsers.find(x => x.sub === el.dataset.sub);
    if (!u) return;
    openMintTokenModal(u);
  },

  'usr-token-go': async el => {
    const box = document.getElementById('tok-body');
    const err = document.getElementById('tok-err');
    err.textContent = '';
    const sub = box.dataset.sub;
    const ttlMinutes = Number(document.getElementById('tok-ttl').value || 480);

    const done = busy(el);
    try {
      const res = await api.issueAgentToken(sub, ttlMinutes);
      box.innerHTML = `
        <div class="callout success">${icon('check')}<div><b>Bearer token minted for ${esc(res.user?.username || sub)}.</b> Copy it now — tokens are not stored or retrievable later.</div></div>
        <div class="meta-grid">
          <div class="meta-item"><div class="meta-label">Token ID (jti)</div><div class="meta-value mono">${esc(res.jti)}</div></div>
          <div class="meta-item"><div class="meta-label">Expires in</div><div class="meta-value mono">${esc(res.expires_in)}s (~${Math.round((res.expires_in || 0) / 60)} min)</div></div>
        </div>
        <div class="field">
          <label>Authorization Bearer Token</label>
          <div class="code-snippet-box"><code style="word-break:break-all">${esc(res.access_token)}</code><button type="button" class="copy-btn" data-action="copy" data-copy="${esc(res.access_token)}" data-msg="Agent bearer token copied">Copy</button></div>
        </div>`;
      const footer = document.getElementById('modal-footer');
      if (footer) footer.innerHTML = '<button class="btn btn-primary" data-action="close-modal">Done</button>';
    } catch (e) {
      err.textContent = e.message;
    } finally { done(); }
  },
});

// ---------------------------------------------------------------------------

export default {
  id: 'settings',
  label: 'Settings',
  icon: 'settings',
  title: 'Settings & access control',
  subtitle: 'Live pipeline configuration and tenant user / service-agent provisioning.',

  async load() {
    const canConfig = hasCapability('can_manage_config');
    const canUsers = hasCapability('can_manage_users');
    const [cfg, usersRes] = await Promise.all([
      canConfig ? api.getConfig() : Promise.resolve(null),
      canUsers ? api.listUsers() : Promise.resolve({ users: [] }),
    ]);
    original = cfg;
    cachedUsers = usersRes?.users || [];
    return {
      cfg,
      users: cachedUsers,
      tenantId: usersRes?.tenant_id || getUser()?.tenant_id || '',
    };
  },

  render({ cfg, users, tenantId }) {
    const canConfig = hasCapability('can_manage_config') && cfg !== null;
    const canUsers = hasCapability('can_manage_users');

    if (!activeTab) activeTab = canConfig ? 'form' : 'users';
    if (!canConfig && (activeTab === 'form' || activeTab === 'json')) activeTab = 'users';
    if (!canUsers && activeTab === 'users') activeTab = 'form';

    const tab = (id, label, extra = '') =>
      `<button class="tab ${activeTab === id ? 'active' : ''}" role="tab" data-tab="${id}" aria-selected="${activeTab === id}">${label}${extra}</button>`;

    return `
      <div class="view-stack">
        ${canConfig ? `<div class="callout warn">${icon('alert')}<div>Pipeline settings are persisted and <b>hot-reloaded into the running server</b>. Lowering file limits or changing model providers affects the next document processed.</div></div>` : ''}
        <div class="panel panel-flush">
          <div class="tabs" role="tablist" style="padding:0 12px">
            ${canConfig ? tab('form', 'Pipeline form') : ''}
            ${canConfig ? tab('json', 'Raw JSON') : ''}
            ${canUsers ? tab('users', `${icon('users')}Users &amp; Agents`, ` <span class="tab-count">${users.length}</span>`) : ''}
          </div>
          ${canConfig ? `
          <div class="tab-panel panel-pad" data-panel="form" ${activeTab === 'form' ? '' : 'hidden'} style="padding-top:18px">
            <div id="cfg-form">${formHtml(cfg)}</div>
            <div class="savebar" id="cfg-savebar" style="margin-top:16px">
              <span id="cfg-dirty" class="small muted">No unsaved changes</span>
              <div class="row"><button class="btn btn-outline" data-action="cfg-discard">Discard</button><button class="btn btn-primary" data-action="cfg-save" id="cfg-save" disabled>Save changes</button></div>
            </div>
          </div>
          <div class="tab-panel panel-pad" data-panel="json" ${activeTab === 'json' ? '' : 'hidden'} style="padding-top:18px">
            <textarea id="cfg-json" class="textarea code" spellcheck="false" style="min-height:460px">${esc(prettyJson(cfg))}</textarea>
            <div class="row-between" style="margin-top:10px"><span id="cfg-json-status" class="tiny"></span><button class="btn btn-primary" data-action="cfg-json-save">Save JSON</button></div>
          </div>` : ''}
          ${canUsers ? `
          <div class="tab-panel panel-pad" data-panel="users" ${activeTab === 'users' ? '' : 'hidden'} style="padding-top:18px">
            ${usersTabHtml(users, tenantId)}
          </div>` : ''}
        </div>
      </div>`;
  },

  mount(root, data, ctx) {
    bindTabs(root, tab => { activeTab = tab; });
    const opts = { signal: ctx.signal };

    const form = root.querySelector('#cfg-form');
    if (form) {
      const label = root.querySelector('#cfg-dirty');
      const save = root.querySelector('#cfg-save');
      const refresh = () => {
        const d = dirtyPaths(form);
        label.textContent = d.length ? `${d.length} unsaved change${d.length > 1 ? 's' : ''}` : 'No unsaved changes';
        label.className = `small ${d.length ? 'text-warning strong' : 'muted'}`;
        save.disabled = !d.length;
      };
      form.addEventListener('input', refresh, opts);
      form.addEventListener('change', refresh, opts);
    }

    const ta = root.querySelector('#cfg-json');
    if (ta) {
      const status = root.querySelector('#cfg-json-status');
      ta.addEventListener('input', () => {
        try { JSON.parse(ta.value); status.textContent = '✓ Valid JSON'; status.className = 'tiny text-success'; }
        catch (e) { status.textContent = `✕ ${e.message}`; status.className = 'tiny text-danger'; }
      }, opts);
    }

    const usrSearch = root.querySelector('#usr-search');
    const usrHost = root.querySelector('#usr-table-host');
    if (usrSearch && usrHost) {
      usrSearch.addEventListener('input', () => {
        userQuery = usrSearch.value;
        usrHost.innerHTML = usersTableHtml(data.users || cachedUsers);
      }, opts);
    }
  },
};
