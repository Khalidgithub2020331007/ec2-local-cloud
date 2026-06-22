// Dashboard load হওয়ার সাথে সাথে token check করে — না থাকলে login-এ পাঠায়
(async function init() {
  const token = getToken();
  if (!token) { window.location.href = '/'; return; }

  const { ok, data } = await apiCall('GET', '/api/v1/auth/me');
  if (!ok) { localStorage.clear(); window.location.href = '/'; return; }

  const { user } = data;
  document.getElementById('user-name').textContent = user.username;
  document.getElementById('user-avatar').textContent = user.username[0].toUpperCase();

  document.getElementById('logout-btn').addEventListener('click', () => {
    localStorage.clear();
    window.location.href = '/';
  });

  setupNavigation();
  setupApiKeys();
  setupStatCards();
  setupIamTabs();
  if (window.setupIam) window.setupIam();
  setupInstances();
  setupImages();
  setupNetworks();
  setupRouters();
  setupFloatingIps();
  setupNetworkInterfaces();
  setupSecurityGroups();
  setupKeyPairs();
  setupVolumes();
  setupMonOverview();
  setupDevstack();
})();


// ── Navigation ────────────────────────────────────────────────────────────────

function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      switchSection(this.dataset.section);
    });
  });

  // Buttons inside sections that link to another section (e.g. IAM → API Keys)
  document.querySelectorAll('[data-section-link]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      switchSection(el.dataset.sectionLink);
    });
  });
}

function switchSection(sectionId) {
  document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
  const activeLink = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  if (activeLink) activeLink.classList.add('active');

  document.querySelectorAll('.console-section').forEach(s => s.style.display = 'none');
  const target = document.getElementById('section-' + sectionId);
  if (target) target.style.display = 'block';

  // Load fresh data each time a section is shown
  const loaders = {
    'api-keys':         loadApiKeys,
    'instances':        loadInstances,
    'images':           loadImages,
    'key-pairs':        loadKeyPairs,
    'networks':         loadNetworks,
    'routers':          loadRouters,
    'floating-ips':     loadFloatingIps,
    'security-groups':  loadSecurityGroups,
    'volumes':          loadVolumes,
    'snapshots':        loadSnapshots,
    'mon-overview':     loadMonOverview,
    'devstack':         loadDevstackStatus,
    'quotas':           () => window.loadQuotas        && window.loadQuotas(),
    'load-balancers':   () => window.loadLoadBalancers && window.loadLoadBalancers(),
    'autoscaling':      () => window.loadAutoscaling   && window.loadAutoscaling(),
    'iam':              () => window.loadIam            && window.loadIam(),
  };
  if (loaders[sectionId]) loaders[sectionId]();
  // metrics section auto-refresh is handled by monitoring.js MutationObserver
}


// ── Overview stat cards ───────────────────────────────────────────────────────

function setupStatCards() {
  document.querySelectorAll('.stat-card[data-goto]').forEach(card => {
    card.addEventListener('click', () => switchSection(card.dataset.goto));
  });
}


// ── API Keys ──────────────────────────────────────────────────────────────────

function setupApiKeys() {
  loadApiKeys();

  document.getElementById('create-key-btn').addEventListener('click', () => {
    document.getElementById('key-create-form').style.display = 'flex';
    document.getElementById('key-name').focus();
    document.getElementById('key-secret-box').style.display = 'none';
  });
  document.getElementById('key-cancel-btn').addEventListener('click', () => {
    document.getElementById('key-create-form').style.display = 'none';
    document.getElementById('key-name').value = '';
  });
  document.getElementById('key-save-btn').addEventListener('click', createApiKey);
  document.getElementById('key-name').addEventListener('keydown', e => { if (e.key === 'Enter') createApiKey(); });
  document.getElementById('key-secret-close').addEventListener('click', () => {
    document.getElementById('key-secret-box').style.display = 'none';
  });
}

