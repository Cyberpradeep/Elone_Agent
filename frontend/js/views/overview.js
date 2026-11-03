/**
 * Overview — pipeline health at a glance: KPIs, job funnel, recent jobs,
 * scheduler, model routing and the security gates the backend reports.
 */

import { api } from '../api.js';
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

function recentJobs(jobs) {
  const rows = [...jobs].sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at))).slice(0, 6);
  if (!rows.length) return emptyState({ icon: 'inbox', title: 'No jobs yet', text: 'Upload an SOP document to start the pipeline.', action: '<a class="btn btn-primary" href="#/ingestion">Ingest an SOP</a>' });
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

function schedulerPanel(s) {
  return `
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">${icon('clock')}Background scheduler</div>
        ${pill(s.running ? 'WATCHER ACTIVE' : 'STANDBY', s.running ? 'success' : 'warning')}
      </div>
      <div class="kv-list">
        <div><span class="k">Scan interval</span><span class="v mono">${esc(s.interval_minutes ?? '—')} min</span></div>
        <div><span class="k">Last run</span><span class="v">${fmt.date(s.last_run_at)} <span class="muted tiny">${fmt.rel(s.last_run_at)}</span></span></div>
        <div><span class="k">Next run</span><span class="v">${fmt.date(s.next_run_at)} <span class="muted tiny">${fmt.rel(s.next_run_at)}</span></span></div>
        <div><span class="k">Total runs</span><span class="v mono">${fmt.num(s.total_runs || 0)}</span></div>
      </div>
      ${s.last_run_summary ? `<details class="accordion" style="margin-top:12px"><summary>Last run summary</summary><div class="acc-body">${jsonBlock(s.last_run_summary)}</div></details>` : ''}
      <button class="btn btn-secondary" style="margin-top:14px;width:100%" data-action="run-scan">${icon('refresh')}Run scan now</button>
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
  subtitle: 'Pipeline health, reviews waiting on a human, and today\'s AI usage.',
  refreshMs: 20000,

  async load(ctx) {
    const [overview, jobs, tasks, incidents] = await Promise.all([
      api.getOverview(),
      api.getGovernanceJobs().catch(() => ({ jobs: [] })),
      api.getReviewTasks().catch(() => ({ tasks: [] })),
      api.getIncidents().catch(() => ({ incidents: [] })),
    ]);
    const pending = (tasks.tasks || []).filter(t => t.status === 'pending');
    ctx.setBadges({ playbooks: overview.stats?.total_playbooks ?? null, pending: pending.length });
    return { overview, jobs: jobs.jobs || [], tasks: tasks.tasks || [], pending, incidents: incidents.incidents || [] };
  },

  render({ overview, jobs, pending, incidents }) {
    const stats = overview.stats || {};
    const t = overview.telemetry || {};
    const unlimited = isUnlimited(t.max_daily_calls);
    const quotaPct = !unlimited && t.max_daily_calls > 0 ? Math.round((t.total_calls / t.max_daily_calls) * 100) : 0;
    const overdue = pending.filter(p => p.is_overdue).length;

    return `
      <div class="view-stack">
        <div class="hero">
          <div>
            <h3>${pending.length ? `${pending.length} review${pending.length > 1 ? 's' : ''} waiting on a human` : 'Nothing is waiting on you'}</h3>
            <p>${pending.length
              ? `${overdue ? `${overdue} overdue. ` : ''}An SOP can't be published until someone other than its uploader approves it.`
              : 'Upload a document to run it through extraction, secret scanning, structuring and verification.'}</p>
          </div>
          <div class="row">
            <a class="btn btn-primary" href="#/ingestion">${icon('upload')}Ingest an SOP</a>
            ${pending.length ? `<a class="btn btn-secondary" href="#/review">${icon('review')}Open review queue</a>` : ''}
          </div>
        </div>

        <div class="kpi-grid kpi-6">
          ${kpi({ title: 'Published playbooks', value: fmt.num(stats.total_playbooks || 0), badge: 'HMAC signed', badgeTone: 'badge-success', sub: `${fmt.num(stats.total_uploads || 0)} files in the uploads folder`, iconName: 'book', href: '#/playbooks' })}
          ${kpi({ title: 'Pending reviews', value: fmt.num(pending.length), badge: overdue ? `${overdue} overdue` : '', badgeTone: 'badge-danger', sub: 'Dual-custody approval required', iconName: 'review', tone: pending.length ? 'warning' : 'success', href: '#/review' })}
          ${kpi({ title: 'Quarantine incidents', value: fmt.num(incidents.length), sub: incidents.length ? 'Documents halted by the secret scanner' : 'No secrets detected so far', iconName: 'lock', tone: incidents.length ? 'danger' : 'success', href: '#/review' })}
          ${kpi({ title: 'Ingestion success', value: `${stats.success_rate ?? 100}<small>%</small>`, badge: `${stats.manifest_success || 0} ok`, badgeTone: 'badge-success', sub: `${stats.manifest_failed || 0} failed of ${stats.manifest_total || 0} processed`, iconName: 'check', tone: 'success' })}
          ${kpi({
            title: 'AI calls today',
            value: fmt.num(t.total_calls || 0),
            badge: unlimited ? 'No daily cap' : `${t.calls_remaining ?? 0} left`,
            badgeTone: quotaPct > 80 ? 'badge-danger' : '',
            iconName: 'chart', tone: quotaPct > 80 ? 'danger' : 'info', href: '#/telemetry',
            extra: unlimited ? '' : `<div class="gauge-track" role="progressbar" aria-valuenow="${quotaPct}" aria-valuemin="0" aria-valuemax="100" aria-label="Daily quota used"><div class="gauge-fill ${quotaPct > 80 ? 'danger' : ''}" style="width:${Math.min(quotaPct, 100)}%"></div></div>`,
          })}
          ${kpi({ title: 'AI spend today', value: fmt.usd(t.total_cost_usd), badge: fmt.inr(t.total_cost_inr), sub: `${fmt.num(t.total_tokens || 0)} tokens`, iconName: 'database', tone: 'warning', href: '#/telemetry' })}
        </div>

        <div class="panel">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('refresh')}Job lifecycle</div>
              <div class="panel-subtitle">Where every ingested SOP currently sits in the orchestrator.</div>
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
            ${recentJobs(jobs)}
          </div>
          <div class="stack">
            ${schedulerPanel(overview.scheduler || {})}
            ${modelsPanel(overview.models)}
          </div>
        </div>

        ${gatesPanel(overview.gates || [])}
      </div>`;
  },
};
