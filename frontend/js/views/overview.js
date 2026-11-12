/**
 * Overview — pipeline health at a glance: KPIs, job funnel, recent jobs,
 * scheduler, model routing and the security gates the backend reports.
 */

import { api } from '../api.js';
import { hasCapability } from '../auth.js';
import { esc, icon, fmt, pill, jobPill, isUnlimited, jsonBlock, emptyState } from '../ui.js';

const FUNNEL = [
  { label: 'In pipeline', states: ['received', 'extracting', 'scanning', 'structuring', 'assessing', 'correcting'], tone: 'info' },
  { label: 'Awaiting review', states: ['awaiting_review', 'changes_requested'], tone: 'warning' },
  { label: 'Approved', states: ['approved'], tone: 'success' },
  { label: 'Published', states: ['published'], tone: 'success' },
  { label: 'Halted', states: ['quarantined', 'rejected', 'failed', 'blocked', 'duplicate'], tone: 'danger' },
];

function kpi({ title, value, badge, badgeTone = '', sub = '', iconName, tone = '', href, extra = '' }) {
  const tag = href ? `a href="${href}"` : 'div';
  const close = href ? 'a' : 'div';
  return `
    <${tag} class="kpi-card">
      <div class="kpi-card-header">
        <span class="kpi-title">${esc(title)}</span>
        <span class="kpi-icon-wrap ${tone ? `tone-${tone}` : ''}">${icon(iconName)}</span>
      </div>
      <div class="kpi-value-row">
        <span class="kpi-value">${value}</span>
        ${badge ? `<span class="kpi-badge ${badgeTone}">${esc(badge)}</span>` : ''}
      </div>
      ${extra}
      ${sub ? `<div class="kpi-subtext">${esc(sub)}</div>` : ''}
    </${close}>`;
}

function funnel(jobs) {
  const counts = FUNNEL.map(f => jobs.filter(j => f.states.includes(j.current_state)).length);
  const max = Math.max(1, ...counts);
  return `
    <div class="flow" role="list">
      ${FUNNEL.map((f, i) => `
        <a class="flow-step tone-${f.tone}" href="#/review" role="listitem" title="${esc(f.states.map(fmt.words).join(', '))}">
          <span class="flow-count">${counts[i]}</span>
          <span class="flow-label">${esc(f.label)}</span>
          <span class="flow-bar"><i style="width:${Math.round((counts[i] / max) * 100)}%"></i></span>
        </a>`).join('')}
    </div>`;
}

