/**
 * Telemetry — LLM usage, token and cost accounting per day, with a per-call ledger.
 * The daily call cap may be the string "unlimited", so quota maths guards for it.
 */

import { api } from '../api.js';
import { barChart } from '../charts.js';
import { esc, icon, fmt, isUnlimited, emptyState } from '../ui.js';

let selectedDate = null;
const ledgerFilter = { text: '', caller: 'all', provider: 'all' };

const PROVIDERS = [
  { key: 'gemini_calls', name: 'Gemini', color: 'var(--series-1)' },
  { key: 'mistral_calls', name: 'Mistral', color: 'var(--series-2)' },
  { key: 'nvidia_vision_calls', name: 'NVIDIA vision', color: 'var(--series-3)' },
];

function ledgerRows(calls) {
  const t = ledgerFilter.text.toLowerCase();
  return calls.filter(c =>
    (ledgerFilter.caller === 'all' || c.caller === ledgerFilter.caller) &&
    (ledgerFilter.provider === 'all' || c.provider === ledgerFilter.provider) &&
    (!t || `${c.sop_id} ${c.model} ${c.caller} ${c.provider}`.toLowerCase().includes(t)));
}

function ledgerHtml(calls) {
  const rows = ledgerRows(calls).slice().reverse();
  if (!calls.length) return emptyState({ icon: 'chart', title: 'No calls recorded for this day', text: 'Calls appear here as soon as the pipeline uses an LLM.' });
  if (!rows.length) return emptyState({ icon: 'search', title: 'No calls match these filters' });
  const shown = rows.slice(0, 200);
  const totalCost = rows.reduce((s, c) => s + (c.cost_usd || 0), 0);
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>Time</th><th>Caller</th><th>Provider / model</th><th>SOP</th><th class="num">Input</th><th class="num">Output</th><th class="num">Cost</th></tr></thead>
        <tbody>
          ${shown.map(c => `
            <tr>
              <td class="mono tiny nowrap">${esc(String(c.timestamp || '').replace('T', ' ').split('.')[0])}</td>
              <td><span class="badge-tag">${esc(c.caller)}</span></td>
              <td><div class="strong">${esc(c.provider)}</div><div class="cell-sub mono">${esc(c.model)}</div></td>
              <td class="mono tiny">${esc(c.sop_id || '—')}</td>
              <td class="num mono">${fmt.num(c.input_tokens || 0)}</td>
              <td class="num mono">${fmt.num(c.output_tokens || 0)}</td>
              <td class="num mono text-warning">${fmt.usd(c.cost_usd, 6)}</td>
            </tr>`).join('')}
        </tbody>
        <tfoot><tr><td colspan="6" class="small muted" style="padding:10px 14px">${rows.length > shown.length ? `Showing the latest ${shown.length} of ${rows.length} calls. ` : `${rows.length} call${rows.length === 1 ? '' : 's'}. `}Total</td><td class="num mono strong" style="padding:10px 14px">${fmt.usd(totalCost, 6)}</td></tr></tfoot>
      </table>
    </div>`;
}

export default {
  id: 'telemetry',
  label: 'Telemetry',
  icon: 'chart',
  title: 'LLM telemetry & cost',
  subtitle: 'Calls, tokens and spend per day, with every individual call.',
  refreshMs: 30000,

  load: () => api.getTelemetry(),

  render(data) {
    const today = data.today || {};
    const history = { ...(data.history || {}) };
    if (today.date && !history[today.date]) history[today.date] = today;
    const dates = Object.keys(history).sort();
    if (!selectedDate || !history[selectedDate]) selectedDate = today.date || dates[dates.length - 1];
    const day = history[selectedDate] || {};
    const unlimited = isUnlimited(day.max_daily_calls);
    const quotaPct = !unlimited && day.max_daily_calls > 0 ? Math.round(((day.total_calls || 0) / day.max_daily_calls) * 100) : 0;

    // Charts: last 14 days that exist, oldest first.
    const recent = dates.slice(-14);
    const calls = barChart({
      labels: recent,
      series: PROVIDERS.map(p => ({ name: p.name, color: p.color, values: recent.map(d => history[d][p.key] || 0) })),
      format: fmt.num, ariaLabel: 'LLM calls per day by provider',
    });
    const tokens = barChart({
      labels: recent,
      series: [{ name: 'Tokens', color: 'var(--series-1)', values: recent.map(d => history[d].total_tokens || 0) }],
      format: fmt.num, ariaLabel: 'Tokens per day',
    });

    const callers = [...new Set((day.call_history || []).map(c => c.caller))].sort();
    const providers = [...new Set((day.call_history || []).map(c => c.provider))].sort();

    return `
      <div class="view-stack">
        <div class="toolbar">
          <div class="field" style="flex-direction:row;align-items:center;gap:10px">
            <label for="tel-date" style="margin:0">Day</label>
            <select id="tel-date" class="select" style="width:auto">
              ${[...dates].reverse().map(d => `<option value="${esc(d)}" ${d === selectedDate ? 'selected' : ''}>${esc(d)}${d === today.date ? ' (today)' : ''}</option>`).join('')}
            </select>
          </div>
          <span class="spacer"></span>
          <span class="tiny muted">Updates every 30 s</span>
        </div>

        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-card-header"><span class="kpi-title">API calls</span><span class="kpi-icon-wrap tone-info">${icon('chart')}</span></div>
            <div class="kpi-value-row"><span class="kpi-value">${fmt.num(day.total_calls || 0)}</span><span class="kpi-badge ${quotaPct > 80 ? 'badge-danger' : ''}">${unlimited ? 'No daily cap' : `${quotaPct}% of ${fmt.num(day.max_daily_calls)}`}</span></div>
            ${unlimited ? '' : `<div class="gauge-track" role="progressbar" aria-valuenow="${quotaPct}" aria-valuemin="0" aria-valuemax="100" aria-label="Daily quota used"><div class="gauge-fill ${quotaPct > 80 ? 'danger' : ''}" style="width:${Math.min(quotaPct, 100)}%"></div></div>`}
            <div class="kpi-subtext">${unlimited ? 'Quota enforcement is off' : `${esc(day.calls_remaining)} calls remaining`}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-card-header"><span class="kpi-title">By provider</span><span class="kpi-icon-wrap">${icon('database')}</span></div>
            <div class="kv-list">${PROVIDERS.map(p => `<div><span class="k row" style="gap:7px;flex-wrap:nowrap"><span class="legend-swatch" style="background:${p.color}"></span>${esc(p.name)}</span><span class="v mono">${fmt.num(day[p.key] || 0)}</span></div>`).join('')}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-card-header"><span class="kpi-title">Tokens</span><span class="kpi-icon-wrap tone-info">${icon('file')}</span></div>
            <div class="kpi-value-row"><span class="kpi-value">${fmt.num(day.total_tokens || 0)}</span></div>
            <div class="kpi-subtext mono">in ${fmt.num(day.total_input_tokens || 0)} · out ${fmt.num(day.total_output_tokens || 0)} · img ${fmt.num(day.total_image_tokens || 0)}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-card-header"><span class="kpi-title">Cost</span><span class="kpi-icon-wrap tone-warning">${icon('database')}</span></div>
            <div class="kpi-value-row"><span class="kpi-value">${fmt.usd(day.total_cost_usd)}</span><span class="kpi-badge badge-warning">${fmt.inr(day.total_cost_inr)}</span></div>
          </div>
        </div>

        <div class="grid-2">
          <div class="panel chart-card"><div class="panel-header"><div class="panel-title">${icon('chart')}Calls per day</div></div>${calls}</div>
          <div class="panel chart-card"><div class="panel-header"><div class="panel-title">${icon('chart')}Tokens per day</div></div>${tokens}</div>
        </div>

        <div class="panel panel-flush">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('file')}Call ledger — ${esc(selectedDate)}</div>
              <div class="panel-subtitle">Every LLM call with its tokens and cost, newest first.</div>
            </div>
            <div class="panel-actions">
              <div class="search-wrapper">${icon('search')}<input id="led-text" type="search" class="search-input" style="width:190px" placeholder="SOP, model…" value="${esc(ledgerFilter.text)}" aria-label="Filter calls"></div>
              <select id="led-caller" class="select" style="width:auto" aria-label="Caller"><option value="all">All callers</option>${callers.map(c => `<option ${ledgerFilter.caller === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
              <select id="led-provider" class="select" style="width:auto" aria-label="Provider"><option value="all">All providers</option>${providers.map(c => `<option ${ledgerFilter.provider === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
            </div>
          </div>
          <div id="ledger">${ledgerHtml(day.call_history || [])}</div>
        </div>
      </div>`;
  },

  mount(root, data, ctx) {
    const history = data.history || {};
    const day = history[selectedDate] || (data.today?.date === selectedDate ? data.today : {}) || {};
    const opts = { signal: ctx.signal };
    const paint = () => { root.querySelector('#ledger').innerHTML = ledgerHtml(day.call_history || []); };

    root.querySelector('#tel-date').addEventListener('change', e => { selectedDate = e.target.value; ctx.reload(); }, opts);
    root.querySelector('#led-text').addEventListener('input', e => { ledgerFilter.text = e.target.value; paint(); }, opts);
    root.querySelector('#led-caller').addEventListener('change', e => { ledgerFilter.caller = e.target.value; paint(); }, opts);
    root.querySelector('#led-provider').addEventListener('change', e => { ledgerFilter.provider = e.target.value; paint(); }, opts);
  },
};
