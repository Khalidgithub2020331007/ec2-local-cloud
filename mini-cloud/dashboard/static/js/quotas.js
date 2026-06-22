/* quotas.js — Step 11: AWS Service Quotas-style resource limits dashboard.
 * Shows progress bars per resource, color-coded by usage percentage.
 * Admin section lets admin override any user's limits inline. */

(function () {
  'use strict';

  // Human-readable labels and units for each resource type
  const RESOURCE_META = {
    instances:            { label: 'Instances',            unit: '' },
    vcpus:                { label: 'vCPUs',                unit: '' },
    ram_mb:               { label: 'RAM',                  unit: 'MB' },
    volumes:              { label: 'Volumes',              unit: '' },
    volume_gb:            { label: 'Volume Storage',       unit: 'GB' },
    floating_ips:         { label: 'Floating IPs',         unit: '' },
    security_groups:      { label: 'Security Groups',      unit: '' },
    security_group_rules: { label: 'SG Rules (total)',     unit: '' },
    key_pairs:            { label: 'Key Pairs',            unit: '' },
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  function authHeaders() {
    const token = localStorage.getItem('mc_token');
    return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
  }

  // Returns CSS class based on usage percentage — matches the 70/90 thresholds in the spec
  function barColorClass(pct) {
    if (pct >= 90) return 'quota-bar-red';
    if (pct >= 70) return 'quota-bar-orange';
    return 'quota-bar-green';
  }

  function fmtValue(value, unit) {
    if (!unit) return String(value);
    return value + ' ' + unit;
  }

  // ── My Quotas section ─────────────────────────────────────────────────────

  async function loadMyQuotas() {
    const container = document.getElementById('quota-bars-container');
    const errEl     = document.getElementById('quota-error');
    if (!container) return;

    container.innerHTML = '<p style="color:var(--gray-400);font-size:13px;">Loading...</p>';

    try {
      const resp = await fetch('/api/v1/quotas', { headers: authHeaders() });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();

      container.innerHTML = Object.entries(data).map(([key, q]) => {
        const meta = RESOURCE_META[key] || { label: key, unit: '' };
        const pct  = q.limit > 0 ? Math.min(100, Math.round(q.used / q.limit * 100)) : 0;
        const cls  = barColorClass(pct);

        return `
          <div class="quota-row">
            <div class="quota-row-header">
              <span class="quota-label">${meta.label}</span>
              <span class="quota-counts">
                <span class="quota-used">${fmtValue(q.used, meta.unit)}</span>
                <span class="quota-sep">/</span>
                <span class="quota-limit">${fmtValue(q.limit, meta.unit)}</span>
                <span class="quota-avail">&nbsp;·&nbsp;${fmtValue(q.available, meta.unit)} available</span>
              </span>
            </div>
            <div class="quota-bar-track">
              <div class="quota-bar-fill ${cls}" style="width:${pct}%"></div>
            </div>
            <div class="quota-pct">${pct}%</div>
          </div>
        `;
      }).join('');

      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      if (errEl) {
        errEl.textContent = 'Could not load quotas: ' + err.message;
        errEl.style.display = 'block';
      }
      container.innerHTML = '';
    }
  }

  // ── Admin section ─────────────────────────────────────────────────────────

  // We store the currently-editing user_id here so the save handler knows who to PATCH
  let editingUserId = null;

  async function loadAdminQuotas() {
    const wrap  = document.getElementById('quota-admin-wrap');
    const tbody = document.getElementById('quota-admin-tbody');
    if (!wrap || !tbody) return;

    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--gray-400);">Loading...</td></tr>';

    try {
      const resp = await fetch('/api/v1/quotas/users', { headers: authHeaders() });
      // 403 is expected for non-admins — hide the section silently
      if (resp.status === 403) { wrap.style.display = 'none'; return; }
      if (!resp.ok) throw new Error('HTTP ' + resp.status);

      const data  = await resp.json();
      const users = data.users || [];

      wrap.style.display = 'block';
      tbody.innerHTML = users.map(u => {
        const instQ = u.quotas['instances'] || {};
        const vcpuQ = u.quotas['vcpus']     || {};
        const ramQ  = u.quotas['ram_mb']    || {};
        const hasOverride = Object.keys(u.overrides || {}).length > 0;

        return `
          <tr data-user-id="${u.id}">
            <td>
              <strong>${escHtml(u.username)}</strong>
              <br><span class="row-hint">${escHtml(u.email)}</span>
            </td>
            <td>
              <span class="badge ${u.role === 'admin' ? 'badge-running' : 'badge-stopped'}">${u.role}</span>
            </td>
            <td style="font-size:12px;color:var(--gray-600);">
              Instances: ${instQ.used}/${instQ.limit} &nbsp;
              vCPUs: ${vcpuQ.used}/${vcpuQ.limit} &nbsp;
              RAM: ${ramQ.used}/${ramQ.limit} MB
              ${hasOverride ? '&nbsp;<span class="badge badge-running" style="font-size:10px;">custom</span>' : ''}
            </td>
            <td>
              <button class="btn btn-ghost btn-xs quota-edit-btn"
                      data-user-id="${u.id}"
                      data-username="${escHtml(u.username)}"
                      data-quotas='${JSON.stringify(u.quotas)}'
                      data-overrides='${JSON.stringify(u.overrides || {})}'>
                Edit Limits
              </button>
            </td>
          </tr>
        `;
      }).join('') || '<tr><td colspan="4" style="text-align:center;padding:20px;color:var(--gray-400);">No users found</td></tr>';

    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:16px;color:var(--red);">Error loading users: ${err.message}</td></tr>`;
    }
  }

  function openEditModal(userId, username, quotas, overrides) {
    editingUserId = userId;
    document.getElementById('quota-edit-username').textContent = username;

    const fieldsWrap = document.getElementById('quota-edit-fields');
    fieldsWrap.innerHTML = Object.entries(RESOURCE_META).map(([key, meta]) => {
      const q     = quotas[key] || { limit: 0, used: 0 };
      const isOvr = overrides.hasOwnProperty(key);
      return `
        <div class="form-group" style="margin-bottom:12px;">
          <label style="font-size:12px;font-weight:600;display:flex;justify-content:space-between;">
            <span>${meta.label}${meta.unit ? ' (' + meta.unit + ')' : ''}</span>
            <span style="font-weight:400;color:var(--gray-400);">Used: ${q.used}</span>
          </label>
          <div style="display:flex;gap:8px;align-items:center;">
            <input type="number" min="0"
                   id="quota-field-${key}"
                   value="${q.limit}"
                   style="flex:1;padding:8px 10px;border:1px solid ${isOvr ? 'var(--blue)' : 'var(--border)'};border-radius:var(--radius);font-size:13px;"
                   title="${isOvr ? 'Custom override active' : 'Using system default'}">
            ${isOvr ? `<button class="btn btn-ghost btn-xs quota-reset-btn" data-key="${key}" title="Remove override — revert to default">Reset</button>` : ''}
          </div>
        </div>
      `;
    }).join('');

    // Wire reset buttons inside the modal to mark the field as "to be removed"
    fieldsWrap.querySelectorAll('.quota-reset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.key;
        const input = document.getElementById('quota-field-' + key);
        // Use a data attribute to signal null (remove override) on save
        input.dataset.reset = 'true';
        input.disabled = true;
        input.style.opacity = '0.4';
        btn.textContent = 'Resetting...';
        btn.disabled = true;
      });
    });

    document.getElementById('quota-edit-modal').style.display = 'flex';
    document.getElementById('quota-edit-error').style.display = 'none';
  }

  async function saveQuotaEdit() {
    if (!editingUserId) return;

    const errEl   = document.getElementById('quota-edit-error');
    const saveBtn = document.getElementById('quota-edit-save');
    saveBtn.disabled = true;

    const payload = {};
    Object.keys(RESOURCE_META).forEach(key => {
      const input = document.getElementById('quota-field-' + key);
      if (!input) return;
      if (input.dataset.reset === 'true') {
        payload[key] = null;  // null tells the API to remove the override
      } else {
        payload[key] = parseInt(input.value, 10);
      }
    });

    try {
      const resp = await fetch(`/api/v1/quotas/${editingUserId}`, {
        method:  'PUT',
        headers: authHeaders(),
        body:    JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.message || 'HTTP ' + resp.status);

      document.getElementById('quota-edit-modal').style.display = 'none';
      showToast('Quota limits saved', 'success');
      loadAdminQuotas();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    } finally {
      saveBtn.disabled = false;
    }
  }

  // ── Defaults editor ───────────────────────────────────────────────────────

  async function loadDefaultsEditor() {
    const wrap = document.getElementById('quota-defaults-wrap');
    if (!wrap) return;

    try {
      const resp = await fetch('/api/v1/quotas/defaults', { headers: authHeaders() });
      if (resp.status === 403) { wrap.style.display = 'none'; return; }
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();

      wrap.style.display = 'block';
      const fieldsWrap = document.getElementById('quota-defaults-fields');
      fieldsWrap.innerHTML = Object.entries(RESOURCE_META).map(([key, meta]) => `
        <div class="form-group" style="margin-bottom:12px;">
          <label style="font-size:12px;font-weight:600;">${meta.label}${meta.unit ? ' (' + meta.unit + ')' : ''}</label>
          <input type="number" min="0" id="quota-default-${key}"
                 value="${data.defaults[key] ?? ''}"
                 style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
        </div>
      `).join('');
    } catch (_) {
      wrap.style.display = 'none';
    }
  }

  async function saveDefaults() {
    const errEl   = document.getElementById('quota-defaults-error');
    const saveBtn = document.getElementById('quota-defaults-save');
    saveBtn.disabled = true;

    const payload = {};
    Object.keys(RESOURCE_META).forEach(key => {
      const el = document.getElementById('quota-default-' + key);
      if (el) payload[key] = parseInt(el.value, 10);
    });

    try {
      const resp = await fetch('/api/v1/quotas/defaults', {
        method:  'PUT',
        headers: authHeaders(),
        body:    JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.message || 'HTTP ' + resp.status);
      showToast('Default limits saved', 'success');
      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      if (errEl) { errEl.textContent = err.message; errEl.style.display = 'block'; }
    } finally {
      saveBtn.disabled = false;
    }
  }

  // ── Utility ───────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // showToast is defined in auth.js and available globally on this page
  function showToast(msg, type) {
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
    }
  }

  // ── Init ─────────────────────────────────────────────────────────────────

  function setupQuotas() {
    // Edit modal close
    const closeBtn = document.getElementById('quota-edit-close');
    if (closeBtn) closeBtn.addEventListener('click', () => {
      document.getElementById('quota-edit-modal').style.display = 'none';
    });

    // Edit modal save
    const saveBtn = document.getElementById('quota-edit-save');
    if (saveBtn) saveBtn.addEventListener('click', saveQuotaEdit);

    // Cancel button in edit modal
    const cancelBtn = document.getElementById('quota-edit-cancel');
    if (cancelBtn) cancelBtn.addEventListener('click', () => {
      document.getElementById('quota-edit-modal').style.display = 'none';
    });

    // Edit button clicks on the user table (event delegation)
    const adminTbody = document.getElementById('quota-admin-tbody');
    if (adminTbody) {
      adminTbody.addEventListener('click', e => {
        const btn = e.target.closest('.quota-edit-btn');
        if (!btn) return;
        openEditModal(
          btn.dataset.userId,
          btn.dataset.username,
          JSON.parse(btn.dataset.quotas),
          JSON.parse(btn.dataset.overrides),
        );
      });
    }

    // Save system defaults
    const defSaveBtn = document.getElementById('quota-defaults-save');
    if (defSaveBtn) defSaveBtn.addEventListener('click', saveDefaults);
  }

  // Called by dashboard.js when the quotas section becomes visible
  window.loadQuotas = function () {
    loadMyQuotas();
    loadAdminQuotas();
    loadDefaultsEditor();
  };

  document.addEventListener('DOMContentLoaded', setupQuotas);
})();