function recentJobs(jobs, canUpload) {
  const rows = [...jobs].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 6);
  if (!rows.length) {
    return emptyState({
      icon: 'inbox',
      title: 'No jobs yet',
      text: canUpload ? 'Upload an SOP document to start the pipeline.' : 'No SOP ingestion jobs have been started for this tenant yet.',
      action: canUpload ? '<a class="btn btn-primary" href="#/ingestion">Ingest an SOP</a>' : '',
    });
  }
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>SOP</th><th>State</th><th>Tenant</th><th>Updated</th></tr></thead>
        <tbody>
          ${rows.map(j => `
            <tr>
              <td><div class="id-cell">${esc(j.sop_id)}</div><div class="cell-sub">${esc(j.job_id)} · v${esc(j.version)}</div></td>
              <td>${jobPill(j.current_state)}</td>
              <td class="secondary">${esc(j.tenant_id)}</td>
              <td class="nowrap"><div class="mono tiny">${fmt.date(j.updated_at)}</div><div class="cell-sub">${fmt.rel(j.updated_at)}</div></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

function schedulerPanel(s, canUpload) {
  const disabled = Boolean(s.disabled);
  const badgeLabel = disabled ? 'DISABLED (GOVERNED)' : (s.running ? 'WATCHER ACTIVE' : 'STANDBY');
  const badgeTone = disabled ? 'neutral' : (s.running ? 'success' : 'warning');
  return `
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">${icon('clock')}Background scheduler</div>
        ${pill(badgeLabel, badgeTone)}
      </div>
      ${disabled
        ? `<div class="callout info" style="margin-bottom:12px">${icon('shield')}<div>${esc(s.disabled_reason || 'Batch scanning is disabled (C1). Use governed per-file ingestion.')}</div></div>`
        : ''}
      <div class="kv-list">
        <div><span class="k">Scan interval</span><span class="v mono">${esc(s.interval_minutes ?? '—')} min</span></div>
        <div><span class="k">Last run</span><span class="v">${fmt.date(s.last_run_at)} <span class="muted tiny">${fmt.rel(s.last_run_at)}</span></span></div>
        <div><span class="k">Next run</span><span class="v">${fmt.date(s.next_run_at)} <span class="muted tiny">${fmt.rel(s.next_run_at)}</span></span></div>
        <div><span class="k">Total runs</span><span class="v mono">${fmt.num(s.total_runs || 0)}</span></div>
      </div>
      ${s.last_run_summary ? `<details class="accordion" style="margin-top:12px"><summary>Last run summary</summary><div class="acc-body">${jsonBlock(s.last_run_summary)}</div></details>` : ''}
      ${disabled
        ? (canUpload ? `<a class="btn btn-secondary" style="margin-top:14px;width:100%" href="#/ingestion">${icon('upload')}Open governed ingestion</a>` : '')
        : `<button class="btn btn-secondary" style="margin-top:14px;width:100%" data-action="run-scan">${icon('refresh')}Run scan now</button>`}
    </div>`;
}

function modelsPanel(models) {
  const entries = Object.entries(models || {});
  return `
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">${icon('database')}Model routing</div>
        <span class="badge-tag">${entries.length} roles</span>
      </div>
      ${entries.length ? `
        <div class="kv-list">
          ${entries.map(([role, cfg]) => {
            const c = typeof cfg === 'object' && cfg ? cfg : { model: cfg };
            const fb = Array.isArray(c.fallbacks) ? c.fallbacks.length : 0;
            return `<div>
              <span class="k">${esc(fmt.words(role))}</span>
              <span class="v"><span class="mono">${esc([c.provider, c.model].filter(Boolean).join(' / ') || '—')}</span>${fb ? `<div class="tiny muted">${fb} fallback${fb > 1 ? 's' : ''}</div>` : ''}</span>
            </div>`;
          }).join('')}
        </div>` : '<p class="muted small">No model routing reported.</p>'}
    </div>`;
}

function gatesPanel(gates) {
  return `
    <div class="panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">${icon('shield')}Security gates</div>
          <div class="panel-subtitle">Safeguards between an uploaded document and a published playbook, as reported by the backend.</div>
        </div>
        ${pill(`${gates.length} reported`, 'info')}
      </div>
      ${gates.map(g => `
        <details class="accordion">
          <summary><span class="row" style="gap:10px;flex-wrap:nowrap"><span class="badge-tag">Gate ${esc(g.gate_id)}</span><span>${esc(g.name)}</span></span>${pill(String(g.status || 'active').toUpperCase(), g.status === 'active' ? 'success' : 'warning')}</summary>
          <div class="acc-body">
            <div class="tiny muted" style="margin-bottom:6px">${esc(g.phase)}</div>
            <ul>${(g.rules || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul>
          </div>
        </details>`).join('')}
    </div>`;
}

export default {
  id: 'overview',
  label: 'Overview',
  icon: 'dashboard',
  title: 'Governance overview',
  subtitle: 'Tenant pipeline health, pending Security Reviewer approvals, and active governance gates.',
  refreshMs: 20000,

  async load(ctx) {
    const canIncidents = hasCapability('can_view_incidents');
    const [overview, jobs, tasks, incidents] = await Promise.all([
      api.getOverview(),
      api.getGovernanceJobs().catch(() => ({ jobs: [] })),
      api.getReviewTasks().catch(() => ({ tasks: [] })),
      canIncidents ? api.getIncidents().catch(() => ({ incidents: [] })) : Promise.resolve({ incidents: [] }),
    ]);
    const pending = (tasks.tasks || []).filter(t => t.status === 'pending');
    ctx.setBadges({ playbooks: overview.stats?.total_playbooks ?? null, pending: pending.length });
    return { overview, jobs: jobs.jobs || [], tasks: tasks.tasks || [], pending, incidents: incidents.incidents || [] };
  },

  render({ overview, jobs, pending, incidents }) {
    const canUpload = hasCapability('can_upload');
    const canReview = hasCapability('can_review');
    const canPublish = hasCapability('can_publish');
    const canIncidents = hasCapability('can_view_incidents');
    const canTelemetry = hasCapability('can_view_telemetry');
    const canSettings = hasCapability('can_manage_config') || hasCapability('can_manage_users');
    const stats = overview.stats || {};
    const t = canTelemetry && overview.telemetry ? overview.telemetry : null;
    const unlimited = t ? isUnlimited(t.max_daily_calls) : true;
    const quotaPct = t && !unlimited && t.max_daily_calls > 0 ? Math.round((t.total_calls / t.max_daily_calls) * 100) : 0;
    const overdue = pending.filter(p => p.is_overdue).length;
    const approvedCount = jobs.filter(j => j.current_state === 'approved').length;
    const changesReqCount = jobs.filter(j => j.current_state === 'changes_requested').length;
    const kpiCount = 3 + (canIncidents ? 1 : 0) + (t ? 2 : 0);

    let heroTitle = 'Nothing is waiting on you';
    let heroSub = 'Review tenant playbooks and pipeline status below.';
    let heroActions = '';
    if (canReview) {
      heroTitle = pending.length
        ? `${pending.length} SOP review${pending.length > 1 ? 's' : ''} waiting for security sign-off`
        : 'Security review queue is clear';
      heroSub = pending.length
        ? `${overdue ? `${overdue} overdue. ` : ''}Inspect drafted steps, verify source quotes and confidentiality tier, then approve or request changes.`
        : 'All L0–L3 drafts within your clearance have been decided. Approved SOPs are published by a Process Owner.';
      heroActions = pending.length ? `<a class="btn btn-primary" href="#/review">${icon('review')}Open review queue</a>` : '';
    } else if (canUpload) {
      if (changesReqCount) {
        heroTitle = `${changesReqCount} SOP draft${changesReqCount > 1 ? 's' : ''} require${changesReqCount === 1 ? 's' : ''} revision`;
        heroSub = 'A Security Reviewer requested changes. Edit the draft steps or JSON and resubmit for security review.';
        heroActions = `<a class="btn btn-primary" href="#/review">${icon('edit')}Revise drafts</a><a class="btn btn-secondary" href="#/ingestion">${icon('upload')}Ingest an SOP</a>`;
      } else if (approvedCount && canPublish) {
        heroTitle = `${approvedCount} approved SOP${approvedCount > 1 ? 's' : ''} ready to publish`;
        heroSub = 'Security Reviewer sign-off succeeded. Publish from Lifecycle jobs to release playbooks to downstream agents.';
        heroActions = `<a class="btn btn-primary" href="#/review">${icon('check')}Review &amp; publish</a><a class="btn btn-secondary" href="#/ingestion">${icon('upload')}Ingest an SOP</a>`;
      } else if (pending.length) {
        heroTitle = `${pending.length} SOP${pending.length > 1 ? 's' : ''} awaiting Security Reviewer sign-off`;
        heroSub = `${overdue ? `${overdue} overdue. ` : ''}Drafts stay locked for publication until an independent Security Reviewer approves them.`;
        heroActions = `<a class="btn btn-primary" href="#/ingestion">${icon('upload')}Ingest an SOP</a><a class="btn btn-secondary" href="#/review">${icon('review')}View review queue</a>`;
      } else {
        heroTitle = 'Ready to author & publish SOPs';
        heroSub = 'Upload a document to run extraction, secret scanning, structuring and Security Reviewer sign-off.';
        heroActions = `<a class="btn btn-primary" href="#/ingestion">${icon('upload')}Ingest an SOP</a>`;
      }
    } else {
      heroTitle = pending.length ? `${pending.length} SOP review${pending.length > 1 ? 's' : ''} in flight` : 'Tenant governance & platform operations';
      heroSub = 'Manage pipeline settings, users and service accounts, LLM telemetry, audit logs, and security incidents for your tenant.';
      heroActions = `${canTelemetry ? `<a class="btn btn-primary" href="#/telemetry">${icon('chart')}LLM telemetry</a>` : ''}${canSettings ? `<a class="btn btn-secondary" href="#/settings">${icon('settings')}Settings &amp; users</a>` : ''}${pending.length ? `<a class="btn btn-outline" href="#/review">${icon('review')}View queue</a>` : ''}`;
    }

    return `
      <div class="view-stack">
        <div class="hero">
          <div>
            <h3>${heroTitle}</h3>
            <p>${heroSub}</p>
          </div>
          <div class="row">${heroActions}</div>
        </div>

        <div class="kpi-grid ${kpiCount === 6 ? 'kpi-6' : ''}">
          ${kpi({ title: 'Published playbooks', value: fmt.num(stats.total_playbooks || 0), badge: 'HMAC signed', badgeTone: 'badge-success', sub: `${fmt.num(stats.total_uploads || 0)} files in tenant uploads`, iconName: 'book', href: '#/playbooks' })}
          ${kpi({ title: 'Pending reviews', value: fmt.num(pending.length), badge: overdue ? `${overdue} overdue` : '', badgeTone: 'badge-danger', sub: 'Security Reviewer sign-off required', iconName: 'review', tone: pending.length ? 'warning' : 'success', href: '#/review' })}
          ${canIncidents ? kpi({ title: 'Quarantine incidents', value: fmt.num(incidents.length), sub: incidents.length ? 'Documents halted by the secret scanner' : 'No secrets detected so far', iconName: 'lock', tone: incidents.length ? 'danger' : 'success', href: '#/review' }) : ''}
          ${kpi({ title: 'Ingestion success', value: `${stats.success_rate ?? 100}<small>%</small>`, badge: `${stats.manifest_success || 0} ok`, badgeTone: 'badge-success', sub: `${stats.manifest_failed || 0} failed of ${stats.manifest_total || 0} processed`, iconName: 'check', tone: 'success' })}
          ${t ? kpi({
            title: 'AI calls today',
            value: fmt.num(t.total_calls || 0),
            badge: unlimited ? 'No daily cap' : `${t.calls_remaining ?? 0} left`,
            badgeTone: quotaPct > 80 ? 'badge-danger' : '',
            iconName: 'chart', tone: quotaPct > 80 ? 'danger' : 'info', href: '#/telemetry',
            extra: unlimited ? '' : `<div class="gauge-track" role="progressbar" aria-valuenow="${quotaPct}" aria-valuemin="0" aria-valuemax="100" aria-label="Daily quota used"><div class="gauge-fill ${quotaPct > 80 ? 'danger' : ''}" style="width:${Math.min(quotaPct, 100)}%"></div></div>`,
          }) : ''}
          ${t ? kpi({ title: 'AI spend today', value: fmt.usd(t.total_cost_usd), badge: fmt.inr(t.total_cost_inr), sub: `${fmt.num(t.total_tokens || 0)} tokens`, iconName: 'database', tone: 'warning', href: '#/telemetry' }) : ''}
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('refresh')}Job lifecycle</div>
              <div class="panel-subtitle">Where every ingested SOP for your tenant currently sits in the orchestrator.</div>
            </div>
            <span class="badge-tag">${jobs.length} jobs</span>
          </div>
          ${funnel(jobs)}
        </div>

        <div class="grid-main-side">
          <div class="panel panel-flush">
            <div class="panel-header">
              <div class="panel-title">${icon('file')}Recent jobs</div>
              <a class="btn btn-sm btn-outline" href="#/review">View all</a>
            </div>
            ${recentJobs(jobs, canUpload)}
          </div>
          <div class="stack">
            ${schedulerPanel(overview.scheduler || {}, canUpload)}
            ${canTelemetry && overview.models && Object.keys(overview.models).length ? modelsPanel(overview.models) : ''}
          </div>
        </div>

        ${gatesPanel(overview.gates || [])}
      </div>`;
  },
};
