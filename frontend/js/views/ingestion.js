/**
 * Ingestion — upload SOP documents, see Gate-1 results, run the pipeline on a
 * file, or preview the LLM plan (dry run) without writing anything.
 */

import { api } from '../api.js';
import {
  esc, icon, fmt, pill, store, toast, busy, openModal, closeModal, registerActions,
  bindTabs, emptyState, jsonBlock, tierBadge,
} from '../ui.js';
import { stepHtml } from './playbooks.js';
import { trackIngest } from '../progress.js';

let filter = 'all';

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

function statusOf(f) {
  if (f.status === 'success') return pill('PROCESSED', 'success');
  if (f.status === 'awaiting_review') return pill('AWAITING REVIEW', 'warning');
  if (f.status === 'failed') return pill('FAILED', 'danger');
  if (f.status === 'unactionable') return pill('UNACTIONABLE', 'muted');
  return pill('NOT PROCESSED', 'neutral');
}

function filterFiles(files) {
  return files.filter(f => {
    if (filter === 'ready') return f.gate1_passed && f.status !== 'success' && f.status !== 'awaiting_review';
    if (filter === 'rejected') return !f.gate1_passed;
    if (filter === 'processed') return f.status === 'success';
    return true;
  });
}

function filesTable(files) {
  const rows = filterFiles(files);
  if (!files.length) return emptyState({ icon: 'inbox', title: 'The uploads folder is empty', text: 'Drop a document above to get started.' });
  if (!rows.length) return emptyState({ icon: 'search', title: 'No files in this filter' });
  return `
    <div class="table-responsive">
      <table class="data-table">
        <thead><tr><th>Document</th><th>Gate 1 checks</th><th>Pipeline</th><th>Playbook</th><th>Modified</th><th></th></tr></thead>
        <tbody>
          ${rows.map(f => `
            <tr>
              <td>
                <div class="mono strong" style="font-size:12.5px;word-break:break-all">${esc(f.filename)}</div>
                <div class="cell-sub">${esc(String(f.extension).replace('.', '').toUpperCase())} · ${fmt.bytes(f.size_bytes)}${f.page_count ? ` · ~${esc(f.page_count)} page${f.page_count > 1 ? 's' : ''}` : ''}</div>
              </td>
              <td style="max-width:260px">
                ${f.gate1_passed ? pill('PASSED', 'success') : pill('REJECTED', 'danger')}
                ${f.gate1_error ? `<div class="cell-sub text-danger">${esc(f.gate1_error)}</div>` : ''}
              </td>
              <td>${statusOf(f)}${f.processed_at ? `<div class="cell-sub">${fmt.date(f.processed_at)}</div>` : ''}</td>
              <td>${f.sop_id ? `<a href="#/playbooks" class="id-cell" title="View in Playbooks">${esc(f.sop_id)}</a>` : '<span class="muted">—</span>'}</td>
              <td class="nowrap"><div class="mono tiny">${fmt.date(f.modified)}</div><div class="cell-sub">${fmt.rel(f.modified)}</div></td>
              <td>
                <div class="row-actions">
                  ${f.status === 'success'
                    ? `<a class="btn btn-sm btn-secondary" href="#/playbooks" title="View published playbook in OKF Hub">${icon('book')}Playbook</a>
                       <button class="btn btn-sm btn-outline" data-action="dry-run" data-file="${esc(f.filename)}" title="Preview the plan without saving anything">Dry run</button>`
                    : f.status === 'awaiting_review'
                    ? `<a class="btn btn-sm btn-secondary" href="#/review" title="Open review queue">${icon('review')}Review</a>
                       <button class="btn btn-sm btn-outline" data-action="dry-run" data-file="${esc(f.filename)}" title="Preview the plan without saving anything">Dry run</button>`
                    : `<button class="btn btn-sm btn-primary" data-action="ingest-file" data-file="${esc(f.filename)}" ${f.gate1_passed ? '' : 'disabled title="Fails Gate 1 checks"'}>${icon('play')}Ingest</button>
                       <button class="btn btn-sm btn-outline" data-action="dry-run" data-file="${esc(f.filename)}" ${f.gate1_passed ? '' : 'disabled'} title="Preview the plan without saving anything">Dry run</button>`}
                </div>
              </td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;
}

// ---------------------------------------------------------------------------
// Ingest flow
// ---------------------------------------------------------------------------

