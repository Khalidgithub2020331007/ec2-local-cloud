// ── Key Pairs ────────────────────────────────────────────────────────────────

function setupKeyPairs() {
  loadKeyPairs();

  document.getElementById('kp-generate-btn').addEventListener('click', () => {
    document.getElementById('kp-generate-modal').style.display = 'flex';
    document.getElementById('kp-gen-name').value = '';
    document.getElementById('kp-gen-error').style.display = 'none';
    document.getElementById('kp-gen-name').focus();
  });

  document.getElementById('kp-upload-btn').addEventListener('click', () => {
    document.getElementById('kp-upload-modal').style.display = 'flex';
    document.getElementById('kp-upload-name').value = '';
    document.getElementById('kp-upload-key').value = '';
    document.getElementById('kp-upload-error').style.display = 'none';
    document.getElementById('kp-upload-name').focus();
  });

  document.getElementById('kp-gen-close').addEventListener('click', closeGenModal);
  document.getElementById('kp-gen-cancel').addEventListener('click', closeGenModal);
  document.getElementById('kp-gen-submit').addEventListener('click', generateKeyPair);

  document.getElementById('kp-upload-close').addEventListener('click', closeUploadModal);
  document.getElementById('kp-upload-cancel').addEventListener('click', closeUploadModal);
  document.getElementById('kp-upload-submit').addEventListener('click', uploadKeyPair);

  // Private key reveal modal — "I have saved it" dismisses and refreshes the list
  document.getElementById('kp-private-saved').addEventListener('click', () => {
    document.getElementById('kp-private-modal').style.display = 'none';
    loadKeyPairs();
  });

  document.getElementById('kp-copy-key').addEventListener('click', copyPrivateKey);
}

function closeGenModal() {
  document.getElementById('kp-generate-modal').style.display = 'none';
}

function closeUploadModal() {
  document.getElementById('kp-upload-modal').style.display = 'none';
}


async function loadKeyPairs() {
  const { ok, data } = await apiCall('GET', '/api/v1/keypairs');
  if (!ok) return;

  const pairs = data.keypairs;
  const empty = document.getElementById('kp-empty');
  const table = document.getElementById('kp-table');
  const tbody = document.getElementById('kp-tbody');

  const statEl = document.getElementById('stat-keypairs');
  if (statEl) statEl.textContent = pairs.length;

  if (pairs.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'block';
  tbody.innerHTML = pairs.map(kp => `
    <tr>
      <td><strong>${escHtml(kp.name)}</strong></td>
      <td><code style="font-size:11px;">${escHtml(kp.fingerprint)}</code></td>
      <td>${new Date(kp.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-danger btn-xs" onclick="deleteKeyPair('${escHtml(kp.id)}', '${escHtml(kp.name)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}


async function generateKeyPair() {
  const name   = document.getElementById('kp-gen-name').value.trim();
  const errEl  = document.getElementById('kp-gen-error');
  const btn    = document.getElementById('kp-gen-submit');

  if (!name) { showError(errEl, 'Name is required.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', '/api/v1/keypairs/generate', { name });
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Failed to generate key pair.'); return; }

  closeGenModal();
  // Show the private key exactly once — after this modal is dismissed it's gone forever.
  document.getElementById('kp-private-name').textContent = data.keypair.name;
  document.getElementById('kp-private-fingerprint').textContent = data.keypair.fingerprint;
  document.getElementById('kp-private-key-text').value = data.private_key;
  document.getElementById('kp-private-modal').style.display = 'flex';
}


async function uploadKeyPair() {
  const name      = document.getElementById('kp-upload-name').value.trim();
  const publicKey = document.getElementById('kp-upload-key').value.trim();
  const errEl     = document.getElementById('kp-upload-error');
  const btn       = document.getElementById('kp-upload-submit');

  if (!name)      { showError(errEl, 'Name is required.'); return; }
  if (!publicKey) { showError(errEl, 'Public key is required.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', '/api/v1/keypairs/upload', { name, public_key: publicKey });
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Failed to import key pair.'); return; }

  closeUploadModal();
  loadKeyPairs();
}


async function deleteKeyPair(keypairId, keypairName) {
  if (!confirm(`Delete key pair "${keypairName}"? Running instances that use it will not be affected.`)) return;

  const { ok, data } = await apiCall('DELETE', `/api/v1/keypairs/${keypairId}`);
  if (!ok) { alert(data.message || 'Delete failed.'); return; }
  loadKeyPairs();
}


function copyPrivateKey() {
  const textarea = document.getElementById('kp-private-key-text');
  textarea.select();
  document.execCommand('copy');

  const btn = document.getElementById('kp-copy-key');
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
}


// Called by instances.js when the launch modal opens — populates the keypair dropdown.
async function loadKeyPairsForLaunch() {
  const { ok, data } = await apiCall('GET', '/api/v1/keypairs');
  if (!ok) return;

  const select = document.getElementById('inst-keypair-select');
  while (select.options.length > 1) select.remove(1);

  data.keypairs.forEach(kp => {
    const opt = document.createElement('option');
    opt.value = kp.id;
    opt.textContent = `${kp.name}  (${kp.fingerprint.slice(0, 14)}…)`;
    select.appendChild(opt);
  });
}
