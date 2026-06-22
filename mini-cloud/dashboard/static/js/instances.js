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
    // Refresh dropdowns each time modal opens so newly created resources appear
    await Promise.all([loadImagesForLaunch(), loadKeyPairsForLaunch(), loadNetworksForLaunch(), loadSgsForLaunch()]);
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
  const statEl = document.getElementById('stat-instances');
  if (statEl) statEl.textContent = instances.filter(i => i.status !== 'terminated').length;

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
      ${isRunning ? `<button class="btn btn-ghost btn-xs" onclick="openConsole('${inst.id}')">Console</button>` : ''}
      ${isStopped ? `<button class="btn btn-ghost btn-xs" onclick="doAction('${inst.id}','start')">Start</button>` : ''}
      <button class="btn btn-danger btn-xs" onclick="doAction('${inst.id}','terminate')">Terminate</button>
    </div>`;
}


function openConsole(instanceId) {
  // Open the noVNC console in a new tab — keeps the dashboard intact.
  // The console page fetches its own WebSocket URL using the stored JWT token.
  window.open(`/console/${instanceId}`, '_blank', 'noopener');
}


async function launchInstance() {
  const name      = document.getElementById('inst-name').value.trim().toLowerCase();
  const flavor    = document.getElementById('inst-flavor').value;
  const imageId   = document.getElementById('inst-image-select').value;
  const keypairId = document.getElementById('inst-keypair-select').value;
  const networkId = document.getElementById('inst-network-select') ? document.getElementById('inst-network-select').value : '';
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
  if (networkId) body.network_id = networkId;

  // Collect multi-select security group IDs
  const sgSelect = document.getElementById('inst-sg-select');
  if (sgSelect) {
    body.security_group_ids = Array.from(sgSelect.selectedOptions).map(o => o.value).filter(Boolean);
  }

  const { ok, data } = await apiCall('POST', '/api/v1/compute/instances', body);

  btn.disabled = false; btnText.style.display = 'inline'; spinner.style.display = 'none';

  if (ok) {
    document.getElementById('launch-modal').style.display = 'none';
    showToast(`Instance "${name}" launched.`, 'success');
    await loadInstances();
  } else {
    showError(errorDiv, data.message || 'Launch failed.');
  }
}


async function doAction(instanceId, action) {
  // Only destructive actions need a confirmation modal — stop/start/reboot do not
  if (action === 'terminate') {
    const ok = await showConfirm(
      'TERMINATE this instance?\n\nThis permanently deletes the VM and its disk. This cannot be undone.',
      'Terminate'
    );
    if (!ok) return;
  }

  const { ok, data } = await apiCall('POST', `/api/v1/compute/instances/${instanceId}/action`, { action });
  if (!ok) { showToast(data.message || `${action} failed.`, 'error'); return; }

  const labels = { stop: 'stopped', start: 'started', reboot: 'rebooting', terminate: 'terminated' };
  showToast(`Instance ${labels[action] || action}.`, 'success');
  await loadInstances();
}
