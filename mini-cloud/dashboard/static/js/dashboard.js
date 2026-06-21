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
  setupInstances();
  setupImages();
  setupNetworks();
  setupRouters();
  setupFloatingIps();
  setupNetworkInterfaces();
  setupSecurityGroups();
  setupKeyPairs();
  setupVolumes();
})();


function setupNavigation() {
  document.querySelectorAll('.nav-item').forEach(link => {
    link.addEventListener('click', function(e) {
      e.preventDefault();
      switchSection(this.dataset.section);
    });
  });

  // IAM page-এর "Manage API Keys" button
  document.querySelectorAll('[data-section-link]').forEach(el => {
    el.addEventListener('click', e => {
      e.preventDefault();
      switchSection(el.dataset.sectionLink);
    });
  });
}

function switchSection(sectionId) {
  // সব nav active class সরাও
  document.querySelectorAll('.nav-item').forEach(l => l.classList.remove('active'));
  const activeLink = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  if (activeLink) activeLink.classList.add('active');

  // সব section লুকাও, target টা দেখাও
  document.querySelectorAll('.console-section').forEach(s => s.style.display = 'none');
  const target = document.getElementById('section-' + sectionId);
  if (target) target.style.display = 'block';

  // Section switch করলে fresh data load করো
  if (sectionId === 'api-keys')            loadApiKeys();
  if (sectionId === 'instances')           loadInstances();
  if (sectionId === 'images')              loadImages();
  if (sectionId === 'networks')            loadNetworks();
  if (sectionId === 'routers')             loadRouters();
  if (sectionId === 'floating-ips')        loadFloatingIps();
  if (sectionId === 'network-interfaces')  loadNetworkInterfaces();
  if (sectionId === 'security-groups')     loadSecurityGroups();
  if (sectionId === 'key-pairs')           loadKeyPairs();
  if (sectionId === 'volumes')             loadVolumes();
  if (sectionId === 'snapshots')           loadSnapshots();
}


// Overview-এর stat cards click করলে সেই section-এ যাবে
function setupStatCards() {
  document.querySelectorAll('.stat-card[data-goto]').forEach(card => {
    card.addEventListener('click', () => switchSection(card.dataset.goto));
  });
}


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
    empty.style.display = 'block'; table.style.display = 'none';
    return;
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
  if (!name) { alert('Enter a key name.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/auth/keys', { name });
  if (!ok) { alert(data.message || 'Failed to create key.'); return; }

  // Secret key একবারই দেখানো হয়
  document.getElementById('disp-access-key').textContent = data.api_key.access_key;
  document.getElementById('disp-secret-key').textContent = data.api_key.secret_key;
  document.getElementById('key-secret-box').style.display = 'block';
  document.getElementById('key-create-form').style.display = 'none';
  document.getElementById('key-name').value = '';
  loadApiKeys();
}


async function deleteApiKey(keyId) {
  if (!confirm('Delete this API key? This cannot be undone.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/auth/keys/' + keyId);
  if (!ok) { alert(data.message || 'Failed to delete key.'); return; }
  loadApiKeys();
}


