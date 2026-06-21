// Instances section setup — dashboard.js এর setupSections() থেকে call হয়
async function setupInstances() {
  await loadFlavors();
  await loadInstances();

  document.getElementById('launch-btn').addEventListener('click', async () => {
    document.getElementById('launch-modal').style.display = 'flex';
    document.getElementById('launch-error').style.display = 'none';
    document.getElementById('inst-name').value            = '';
    document.getElementById('inst-image-select').value    = '';
    document.getElementById('inst-flavor').value          = '';
    document.getElementById('inst-keypair-select').value  = '';
    // Refresh image and keypair lists each time modal opens so new items appear
    await Promise.all([loadImagesForLaunch(), loadKeyPairsForLaunch()]);
  });

  ['modal-close', 'modal-cancel'].forEach(id => {
    document.getElementById(id).addEventListener('click', () => {
      document.getElementById('launch-modal').style.display = 'none';
    });
  });

  // Modal outside click করলে বন্ধ হয়
  document.getElementById('launch-modal').addEventListener('click', function(e) {
    if (e.target === this) this.style.display = 'none';
  });

  document.getElementById('inst-flavor').addEventListener('change', updateFlavorHint);
  document.getElementById('modal-launch-btn').addEventListener('click', launchInstance);
}


async function loadImagesForLaunch() {
  const { ok, data } = await apiCall('GET', '/api/v1/images');
  if (!ok) return;

  const select = document.getElementById('inst-image-select');
  // Keep the blank-disk placeholder (first option), replace the rest
  while (select.options.length > 1) select.remove(1);

  data.images.forEach(img => {
    const opt = document.createElement('option');
    opt.value = img.id;
    opt.textContent = `${img.name}  (${img.format}, ${formatBytes(img.file_size)})`;
    select.appendChild(opt);
  });
}


async function loadFlavors() {
  const { ok, data } = await apiCall('GET', '/api/v1/compute/flavors');
  if (!ok) return;

  const select = document.getElementById('inst-flavor');
  // Existing options (placeholder) রেখে বাকি গুলো add করো
  data.flavors.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.name;
    opt.textContent = `${f.name}  —  ${f.vcpus} vCPU  |  ${f.ram_mb >= 1024 ? f.ram_mb/1024 + ' GB' : f.ram_mb + ' MB'} RAM  |  ${f.disk_gb} GB Disk`;
    opt.dataset.vcpus   = f.vcpus;
    opt.dataset.ram_mb  = f.ram_mb;
    opt.dataset.disk_gb = f.disk_gb;
    select.appendChild(opt);
  });
}


function updateFlavorHint() {
  const select = document.getElementById('inst-flavor');
  const opt    = select.options[select.selectedIndex];
  const hint   = document.getElementById('flavor-hint');
  if (opt && opt.dataset.vcpus) {
    const ram = opt.dataset.ram_mb >= 1024 ? (opt.dataset.ram_mb / 1024) + ' GB' : opt.dataset.ram_mb + ' MB';
    hint.textContent = `${opt.dataset.vcpus} virtual CPUs, ${ram} RAM, ${opt.dataset.disk_gb} GB disk`;
  } else {
    hint.textContent = '';
  }
}


async function loadInstances() {
  const { ok, data } = await apiCall('GET', '/api/v1/compute/instances');
  if (!ok) return;

  const { instances } = data;
  const empty     = document.getElementById('instances-empty');
  const wrap      = document.getElementById('instances-table-wrap');
  const tbody     = document.getElementById('instances-tbody');

  if (instances.length === 0) {
    empty.style.display = 'block'; wrap.style.display = 'none';
    return;
  }

  empty.style.display = 'none'; wrap.style.display = 'block';
  tbody.innerHTML = instances.map(inst => `
    <tr>
      <td><strong>${escHtml(inst.name)}</strong></td>
      <td><code style="font-size:11px;">${inst.id.split('-')[0]}</code></td>
      <td>${escHtml(inst.flavor)}</td>
      <td>${inst.vcpus} vCPU / ${inst.ram_mb >= 1024 ? inst.ram_mb/1024+'GB' : inst.ram_mb+'MB'}</td>
      <td>${statusBadge(inst.status)}</td>
      <td>${inst.vnc_port && inst.vnc_port > 0 ? '<code>:' + inst.vnc_port + '</code>' : '—'}</td>
      <td>${new Date(inst.created_at).toLocaleString()}</td>
      <td>${actionButtons(inst)}</td>
    </tr>
  `).join('');
}


function statusBadge(status) {
  const map = {
    running:    'badge-running',
    stopped:    'badge-stopped',
    pending:    'badge-pending',
    error:      'badge-error',
    paused:     'badge-paused',
    rebooting:  'badge-pending',
    terminated: 'badge-stopped',
  };
  return `<span class="badge ${map[status] || 'badge-stopped'}">${status}</span>`;
}


function actionButtons(inst) {
  const isRunning = inst.status === 'running';
  const isStopped = inst.status === 'stopped' || inst.status === 'error';
  return `
    <div class="action-group">
      ${isRunning ? `<button class="btn btn-ghost btn-xs" onclick="doAction('${inst.id}','stop')">Stop</button>` : ''}
      ${isRunning ? `<button class="btn btn-ghost btn-xs" onclick="doAction('${inst.id}','reboot')">Reboot</button>` : ''}
      ${isStopped ? `<button class="btn btn-ghost btn-xs" onclick="doAction('${inst.id}','start')">Start</button>` : ''}
      <button class="btn btn-danger btn-xs" onclick="doAction('${inst.id}','terminate')">Terminate</button>
    </div>`;
}


async function launchInstance() {
  const name      = document.getElementById('inst-name').value.trim().toLowerCase();
  const flavor    = document.getElementById('inst-flavor').value;
  const imageId   = document.getElementById('inst-image-select').value;
  const keypairId = document.getElementById('inst-keypair-select').value;
  const errorDiv  = document.getElementById('launch-error');
  const btnText   = document.getElementById('modal-btn-text');
  const spinner   = document.getElementById('modal-spinner');
  const btn       = document.getElementById('modal-launch-btn');

  errorDiv.style.display = 'none';

  if (!name)   { showError(errorDiv, 'Instance name is required.'); return; }
  if (!flavor) { showError(errorDiv, 'Select a flavor.'); return; }

  btn.disabled = true; btnText.style.display = 'none'; spinner.style.display = 'inline-block';

  const body = { name, flavor };
  if (imageId)   body.image_id   = imageId;
  if (keypairId) body.keypair_id = keypairId;

  const { ok, data } = await apiCall('POST', '/api/v1/compute/instances', body);

  btn.disabled = false; btnText.style.display = 'inline'; spinner.style.display = 'none';

  if (ok) {
    document.getElementById('launch-modal').style.display = 'none';
    await loadInstances();
  } else {
    showError(errorDiv, data.message || 'Launch failed.');
  }
}


async function doAction(instanceId, action) {
  const confirmMsg = {
    stop:      'Stop this instance?',
    start:     'Start this instance?',
    reboot:    'Reboot this instance?',
    terminate: 'TERMINATE this instance? This will DELETE the VM and its disk permanently.',
  };

  if (!confirm(confirmMsg[action])) return;

  const { ok, data } = await apiCall('POST', `/api/v1/compute/instances/${instanceId}/action`, { action });
  if (!ok) { alert(data.message || `${action} failed.`); return; }

  // Action এর পরে table refresh করো
  await loadInstances();
}
