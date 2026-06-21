// Images section — upload with progress bar, list, delete, toggle visibility

async function setupImages() {
  await loadImages();

  document.getElementById('upload-img-btn').addEventListener('click', () => {
    document.getElementById('img-upload-modal').style.display = 'flex';
    document.getElementById('img-upload-error').style.display = 'none';
    document.getElementById('img-name').value         = '';
    document.getElementById('img-desc').value         = '';
    document.getElementById('img-file').value         = '';
    document.getElementById('img-progress-wrap').style.display = 'none';
    document.getElementById('img-progress-bar').style.width    = '0%';
    document.getElementById('img-progress-text').textContent   = '';
    document.getElementById('img-upload-submit').disabled      = false;
  });

  ['img-modal-close', 'img-modal-cancel'].forEach(id => {
    document.getElementById(id).addEventListener('click', () => {
      document.getElementById('img-upload-modal').style.display = 'none';
    });
  });

  document.getElementById('img-upload-modal').addEventListener('click', function(e) {
    if (e.target === this) this.style.display = 'none';
  });

  document.getElementById('img-upload-submit').addEventListener('click', uploadImage);
}


async function loadImages() {
  const { ok, data } = await apiCall('GET', '/api/v1/images');
  if (!ok) return;

  const { images } = data;
  const empty  = document.getElementById('images-empty');
  const wrap   = document.getElementById('images-table-wrap');
  const tbody  = document.getElementById('images-tbody');

  // Keep the overview stat card in sync
  const statEl = document.getElementById('stat-images');
  if (statEl) statEl.textContent = images.length;

  if (images.length === 0) {
    empty.style.display = 'block'; wrap.style.display = 'none';
    return;
  }

  empty.style.display = 'none'; wrap.style.display = 'block';
  tbody.innerHTML = images.map(img => `
    <tr>
      <td><strong>${escHtml(img.name)}</strong>${img.description ? `<br><span class="row-hint">${escHtml(img.description)}</span>` : ''}</td>
      <td><span class="badge badge-format">${escHtml(img.format)}</span></td>
      <td>${formatBytes(img.file_size)}</td>
      <td>${img.is_owner ? 'You' : 'Shared'}</td>
      <td><span class="badge ${img.is_public ? 'badge-green' : 'badge-stopped'}">${img.is_public ? 'Public' : 'Private'}</span></td>
      <td>${new Date(img.created_at).toLocaleDateString()}</td>
      <td>
        <div class="action-group">
          ${img.is_owner ? `
            <button class="btn btn-ghost btn-xs"
              onclick="toggleImageVisibility('${escHtml(img.id)}', ${!img.is_public})">
              ${img.is_public ? 'Make Private' : 'Make Public'}
            </button>
            <button class="btn btn-danger btn-xs" onclick="deleteImage('${escHtml(img.id)}')">Delete</button>
          ` : '—'}
        </div>
      </td>
    </tr>
  `).join('');
}


function uploadImage() {
  const name     = document.getElementById('img-name').value.trim();
  const desc     = document.getElementById('img-desc').value.trim();
  const fileInput = document.getElementById('img-file');
  const file     = fileInput.files[0];
  const errorDiv = document.getElementById('img-upload-error');

  errorDiv.style.display = 'none';
  if (!name) { showError(errorDiv, 'Image name is required.'); return; }
  if (!file) { showError(errorDiv, 'Select a file to upload.'); return; }

  const formData = new FormData();
  formData.append('name', name);
  if (desc) formData.append('description', desc);
  formData.append('file', file);

  const progressWrap = document.getElementById('img-progress-wrap');
  const progressBar  = document.getElementById('img-progress-bar');
  const progressText = document.getElementById('img-progress-text');
  const submitBtn    = document.getElementById('img-upload-submit');

  progressWrap.style.display = 'block';
  submitBtn.disabled = true;

  // Use XHR instead of fetch so we get upload progress events
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/v1/images');
  xhr.setRequestHeader('Authorization', 'Bearer ' + getToken());

  xhr.upload.addEventListener('progress', function(e) {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    progressBar.style.width    = pct + '%';
    progressText.textContent   = `${pct}%  —  ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
  });

  xhr.addEventListener('load', function() {
    submitBtn.disabled = false;
    let resp = {};
    try { resp = JSON.parse(xhr.responseText); } catch (_) {}
    if (xhr.status === 201) {
      document.getElementById('img-upload-modal').style.display = 'none';
      loadImages();
    } else {
      showError(errorDiv, resp.message || 'Upload failed.');
      progressWrap.style.display = 'none';
    }
  });

  xhr.addEventListener('error', function() {
    submitBtn.disabled = false;
    showError(errorDiv, 'Network error — upload did not complete.');
    progressWrap.style.display = 'none';
  });

  xhr.send(formData);
}


async function deleteImage(imageId) {
  if (!confirm('Delete this image? This cannot be undone.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/images/' + imageId);
  if (!ok) { alert(data.message || 'Delete failed.'); return; }
  loadImages();
}


async function toggleImageVisibility(imageId, makePublic) {
  const { ok, data } = await apiCall('POST', `/api/v1/images/${imageId}/visibility`, { is_public: makePublic });
  if (!ok) { alert(data.message || 'Could not update visibility.'); return; }
  loadImages();
}
