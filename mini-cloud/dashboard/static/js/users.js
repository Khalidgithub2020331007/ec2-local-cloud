// Users & Projects — admin-only section
//
// Non-admin users see a notice. Admins see two tabs:
//   Users      — full CRUD: create, toggle role, activate/deactivate, reset password, delete
//   Resource Usage — per-user card showing instance / volume / network counts

let _upResetTargetId = null;

function setupUsersProjects() {
  _bindUpTabs();
  _bindCreateModal();
  _bindResetModal();

  document.getElementById('up-create-btn').addEventListener('click', () => {
    _clearUpCreateForm();
    document.getElementById('up-create-modal').style.display = 'flex';
    document.getElementById('up-new-username').focus();
  });
}

// Called by dashboard.js switchSection('users-projects')
async function loadUsersProjects() {
  const { ok, data } = await apiCall('GET', '/api/v1/auth/users');

  if (!ok) {
    // 403 = non-admin — show notice, hide the rest
    document.getElementById('up-admin-notice').style.display = 'block';
    document.getElementById('up-create-btn').style.display  = 'none';
    return;
  }

  document.getElementById('up-admin-notice').style.display = 'none';
  document.getElementById('up-create-btn').style.display   = '';

  const users = data.users || [];
  _renderUsersTable(users);
  _renderResourceCards(users);
}

// ── Tab switching ──────────────────────────────────────────────────────────────

function _bindUpTabs() {
  document.querySelectorAll('#section-users-projects .tab-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('#section-users-projects .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('#section-users-projects .tab-panel').forEach(p => p.classList.remove('active'));
      this.classList.add('active');
      const panel = document.getElementById(this.dataset.tab);
      if (panel) panel.classList.add('active');
    });
  });
}

// ── Users table ───────────────────────────────────────────────────────────────

function _renderUsersTable(users) {
  const empty = document.getElementById('up-users-empty');
  const table = document.getElementById('up-users-table');
  const tbody = document.getElementById('up-users-tbody');

  if (users.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';

  tbody.innerHTML = users.map(u => {
    const roleBadge   = u.role === 'admin'
      ? '<span class="badge badge-blue">admin</span>'
      : '<span class="badge">user</span>';
    const statusBadge = u.is_active
      ? '<span class="badge badge-green">Active</span>'
      : '<span class="badge badge-red">Inactive</span>';
    const joined = new Date(u.created_at).toLocaleDateString();

    // Disable destructive actions on own account (server also enforces this)
    const isSelf    = u.id === _currentUserId();
    const selfTitle = isSelf ? ' title="Cannot modify your own account"' : '';
    const disAttr   = isSelf ? ' disabled' : '';

    const toggleRoleLabel = u.role === 'admin' ? 'Make User' : 'Make Admin';
    const toggleActiveLabel = u.is_active ? 'Deactivate' : 'Activate';

    return `<tr>
      <td><strong>${escHtml(u.username)}</strong>${isSelf ? ' <span style="font-size:11px;color:var(--gray-400)">(you)</span>' : ''}</td>
      <td>${escHtml(u.email)}</td>
      <td>${roleBadge}</td>
      <td>${statusBadge}</td>
      <td>${u.instance_count}</td>
      <td>${u.volume_count}</td>
      <td>${u.network_count}</td>
      <td>${joined}</td>
      <td style="white-space:nowrap;display:flex;gap:6px;flex-wrap:wrap;">
        <button class="btn btn-ghost btn-sm"${disAttr}${selfTitle}
          onclick="upToggleRole('${escHtml(u.id)}','${escHtml(u.role)}')">${toggleRoleLabel}</button>
        <button class="btn btn-ghost btn-sm"${disAttr}${selfTitle}
          onclick="upToggleActive('${escHtml(u.id)}',${u.is_active})">${toggleActiveLabel}</button>
        <button class="btn btn-ghost btn-sm"${disAttr}${selfTitle}
          onclick="upOpenReset('${escHtml(u.id)}','${escHtml(u.username)}')">Reset PW</button>
        <button class="btn btn-danger btn-sm"${disAttr}${selfTitle}
          onclick="upDeleteUser('${escHtml(u.id)}','${escHtml(u.username)}')">Delete</button>
      </td>
    </tr>`;
  }).join('');
}

// ── Resource cards ────────────────────────────────────────────────────────────

function _renderResourceCards(users) {
  const empty = document.getElementById('up-res-empty');
  const grid  = document.getElementById('up-res-cards');

  if (users.length === 0) {
    empty.style.display = 'block'; grid.innerHTML = ''; return;
  }
  empty.style.display = 'none';

  grid.innerHTML = users.map(u => `
    <div class="res-user-card">
      <div class="res-user-header">
        <div class="res-avatar">${escHtml(u.username[0].toUpperCase())}</div>
        <div>
          <div class="res-username">${escHtml(u.username)}</div>
          <div class="res-email">${escHtml(u.email)}</div>
        </div>
        <span class="badge ${u.role === 'admin' ? 'badge-blue' : ''}" style="margin-left:auto">${escHtml(u.role)}</span>
      </div>
      <div class="res-stats">
        <div class="res-stat"><span class="res-stat-num">${u.instance_count}</span><span class="res-stat-label">Instances</span></div>
        <div class="res-stat"><span class="res-stat-num">${u.volume_count}</span><span class="res-stat-label">Volumes</span></div>
        <div class="res-stat"><span class="res-stat-num">${u.network_count}</span><span class="res-stat-label">Networks</span></div>
        <div class="res-stat"><span class="res-stat-num">${u.api_key_count}</span><span class="res-stat-label">API Keys</span></div>
      </div>
      <div class="res-joined">Joined ${new Date(u.created_at).toLocaleDateString()}</div>
    </div>
  `).join('');
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function upToggleRole(userId, currentRole) {
  const newRole = currentRole === 'admin' ? 'user' : 'admin';
  const label   = newRole === 'admin' ? 'grant admin role to' : 'revoke admin role from';
  if (!await showConfirm(`This will ${label} this user. Continue?`)) return;

  const { ok, data } = await apiCall('PUT', '/api/v1/auth/users/' + userId, { role: newRole });
  if (!ok) { showToast(data.message || 'Failed to update role.', 'error'); return; }
  showToast(`Role updated to "${newRole}".`, 'success');
  loadUsersProjects();
}

async function upToggleActive(userId, currentActive) {
  const newActive = !currentActive;
  const label     = newActive ? 'activate' : 'deactivate';
  if (!await showConfirm(`This will ${label} the account. Continue?`)) return;

  const { ok, data } = await apiCall('PUT', '/api/v1/auth/users/' + userId, { is_active: newActive });
  if (!ok) { showToast(data.message || 'Failed to update status.', 'error'); return; }
  showToast(`Account ${newActive ? 'activated' : 'deactivated'}.`, 'success');
  loadUsersProjects();
}

async function upDeleteUser(userId, username) {
  if (!await showConfirm(`Deactivate "${username}"? They will no longer be able to log in. Their resources are preserved.`)) return;

  const { ok, data } = await apiCall('DELETE', '/api/v1/auth/users/' + userId);
  if (!ok) { showToast(data.message || 'Failed to delete user.', 'error'); return; }
  showToast(`"${username}" has been deactivated.`, 'success');
  loadUsersProjects();
}

// ── Create user modal ─────────────────────────────────────────────────────────

function _bindCreateModal() {
  ['up-create-close', 'up-create-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('up-create-modal').style.display = 'none'
    )
  );
  document.getElementById('up-create-save').addEventListener('click', _createUser);
  document.getElementById('up-new-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') _createUser();
  });

  // Close on backdrop click
  document.getElementById('up-create-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('up-create-modal'))
      document.getElementById('up-create-modal').style.display = 'none';
  });
}

