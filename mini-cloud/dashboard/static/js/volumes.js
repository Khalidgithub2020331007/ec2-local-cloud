// ── Volumes & Snapshots ───────────────────────────────────────────────────────

// State shared between volumes and snapshots sections
let _attachTargetVolumeId = null;
let _snapshotTargetVolumeId = null;
let _restoreTargetSnapId = null;

function setupVolumes() {
  // Volume section buttons
  document.getElementById('vol-create-btn').addEventListener('click', openCreateVolumeModal);
  document.getElementById('vol-create-close').addEventListener('click', closeCreateVolumeModal);
  document.getElementById('vol-create-cancel').addEventListener('click', closeCreateVolumeModal);
  document.getElementById('vol-create-submit').addEventListener('click', createVolume);

  // Attach modal
  document.getElementById('vol-attach-close').addEventListener('click', closeAttachModal);
  document.getElementById('vol-attach-cancel').addEventListener('click', closeAttachModal);
  document.getElementById('vol-attach-submit').addEventListener('click', doAttach);

  // Snapshot modal
  document.getElementById('vol-snap-close').addEventListener('click', closeSnapModal);
  document.getElementById('vol-snap-cancel').addEventListener('click', closeSnapModal);
  document.getElementById('vol-snap-submit').addEventListener('click', doCreateSnapshot);

  // Snapshots section buttons
  document.getElementById('snap-restore-close').addEventListener('click', closeRestoreModal);
  document.getElementById('snap-restore-cancel').addEventListener('click', closeRestoreModal);
  document.getElementById('snap-restore-submit').addEventListener('click', doRestoreSnapshot);
}


// ── Create Volume ─────────────────────────────────────────────────────────────

function openCreateVolumeModal() {
  document.getElementById('vol-create-name').value = '';
  document.getElementById('vol-create-size').value = '10';
  document.getElementById('vol-create-error').style.display = 'none';
  document.getElementById('vol-create-modal').style.display = 'flex';
  document.getElementById('vol-create-name').focus();
}

function closeCreateVolumeModal() {
  document.getElementById('vol-create-modal').style.display = 'none';
}

