# Elone SOP Governance Hub — Frontend

A dependency-free single-page dashboard (plain HTML, CSS and ES modules — no build step) for the
Elone backend. It covers every endpoint in `backend/api/routes_*.py`.

## Run it

```powershell
cd backend
python server.py        # serves the API and this folder at http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>. If you serve the folder separately (Live Server, `python -m http.server`),
`js/api.js` falls back to `http://127.0.0.1:8000` for API calls (CORS is open on the backend).

## What's in it

| Route | View | Backend endpoints |
|---|---|---|
| `#/overview` | KPIs, job funnel, recent jobs, scheduler, model routing, security gates | `/api/overview`, `/api/governance/jobs`, `/review-tasks`, `/incidents` |
| `#/playbooks` | Searchable library (cards/table), category filters, step inspector, HMAC re-verify, **delete** (type-the-id confirmation) | `GET /api/sops`, `GET /api/sops/{id}`, `POST /api/sops/{id}/verify`, `DELETE /api/sops/{id}` |
| `#/review` | Review tasks, lifecycle jobs, quarantine incidents; publish, job history | `/api/governance/*` |
| `#/review/<task_id>` | **Review page** for one task: steps with the evidence for each quote, document details, history, JSON, classification and quality, and the decision form | `/api/governance/review-tasks`, `/sops/{id}/canonical`, `/jobs/{id}` |
| `#/catalog` | Published SOPs per clearance tier + agent-query simulator | `/api/governance/downstream/*` |
| `#/ingestion` | Multi-file upload with Gate-1 feedback, ingest, dry-run, scan | `/api/uploads*`, `/api/plan-preview` |
| `#/tools` | Searchable tool catalog with response schemas | `/api/tools` |
| `#/telemetry` | Per-day calls/tokens/cost charts and call ledger | `/api/telemetry` |
| `#/audit` | Log browser: line numbers, severity colours, in-log search, download | `/api/logs`, `/api/logs/{file}` |
| `#/security` | Try the DLP, command-blacklist and hidden-Unicode filters | `/api/security/test` |
| `#/settings` | Generated config form + raw JSON editor (hot-reloaded server-side) | `/api/config` |

The header also shows live API health (`/api/health`), and the sidebar badges track published playbooks
and pending reviews.

## Layout

```
frontend/
├── index.html            App shell (sidebar, header, modal + toast hosts)
├── css/
│   ├── style.css         Design tokens (dark + light), shell, forms, buttons, modal, toasts
│   └── components.css    Cards, tables, tabs, timeline, charts, log viewer, settings form…
└── js/
    ├── app.js            Hash router, view lifecycle, polling, theme, health, shortcuts
    ├── api.js            One request layer + ApiError for every endpoint
    ├── ui.js             esc(), icons, formatters, toasts, modal host, data-action registry
    ├── charts.js         Dependency-free stacked/single bar charts with tooltip + table view
    ├── progress.js       Live ingestion progress (polls the job + LLM calls while the request runs)
    └── views/            One module per route (default export; see below)
```

### Writing a view

```js
export default {
  id: 'example', label: 'Example', icon: 'file',
  title: 'Page title', subtitle: 'One line under it.',
  refreshMs: 15000,                      // optional background refresh (pauses while a modal/input is active)
  async load(ctx)  { return api.something(); },
  render(data, ctx) { return `<div class="panel">…</div>`; },   // return an HTML string; escape with esc()
  mount(root, data, ctx) { /* optional: bind listeners with { signal: ctx.signal } */ },
};
```

Add it to `VIEWS` / `GROUPS` in `app.js`. A view with `hidden: true` and a `parent` (like the review page) is reachable only by its sub-route and keeps its parent highlighted in the sidebar; route segments arrive as `ctx.params`. Interactivity uses `data-action="name"` attributes handled by
`registerActions({...})` in `ui.js` — there are no inline `onclick` handlers and no `window.*` globals.

## Conventions

- **Everything dynamic is escaped** with `esc()`; toasts use `textContent`. Server text (logs, SOP steps, job reasons) can't inject HTML.
- **Never colour alone:** status pills carry a label, charts have a legend and a "view as table" fallback.
- **Quota fields can be the string `"unlimited"`** (`isUnlimited()` in `ui.js`).
- **Light/dark** follow the OS until toggled; the choice is stored in `localStorage`.
- **Shortcuts:** `/` or `Ctrl/⌘+K` focuses search, `Esc` closes dialogs.

## Notes on governance behaviour

- **Cache-busting:** browsers keep imported modules for days, so `index.html` maps every JS file to a versioned URL. Bump `v=` (find/replace) whenever any JS or CSS changes.
- **Deleting a playbook moves files, it doesn't erase them:** the playbook, its canonical JSON and rulebook go to `knowledge_base/_trash/<time>_<id>/` with a `_manifest.json` (who, why, and how to restore). It is also removed from the agent catalog and its job is soft-deleted.
- A review decision sends the draft's measured `traceability`, `completeness`, `schema_valid` and blocking-issue count to the server, so the publication gates judge real numbers instead of the server's defaults.
- Approving requires ticking the confidentiality-tier confirmation (publication gate 6).
- Saving the canonical editor for an SOP that isn't published yet writes files into the knowledge base before approval, so the UI asks for explicit confirmation first.
