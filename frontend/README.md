# Elone Agent — SOP Governance Hub Frontend (Pure Client-Side UI)

A clean, modern, self-contained single-page web dashboard for the **Elone SOP Governance Hub**.

This folder contains **strictly client-side code** (HTML, CSS, JS) with **zero backend Python files**. All backend logic, AI orchestration, validation gates, and API endpoints reside in the [`backend/`](../backend) directory.

---

## 📁 Frontend Architecture

```
frontend/
├── index.html         # Main dashboard HTML shell
├── css/
│   ├── style.css      # Dark & light design system, glassmorphism tokens, typography
│   └── components.css # Bento grid, metric cards, pipeline steppers, tables, modal
└── js/
    ├── api.js         # API client layer (connects to http://127.0.0.1:8000/api)
    ├── app.js         # State management, navigation, theme toggle, modals, toasts
    └── views/
        ├── overview.js    # Executive KPIs, quota gauge, provider matrix
        ├── pipeline.js    # 5-Phase Pipeline & 7 Gates + Interactive Security Simulator
        ├── playbooks.js   # OKF Playbook catalog, step inspector & HMAC verifier
        ├── ingestion.js   # Drag-and-drop uploader, manifest queue & dry-run planner
        ├── tools.js       # Registered platform tool catalog explorer
        ├── telemetry.js   # Multi-model call ledger, daily cost accounting (USD/INR)
        └── audit.js       # Raw debug logs and full reasoning traces viewer
```

---

## 🔌 API Connection

`frontend/js/api.js` is pre-configured with a smart host detector:
```javascript
const API_BASE = (window.location.port === '8000')
  ? window.location.origin
  : 'http://127.0.0.1:8000';
```
* **Served by Backend Server:** Automatically routes to `/api/...`.
* **Served Standalone (e.g. Vite, Live Server, npm):** Automatically proxies to `http://127.0.0.1:8000/api/...` with full CORS support.

---

## 🚀 Running the System

You can run the full system using the root launcher:
```powershell
.\start.ps1   # or double-click start.bat
```
Or start the backend from `backend/`:
```powershell
cd backend
python server.py
```
And open **http://127.0.0.1:8000** in your browser.