async function createVolume() {
  const name   = document.getElementById('vol-create-name').value.trim();
  const sizeGb = parseInt(document.getElementById('vol-create-size').value, 10);
  const errEl  = document.getElementById('vol-create-error');
  const btn    = document.getElementById('vol-create-submit');

  if (!name)          { showError(errEl, 'Name is required.'); return; }
  if (!sizeGb || sizeGb < 1) { showError(errEl, 'Size must be at least 1 GB.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', '/api/v1/volumes', { name, size_gb: sizeGb });
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Failed to create volume.'); return; }

  closeCreateVolumeModal();
  loadVolumes();
}


// ── Volumes List ──────────────────────────────────────────────────────────────

async function loadVolumes() {
  const { ok, data } = await apiCall('GET', '/api/v1/volumes');
  if (!ok) return;

  const volumes = data.volumes;
  const statEl  = document.getElementById('stat-volumes');
  if (statEl) statEl.textContent = volumes.length;

  const emptyEl = document.getElementById('vol-empty');
  const tableEl = document.getElementById('vol-table');
  const tbody   = document.getElementById('vol-tbody');

  if (volumes.length === 0) {
    emptyEl.style.display = 'block'; tableEl.style.display = 'none'; return;
  }
  emptyEl.style.display = 'none'; tableEl.style.display = 'block';

  tbody.innerHTML = volumes.map(v => {
    const statusBadge = v.status === 'in-use'
      ? `<span class="badge badge-green">in-use</span>`
      : `<span class="badge badge-stopped">available</span>`;

    const attachedTo = v.vm_id
      ? `<code style="font-size:11px;">${escHtml(v.device_name)}</code> on <span style="font-size:11px;">${escHtml(v.vm_id.slice(0, 8))}</span>`
      : '—';

    const attachBtn = v.status === 'available'
      ? `<button class="btn btn-ghost btn-xs" onclick="openAttachModal('${escHtml(v.id)}')">Attach</button>`
      : '';
    const detachBtn = v.status === 'in-use'
      ? `<button class="btn btn-ghost btn-xs" onclick="doDetach('${escHtml(v.id)}')">Detach</button>`
      : '';
    const snapBtn   = `<button class="btn btn-ghost btn-xs" onclick="openSnapModal('${escHtml(v.id)}')">Snapshot</button>`;
    const delBtn    = v.status === 'available'
      ? `<button class="btn btn-danger btn-xs" onclick="deleteVolume('${escHtml(v.id)}', '${escHtml(v.name)}')">Delete</button>`
      : '';

    return `
      <tr>
        <td><strong>${escHtml(v.name)}</strong></td>
        <td>${v.size_gb} GB</td>
        <td>${statusBadge}</td>
        <td>${attachedTo}</td>
        <td>${new Date(v.created_at).toLocaleDateString()}</td>
        <td style="white-space:nowrap;">
          ${attachBtn} ${detachBtn} ${snapBtn} ${delBtn}
        </td>
      </tr>`;
  }).join('');
}


// ── Attach Volume ─────────────────────────────────────────────────────────────

async function openAttachModal(volumeId) {
  _attachTargetVolumeId = volumeId;
  const select = document.getElementById('vol-attach-instance-select');
  const errEl  = document.getElementById('vol-attach-error');
  errEl.style.display = 'none';
  select.innerHTML = '<option value="">Loading instances...</option>';
  document.getElementById('vol-attach-modal').style.display = 'flex';

  const { ok, data } = await apiCall('GET', '/api/v1/instances');
  select.innerHTML = '';
  if (!ok || data.instances.length === 0) {
    select.innerHTML = '<option value="">No instances available</option>';
    return;
  }
  // Show all instances — attach to stopped VM is valid (volume appears on next boot).
  data.instances.forEach(inst => {
    const opt = document.createElement('option');
    opt.value       = inst.id;
    opt.textContent = `${inst.name}  (${inst.status})`;
    select.appendChild(opt);
  });
}

function closeAttachModal() {
  document.getElementById('vol-attach-modal').style.display = 'none';
  _attachTargetVolumeId = null;
}

async function doAttach() {
  const vmId  = document.getElementById('vol-attach-instance-select').value;
  const errEl = document.getElementById('vol-attach-error');
  const btn   = document.getElementById('vol-attach-submit');

  if (!vmId) { showError(errEl, 'Select an instance.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', `/api/v1/volumes/${_attachTargetVolumeId}/attach/${vmId}`);
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Attach failed.'); return; }

  closeAttachModal();
  loadVolumes();
}


// ── Detach Volume ─────────────────────────────────────────────────────────────

async function doDetach(volumeId) {
  if (!confirm('Detach this volume? Make sure the guest OS has unmounted it first to avoid data corruption.')) return;

  const { ok, data } = await apiCall('POST', `/api/v1/volumes/${volumeId}/detach`);
  if (!ok) { alert(data.message || 'Detach failed.'); return; }
  loadVolumes();
}


// ── Delete Volume ─────────────────────────────────────────────────────────────

async function deleteVolume(volumeId, volumeName) {
  if (!confirm(`Delete volume "${volumeName}"? This permanently destroys its LVM logical volume and all data.`)) return;

  const { ok, data } = await apiCall('DELETE', `/api/v1/volumes/${volumeId}`);
  if (!ok) { alert(data.message || 'Delete failed.'); return; }
  loadVolumes();
}


// ── Create Snapshot ───────────────────────────────────────────────────────────

function openSnapModal(volumeId) {
  _snapshotTargetVolumeId = volumeId;
  document.getElementById('vol-snap-name').value = '';
  document.getElementById('vol-snap-error').style.display = 'none';
  document.getElementById('vol-snap-modal').style.display = 'flex';
  document.getElementById('vol-snap-name').focus();
}

function closeSnapModal() {
  document.getElementById('vol-snap-modal').style.display = 'none';
  _snapshotTargetVolumeId = null;
}

async function doCreateSnapshot() {
  const name  = document.getElementById('vol-snap-name').value.trim();
  const errEl = document.getElementById('vol-snap-error');
  const btn   = document.getElementById('vol-snap-submit');

  if (!name) { showError(errEl, 'Snapshot name is required.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', `/api/v1/volumes/${_snapshotTargetVolumeId}/snapshot`, { name });
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Snapshot failed.'); return; }

  closeSnapModal();
  // Refresh both sections since the snapshot list may be visible.
  loadVolumes();
  loadSnapshots();
}


// ── Snapshots List ────────────────────────────────────────────────────────────

async function loadSnapshots() {
  const { ok, data } = await apiCall('GET', '/api/v1/snapshots');
  if (!ok) return;

  const snaps   = data.snapshots;
  const emptyEl = document.getElementById('snap-empty');
  const tableEl = document.getElementById('snap-table');
  const tbody   = document.getElementById('snap-tbody');

  if (snaps.length === 0) {
    emptyEl.style.display = 'block'; tableEl.style.display = 'none'; return;
  }
  emptyEl.style.display = 'none'; tableEl.style.display = 'block';

  tbody.innerHTML = snaps.map(s => `
    <tr>
      <td><strong>${escHtml(s.name)}</strong></td>
      <td>${s.size_gb} GB</td>
      <td><code style="font-size:11px;">${escHtml(s.volume_id.slice(0, 8))}…</code></td>
      <td>${new Date(s.created_at).toLocaleDateString()}</td>
      <td style="white-space:nowrap;">
        <button class="btn btn-ghost btn-xs" onclick="openRestoreModal('${escHtml(s.id)}')">Restore</button>
        <button class="btn btn-danger btn-xs" onclick="deleteSnapshot('${escHtml(s.id)}', '${escHtml(s.name)}')">Delete</button>
      </td>
    </tr>`
  ).join('');
}


// ── Restore Snapshot ──────────────────────────────────────────────────────────

function openRestoreModal(snapId) {
  _restoreTargetSnapId = snapId;
  document.getElementById('snap-restore-name').value = '';
  document.getElementById('snap-restore-error').style.display = 'none';
  document.getElementById('snap-restore-modal').style.display = 'flex';
  document.getElementById('snap-restore-name').focus();
}

function closeRestoreModal() {
  document.getElementById('snap-restore-modal').style.display = 'none';
  _restoreTargetSnapId = null;
}

async function doRestoreSnapshot() {
  const name  = document.getElementById('snap-restore-name').value.trim();
  const errEl = document.getElementById('snap-restore-error');
  const btn   = document.getElementById('snap-restore-submit');

  if (!name) { showError(errEl, 'Name for the new volume is required.'); return; }

  btn.disabled = true;
  const { ok, data } = await apiCall('POST', `/api/v1/snapshots/${_restoreTargetSnapId}/restore`, { name });
  btn.disabled = false;

  if (!ok) { showError(errEl, data.message || 'Restore failed.'); return; }

  closeRestoreModal();
  loadVolumes();
  loadSnapshots();
}


// ── Delete Snapshot ───────────────────────────────────────────────────────────

async function deleteSnapshot(snapId, snapName) {
  if (!confirm(`Delete snapshot "${snapName}"? This is permanent and cannot be undone.`)) return;

  const { ok, data } = await apiCall('DELETE', `/api/v1/snapshots/${snapId}`);
  if (!ok) { alert(data.message || 'Delete failed.'); return; }
  loadSnapshots();
}
