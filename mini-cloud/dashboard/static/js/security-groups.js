// ── Security Groups ────────────────────────────────────────────────────────────

// Holds the group ID currently open in the manage-rules modal
let _activeSgId = null;

function setupSecurityGroups() {
  document.getElementById('sg-create-btn').addEventListener('click', openSgCreateModal);
  document.getElementById('sg-create-close').addEventListener('click', closeSgCreateModal);
  document.getElementById('sg-create-cancel').addEventListener('click', closeSgCreateModal);
  document.getElementById('sg-create-submit').addEventListener('click', createSecurityGroup);
  document.getElementById('sg-name').addEventListener('keydown', e => { if (e.key === 'Enter') createSecurityGroup(); });

  document.getElementById('sg-manage-close').addEventListener('click', closeSgManageModal);
  document.getElementById('sg-manage-done').addEventListener('click', closeSgManageModal);
  document.getElementById('sg-rule-add-btn').addEventListener('click', addSgRule);
  document.getElementById('sg-rule-proto').addEventListener('change', sgProtoChange);
  document.getElementById('sg-attach-btn').addEventListener('click', attachSgToVm);
  document.getElementById('sg-detach-btn').addEventListener('click', detachSgFromVm);
}


// ── Load & render ──────────────────────────────────────────────────────────────