async function loadApiKeys() {
  const { ok, data } = await apiCall('GET', '/api/v1/auth/keys');
  if (!ok) return;

  const keys  = data.api_keys;
  const empty = document.getElementById('keys-empty');
  const table = document.getElementById('keys-table');
  const tbody = document.getElementById('keys-tbody');

  if (keys.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';
  tbody.innerHTML = keys.map(k => `
    <tr>
      <td>${escHtml(k.name)}</td>
      <td><code>${escHtml(k.access_key)}</code></td>
      <td>${new Date(k.created_at).toLocaleDateString()}</td>
      <td><span class="badge ${k.is_active ? 'badge-green' : 'badge-red'}">${k.is_active ? 'Active' : 'Inactive'}</span></td>
      <td><button class="btn btn-danger btn-sm" onclick="deleteApiKey('${escHtml(k.id)}')">Delete</button></td>
    </tr>
  `).join('');
}

async function createApiKey() {
  const name = document.getElementById('key-name').value.trim();
  if (!name) { showToast('Enter a key name.', 'error'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/auth/keys', { name });
  if (!ok) { showToast(data.message || 'Failed to create key.', 'error'); return; }

  document.getElementById('disp-access-key').textContent = data.api_key.access_key;
  document.getElementById('disp-secret-key').textContent = data.api_key.secret_key;
  document.getElementById('key-secret-box').style.display = 'block';
  document.getElementById('key-create-form').style.display = 'none';
  document.getElementById('key-name').value = '';
  loadApiKeys();
}

async function deleteApiKey(keyId) {
  if (!await showConfirm('Delete this API key? This cannot be undone.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/auth/keys/' + keyId);
  if (!ok) { showToast(data.message || 'Failed to delete key.', 'error'); return; }
  showToast('API key deleted.', 'success');
  loadApiKeys();
}


// ── IAM Tabs ──────────────────────────────────────────────────────────────────

function setupIamTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const panel = this.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      this.classList.add('active');
      const el = document.getElementById(panel);
      if (el) el.classList.add('active');
    });
  });
}


// ── Monitoring Overview (new section) ─────────────────────────────────────────

function setupMonOverview() {
  document.getElementById('mon-ov-refresh-btn').addEventListener('click', loadMonOverview);
}

async function loadMonOverview() {
  const errEl = document.getElementById('mon-ov-error');
  errEl.style.display = 'none';

  const { ok, data } = await apiCall('GET', '/api/v1/monitoring/summary');
  if (!ok) {
    errEl.textContent = 'Could not load monitoring data. Is the backend running?';
    errEl.style.display = 'block';
    return;
  }

  // VM count cards
  document.getElementById('mon-ov-running').textContent = data.vm_running ?? '—';
  document.getElementById('mon-ov-total').textContent   = data.vm_total   ?? '—';

  // CPU
  const cpuPct = data.cpu_percent || 0;
  document.getElementById('mon-ov-cpu').textContent     = cpuPct.toFixed(1) + '%';
  document.getElementById('mon-ov-cpu-val').textContent = cpuPct.toFixed(1) + '%';
  _setBar('mon-ov-cpu-bar', cpuPct);
  document.getElementById('mon-ov-cpu-sub').textContent = 'Sampled from /proc/stat';

  // RAM
  const ram    = data.ram || {};
  const ramPct = ram.total_mb ? Math.round(ram.used_mb / ram.total_mb * 100) : 0;
  document.getElementById('mon-ov-ram').textContent     = ramPct + '%';
  document.getElementById('mon-ov-ram-val').textContent = ramPct + '%';
  _setBar('mon-ov-ram-bar', ramPct);
  document.getElementById('mon-ov-ram-sub').textContent =
    ram.total_mb ? `${ram.used_mb} MB used / ${ram.total_mb} MB total` : '';

  // Disk
  const disk    = data.disk || {};
  const diskPct = disk.total_gb ? Math.round(disk.used_gb / disk.total_gb * 100) : 0;
  document.getElementById('mon-ov-disk-val').textContent = diskPct + '%';
  _setBar('mon-ov-disk-bar', diskPct);
  document.getElementById('mon-ov-disk-sub').textContent =
    disk.total_gb ? `${disk.used_gb} GB used / ${disk.total_gb} GB total (${disk.free_gb} GB free)` : '';

  // Network
  const net = data.network || {};
  document.getElementById('mon-ov-rx').textContent = _fmtBytes(net.rx_bytes);
  document.getElementById('mon-ov-tx').textContent = _fmtBytes(net.tx_bytes);

  // Timestamp
  const el = document.getElementById('mon-ov-updated');
  if (el) el.textContent = 'Updated ' + new Date().toLocaleTimeString();
}