function _clearUpCreateForm() {
  ['up-new-username', 'up-new-email', 'up-new-password'].forEach(id =>
    document.getElementById(id).value = ''
  );
  document.getElementById('up-new-role').value = 'user';
  _hideUpError('up-create-error');
}

async function _createUser() {
  const username = document.getElementById('up-new-username').value.trim();
  const email    = document.getElementById('up-new-email').value.trim();
  const password = document.getElementById('up-new-password').value;
  const role     = document.getElementById('up-new-role').value;

  _hideUpError('up-create-error');

  if (!username || !email || !password) {
    _showUpError('up-create-error', 'All fields are required.'); return;
  }

  const { ok, data } = await apiCall('POST', '/api/v1/auth/users', { username, email, password, role });
  if (!ok) { _showUpError('up-create-error', data.message || 'Failed to create user.'); return; }

  showToast(`User "${username}" created.`, 'success');
  document.getElementById('up-create-modal').style.display = 'none';
  loadUsersProjects();
}

// ── Reset password modal ──────────────────────────────────────────────────────

function _bindResetModal() {
  ['up-reset-close', 'up-reset-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () => {
      document.getElementById('up-reset-modal').style.display = 'none';
      _upResetTargetId = null;
    })
  );
  document.getElementById('up-reset-save').addEventListener('click', _resetPassword);
  document.getElementById('up-reset-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') _resetPassword();
  });

  document.getElementById('up-reset-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('up-reset-modal')) {
      document.getElementById('up-reset-modal').style.display = 'none';
      _upResetTargetId = null;
    }
  });
}

function upOpenReset(userId, username) {
  _upResetTargetId = userId;
  document.getElementById('up-reset-username').textContent = username;
  document.getElementById('up-reset-password').value = '';
  _hideUpError('up-reset-error');
  document.getElementById('up-reset-modal').style.display = 'flex';
  document.getElementById('up-reset-password').focus();
}

async function _resetPassword() {
  const password = document.getElementById('up-reset-password').value;
  _hideUpError('up-reset-error');

  if (password.length < 8) {
    _showUpError('up-reset-error', 'Password must be at least 8 characters.'); return;
  }

  const { ok, data } = await apiCall('POST', `/api/v1/auth/users/${_upResetTargetId}/reset-password`, { password });
  if (!ok) { _showUpError('up-reset-error', data.message || 'Failed to reset password.'); return; }

  showToast('Password reset successfully.', 'success');
  document.getElementById('up-reset-modal').style.display = 'none';
  _upResetTargetId = null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _showUpError(elId, msg) {
  const el = document.getElementById(elId);
  el.textContent = msg; el.style.display = 'block';
}

function _hideUpError(elId) {
  const el = document.getElementById(elId);
  el.style.display = 'none'; el.textContent = '';
}

// Reads the logged-in user's ID from the JWT stored in localStorage
function _currentUserId() {
  try {
    const token   = localStorage.getItem('token') || '';
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.user_id || '';
  } catch {
    return '';
  }
}
