/**
 * Audit — browse the pipeline's debug/reasoning logs. Plain text from the API,
 * rendered escaped with line numbers, severity colouring, in-log search and download.
 */

import { api } from '../api.js';
import { esc, icon, fmt, toast, copyText, downloadText, registerActions, emptyState, debounce } from '../ui.js';

const MAX_LINES = 3000;
let selected = null;
let content = '';
let listFilter = '';
let logQuery = '';
let onlyMatches = false;
let wrap = false;

function severity(line) {
  if (/\b(error|exception|traceback|fatal|failed|violation)\b/i.test(line)) return 'err';
  if (/\b(warn(ing)?|retry|quota|blocked)\b/i.test(line)) return 'warn';
  if (/\b(success|passed|authentic|verified)\b/i.test(line)) return 'ok';
  return '';
}

function highlight(line, q) {
  const safe = esc(line);
  if (!q) return safe;
  const re = new RegExp(esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  return safe.replace(re, m => `<mark>${m}</mark>`);
}

function viewerHtml() {
  if (!selected) return emptyState({ icon: 'file', title: 'Select a log', text: 'Pick a file on the left to read its reasoning trace.' });
  const lines = content.split(/\r?\n/);
  const q = logQuery.trim();
  const indexed = lines.map((text, i) => ({ text, no: i + 1 }));
  const visible = (q && onlyMatches ? indexed.filter(l => l.text.toLowerCase().includes(q.toLowerCase())) : indexed);
  const shown = visible.slice(0, MAX_LINES);
  const hits = q ? indexed.filter(l => l.text.toLowerCase().includes(q.toLowerCase())).length : 0;
  return `
    ${q ? `<div class="tiny muted" style="padding:0 14px 6px">${hits} matching line${hits === 1 ? '' : 's'}</div>` : ''}
    ${shown.map(l => `<div class="log-line ${severity(l.text)}"><span class="ll-no">${l.no}</span><span class="ll-text">${highlight(l.text, q) || '&nbsp;'}</span></div>`).join('')}
    ${visible.length > shown.length ? `<div class="tiny muted" style="padding:10px 14px">Showing the first ${MAX_LINES} of ${fmt.num(visible.length)} lines — download the file to read the rest.</div>` : ''}`;
}

function listHtml(logs) {
  const f = listFilter.toLowerCase();
  const rows = logs.filter(l => !f || l.filename.toLowerCase().includes(f));
  if (!rows.length) return '<div class="tiny muted" style="padding:16px;text-align:center">No logs match.</div>';
  return rows.map(l => `
    <button class="log-item ${l.filename === selected ? 'active' : ''}" data-action="open-log" data-file="${esc(l.filename)}">
      <div class="li-name">${esc(l.filename)}</div>
      <div class="li-meta"><span>${fmt.bytes(l.size_bytes)}</span><span>${fmt.rel(l.modified)}</span></div>
    </button>`).join('');
}

async function fetchLog(name) {
  selected = name;
  content = await api.getLog(name);
}

registerActions({
  'open-log': async el => {
    try { await fetchLog(el.dataset.file); } catch (e) { toast(`Couldn't read log: ${e.message}`, 'error'); return; }
    document.querySelectorAll('.log-item').forEach(b => b.classList.toggle('active', b === el));
    document.getElementById('log-name').textContent = selected;
    const v = document.getElementById('log-view'); v.innerHTML = viewerHtml(); v.scrollTop = 0;
  },
  'log-copy': () => copyText(content, 'Log copied'),
  'log-download': () => downloadText(selected || 'log.txt', content),
  'log-end': () => { const v = document.getElementById('log-view'); v.scrollTop = v.scrollHeight; },
});

export default {
  id: 'audit',
  label: 'Audit logs',
  icon: 'file',
  title: 'Audit logs & traces',
  subtitle: 'Reasoning traces and validation records written during ingestion.',

  async load() {
    const data = await api.listLogs();
    const logs = data.logs || [];
    if (!logs.some(l => l.filename === selected)) { selected = logs[0]?.filename || null; content = ''; }
    if (selected && !content) { try { content = await api.getLog(selected); } catch { content = ''; } }
    return data;
  },

  render(data) {
    const logs = data.logs || [];
    if (!logs.length) {
      return `<div class="panel">${emptyState({ icon: 'file', title: 'No debug logs yet', text: 'Logs are written to knowledge_base/logs/debug as documents are processed.' })}</div>`;
    }
    return `
      <div class="panel">
        <div class="log-layout">
          <div class="stack-sm">
            <div class="search-wrapper">${icon('search')}<input id="log-filter" type="search" class="search-input" style="width:100%" placeholder="Filter ${logs.length} logs…" value="${esc(listFilter)}" aria-label="Filter log files"></div>
            <div class="log-list" id="log-list">${listHtml(logs)}</div>
          </div>
          <div class="stack-sm" style="min-width:0">
            <div class="row-between">
              <span class="mono strong small truncate" id="log-name">${esc(selected || '')}</span>
              <div class="row">
                <div class="search-wrapper">${icon('search')}<input id="log-search" type="search" class="search-input" style="width:190px" placeholder="Search in log…" value="${esc(logQuery)}" aria-label="Search within the log"></div>
                <label class="row small secondary" style="gap:6px;cursor:pointer"><span class="switch"><input type="checkbox" id="log-only" ${onlyMatches ? 'checked' : ''}><span></span></span>Only matches</label>
                <label class="row small secondary" style="gap:6px;cursor:pointer"><span class="switch"><input type="checkbox" id="log-wrap" ${wrap ? 'checked' : ''}><span></span></span>Wrap</label>
                <button class="btn btn-sm btn-outline" data-action="log-end">End</button>
                <button class="btn btn-sm btn-outline" data-action="log-copy">${icon('copy')}Copy</button>
                <button class="btn btn-sm btn-outline" data-action="log-download">${icon('download')}Download</button>
              </div>
            </div>
            <div class="log-view ${wrap ? 'wrap' : ''}" id="log-view" tabindex="0" aria-label="Log contents">${viewerHtml()}</div>
          </div>
        </div>
      </div>`;
  },

  mount(root, data, ctx) {
    const logs = data.logs || [];
    const opts = { signal: ctx.signal };
    const view = root.querySelector('#log-view');
    if (!view) return;
    const repaint = () => { view.innerHTML = viewerHtml(); };

    root.querySelector('#log-filter').addEventListener('input', debounce(e => {
      listFilter = e.target.value; root.querySelector('#log-list').innerHTML = listHtml(logs);
    }, 120), opts);
    root.querySelector('#log-search').addEventListener('input', debounce(e => { logQuery = e.target.value; repaint(); }, 160), opts);
    root.querySelector('#log-only').addEventListener('change', e => { onlyMatches = e.target.checked; repaint(); }, opts);
    root.querySelector('#log-wrap').addEventListener('change', e => { wrap = e.target.checked; view.classList.toggle('wrap', wrap); }, opts);
  },
};