registerActions({
  'ingest-file': el => {
    const file = el.dataset.file;
    openModal({
      title: 'Ingest document',
      size: 'md',
      body: `
        <form id="ingest-form" class="stack" data-file="${esc(file)}">
          <div class="meta-item"><div class="meta-label">Document</div><div class="meta-value mono">${esc(file)}</div></div>
          <div class="callout">${icon('info')}<div>Runs extraction, secret scanning, LLM structuring and quality assessment. It can take a minute or two and uses LLM quota. <b>Nothing is published</b> until someone else reviews and approves it.</div></div>
          <div class="form-grid">
            <div class="field"><label for="ing-uploader">Uploaded by</label><input id="ing-uploader" class="input" value="${esc(store.get('uploader', 'analyst@example.com'))}" autocomplete="username"><span class="field-hint">The reviewer must be someone else.</span></div>
            <div class="field"><label for="ing-tenant">Tenant</label><input id="ing-tenant" class="input" value="${esc(store.get('tenant', 'tn_northwind'))}"></div>
          </div>
          <div class="field"><label for="ing-sopid">SOP ID <span class="muted" style="text-transform:none">(optional)</span></label><input id="ing-sopid" class="input mono" placeholder="Generated from the file hash if left empty"></div>
        </form>`,
      footer: `<button class="btn btn-outline" data-action="close-modal">Cancel</button>
               <button class="btn btn-primary" data-action="ingest-run">${icon('play')}Start ingestion</button>`,
    });
  },

  'ingest-run': async (_el, _e, ctx) => {
    const form = document.getElementById('ingest-form');
    const file = form.dataset.file;
    const opts = {
      uploadedBy: form.querySelector('#ing-uploader').value.trim(),
      tenantId: form.querySelector('#ing-tenant').value.trim(),
      sopId: form.querySelector('#ing-sopid').value.trim(),
    };
    store.set('uploader', opts.uploadedBy); store.set('tenant', opts.tenantId);

    const tracker = trackIngest(file, { actor: opts.uploadedBy });       // live stage list; the request itself only answers at the end
    let res;
    try {
      res = await api.ingestSingle(file, opts);
    } catch (err) {
      res = { success: false, status: 'INGESTION_ERROR', error: err.message };
    }
    await tracker.finish(res.status === 'awaiting_review' ? 800 : 500);
    openModal({ title: 'Ingestion result', size: 'md', ...resultModal(res, file) });
    ctx.reload();
    ctx.refreshBadges();
  },

  'dry-run': async el => {
    const file = el.dataset.file;
    const done = busy(el);
    try {
      const { draft } = await api.planPreview(file);
      const fm = draft.frontmatter || draft;
      const steps = draft.steps || fm.steps || [];
      openModal({
        title: `Dry run — ${file}`,
        size: 'lg',
        body: `
          <div class="stack">
            <div class="callout">${icon('info')}<div>This is what the LLM would produce. <b>Nothing was saved</b> and no review task was created.</div></div>
            <div class="meta-grid">
              <div class="meta-item"><div class="meta-label">Title</div><div class="meta-value">${esc(fm.title || '—')}</div></div>
              <div class="meta-item"><div class="meta-label">Category</div><div class="meta-value">${esc(fm.category || '—')}</div></div>
              <div class="meta-item"><div class="meta-label">Platform / OS</div><div class="meta-value mono">${esc(fm.platform || '—')} / ${esc(fm.target_os || '—')}</div></div>
              <div class="meta-item"><div class="meta-label">Executable</div><div class="meta-value">${fm.is_executable === false ? pill('NO', 'danger') : pill('YES', 'success')}</div></div>
              <div class="meta-item"><div class="meta-label">Confidence</div><div class="meta-value">${fm.confidence_score != null ? `${Math.round(fm.confidence_score * 100)}% ${esc(fm.confidence_level || '')}` : '—'}</div></div>
            </div>
            ${fm.unexecutable_reason ? `<div class="callout warn">${icon('alert')}<div>${esc(fm.unexecutable_reason)}</div></div>` : ''}
            <div class="tabs in-modal"><button class="tab active" data-tab="steps">Steps <span class="tab-count">${steps.length}</span></button><button class="tab" data-tab="json">Raw draft</button></div>
            <div>
              <div class="tab-panel" data-panel="steps"><div class="stack">${steps.length ? steps.map(stepHtml).join('') : emptyState({ icon: 'list', title: 'No steps were produced' })}</div></div>
              <div class="tab-panel" data-panel="json" hidden>${jsonBlock(draft)}</div>
            </div>
          </div>`,
        footer: `<button class="btn btn-outline" data-action="copy" data-copy="${esc(JSON.stringify(draft, null, 2))}" data-msg="Draft JSON copied">${icon('copy')}Copy JSON</button>
                 <button class="btn btn-primary" data-action="close-modal">Close</button>`,
        onMount: root => bindTabs(root),
      });
    } catch (err) {
      toast(`Dry run failed: ${err.message}`, 'error', 7000);
    } finally { done(); }
  },

  // Go straight to the review page for the task this ingest just created (fall back to the queue).
  'goto-review': el => { closeModal(); location.hash = el.dataset.task ? `#/review/${encodeURIComponent(el.dataset.task)}` : '#/review'; },
  'ing-filter': (el, _e, ctx) => { filter = el.dataset.filter; ctx.reload(); },
});

