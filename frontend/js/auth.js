/**
 * Elone SOP Governance Hub — In-memory auth session store & Login view.
 * No JWTs are stored in localStorage/sessionStorage; authentication relies
 * on verified HttpOnly cookies set by POST /api/auth/login.
 */

import { api } from './api.js';
import { esc, icon, busy, tierBadge } from './ui.js';

const session = {
  user: null,
  capabilities: {},
};

const ROLE_LABELS = {
  process_owner: 'Process Owner',
  security_reviewer: 'Security Reviewer',
  admin: 'Admin',
  agent: 'Agent',
};

export function formatRoleLabel(role) {
  return ROLE_LABELS[String(role || '').toLowerCase()] || String(role || '');
}

export function getUser() { return session.user; }
export function getCapabilities() { return session.capabilities || {}; }
export function isAuthenticated() { return Boolean(session.user); }
export function isHumanUser() { return session.user?.actor_type === 'human'; }

export function hasRole(role) {
  const r = String(role || '').trim().toLowerCase();
  return Boolean(session.user?.roles?.some(x => String(x).toLowerCase() === r));
}

export function hasAnyRole(roles = []) {
  return roles.some(r => hasRole(r));
}

export function hasCapability(cap) {
  return Boolean(session.capabilities?.[cap]);
}

export function setSession(user, capabilities) {
  session.user = user || null;
  session.capabilities = capabilities || user?.capabilities || {};
}

export function clearSession() {
  session.user = null;
  session.capabilities = {};
}

export function canAccessView(viewId) {
  if (!isAuthenticated() || !isHumanUser()) return false;
  if (viewId === 'ingestion') return hasCapability('can_upload') || hasCapability('can_ingest');
  if (viewId === 'tools') return hasCapability('can_view_tools');
  if (viewId === 'security') return hasCapability('can_run_security_lab');
  if (viewId === 'telemetry') return hasCapability('can_view_telemetry');
  if (viewId === 'audit') return hasCapability('can_view_logs');
  if (viewId === 'settings') return hasCapability('can_manage_config') || hasCapability('can_manage_users');
  return true;
}

export function initialsFor(name) {
  const parts = String(name || 'U').trim().split(/[\s.@_-]+/).filter(Boolean);
  if (!parts.length) return 'U';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export async function initAuth() {
  try {
    const res = await api.getMe();
    if (res?.user?.actor_type !== 'human') {
      await api.logout().catch(() => {});
      clearSession();
      return {
        authenticated: false,
        error: 'Service accounts (role "agent") cannot sign in to the interactive dashboard. Use a human operator account.',
      };
    }
    setSession(res.user, res.capabilities || res.user.capabilities);
    return { authenticated: true, user: res.user };
  } catch (err) {
    clearSession();
    if (err.status === 401) {
      return { authenticated: false, error: null };
    }
    return { authenticated: false, error: err.message || 'Unable to verify session.', status: err.status || 0 };
  }
}

export function renderLoginHtml(initialError = null) {
  const isDark = (document.documentElement.getAttribute('data-theme') || 'dark') === 'dark';
  return `
    <div class="login-shell">
      <div class="login-theme-wrap">
        <button type="button" class="btn btn-outline btn-icon-only" id="login-theme-toggle" data-action="toggle-theme" aria-label="Toggle dark / light theme" title="Toggle theme">${icon(isDark ? 'sun' : 'moon')}</button>
      </div>
      <div class="login-card" role="main" aria-labelledby="login-heading">
        <div class="login-brand">
          <div class="brand-logo-badge" aria-hidden="true">E</div>
          <div>
            <h1 id="login-heading">Elone <span class="badge-tag">OKF</span></h1>
            <p>SOP Governance Hub</p>
          </div>
        </div>

        <div class="login-intro">
          <h2>Sign in to your workspace</h2>
          <p class="secondary small">Authenticated identity, tenant isolation, clearance tier, and separation of duties are enforced per token.</p>
        </div>

        <div id="login-error" role="alert">${initialError ? `<div class="callout danger">${icon('alert')}<div>${esc(initialError)}</div></div>` : ''}</div>

        <form id="login-form" class="stack" novalidate>
          <div class="field">
            <label for="login-username">Username or Email</label>
            <input id="login-username" name="username" class="input" type="text" autocomplete="username" placeholder="alice.owner or admin@northwind.example" required autofocus>
          </div>
          <div class="field">
            <label for="login-password">Password</label>
            <input id="login-password" name="password" class="input" type="password" autocomplete="current-password" placeholder="Enter your password" required>
          </div>
          <button type="submit" id="login-submit" class="btn btn-primary" style="width:100%;margin-top:4px">${icon('lock')}<span>Sign in</span></button>
        </form>

        <div class="login-foot tiny muted">
          <div>${icon('shield')} <span>Accounts are provisioned by your tenant administrator or <code>python -m auth.cli</code>.</span></div>
        </div>
      </div>
    </div>`;
}

export function mountLoginView(container, onSuccess) {
  const form = container.querySelector('#login-form');
  const errBox = container.querySelector('#login-error');
  const userInput = container.querySelector('#login-username');
  const passInput = container.querySelector('#login-password');
  const submitBtn = container.querySelector('#login-submit');
  if (!form) return;

  const showErr = msg => {
    errBox.innerHTML = msg ? `<div class="callout danger">${icon('alert')}<div>${esc(msg)}</div></div>` : '';
  };

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const username = userInput.value.trim();
    const password = passInput.value;
    showErr('');

    if (!username || !password) {
      showErr('Enter both your username/email and password.');
      (username ? passInput : userInput).focus();
      return;
    }

    const done = busy(submitBtn);
    try {
      const data = await api.login(username, password);
      if (data?.user?.actor_type !== 'human') {
        await api.logout().catch(() => {});
        clearSession();
        showErr('Service accounts (role "agent") cannot open the web dashboard. Sign in with a human account.');
        return;
      }
      setSession(data.user, data.capabilities || data.user.capabilities);
      passInput.value = '';
      await onSuccess();
    } catch (err) {
      let msg = err.message || 'Sign in failed.';
      if (err.status === 429 && err.retryAfter) {
        msg = `${msg} Try again in ${err.retryAfter}s.`;
      }
      showErr(msg);
      passInput.select?.();
      passInput.focus();
    } finally {
      done();
    }
  });
}

export function renderSidebarUserHtml() {
  const u = getUser();
  if (!u) return '';
  const roles = (u.roles || []).map(r => `<span class="role-pill">${esc(formatRoleLabel(r))}</span>`).join('');
  return `
    <div class="user-card">
      <div class="user-card-top">
        <div class="user-avatar" aria-hidden="true">${esc(initialsFor(u.display_name || u.identity))}</div>
        <div class="user-meta">
          <div class="user-name truncate" title="${esc(u.display_name || u.identity)}">${esc(u.display_name || u.identity)}</div>
          <div class="user-identity truncate mono tiny muted" title="${esc(u.identity)}">${esc(u.identity)}</div>
        </div>
        <button type="button" class="btn btn-ghost btn-icon-only btn-sm" id="logout-btn" data-action="logout" aria-label="Sign out" title="Sign out">${icon('logout')}</button>
      </div>
      <div class="user-badges">
        ${roles}
        <span class="tenant-pill mono">${esc(u.tenant_id)}</span>
        ${tierBadge(u.clearance)}
      </div>
    </div>`;
}

