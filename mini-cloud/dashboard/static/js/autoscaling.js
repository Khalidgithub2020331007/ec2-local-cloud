/* autoscaling.js — Step 13: Auto Scaling Groups.
 * List, create, delete ASGs. View instances and scaling history.
 * Update scaling policy. Attach / detach load balancers. */

(function () {
  'use strict';

  // asg_id whose detail panel is currently expanded
  let expandedAsgId = null;
  // which tab is shown inside the expanded panel
  let expandedTab   = 'instances';  // 'instances' | 'history'

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function authHeaders() {
    return {
      'Authorization': 'Bearer ' + localStorage.getItem('mc_token'),
      'Content-Type':  'application/json',
    };
  }

  function escHtml(str) {
    return String(str ?? '')
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

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  function statusBadge(status) {
    const map = {
      active:   { color: '#15803d', bg: '#dcfce7' },
      paused:   { color: '#b45309', bg: '#fef3c7' },
      deleting: { color: '#b91c1c', bg: '#fee2e2' },
    };
    const s = map[status] || { color: '#6b7280', bg: '#f3f4f6' };
    return `<span style="display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;color:${s.color};background:${s.bg};">${escHtml(status)}</span>`;
  }

  function vmStatusBadge(status) {
    const color = status === 'running' ? '#15803d' : '#9ca3af';
    const bg    = status === 'running' ? '#dcfce7'  : '#f3f4f6';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;color:${color};background:${bg};">${escHtml(status)}</span>`;
  }

  function actionBadge(action) {
    if (action === 'scale_up' || action === 'ensure_min') {
      return `<span style="color:#15803d;font-weight:600;font-size:12px;">▲ ${action === 'ensure_min' ? 'ensure min' : 'scale up'}</span>`;
    }
    return `<span style="color:#b91c1c;font-weight:600;font-size:12px;">▼ scale down</span>`;
  }

  function renderInstanceRows(instances) {
    if (!instances.length) {
      return `<tr><td colspan="5" style="text-align:center;padding:14px;color:var(--gray-400);font-size:13px;">
        No instances yet — the monitor will launch the minimum count within 30 s
      </td></tr>`;
    }
    return instances.map(vm => `
      <tr style="background:#f9fafb;">
        <td style="padding-left:36px;font-size:13px;font-family:monospace;">${escHtml(vm.vm_id.slice(0, 8))}…</td>
        <td style="font-size:13px;">${escHtml(vm.name)}</td>
        <td>${vmStatusBadge(vm.status)}</td>
        <td style="font-size:13px;color:var(--gray-600);">${escHtml(vm.ip_address || '—')}</td>
        <td style="font-size:12px;color:var(--gray-500);">${fmtDate(vm.asg_launched_at)}</td>
      </tr>
    `).join('');
  }

  function renderHistoryRows(history) {
    if (!history.length) {
      return `<tr><td colspan="5" style="text-align:center;padding:14px;color:var(--gray-400);font-size:13px;">No scaling events yet</td></tr>`;
    }
    return history.map(ev => `
      <tr style="background:#f9fafb;">
        <td style="padding-left:36px;">${fmtDate(ev.created_at)}</td>
        <td>${actionBadge(ev.action)}</td>
        <td style="font-size:13px;">${escHtml(String(ev.instance_count))}</td>
        <td style="font-size:13px;">${escHtml(String(ev.avg_cpu))}%</td>
        <td style="font-size:12px;color:var(--gray-600);">${escHtml(ev.reason)}</td>
      </tr>
    `).join('');
  }

  function renderAsgList(asgs) {
    const listEl  = document.getElementById('asg-list');
    const emptyEl = document.getElementById('asg-empty');
    if (!listEl) return;

    if (!asgs.length) {
      if (emptyEl) emptyEl.style.display = 'block';
      listEl.innerHTML = '';
      return;
    }
    if (emptyEl) emptyEl.style.display = 'none';

    listEl.innerHTML = asgs.map(asg => {
      const isExpanded = expandedAsgId === asg.id;
      const tabInstActive = expandedTab === 'instances' ? 'border-bottom:2px solid var(--blue,#2563eb);color:var(--blue,#2563eb);' : '';
      const tabHistActive = expandedTab === 'history'   ? 'border-bottom:2px solid var(--blue,#2563eb);color:var(--blue,#2563eb);' : '';

      return `
        <div class="card" style="margin-bottom:16px;border-radius:var(--radius);border:1px solid var(--border);overflow:hidden;">
          <!-- Header row -->
          <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:#fff;gap:12px;flex-wrap:wrap;">
            <div>
              <div style="font-weight:600;font-size:14px;">${escHtml(asg.name)}</div>
              <div style="font-size:12px;color:var(--gray-400);margin-top:2px;">
                ${escHtml(asg.flavor)} &nbsp;·&nbsp;
                ${asg.instance_count} / ${asg.max_instances} instances &nbsp;·&nbsp;
                CPU ↑ ${asg.scale_up_threshold}% &nbsp;/&nbsp; ↓ ${asg.scale_down_threshold}% &nbsp;·&nbsp;
                cooldown ${asg.cooldown_seconds}s
                ${asg.lb_id ? '&nbsp;·&nbsp; <span style="color:#2563eb;">LB attached</span>' : ''}
              </div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-shrink:0;">
              ${statusBadge(asg.status)}
              <button class="btn btn-ghost btn-xs asg-expand-btn" data-asg-id="${escHtml(asg.id)}"
                      style="font-size:18px;line-height:1;padding:2px 10px;" title="Show details">
                ${isExpanded ? '▲' : '▼'}
              </button>
              <button class="btn btn-danger btn-xs asg-delete-btn"
                      data-asg-id="${escHtml(asg.id)}" data-asg-name="${escHtml(asg.name)}">
                Delete
              </button>
            </div>
          </div>

          <!-- Expanded detail panel -->
          <div id="asg-detail-${escHtml(asg.id)}" style="display:${isExpanded ? 'block' : 'none'};border-top:1px solid var(--border);">

            <!-- Sub-tabs -->
            <div style="display:flex;gap:0;border-bottom:1px solid var(--border);background:#fafafa;">
              <button class="asg-tab-btn" data-asg-id="${escHtml(asg.id)}" data-tab="instances"
                      style="padding:8px 16px;font-size:13px;font-weight:500;background:none;border:none;cursor:pointer;${tabInstActive}">
                Instances (${asg.instance_count})
              </button>
              <button class="asg-tab-btn" data-asg-id="${escHtml(asg.id)}" data-tab="history"
                      style="padding:8px 16px;font-size:13px;font-weight:500;background:none;border:none;cursor:pointer;${tabHistActive}">
                Scaling History
              </button>
              <button class="asg-tab-btn" data-asg-id="${escHtml(asg.id)}" data-tab="policy"
                      style="padding:8px 16px;font-size:13px;font-weight:500;background:none;border:none;cursor:pointer;">
                Edit Policy
              </button>
              <button class="asg-tab-btn" data-asg-id="${escHtml(asg.id)}" data-tab="lb"
                      style="padding:8px 16px;font-size:13px;font-weight:500;background:none;border:none;cursor:pointer;">
                Load Balancer
              </button>
            </div>

            <!-- Instances tab -->
            <div id="asg-tab-instances-${escHtml(asg.id)}" style="display:${expandedTab === 'instances' ? 'block' : 'none'};overflow-x:auto;">
              <table class="data-table" style="margin:0;">
                <thead>
                  <tr>
                    <th style="padding-left:36px;">VM ID</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>IP Address</th>
                    <th>Launched</th>
                  </tr>
                </thead>
                <tbody id="asg-instances-tbody-${escHtml(asg.id)}">
                  <tr><td colspan="5" style="text-align:center;padding:16px;color:var(--gray-400);">Loading…</td></tr>
                </tbody>
              </table>
            </div>

            <!-- History tab -->
            <div id="asg-tab-history-${escHtml(asg.id)}" style="display:${expandedTab === 'history' ? 'block' : 'none'};overflow-x:auto;">
              <table class="data-table" style="margin:0;">
                <thead>
                  <tr>
                    <th style="padding-left:36px;">Time</th>
                    <th>Action</th>
                    <th>Count After</th>
                    <th>Avg CPU</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody id="asg-history-tbody-${escHtml(asg.id)}">
                  <tr><td colspan="5" style="text-align:center;padding:16px;color:var(--gray-400);">Loading…</td></tr>
                </tbody>
              </table>
            </div>

            <!-- Policy tab -->
            <div id="asg-tab-policy-${escHtml(asg.id)}" style="display:${expandedTab === 'policy' ? 'block' : 'none'};padding:16px 20px;">
              <div id="asg-policy-error-${escHtml(asg.id)}" class="alert alert-error" style="display:none;margin-bottom:12px;"></div>
              <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;max-width:540px;">
                <div class="form-group" style="margin:0;">
                  <label style="font-size:12px;">Scale Up CPU %</label>
                  <input type="number" class="asg-policy-up" data-asg-id="${escHtml(asg.id)}"
                         value="${asg.scale_up_threshold}" min="1" max="100"
                         style="width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label style="font-size:12px;">Scale Down CPU %</label>
                  <input type="number" class="asg-policy-down" data-asg-id="${escHtml(asg.id)}"
                         value="${asg.scale_down_threshold}" min="1" max="100"
                         style="width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
                </div>
                <div class="form-group" style="margin:0;">
                  <label style="font-size:12px;">Cooldown (s)</label>
                  <input type="number" class="asg-policy-cd" data-asg-id="${escHtml(asg.id)}"
                         value="${asg.cooldown_seconds}" min="0"
                         style="width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
                </div>
              </div>
              <button class="btn btn-primary btn-sm asg-policy-save-btn" data-asg-id="${escHtml(asg.id)}"
                      style="margin-top:12px;">Save Policy</button>
            </div>

            <!-- LB tab -->
            <div id="asg-tab-lb-${escHtml(asg.id)}" style="display:${expandedTab === 'lb' ? 'block' : 'none'};padding:16px 20px;">
              <div id="asg-lb-error-${escHtml(asg.id)}" class="alert alert-error" style="display:none;margin-bottom:12px;"></div>
              ${asg.lb_id ? `
                <p style="font-size:13px;margin-bottom:12px;">
                  Attached to LB: <strong id="asg-lb-name-${escHtml(asg.id)}">${escHtml(asg.lb_id.slice(0,8))}…</strong>
                  &nbsp;·&nbsp; member port <strong>${escHtml(String(asg.lb_member_port))}</strong>
                </p>
                <button class="btn btn-danger btn-xs asg-detach-lb-btn" data-asg-id="${escHtml(asg.id)}">
                  Detach Load Balancer
                </button>
              ` : `
                <p style="font-size:13px;color:var(--gray-500);margin-bottom:12px;">
                  No load balancer attached. New ASG instances will not be added to any LB.
                </p>
                <div style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;">
                  <div class="form-group" style="margin:0;">
                    <label style="font-size:12px;">Load Balancer</label>
                    <select class="asg-lb-select" data-asg-id="${escHtml(asg.id)}"
                            style="padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
                      <option value="">Loading…</option>
                    </select>
                  </div>
                  <div class="form-group" style="margin:0;">
                    <label style="font-size:12px;">Member Port</label>
                    <input type="number" class="asg-lb-port" data-asg-id="${escHtml(asg.id)}"
                           placeholder="e.g. 80" min="1" max="65535"
                           style="width:100px;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;">
                  </div>
                  <button class="btn btn-primary btn-xs asg-attach-lb-btn" data-asg-id="${escHtml(asg.id)}">
                    Attach LB
                  </button>
                </div>
              `}
            </div>

          </div>
        </div>
      `;
    }).join('');

    // Wire expand toggle
    listEl.querySelectorAll('.asg-expand-btn').forEach(btn => {
      btn.addEventListener('click', () => toggleExpand(btn.dataset.asgId));
    });

    // Wire sub-tabs
    listEl.querySelectorAll('.asg-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.asgId, btn.dataset.tab));
    });

    // Wire delete
    listEl.querySelectorAll('.asg-delete-btn').forEach(btn => {
      btn.addEventListener('click', () => deleteAsg(btn.dataset.asgId, btn.dataset.asgName));
    });

    // Wire policy save
    listEl.querySelectorAll('.asg-policy-save-btn').forEach(btn => {
      btn.addEventListener('click', () => savePolicy(btn.dataset.asgId));
    });

    // Wire LB attach
    listEl.querySelectorAll('.asg-attach-lb-btn').forEach(btn => {
      btn.addEventListener('click', () => attachLb(btn.dataset.asgId));
    });

    // Wire LB detach
    listEl.querySelectorAll('.asg-detach-lb-btn').forEach(btn => {
      btn.addEventListener('click', () => detachLb(btn.dataset.asgId));
    });

    // Populate LB dropdowns for expanded panels showing the lb tab
    listEl.querySelectorAll('.asg-lb-select').forEach(sel => {
      populateLbDropdown(sel, sel.dataset.asgId);
    });

    if (expandedAsgId) loadDetailData(expandedAsgId);
  }

  // ── Load ──────────────────────────────────────────────────────────────────────

  async function loadAsgs() {
    const errEl = document.getElementById('asg-error');
    try {
      const { ok, data } = await apiCall('GET', '/api/v1/autoscaling');
      if (!ok) throw new Error(data.message || 'Failed to load auto scaling groups');
      renderAsgList(data.autoscaling_groups || []);
      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      if (errEl) { errEl.textContent = err.message; errEl.style.display = 'block'; }
    }
  }

  async function loadDetailData(asgId) {
    if (expandedTab === 'instances') {
      const tbody = document.getElementById(`asg-instances-tbody-${asgId}`);
      if (!tbody) return;
      const { ok, data } = await apiCall('GET', `/api/v1/autoscaling/${asgId}/instances`);
      tbody.innerHTML = renderInstanceRows(ok ? (data.instances || []) : []);
    } else if (expandedTab === 'history') {
      const tbody = document.getElementById(`asg-history-tbody-${asgId}`);
      if (!tbody) return;
      const { ok, data } = await apiCall('GET', `/api/v1/autoscaling/${asgId}/history`);
      tbody.innerHTML = renderHistoryRows(ok ? (data.history || []) : []);
    }
  }

  async function populateLbDropdown(selectEl, asgId) {
    const { ok, data } = await apiCall('GET', '/api/v1/load-balancers');
    if (!ok || !data.load_balancers || !data.load_balancers.length) {
      selectEl.innerHTML = '<option value="">No load balancers — create one first</option>';
      return;
    }
    selectEl.innerHTML = '<option value="">Select a load balancer…</option>' +
      data.load_balancers.map(lb =>
        `<option value="${escHtml(lb.id)}">${escHtml(lb.name)} (port ${lb.port})</option>`
      ).join('');
  }

  // ── Expand / Tab ──────────────────────────────────────────────────────────────

  function toggleExpand(asgId) {
    expandedAsgId = expandedAsgId === asgId ? null : asgId;
    expandedTab   = 'instances';
    loadAsgs();
  }

  function switchTab(asgId, tab) {
    expandedTab   = tab;
    expandedAsgId = asgId;
    loadAsgs();
  }

  // ── Create ASG ────────────────────────────────────────────────────────────────

  async function openCreateModal() {
    const modal = document.getElementById('asg-create-modal');
    const errEl = document.getElementById('asg-create-error');
    errEl.style.display = 'none';

    // Populate dropdowns
    await Promise.all([
      populateFlavorSelect('asg-flavor-select'),
      populateImageSelect('asg-image-select'),
      populateKeypairSelect('asg-keypair-select'),
    ]);

    modal.style.display = 'flex';
    document.getElementById('asg-name-input').focus();
  }

  async function populateFlavorSelect(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const { ok, data } = await apiCall('GET', '/api/v1/compute/flavors');
    if (!ok) return;
    sel.innerHTML = '<option value="">Select flavor…</option>' +
      (data.flavors || []).map(f =>
        `<option value="${escHtml(f.name)}">${escHtml(f.name)} — ${f.vcpus}vCPU / ${f.ram_mb}MB RAM / ${f.disk_gb}GB</option>`
      ).join('');
  }

  async function populateImageSelect(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const { ok, data } = await apiCall('GET', '/api/v1/images');
    if (!ok) return;
    sel.innerHTML = '<option value="">No image (blank disk)</option>' +
      (data.images || []).filter(i => i.status === 'available').map(i =>
        `<option value="${escHtml(i.id)}">${escHtml(i.name)}</option>`
      ).join('');
  }

  async function populateKeypairSelect(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const { ok, data } = await apiCall('GET', '/api/v1/keypairs');
    if (!ok) return;
    sel.innerHTML = '<option value="">No key pair</option>' +
      (data.keypairs || []).map(kp =>
        `<option value="${escHtml(kp.id)}">${escHtml(kp.name)}</option>`
      ).join('');
  }

  async function submitCreateAsg() {
    const errEl   = document.getElementById('asg-create-error');
    const btnText = document.getElementById('asg-create-btn-text');
    const spinner = document.getElementById('asg-create-spinner');

    const name     = document.getElementById('asg-name-input').value.trim();
    const flavor   = document.getElementById('asg-flavor-select').value;
    const image_id = document.getElementById('asg-image-select').value || null;
    const keypair_id = document.getElementById('asg-keypair-select').value || null;
    const minInst  = parseInt(document.getElementById('asg-min-input').value, 10) || 1;
    const maxInst  = parseInt(document.getElementById('asg-max-input').value, 10) || 5;
    const upThresh = parseFloat(document.getElementById('asg-up-threshold').value) || 70;
    const dnThresh = parseFloat(document.getElementById('asg-down-threshold').value) || 30;
    const cooldown = parseInt(document.getElementById('asg-cooldown').value, 10) || 120;

    if (!name)   { errEl.textContent = 'Name is required.';   errEl.style.display = 'block'; return; }
    if (!flavor) { errEl.textContent = 'Flavor is required.'; errEl.style.display = 'block'; return; }

    btnText.style.display = 'none';
    spinner.style.display = 'inline-block';

    const { ok, data } = await apiCall('POST', '/api/v1/autoscaling', {
      name, flavor, image_id, keypair_id,
      min_instances:        minInst,
      max_instances:        maxInst,
      scale_up_threshold:   upThresh,
      scale_down_threshold: dnThresh,
      cooldown_seconds:     cooldown,
    });

    btnText.style.display = 'inline';
    spinner.style.display = 'none';

    if (!ok) {
      errEl.textContent   = data.message || 'Failed to create auto scaling group';
      errEl.style.display = 'block';
      return;
    }

    closeCreateModal();
    showToast('Auto scaling group created — monitor will launch instances within 30 s', 'success');
    loadAsgs();
  }

  function closeCreateModal() {
    document.getElementById('asg-create-modal').style.display = 'none';
    document.getElementById('asg-create-error').style.display = 'none';
    ['asg-name-input', 'asg-min-input', 'asg-max-input', 'asg-up-threshold',
     'asg-down-threshold', 'asg-cooldown'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = el.defaultValue;
    });
  }

  // ── Delete ASG ────────────────────────────────────────────────────────────────

  async function deleteAsg(asgId, asgName) {
    if (typeof window.showConfirm === 'function') {
      const ok = await window.showConfirm(
        `Delete auto scaling group "${asgName}"? All managed instances will be terminated.`
      );
      if (!ok) return;
    }

    const { ok, data } = await apiCall('DELETE', `/api/v1/autoscaling/${asgId}`);
    if (!ok) { showToast(data.message || 'Delete failed', 'error'); return; }

    if (expandedAsgId === asgId) expandedAsgId = null;
    showToast('Auto scaling group deleted', 'success');
    loadAsgs();
  }

  // ── Save Policy ───────────────────────────────────────────────────────────────

  async function savePolicy(asgId) {
    const errEl  = document.getElementById(`asg-policy-error-${asgId}`);
    const upEl   = document.querySelector(`.asg-policy-up[data-asg-id="${asgId}"]`);
    const downEl = document.querySelector(`.asg-policy-down[data-asg-id="${asgId}"]`);
    const cdEl   = document.querySelector(`.asg-policy-cd[data-asg-id="${asgId}"]`);

    const { ok, data } = await apiCall('PUT', `/api/v1/autoscaling/${asgId}/policy`, {
      scale_up_threshold:   parseFloat(upEl.value),
      scale_down_threshold: parseFloat(downEl.value),
      cooldown_seconds:     parseInt(cdEl.value, 10),
    });

    if (!ok) {
      errEl.textContent   = data.message || 'Failed to update policy';
      errEl.style.display = 'block';
      return;
    }

    errEl.style.display = 'none';
    showToast('Scaling policy updated', 'success');
    loadAsgs();
  }

  // ── LB Attach / Detach ────────────────────────────────────────────────────────

  async function attachLb(asgId) {
    const errEl  = document.getElementById(`asg-lb-error-${asgId}`);
    const selEl  = document.querySelector(`.asg-lb-select[data-asg-id="${asgId}"]`);
    const portEl = document.querySelector(`.asg-lb-port[data-asg-id="${asgId}"]`);

    const lbId  = selEl ? selEl.value : '';
    const mPort = portEl ? parseInt(portEl.value, 10) : NaN;

    if (!lbId)      { errEl.textContent = 'Select a load balancer.';      errEl.style.display = 'block'; return; }
    if (isNaN(mPort)) { errEl.textContent = 'Member port is required.'; errEl.style.display = 'block'; return; }

    const { ok, data } = await apiCall('POST', `/api/v1/autoscaling/${asgId}/attach-lb/${lbId}`, {
      member_port: mPort,
    });

    if (!ok) {
      errEl.textContent   = data.message || 'Failed to attach load balancer';
      errEl.style.display = 'block';
      return;
    }

    errEl.style.display = 'none';
    showToast('Load balancer attached — new ASG instances will be added automatically', 'success');
    loadAsgs();
  }

  async function detachLb(asgId) {
    const { ok, data } = await apiCall('POST', `/api/v1/autoscaling/${asgId}/detach-lb`);
    if (!ok) { showToast(data.message || 'Detach failed', 'error'); return; }
    showToast('Load balancer detached', 'success');
    loadAsgs();
  }

  // ── Init ──────────────────────────────────────────────────────────────────────

  function setupAutoscaling() {
    const createBtn = document.getElementById('asg-create-btn');
    if (createBtn) createBtn.addEventListener('click', openCreateModal);

    const closeBtn  = document.getElementById('asg-modal-close');
    const cancelBtn = document.getElementById('asg-modal-cancel');
    if (closeBtn)  closeBtn.addEventListener('click',  closeCreateModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeCreateModal);

    const submitBtn = document.getElementById('asg-modal-submit');
    if (submitBtn) submitBtn.addEventListener('click', submitCreateAsg);
  }

  window.loadAutoscaling = loadAsgs;

  document.addEventListener('DOMContentLoaded', setupAutoscaling);
})();
