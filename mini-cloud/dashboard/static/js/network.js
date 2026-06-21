// ── Networks ──────────────────────────────────────────────────────────────────

function setupNetworks() {
  loadNetworks();

  document.getElementById('net-create-btn').addEventListener('click', () => {
    document.getElementById('net-modal').style.display = 'flex';
    document.getElementById('net-name').focus();
    document.getElementById('net-modal-error').style.display = 'none';
  });

  document.getElementById('net-modal-close').addEventListener('click', closeNetModal);
  document.getElementById('net-modal-cancel').addEventListener('click', closeNetModal);
  document.getElementById('net-modal-submit').addEventListener('click', createNetwork);
}

function closeNetModal() {
  document.getElementById('net-modal').style.display = 'none';
  document.getElementById('net-name').value = '';
  document.getElementById('net-cidr').value = '';
}

async function loadNetworks() {
  const { ok, data } = await apiCall('GET', '/api/v1/network/networks');
  if (!ok) return;

  const nets  = data.networks;
  const empty = document.getElementById('networks-empty');
  const table = document.getElementById('networks-table-wrap');
  const tbody = document.getElementById('networks-tbody');

  // Also update overview stat card
  const statEl = document.getElementById('stat-networks');
  if (statEl) statEl.textContent = nets.length;

  if (nets.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'block';
  tbody.innerHTML = nets.map(n => `
    <tr>
      <td>${escHtml(n.name)}</td>
      <td><code>${escHtml(n.bridge_name)}</code></td>
      <td><code>${escHtml(n.cidr)}</code></td>
      <td><code>${escHtml(n.gateway)}</code></td>
      <td><span class="badge badge-green">${escHtml(n.status)}</span></td>
      <td>${new Date(n.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-danger btn-xs" onclick="deleteNetwork('${escHtml(n.id)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function createNetwork() {
  const name = document.getElementById('net-name').value.trim().toLowerCase();
  const cidr = document.getElementById('net-cidr').value.trim();
  const errEl = document.getElementById('net-modal-error');

  if (!name || !cidr) {
    errEl.textContent = 'Name and CIDR are required.';
    errEl.style.display = 'block'; return;
  }

  errEl.style.display = 'none';
  const { ok, data } = await apiCall('POST', '/api/v1/network/networks', { name, cidr });
  if (!ok) {
    errEl.textContent = data.message || 'Failed to create network.';
    errEl.style.display = 'block'; return;
  }

  closeNetModal();
  loadNetworks();
}

async function deleteNetwork(networkId) {
  if (!confirm('Delete this network? The bridge and DHCP server will be removed.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/network/networks/' + networkId);
  if (!ok) { alert(data.message || 'Failed to delete network.'); return; }
  loadNetworks();
  loadRouters(); // router list may change
}


// ── Routers ───────────────────────────────────────────────────────────────────

function setupRouters() {
  loadRouters();

  document.getElementById('router-create-btn').addEventListener('click', async () => {
    await _populateNetworkDropdown('router-network-select');
    document.getElementById('router-modal').style.display = 'flex';
    document.getElementById('router-name').focus();
    document.getElementById('router-modal-error').style.display = 'none';
  });

  document.getElementById('router-modal-close').addEventListener('click', closeRouterModal);
  document.getElementById('router-modal-cancel').addEventListener('click', closeRouterModal);
  document.getElementById('router-modal-submit').addEventListener('click', createRouter);
}

function closeRouterModal() {
  document.getElementById('router-modal').style.display = 'none';
  document.getElementById('router-name').value = '';
}

async function loadRouters() {
  const { ok, data } = await apiCall('GET', '/api/v1/network/routers');
  if (!ok) return;

  const routers = data.routers;
  const empty   = document.getElementById('routers-empty');
  const table   = document.getElementById('routers-table-wrap');
  const tbody   = document.getElementById('routers-tbody');

  if (routers.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'block';
  tbody.innerHTML = routers.map(r => `
    <tr>
      <td>${escHtml(r.name)}</td>
      <td>${escHtml(r.network_name)} <span class="row-hint">${escHtml(r.network_cidr)}</span></td>
      <td><code>${escHtml(r.ext_iface)}</code></td>
      <td><span class="badge badge-green">${escHtml(r.status)}</span></td>
      <td>${new Date(r.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-danger btn-xs" onclick="deleteRouter('${escHtml(r.id)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function createRouter() {
  const name      = document.getElementById('router-name').value.trim().toLowerCase();
  const networkId = document.getElementById('router-network-select').value;
  const errEl     = document.getElementById('router-modal-error');

  if (!name || !networkId) {
    errEl.textContent = 'Name and network are required.';
    errEl.style.display = 'block'; return;
  }

  errEl.style.display = 'none';
  const { ok, data } = await apiCall('POST', '/api/v1/network/routers',
    { name, network_id: networkId });
  if (!ok) {
    errEl.textContent = data.message || 'Failed to create router.';
    errEl.style.display = 'block'; return;
  }

  closeRouterModal();
  loadRouters();
}

async function deleteRouter(routerId) {
  if (!confirm('Delete this router? NAT rules will be removed.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/network/routers/' + routerId);
  if (!ok) { alert(data.message || 'Failed to delete router.'); return; }
  loadRouters();
}


// ── Floating IPs ──────────────────────────────────────────────────────────────

function setupFloatingIps() {
  loadFloatingIps();

  document.getElementById('fip-allocate-btn').addEventListener('click', allocateFloatingIp);
}

async function loadFloatingIps() {
  const { ok, data } = await apiCall('GET', '/api/v1/network/floating-ips');
  if (!ok) return;

  const fips  = data.floating_ips;
  const empty = document.getElementById('fips-empty');
  const table = document.getElementById('fips-table-wrap');
  const tbody = document.getElementById('fips-tbody');

  const statEl = document.getElementById('stat-fips');
  if (statEl) statEl.textContent = fips.length;

  if (fips.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'block';
  tbody.innerHTML = fips.map(f => `
    <tr>
      <td><code>${escHtml(f.ip_address)}</code></td>
      <td>${f.instance_name ? escHtml(f.instance_name) : '<span class="row-hint">—</span>'}</td>
      <td>${f.private_ip ? '<code>' + escHtml(f.private_ip) + '</code>' : '<span class="row-hint">—</span>'}</td>
      <td><span class="badge ${f.status === 'associated' ? 'badge-green' : 'badge-stopped'}">${escHtml(f.status)}</span></td>
      <td class="action-group">
        ${f.status === 'allocated'
          ? `<button class="btn btn-primary btn-xs" onclick="openAssociateModal('${escHtml(f.id)}')">Associate</button>`
          : `<button class="btn btn-ghost btn-xs" onclick="disassociateFip('${escHtml(f.id)}')">Disassociate</button>`
        }
        <button class="btn btn-danger btn-xs"
          onclick="releaseFip('${escHtml(f.id)}')"
          ${f.status === 'associated' ? 'disabled title="Disassociate first"' : ''}>Release</button>
      </td>
    </tr>
  `).join('');
}

async function allocateFloatingIp() {
  const { ok, data } = await apiCall('POST', '/api/v1/network/floating-ips', {});
  if (!ok) { alert(data.message || 'Failed to allocate IP.'); return; }
  loadFloatingIps();
}

// Associate modal — inline dropdown of running instances
let _pendingFipId = null;
async function openAssociateModal(fipId) {
  _pendingFipId = fipId;
  await _populateInstanceDropdown('fip-instance-select');
  document.getElementById('fip-associate-modal').style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', () => {
  const closeBtn = document.getElementById('fip-modal-close');
  if (closeBtn) closeBtn.addEventListener('click', () => {
    document.getElementById('fip-associate-modal').style.display = 'none';
  });
  const cancelBtn = document.getElementById('fip-modal-cancel');
  if (cancelBtn) cancelBtn.addEventListener('click', () => {
    document.getElementById('fip-associate-modal').style.display = 'none';
  });
  const submitBtn = document.getElementById('fip-modal-submit');
  if (submitBtn) submitBtn.addEventListener('click', doAssociate);
});

async function doAssociate() {
  const instanceId = document.getElementById('fip-instance-select').value;
  if (!instanceId) { alert('Select an instance.'); return; }

  const { ok, data } = await apiCall('POST',
    `/api/v1/network/floating-ips/${_pendingFipId}/associate`,
    { instance_id: instanceId });

  if (!ok) { alert(data.message || 'Failed to associate.'); return; }
  document.getElementById('fip-associate-modal').style.display = 'none';
  loadFloatingIps();
}

async function disassociateFip(fipId) {
  if (!confirm('Disassociate this floating IP?')) return;
  const { ok, data } = await apiCall('POST',
    `/api/v1/network/floating-ips/${fipId}/disassociate`, {});
  if (!ok) { alert(data.message || 'Failed.'); return; }
  loadFloatingIps();
}

async function releaseFip(fipId) {
  if (!confirm('Release this floating IP? It will be returned to the pool.')) return;
  const { ok, data } = await apiCall('DELETE',
    `/api/v1/network/floating-ips/${fipId}`);
  if (!ok) { alert(data.message || 'Failed.'); return; }
  loadFloatingIps();
}


// ── Network Interfaces ────────────────────────────────────────────────────────

function setupNetworkInterfaces() {
  loadNetworkInterfaces();
  document.getElementById('nics-refresh-btn').addEventListener('click', loadNetworkInterfaces);
}

async function loadNetworkInterfaces() {
  const { ok, data } = await apiCall('GET', '/api/v1/network/interfaces');
  if (!ok) return;

  const ifaces = data.interfaces;
  const empty  = document.getElementById('nics-empty');
  const table  = document.getElementById('nics-table-wrap');
  const tbody  = document.getElementById('nics-tbody');

  if (ifaces.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'block';
  tbody.innerHTML = ifaces.map(n => `
    <tr>
      <td>${escHtml(n.instance_name)}</td>
      <td><code>${escHtml(n.mac)}</code></td>
      <td>${escHtml(n.network)}</td>
      <td>${n.ip ? '<code>' + escHtml(n.ip) + '</code>' : '<span class="row-hint">—</span>'}</td>
    </tr>
  `).join('');
}


// ── Shared helpers ────────────────────────────────────────────────────────────

async function _populateNetworkDropdown(selectId) {
  const sel = document.getElementById(selectId);
  sel.innerHTML = '<option value="">Loading...</option>';
  const { ok, data } = await apiCall('GET', '/api/v1/network/networks');
  if (!ok) { sel.innerHTML = '<option value="">Failed to load</option>'; return; }
  if (data.networks.length === 0) {
    sel.innerHTML = '<option value="">No networks — create one first</option>'; return;
  }
  sel.innerHTML = data.networks.map(n =>
    `<option value="${escHtml(n.id)}">${escHtml(n.name)} (${escHtml(n.cidr)})</option>`
  ).join('');
}

async function _populateInstanceDropdown(selectId) {
  const sel = document.getElementById(selectId);
  sel.innerHTML = '<option value="">Loading...</option>';
  const { ok, data } = await apiCall('GET', '/api/v1/compute/instances');
  if (!ok) { sel.innerHTML = '<option value="">Failed to load</option>'; return; }
  const running = (data.instances || []).filter(i => i.status === 'running');
  if (running.length === 0) {
    sel.innerHTML = '<option value="">No running instances</option>'; return;
  }
  sel.innerHTML = running.map(i =>
    `<option value="${escHtml(i.id)}">${escHtml(i.name)} (${escHtml(i.id.slice(0,8))}…)</option>`
  ).join('');
}