async function loadSecurityGroups() {
  const { ok, data } = await apiCall('GET', '/api/v1/security-groups');
  if (!ok) return;

  const groups    = data.security_groups;
  const emptyEl   = document.getElementById('sg-empty');
  const tableWrap = document.getElementById('sg-table-wrap');
  const tbody     = document.getElementById('sg-tbody');

  if (groups.length === 0) {
    emptyEl.style.display = 'block'; tableWrap.style.display = 'none'; return;
  }
  emptyEl.style.display = 'none'; tableWrap.style.display = 'block';
  tbody.innerHTML = groups.map(g => `
    <tr>
      <td><strong>${escHtml(g.name)}</strong></td>
      <td style="color:var(--gray-600);font-size:13px;">${escHtml(g.description || '—')}</td>
      <td><span class="badge badge-green">${g.rules ? g.rules.length : 0} rule${g.rules && g.rules.length === 1 ? '' : 's'}</span></td>
      <td style="font-size:12px;color:var(--gray-400);">${new Date(g.created_at).toLocaleDateString()}</td>
      <td style="display:flex;gap:6px;">
        <button class="btn btn-ghost btn-xs" onclick="openSgManageModal('${escHtml(g.id)}', '${escHtml(g.name)}')">Manage Rules</button>
        <button class="btn btn-danger btn-xs" onclick="deleteSecurityGroup('${escHtml(g.id)}', '${escHtml(g.name)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}


// ── Create / Delete Group ──────────────────────────────────────────────────────

function openSgCreateModal() {
  document.getElementById('sg-name').value = '';
  document.getElementById('sg-desc').value = '';
  document.getElementById('sg-create-error').style.display = 'none';
  document.getElementById('sg-create-modal').style.display = 'flex';
  document.getElementById('sg-name').focus();
}

function closeSgCreateModal() {
  document.getElementById('sg-create-modal').style.display = 'none';
}

async function createSecurityGroup() {
  const name    = document.getElementById('sg-name').value.trim();
  const desc    = document.getElementById('sg-desc').value.trim();
  const errorEl = document.getElementById('sg-create-error');
  errorEl.style.display = 'none';

  if (!name) { showSgCreateError('Name is required.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/security-groups', { name, description: desc });
  if (!ok) { showSgCreateError(data.message || 'Failed to create security group.'); return; }

  closeSgCreateModal();
  loadSecurityGroups();
}

function showSgCreateError(msg) {
  const el = document.getElementById('sg-create-error');
  el.textContent = msg; el.style.display = 'block';
}

async function deleteSecurityGroup(groupId, groupName) {
  if (!confirm(`Delete security group "${groupName}"? This cannot be undone.`)) return;
  const { ok, data } = await apiCall('DELETE', `/api/v1/security-groups/${groupId}`);
  if (!ok) { alert(data.message || 'Failed to delete security group.'); return; }
  loadSecurityGroups();
}


// ── Manage Rules Modal ─────────────────────────────────────────────────────────

async function openSgManageModal(groupId, groupName) {
  _activeSgId = groupId;
  document.getElementById('sg-manage-title').textContent = `Rules — ${groupName}`;
  document.getElementById('sg-rule-error').style.display = 'none';
  document.getElementById('sg-vm-error').style.display = 'none';

  // Reset add-rule form
  document.getElementById('sg-rule-dir').value = 'inbound';
  document.getElementById('sg-rule-proto').value = 'tcp';
  document.getElementById('sg-rule-port-min').value = '';
  document.getElementById('sg-rule-port-max').value = '';
  document.getElementById('sg-rule-cidr').value = '0.0.0.0/0';
  sgProtoChange();

  document.getElementById('sg-manage-modal').style.display = 'flex';
  await loadSgRules();
  await loadInstancesIntoSgSelect();
}

function closeSgManageModal() {
  document.getElementById('sg-manage-modal').style.display = 'none';
  _activeSgId = null;
  loadSecurityGroups(); // Refresh rule counts in the main table
}

async function loadSgRules() {
  if (!_activeSgId) return;
  const { ok, data } = await apiCall('GET', '/api/v1/security-groups');
  if (!ok) return;

  const group = (data.security_groups || []).find(g => g.id === _activeSgId);
  const rules = group ? (group.rules || []) : [];

  const emptyEl   = document.getElementById('sg-rules-empty');
  const tableWrap = document.getElementById('sg-rules-table-wrap');
  const tbody     = document.getElementById('sg-rules-tbody');

  if (rules.length === 0) {
    emptyEl.style.display = 'block'; tableWrap.style.display = 'none'; return;
  }
  emptyEl.style.display = 'none'; tableWrap.style.display = 'block';
  tbody.innerHTML = rules.map(r => {
    const ports = (r.protocol === 'tcp' || r.protocol === 'udp')
      ? (r.port_min === r.port_max ? `${r.port_min}` : `${r.port_min}–${r.port_max}`)
      : '—';
    const dirBadge = r.direction === 'inbound'
      ? '<span class="badge badge-green">inbound</span>'
      : '<span class="badge badge-red">outbound</span>';
    return `
      <tr>
        <td>${dirBadge}</td>
        <td><code>${escHtml(r.protocol.toUpperCase())}</code></td>
        <td style="font-size:13px;">${escHtml(ports)}</td>
        <td><code>${escHtml(r.cidr)}</code></td>
        <td><button class="btn btn-danger btn-xs" onclick="deleteSgRule('${escHtml(r.id)}')">Remove</button></td>
      </tr>
    `;
  }).join('');
}


// ── Add / Remove Rule ──────────────────────────────────────────────────────────

function sgProtoChange() {
  const proto      = document.getElementById('sg-rule-proto').value;
  const showPorts  = proto === 'tcp' || proto === 'udp';
  document.getElementById('sg-port-min-wrap').style.visibility = showPorts ? 'visible' : 'hidden';
  document.getElementById('sg-port-max-wrap').style.visibility = showPorts ? 'visible' : 'hidden';
}

async function addSgRule() {
  if (!_activeSgId) return;
  const errorEl  = document.getElementById('sg-rule-error');
  errorEl.style.display = 'none';

  const direction = document.getElementById('sg-rule-dir').value;
  const protocol  = document.getElementById('sg-rule-proto').value;
  const cidr      = document.getElementById('sg-rule-cidr').value.trim();
  const body      = { direction, protocol, cidr };

  if (protocol === 'tcp' || protocol === 'udp') {
    const portMin = parseInt(document.getElementById('sg-rule-port-min').value, 10);
    const portMax = parseInt(document.getElementById('sg-rule-port-max').value, 10);
    if (!portMin || !portMax) { showSgRuleError('Port min and port max are required for TCP/UDP.'); return; }
    body.port_min = portMin;
    body.port_max = portMax;
  }

  const { ok, data } = await apiCall('POST', `/api/v1/security-groups/${_activeSgId}/rules`, body);
  if (!ok) { showSgRuleError(data.message || 'Failed to add rule.'); return; }

  document.getElementById('sg-rule-port-min').value = '';
  document.getElementById('sg-rule-port-max').value = '';
  loadSgRules();
}

async function deleteSgRule(ruleId) {
  if (!_activeSgId) return;
  const { ok, data } = await apiCall('DELETE', `/api/v1/security-groups/${_activeSgId}/rules/${ruleId}`);
  if (!ok) { alert(data.message || 'Failed to remove rule.'); return; }
  loadSgRules();
}

function showSgRuleError(msg) {
  const el = document.getElementById('sg-rule-error');
  el.textContent = msg; el.style.display = 'block';
}


// ── Attach / Detach VM ─────────────────────────────────────────────────────────

async function loadInstancesIntoSgSelect() {
  const select = document.getElementById('sg-vm-select');
  select.innerHTML = '<option value="">Loading...</option>';

  const { ok, data } = await apiCall('GET', '/api/v1/compute/instances');
  if (!ok) { select.innerHTML = '<option value="">Could not load instances</option>'; return; }

  const instances = (data.instances || []).filter(i => i.status !== 'terminated');
  if (instances.length === 0) {
    select.innerHTML = '<option value="">No instances available</option>'; return;
  }
  select.innerHTML = instances.map(i =>
    `<option value="${escHtml(i.id)}">${escHtml(i.name)} (${escHtml(i.status)})</option>`
  ).join('');
}

async function attachSgToVm() {
  if (!_activeSgId) return;
  const vmId   = document.getElementById('sg-vm-select').value;
  const errEl  = document.getElementById('sg-vm-error');
  errEl.style.display = 'none';

  if (!vmId) { errEl.textContent = 'Select an instance first.'; errEl.style.display = 'block'; return; }

  const { ok, data } = await apiCall('POST', `/api/v1/security-groups/${_activeSgId}/attach/${vmId}`);
  if (!ok) { errEl.textContent = data.message || 'Failed to attach.'; errEl.style.display = 'block'; return; }

  errEl.style.display = 'none';
  alert(`Security group attached to VM successfully.\niptables chain updated — rules are now enforced.`);
}

async function detachSgFromVm() {
  if (!_activeSgId) return;
  const vmId  = document.getElementById('sg-vm-select').value;
  const errEl = document.getElementById('sg-vm-error');
  errEl.style.display = 'none';

  if (!vmId) { errEl.textContent = 'Select an instance first.'; errEl.style.display = 'block'; return; }

  const { ok, data } = await apiCall('POST', `/api/v1/security-groups/${_activeSgId}/detach/${vmId}`);
  if (!ok) { errEl.textContent = data.message || 'Failed to detach.'; errEl.style.display = 'block'; return; }

  errEl.style.display = 'none';
  alert('Security group detached. iptables chain rebuilt without these rules.');
}
