/* loadbalancers.js — Step 12: HAProxy-backed load balancers.
 * Shows all LBs, expandable member rows with live health badges,
 * and forms to create LBs and add/remove member VMs. */

(function () {
  'use strict';

  // lb_id whose member row is currently expanded (one at a time)
  let expandedLbId = null;
  // lb_id that the Add Member modal is currently targeting
  let targetLbId   = null;

  // ── Helpers ─────────────────────────────────────────────────────────────────

  function authHeaders() {
    return {
      'Authorization': 'Bearer ' + localStorage.getItem('mc_token'),
      'Content-Type':  'application/json',
    };
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function showToast(msg, type) {
    if (typeof window.showToast === 'function') window.showToast(msg, type);
  }

  async function apiCall(method, url, body) {
    const opts = { method, headers: authHeaders() };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fetch(url, opts);
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok, status: resp.status, data };
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  // Renders a health badge: green for healthy, red for anything else
  function healthBadge(status) {
    const isHealthy = status === 'healthy';
    const color     = isHealthy ? '#16a34a' : '#dc2626';
    const bg        = isHealthy ? '#dcfce7' : '#fee2e2';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;color:${color};background:${bg};">${escHtml(status)}</span>`;
  }

  function renderMemberRows(lb_id, members, health) {
    if (!members.length) {
      return `<tr><td colspan="5" style="text-align:center;padding:12px;color:var(--gray-400);font-size:13px;">No members yet — click <strong>Add Member</strong> to add a VM</td></tr>`;
    }
    return members.map(m => {
      const h = health[m.vm_id] || {};
      return `
        <tr style="background:#f9fafb;">
          <td style="padding-left:40px;font-size:13px;color:var(--gray-600);">${escHtml(m.vm_id.slice(0, 8))}…</td>
          <td style="font-size:13px;">${escHtml(m.vm_private_ip)}</td>
          <td style="font-size:13px;">${escHtml(String(m.member_port))}</td>
          <td>${healthBadge(h.status || 'unknown')}</td>
          <td style="font-size:12px;color:var(--gray-500);">${h.requests_served !== undefined ? h.requests_served : '—'}</td>
          <td>
            <button class="btn btn-danger btn-xs lb-remove-member-btn"
                    data-lb-id="${escHtml(lb_id)}"
                    data-vm-id="${escHtml(m.vm_id)}">
              Remove
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  function renderLbList(lbs) {
    const listEl = document.getElementById('lb-list');
    const emptyEl = document.getElementById('lb-empty');
    if (!listEl) return;

    if (!lbs.length) {
      emptyEl.style.display = 'block';
      listEl.innerHTML = '';
      return;
    }
    emptyEl.style.display = 'none';

    listEl.innerHTML = lbs.map(lb => `
      <div class="card" style="margin-bottom:16px;border-radius:var(--radius);border:1px solid var(--border);overflow:hidden;">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:#fff;">
          <div style="display:flex;align-items:center;gap:16px;">
            <div>
              <div style="font-weight:600;font-size:14px;">${escHtml(lb.name)}</div>
              <div style="font-size:12px;color:var(--gray-400);">Port ${lb.port} &nbsp;·&nbsp; ${lb.algorithm} &nbsp;·&nbsp; ${lb.member_count} member${lb.member_count !== 1 ? 's' : ''}</div>
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span class="badge badge-running" style="font-size:11px;">${escHtml(lb.status)}</span>
            <button class="btn btn-ghost btn-xs lb-add-member-btn" data-lb-id="${escHtml(lb.id)}">+ Add Member</button>
            <button class="btn btn-ghost btn-xs lb-expand-btn" data-lb-id="${escHtml(lb.id)}" style="font-size:18px;line-height:1;padding:2px 10px;" title="Show members">
              ${expandedLbId === lb.id ? '▲' : '▼'}
            </button>
            <button class="btn btn-danger btn-xs lb-delete-btn" data-lb-id="${escHtml(lb.id)}" data-lb-name="${escHtml(lb.name)}">Delete</button>
          </div>
        </div>

        <!-- Expanded members sub-table — hidden until user clicks the toggle -->
        <div id="lb-members-${escHtml(lb.id)}" style="display:${expandedLbId === lb.id ? 'block' : 'none'};border-top:1px solid var(--border);">
          <div style="overflow-x:auto;">
            <table class="data-table" style="margin:0;">
              <thead>
                <tr>
                  <th style="padding-left:40px;">VM ID</th>
                  <th>Private IP</th>
                  <th>Port</th>
                  <th>Health</th>
                  <th>Requests Served</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="lb-members-tbody-${escHtml(lb.id)}">
                <tr><td colspan="6" style="text-align:center;padding:16px;color:var(--gray-400);">Loading…</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `).join('');

    // Wire expand toggles
    listEl.querySelectorAll('.lb-expand-btn').forEach(btn => {
      btn.addEventListener('click', () => toggleExpand(btn.dataset.lbId));
    });

    // Wire Add Member buttons
    listEl.querySelectorAll('.lb-add-member-btn').forEach(btn => {
      btn.addEventListener('click', () => openAddMemberModal(btn.dataset.lbId));
    });

    // Wire Delete buttons
    listEl.querySelectorAll('.lb-delete-btn').forEach(btn => {
      btn.addEventListener('click', () => deleteLb(btn.dataset.lbId, btn.dataset.lbName));
    });

    // Wire Remove Member buttons (event delegation — rows are rebuilt on expand)
    listEl.addEventListener('click', e => {
      const btn = e.target.closest('.lb-remove-member-btn');
      if (btn) removeMember(btn.dataset.lbId, btn.dataset.vmId);
    });

    // If a section was expanded before re-render, load its member data
    if (expandedLbId) loadMemberRows(expandedLbId);
  }

  // ── Load ─────────────────────────────────────────────────────────────────────

  async function loadLbs() {
    const errEl = document.getElementById('lb-error');
    try {
      const { ok, data } = await apiCall('GET', '/api/v1/load-balancers');
      if (!ok) throw new Error(data.message || 'Failed to load load balancers');
      renderLbList(data.load_balancers || []);
      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      if (errEl) { errEl.textContent = err.message; errEl.style.display = 'block'; }
    }
  }

  async function loadMemberRows(lb_id) {
    const tbody = document.getElementById(`lb-members-tbody-${lb_id}`);
    if (!tbody) return;

    // Fetch member list and live health in parallel — health can fail gracefully
    const [memberResp, statusResp] = await Promise.all([
      apiCall('GET', `/api/v1/load-balancers/${lb_id}/members`),
      apiCall('GET', `/api/v1/load-balancers/${lb_id}/status`),
    ]);

    const members = memberResp.ok ? (memberResp.data.members || []) : [];
    // health is a map of vm_id → { status, requests_served } derived from the status response
    const health  = {};
    if (statusResp.ok) {
      (statusResp.data.members || []).forEach(m => { health[m.vm_id] = m; });
    }

    tbody.innerHTML = renderMemberRows(lb_id, members, health);
  }

  // ── Expand/collapse ──────────────────────────────────────────────────────────

  function toggleExpand(lb_id) {
    if (expandedLbId === lb_id) {
      expandedLbId = null;
    } else {
      expandedLbId = lb_id;
    }
    // Re-render the full list so the toggle arrow and visibility update
    loadLbs();
  }

  // ── Create LB ────────────────────────────────────────────────────────────────

  async function createLb() {
    const name    = document.getElementById('lb-name-input').value.trim();
    const port    = parseInt(document.getElementById('lb-port-input').value, 10);
    const errEl   = document.getElementById('lb-create-error');
    const btnText = document.getElementById('lb-form-btn-text');
    const spinner = document.getElementById('lb-form-spinner');

    if (!name) { errEl.textContent = 'Name is required.'; errEl.style.display = 'block'; return; }
    if (!port)  { errEl.textContent = 'Port is required.'; errEl.style.display = 'block'; return; }

    btnText.style.display = 'none';
    spinner.style.display = 'inline-block';

    const { ok, data } = await apiCall('POST', '/api/v1/load-balancers', { name, port });

    btnText.style.display = 'inline';
    spinner.style.display = 'none';

    if (!ok) {
      errEl.textContent = data.message || 'Failed to create load balancer';
      errEl.style.display = 'block';
      return;
    }

    document.getElementById('lb-create-form').style.display = 'none';
    document.getElementById('lb-name-input').value = '';
    document.getElementById('lb-port-input').value = '';
    errEl.style.display = 'none';
    showToast('Load balancer created', 'success');
    loadLbs();
  }

  // ── Delete LB ────────────────────────────────────────────────────────────────

  async function deleteLb(lb_id, lb_name) {
    if (typeof window.showConfirm === 'function') {
      const ok = await window.showConfirm(`Delete load balancer "${lb_name}"? All members will be removed and HAProxy will stop listening on that port.`);
      if (!ok) return;
    }

    const { ok, data } = await apiCall('DELETE', `/api/v1/load-balancers/${lb_id}`);
    if (!ok) { showToast(data.message || 'Delete failed', 'error'); return; }

    if (expandedLbId === lb_id) expandedLbId = null;
    showToast('Load balancer deleted', 'success');
    loadLbs();
  }

  // ── Add Member ───────────────────────────────────────────────────────────────

  async function openAddMemberModal(lb_id) {
    targetLbId = lb_id;
    const select = document.getElementById('lb-member-vm-select');
    const errEl  = document.getElementById('lb-member-error');
    errEl.style.display = 'none';
    select.innerHTML = '<option value="">Loading instances...</option>';
    document.getElementById('lb-member-port-input').value = '';
    document.getElementById('lb-member-modal').style.display = 'flex';

    // Populate the VM dropdown with running instances that have a private IP
    const { ok, data } = await apiCall('GET', '/api/v1/compute/instances');
    if (!ok) {
      select.innerHTML = '<option value="">Failed to load instances</option>';
      return;
    }
    const running = (data.instances || []).filter(i => i.status === 'running' && i.ip_address);
    if (!running.length) {
      select.innerHTML = '<option value="">No running VMs with a private IP</option>';
      return;
    }
    select.innerHTML = '<option value="">Select a VM...</option>' +
      running.map(i => `<option value="${escHtml(i.id)}" data-ip="${escHtml(i.ip_address)}">${escHtml(i.name)} — ${escHtml(i.ip_address)}</option>`).join('');
  }

  async function submitAddMember() {
    const select    = document.getElementById('lb-member-vm-select');
    const portInput = document.getElementById('lb-member-port-input');
    const errEl     = document.getElementById('lb-member-error');
    const vm_id     = select.value;
    const option    = select.selectedOptions[0];
    const ip        = option ? option.dataset.ip : '';
    const port      = parseInt(portInput.value, 10);

    if (!vm_id || !ip) { errEl.textContent = 'Select a VM.'; errEl.style.display = 'block'; return; }
    if (!port)         { errEl.textContent = 'Backend port is required.'; errEl.style.display = 'block'; return; }

    const { ok, data } = await apiCall('POST', `/api/v1/load-balancers/${targetLbId}/members`, {
      vm_id, vm_private_ip: ip, member_port: port,
    });

    if (!ok) {
      errEl.textContent = data.message || 'Failed to add member';
      errEl.style.display = 'block';
      return;
    }

    document.getElementById('lb-member-modal').style.display = 'none';
    showToast('Member added', 'success');
    // Expand the LB row so the user sees the new member immediately
    expandedLbId = targetLbId;
    loadLbs();
  }

  // ── Remove Member ─────────────────────────────────────────────────────────────

  async function removeMember(lb_id, vm_id) {
    if (typeof window.showConfirm === 'function') {
      const ok = await window.showConfirm('Remove this VM from the load balancer?');
      if (!ok) return;
    }

    const { ok, data } = await apiCall('DELETE', `/api/v1/load-balancers/${lb_id}/members/${vm_id}`);
    if (!ok) { showToast(data.message || 'Remove failed', 'error'); return; }

    showToast('Member removed', 'success');
    expandedLbId = lb_id;  // Keep the row expanded so the user sees the updated list
    loadLbs();
  }

  // ── Init ──────────────────────────────────────────────────────────────────────

  function setupLoadBalancers() {
    const createBtn = document.getElementById('lb-create-btn');
    if (createBtn) createBtn.addEventListener('click', () => {
      document.getElementById('lb-create-error').style.display = 'none';
      document.getElementById('lb-create-form').style.display  = 'flex';
      document.getElementById('lb-name-input').focus();
    });

    const closeBtn = document.getElementById('lb-form-close');
    if (closeBtn) closeBtn.addEventListener('click', () => {
      document.getElementById('lb-create-form').style.display = 'none';
    });

    const cancelBtn = document.getElementById('lb-form-cancel');
    if (cancelBtn) cancelBtn.addEventListener('click', () => {
      document.getElementById('lb-create-form').style.display = 'none';
    });

    const submitBtn = document.getElementById('lb-form-submit');
    if (submitBtn) submitBtn.addEventListener('click', createLb);

    // Add Member modal
    const memberClose  = document.getElementById('lb-member-close');
    const memberCancel = document.getElementById('lb-member-cancel');
    const memberSubmit = document.getElementById('lb-member-submit');
    if (memberClose)  memberClose.addEventListener('click',  () => { document.getElementById('lb-member-modal').style.display = 'none'; });
    if (memberCancel) memberCancel.addEventListener('click', () => { document.getElementById('lb-member-modal').style.display = 'none'; });
    if (memberSubmit) memberSubmit.addEventListener('click', submitAddMember);
  }

  // Called by dashboard.js whenever the Load Balancers section becomes visible
  window.loadLoadBalancers = loadLbs;

  document.addEventListener('DOMContentLoaded', setupLoadBalancers);
})();