function resultModal(res, file) {
  const close = '<button class="btn btn-outline" data-action="close-modal">Close</button>';
  const status = res.status;

  if (res.success && status === 'awaiting_review') {
    const c = res.confidentiality || {};
    const q = res.quality || {};
    return {
      body: `
        <div class="stack">
          <div class="callout success">${icon('check')}<div><b>${esc(res.sop_id)} is ready for review.</b> A human other than the uploader must now approve it.</div></div>
          <div class="meta-grid">
            <div class="meta-item"><div class="meta-label">Review task</div><div class="meta-value mono">${esc(res.task_id)}</div></div>
            <div class="meta-item"><div class="meta-label">Assigned to</div><div class="meta-value">${esc(res.assigned_role)}</div></div>
            <div class="meta-item"><div class="meta-label">Due</div><div class="meta-value">${fmt.date(res.due_date)}</div></div>
            <div class="meta-item"><div class="meta-label">Confidentiality</div><div class="meta-value">${tierBadge(c.level)} <span class="mono tiny muted">${esc(c.score)}/100</span></div></div>
            <div class="meta-item"><div class="meta-label">Quality</div><div class="meta-value">${esc(q.status || '—')} <span class="mono tiny muted">${esc(q.quality_score ?? '')}</span></div></div>
          </div>
        </div>`,
      footer: `${close}<button class="btn btn-primary" data-action="goto-review" data-task="${esc(res.task_id)}">${icon('review')}Review this SOP</button>`,
    };
  }
  if (status === 'quarantined') {
    const inc = res.incident || {};
    return {
      body: `<div class="stack">
        <div class="callout danger">${icon('lock')}<div><b>Quarantined — live credentials detected.</b> ${esc(res.error || '')}</div></div>
        <div class="meta-grid">
          <div class="meta-item"><div class="meta-label">Incident</div><div class="meta-value mono">${esc(res.incident_id)}</div></div>
          <div class="meta-item"><div class="meta-label">Secrets found</div><div class="meta-value">${esc(inc.secrets_count ?? '—')}</div></div>
          <div class="meta-item"><div class="meta-label">Types</div><div class="meta-value">${(inc.secret_types || []).map(t => `<span class="badge-tag">${esc(fmt.words(t))}</span>`).join(' ') || '—'}</div></div>
        </div>
        <p class="small muted">Remove the credentials from <b>${esc(file)}</b> and upload a clean copy.</p></div>`,
      footer: close,
    };
  }
  if (status === 'cancelled') {
    return {
      body: `<div class="stack">
        <div class="callout">${icon('info')}<div><b>Processing was stopped.</b> Nothing was saved and no review task was created.</div></div>
        <p class="small muted">A model call that was already in progress may still finish in the background, but its result is thrown away. You can ingest <b>${esc(file)}</b> again whenever you like.</p></div>`,
      footer: `${close}<button class="btn btn-primary" data-action="ingest-file" data-file="${esc(file)}">${icon('play')}Ingest again</button>`,
    };
  }
  if (status === 'already_running') {
    return { body: `<div class="callout warn">${icon('alert')}<div><b>Already being processed.</b> ${esc(res.error || '')} Wait for it to finish, or stop it first.</div></div>`, footer: close };
  }
  if (status === 'duplicate') {
    return { body: `<div class="callout warn">${icon('alert')}<div><b>Duplicate document.</b> ${esc(res.message || 'This exact file has already been processed.')}</div></div>`, footer: close };
  }
  if (status === 'unactionable') {
    return { body: `<div class="callout warn">${icon('alert')}<div><b>Not actionable as an automated procedure.</b><div style="margin-top:4px">${esc(res.reason || '')}</div></div></div>`, footer: close };
  }
  if (status === 'REJECTED_GATE_1') {
    return { body: `<div class="callout danger">${icon('alert')}<div><b>Rejected at Gate 1.</b> ${esc(res.reason || '')}</div></div>`, footer: close };
  }
  return {
    body: `<div class="callout danger">${icon('alert')}<div><b>Ingestion failed.</b><div style="margin-top:4px">${esc(res.error || res.reason || res.message || 'Unknown error')}</div></div></div>`,
    footer: close,
  };
}

// ---------------------------------------------------------------------------
// Uploading
// ---------------------------------------------------------------------------