// Shared bar helper — used by both overview and devstack sections
function _setBar(barId, pct) {
  const el = document.getElementById(barId);
  if (!el) return;
  el.classList.remove('mon-bar-green', 'mon-bar-orange', 'mon-bar-red');
  el.classList.add(pct >= 80 ? 'mon-bar-red' : pct >= 60 ? 'mon-bar-orange' : 'mon-bar-green');
  el.style.width = Math.min(pct, 100) + '%';
}

function _fmtBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1073741824).toFixed(2) + ' GB';
}


// ── DevStack Monitor (new section) ────────────────────────────────────────────

const DEVSTACK_SERVICES = [
  { id: 'api',        name: 'API Server',        desc: 'Flask REST API — Step 1',           endpoint: '/api/v1/auth/me'            },
  { id: 'compute',    name: 'KVM / libvirt',      desc: 'VM management — Step 2',            endpoint: '/api/v1/compute/instances'  },
  { id: 'images',     name: 'Image Store',        desc: 'qcow2/iso storage — Step 3',        endpoint: '/api/v1/images'             },
  { id: 'network',    name: 'Networking',         desc: 'Bridge + dnsmasq — Step 4',         endpoint: '/api/v1/network/networks'   },
  { id: 'fips',       name: 'Floating IPs',       desc: 'iptables DNAT/SNAT — Step 5',       endpoint: '/api/v1/network/floating-ips' },
  { id: 'secgroups',  name: 'Security Groups',    desc: 'iptables chains — Step 6',          endpoint: '/api/v1/security-groups'    },
  { id: 'keypairs',   name: 'Key Pairs',          desc: 'cloud-init SSH keys — Step 7',      endpoint: '/api/v1/keypairs'           },
  { id: 'storage',    name: 'Block Storage',      desc: 'LVM volumes — Step 8',              endpoint: '/api/v1/volumes'            },
  { id: 'monitoring', name: 'Monitoring Agent',   desc: 'Host + VM metrics — Step 9',        endpoint: '/api/v1/monitoring/host'   },
];

function setupDevstack() {
  document.getElementById('devstack-refresh-btn').addEventListener('click', loadDevstackStatus);
}

async function loadDevstackStatus() {
  const grid = document.getElementById('devstack-grid');

  // Render all cards in "checking" state first
  grid.innerHTML = DEVSTACK_SERVICES.map(s => `
    <div class="service-card" id="svc-${s.id}">
      <div class="service-card-header">
        <span class="service-name">${escHtml(s.name)}</span>
        <span class="badge badge-stopped">Checking...</span>
      </div>
      <div class="service-desc">${escHtml(s.desc)}</div>
      <div class="service-checked">Probing endpoint...</div>
    </div>
  `).join('');

  // Probe all services in parallel and update each card as it resolves
  await Promise.all(DEVSTACK_SERVICES.map(async svc => {
    const card = document.getElementById('svc-' + svc.id);
    if (!card) return;

    const t0 = performance.now();
    const { ok, status } = await apiCall('GET', svc.endpoint);
    const ms = Math.round(performance.now() - t0);

    const badge = ok
      ? '<span class="badge badge-green">Running</span>'
      : `<span class="badge badge-red">Error ${status}</span>`;

    card.querySelector('.service-card-header').innerHTML =
      `<span class="service-name">${escHtml(svc.name)}</span>${badge}`;
    card.querySelector('.service-checked').textContent =
      `Checked ${new Date().toLocaleTimeString()} — ${ms} ms`;
  }));
}
