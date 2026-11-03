/**
 * Elone SOP Governance Hub — tiny dependency-free bar charts (stacked or single series).
 * Colours come from CSS custom properties (--series-1..3), which carry the validated
 * light/dark categorical steps. Every chart ships a legend (>=2 series), a hover/focus
 * tooltip, and a "view as table" fallback so identity is never colour-alone.
 */

import { esc } from './ui.js';

const W = 640;
const M = { l: 46, r: 8, t: 10, b: 26 };

function niceMax(v) {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

function compact(n) {
  if (n >= 1e6) return `${+(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${+(n / 1e3).toFixed(1)}k`;
  return String(+n.toFixed(n < 10 ? 2 : 0));
}

/** Rectangle with only the top corners rounded (data end), flat on the baseline. */
function topRounded(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, h, w / 2));
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

/**
 * @param {{labels:string[], series:{name:string,color:string,values:number[]}[], height?:number,
 *          format?:(n:number)=>string, ariaLabel?:string}} opts
 * @returns {string} HTML
 */
export function barChart({ labels, series, height = 220, format = n => String(n), ariaLabel = 'Bar chart' }) {
  const n = labels.length;
  const totals = labels.map((_, i) => series.reduce((s, ser) => s + (ser.values[i] || 0), 0));
  const max = niceMax(Math.max(0, ...totals));

  if (n === 0 || Math.max(0, ...totals) === 0) {
    return '<div class="empty-state" style="padding:28px 12px"><div class="empty-title">No data recorded yet</div></div>';
  }

  const H = height;
  const iw = W - M.l - M.r;
  const ih = H - M.t - M.b;
  const band = iw / n;
  const bw = Math.min(30, band * 0.62);
  const y = v => M.t + ih - (v / max) * ih;

  const grid = [0, 1, 2, 3, 4].map(k => {
    const v = (max / 4) * k;
    return `<line class="grid-line" x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/>` +
           `<text x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${compact(v)}</text>`;
  }).join('');

  const every = Math.ceil(n / 8);
  const groups = labels.map((label, i) => {
    const cx = M.l + band * i + band / 2;
    const x = cx - bw / 2;
    const rows = series.map(s => ({ name: s.name, color: s.color, value: s.values[i] || 0 }));
    const tipRows = rows.map(r => ({ name: r.name, color: r.color, value: format(r.value) }));
    if (series.length > 1) tipRows.push({ name: 'Total', color: '', value: format(totals[i]) });

    // Stack from the baseline; the last non-empty segment carries the rounded data end.
    const nonEmpty = rows.filter(r => r.value > 0);
    let acc = 0;
    const bars = rows.map(r => {
      if (r.value <= 0) return '';
      const top = y(acc + r.value);
      const h = y(acc) - top;
      acc += r.value;
      const isTop = r === nonEmpty[nonEmpty.length - 1];
      const d = isTop ? topRounded(x, top, bw, h, 4) : `M${x},${top} h${bw} v${h} h${-bw} Z`;
      return `<path class="bar" d="${d}" fill="${r.color}" stroke="var(--card-bg)" stroke-width="${series.length > 1 ? 2 : 0}" stroke-linejoin="round"/>`;
    }).join('');

    const aria = `${label}: ${tipRows.map(t => `${t.name} ${t.value}`).join(', ')}`;
    return `
      <g class="bar-group" tabindex="0" role="img" aria-label="${esc(aria)}"
         data-tt-title="${esc(label)}" data-tt-rows="${esc(JSON.stringify(tipRows))}">
        <rect class="hit" x="${M.l + band * i}" y="${M.t}" width="${band}" height="${ih}"/>
        ${bars}
        ${i % every === 0 ? `<text x="${cx}" y="${H - 8}" text-anchor="middle">${esc(label.length > 5 ? label.slice(5) : label)}</text>` : ''}
      </g>`;
  }).join('');

  const legend = series.length > 1
    ? `<div class="legend">${series.map(s => `<span class="legend-item"><span class="legend-swatch" style="background:${s.color}"></span>${esc(s.name)}</span>`).join('')}</div>`
    : '';

  const table = `
    <details class="accordion" style="margin-top:10px">
      <summary>View as table</summary>
      <div class="acc-body table-responsive">
        <table class="data-table">
          <thead><tr><th>Date</th>${series.map(s => `<th class="num">${esc(s.name)}</th>`).join('')}${series.length > 1 ? '<th class="num">Total</th>' : ''}</tr></thead>
          <tbody>${labels.map((l, i) => `<tr><td>${esc(l)}</td>${series.map(s => `<td class="num">${esc(format(s.values[i] || 0))}</td>`).join('')}${series.length > 1 ? `<td class="num">${esc(format(totals[i]))}</td>` : ''}</tr>`).join('')}</tbody>
        </table>
      </div>
    </details>`;

  return `
    <div class="chart-card">
      ${legend}
      <svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(ariaLabel)}">
        ${grid}
        ${groups}
      </svg>
      ${table}
    </div>`;
}

// ---------------------------------------------------------------------------
// Shared tooltip (event delegation — call once at startup)
// ---------------------------------------------------------------------------

export function initChartTooltip() {
  let tip = document.getElementById('chart-tooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'chart-tooltip';
    tip.setAttribute('role', 'tooltip');
    document.body.appendChild(tip);
  }

  const show = (group, x, y) => {
    let rows = [];
    try { rows = JSON.parse(group.dataset.ttRows || '[]'); } catch { /* ignore */ }
    tip.innerHTML = `<div class="tt-title">${esc(group.dataset.ttTitle)}</div>` + rows.map(r =>
      `<div class="tt-row"><span class="row" style="gap:6px;flex-wrap:nowrap">${r.color ? `<span class="legend-swatch" style="background:${r.color}"></span>` : ''}${esc(r.name)}</span><b>${esc(r.value)}</b></div>`
    ).join('');
    tip.classList.add('show');
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let left = x + pad;
    let top = y - rect.height - pad;
    if (left + rect.width > window.innerWidth - 8) left = x - rect.width - pad;
    if (top < 8) top = y + pad;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${top}px`;
  };
  const hide = () => tip.classList.remove('show');

  document.addEventListener('mousemove', e => {
    const g = e.target.closest?.('.bar-group');
    g ? show(g, e.clientX, e.clientY) : hide();
  });
  document.addEventListener('focusin', e => {
    const g = e.target.closest?.('.bar-group');
    if (!g) return;
    const r = g.getBoundingClientRect();
    show(g, r.left + r.width / 2, r.top + 20);
  });
  document.addEventListener('focusout', hide);
  document.addEventListener('scroll', hide, true);
}