async function uploadFiles(fileList, root, meta, ctx) {
  const queue = root.querySelector('#upload-queue');
  const allowed = (meta.allowed_extensions || []).map(e => e.toLowerCase());
  const maxBytes = (meta.max_size_mb || 0) * 1024 * 1024;
  let uploaded = 0;

  for (const file of fileList) {
    const row = document.createElement('div');
    row.className = 'upload-item';
    row.innerHTML = `<div class="grow"><div class="ui-name">${esc(file.name)}</div><div class="ui-note">${fmt.bytes(file.size)}</div></div><span class="ui-status"></span>`;
    queue.prepend(row);
    const setStatus = (html, note) => { row.querySelector('.ui-status').innerHTML = html; if (note) row.querySelector('.ui-note').textContent = note; };

    const ext = `.${file.name.split('.').pop().toLowerCase()}`;
    if (allowed.length && !allowed.includes(ext)) { setStatus(pill('REJECTED', 'danger'), `Type ${ext} isn't allowed. Allowed: ${allowed.join(', ')}`); continue; }
    if (maxBytes && file.size > maxBytes) { setStatus(pill('TOO LARGE', 'danger'), `Over the ${meta.max_size_mb} MB limit`); continue; }

    setStatus(pill('UPLOADING', 'info'));
    try {
      const res = await api.uploadFile(file);
      uploaded++;
      if (res.gate1_passed) setStatus(pill('GATE 1 PASSED', 'success'), 'Ready to ingest');
      else setStatus(pill('GATE 1 FAILED', 'danger'), res.gate1_error);
    } catch (err) {
      setStatus(pill('FAILED', 'danger'), err.message);
    }
  }
  if (uploaded) { toast(`${uploaded} file${uploaded > 1 ? 's' : ''} uploaded.`, 'success'); ctx.reload(); }
}

// ---------------------------------------------------------------------------

export default {
  id: 'ingestion',
  label: 'Ingestion',
  icon: 'upload',
  title: 'Ingest SOPs',
  subtitle: 'Upload documents, check Gate 1, then run the pipeline or preview the plan.',

  load: () => api.listUploads(),

  render(data) {
    const files = data.files || [];
    const allowed = data.allowed_extensions || [];
    const count = {
      all: files.length,
      ready: files.filter(f => f.gate1_passed && f.status !== 'success').length,
      rejected: files.filter(f => !f.gate1_passed).length,
      processed: files.filter(f => f.status === 'success').length,
    };
    return `
      <div class="view-stack">
        <div class="panel panel-flush">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('upload')}Upload documents</div>
              <div class="panel-subtitle">Allowed: ${allowed.map(e => `<code>${esc(e)}</code>`).join(' ') || '—'} · up to ${esc(data.max_size_mb)} MB. Files are checked for type, size, spoofed headers and length before anything is read.</div>
            </div>
          </div>
          <div class="dropzone-container" id="dropzone" tabindex="0" role="button" aria-label="Choose files to upload">
            <input type="file" id="file-input" multiple hidden accept="${esc(allowed.join(','))}">
            <div class="dropzone-icon">${icon('upload')}</div>
            <div class="dropzone-title">Drop files here, or click to browse</div>
            <div class="dropzone-subtext">You can select several at once</div>
          </div>
          <div class="upload-queue" id="upload-queue"></div>
        </div>

        <div class="panel panel-flush">
          <div class="panel-header">
            <div>
              <div class="panel-title">${icon('file')}Uploads folder</div>
              <div class="panel-subtitle">Everything currently in <code>knowledge_base/_uploads</code> and how far it got.</div>
            </div>
            <div class="panel-actions">
              <div class="chips" role="group" aria-label="Filter files">
                ${[['all', 'All'], ['ready', 'Ready'], ['rejected', 'Rejected'], ['processed', 'Processed']].map(([k, l]) => `<button class="chip ${filter === k ? 'active' : ''}" data-action="ing-filter" data-filter="${k}">${l} <span class="count">${count[k]}</span></button>`).join('')}
              </div>
              <button class="btn btn-secondary btn-sm" data-action="run-scan">${icon('refresh')}Scan all</button>
            </div>
          </div>
          ${filesTable(files)}
        </div>
      </div>`;
  },

  mount(root, data, ctx) {
    const dz = root.querySelector('#dropzone');
    const input = root.querySelector('#file-input');
    const opts = { signal: ctx.signal };
    const go = files => files.length && uploadFiles([...files], root, data, ctx);

    dz.addEventListener('click', () => input.click(), opts);
    dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } }, opts);
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); }, opts);
    dz.addEventListener('dragleave', () => dz.classList.remove('dragover'), opts);
    dz.addEventListener('drop', e => { e.preventDefault(); dz.classList.remove('dragover'); go(e.dataTransfer.files); }, opts);
    input.addEventListener('change', () => { go(input.files); input.value = ''; }, opts);
  },
};
