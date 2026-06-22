// IAM — Identity and Access Management
//
// WHY this is separate from auth.js (Step 1):
//   auth.js controls who can LOG IN to the dashboard (login users, JWT tokens, API keys).
//   IAM controls what identities are ALLOWED TO DO inside the cloud once they're in.
//
//   - IAM User:   a named identity (e.g. "alice") that can be granted permissions via policies.
//                 Different from a login user — IAM users don't have passwords here.
//   - IAM Group:  a collection of IAM users. Attach a policy once to the group and every
//                 member inherits it — avoids attaching the same policy to 50 individual users.
//   - IAM Role:   a temporary identity assumed by a SERVICE (e.g. an EC2 instance assuming a
//                 role to read S3). Not tied to a person; the trusted service calls AssumeRole.
//   - IAM Policy: a JSON document that says what Actions are Allowed/Denied on what Resources.
//                 A policy has no effect until it is attached to a User, Group, or Role.

// Modal-scoped state — tracks which entity the Members / Attach modals are operating on
let _membersGroupId   = null;
let _membersGroupName = null;
let _attachEntityType = null;
let _attachEntityId   = null;
let _attachEntityName = null;
let _allPoliciesCache = [];  // kept fresh each time the attach modal opens


// ── Setup ──────────────────────────────────────────────────────────────────────

function setupIam() {
  _bindTabDataLoaders();
  _bindCreateUserModal();
  _bindCreateGroupModal();
  _bindCreateRoleModal();
  _bindCreatePolicyModal();
  _bindMembersModal();
  _bindAttachModal();
  _bindJsonModal();
  _bindOutsideClick();
}

function _bindTabDataLoaders() {
  // Each IAM sub-tab reloads only its own data when clicked
  const tabMap = {
    'iam-users':    loadIamUsers,
    'iam-groups':   loadIamGroups,
    'iam-roles':    loadIamRoles,
    'iam-policies': loadIamPolicies,
  };
  document.querySelectorAll('#section-iam .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const loader = tabMap[btn.dataset.tab];
      if (loader) loader();
    });
  });
}

function _bindCreateUserModal() {
  document.getElementById('iam-add-user-btn').addEventListener('click', () => {
    document.getElementById('iam-user-username').value = '';
    _hideError('iam-create-user-error');
    document.getElementById('iam-create-user-modal').style.display = 'flex';
    document.getElementById('iam-user-username').focus();
  });
  ['iam-create-user-close', 'iam-create-user-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-create-user-modal').style.display = 'none'
    )
  );
  document.getElementById('iam-create-user-save').addEventListener('click', createIamUser);
  document.getElementById('iam-user-username').addEventListener('keydown', e => {
    if (e.key === 'Enter') createIamUser();
  });
}

function _bindCreateGroupModal() {
  document.getElementById('iam-add-group-btn').addEventListener('click', () => {
    document.getElementById('iam-group-name').value = '';
    _hideError('iam-create-group-error');
    document.getElementById('iam-create-group-modal').style.display = 'flex';
    document.getElementById('iam-group-name').focus();
  });
  ['iam-create-group-close', 'iam-create-group-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-create-group-modal').style.display = 'none'
    )
  );
  document.getElementById('iam-create-group-save').addEventListener('click', createIamGroup);
  document.getElementById('iam-group-name').addEventListener('keydown', e => {
    if (e.key === 'Enter') createIamGroup();
  });
}

function _bindCreateRoleModal() {
  document.getElementById('iam-add-role-btn').addEventListener('click', () => {
    document.getElementById('iam-role-name').value    = '';
    document.getElementById('iam-role-desc').value    = '';
    document.getElementById('iam-role-service').value = '';
    _hideError('iam-create-role-error');
    document.getElementById('iam-create-role-modal').style.display = 'flex';
    document.getElementById('iam-role-name').focus();
  });
  ['iam-create-role-close', 'iam-create-role-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-create-role-modal').style.display = 'none'
    )
  );
  document.getElementById('iam-create-role-save').addEventListener('click', createIamRole);
}

function _bindCreatePolicyModal() {
  document.getElementById('iam-add-policy-btn').addEventListener('click', () => {
    document.getElementById('iam-policy-name').value = '';
    document.getElementById('iam-policy-desc').value = '';
    document.getElementById('iam-policy-json').value = '';
    _hideError('iam-create-policy-error');
    document.getElementById('iam-create-policy-modal').style.display = 'flex';
    document.getElementById('iam-policy-name').focus();
  });
  ['iam-create-policy-close', 'iam-create-policy-cancel'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-create-policy-modal').style.display = 'none'
    )
  );
  document.getElementById('iam-create-policy-save').addEventListener('click', createIamPolicy);
}

function _bindMembersModal() {
  ['iam-members-close', 'iam-members-done'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-members-modal').style.display = 'none'
    )
  );
  document.getElementById('iam-members-add-btn').addEventListener('click', addGroupMember);
}

function _bindAttachModal() {
  ['iam-attach-close', 'iam-attach-done'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-attach-modal').style.display = 'none'
    )
  );
  // Live search filters the policy list without another API call
  document.getElementById('iam-attach-search').addEventListener('input', _filterAttachList);
}

function _bindJsonModal() {
  ['iam-json-close', 'iam-json-close-btn'].forEach(id =>
    document.getElementById(id).addEventListener('click', () =>
      document.getElementById('iam-json-modal').style.display = 'none'
    )
  );
}

function _bindOutsideClick() {
  const modals = [
    'iam-create-user-modal', 'iam-create-group-modal', 'iam-create-role-modal',
    'iam-create-policy-modal', 'iam-members-modal', 'iam-attach-modal', 'iam-json-modal',
  ];
  modals.forEach(id => {
    document.getElementById(id).addEventListener('click', function(e) {
      if (e.target === this) this.style.display = 'none';
    });
  });
}


// ── Top-level loader (called by dashboard.js when the IAM section becomes active) ──

async function loadIam() {
  await Promise.all([loadIamUsers(), loadIamGroups(), loadIamRoles(), loadIamPolicies()]);
}


// ── Users ──────────────────────────────────────────────────────────────────────

async function loadIamUsers() {
  const { ok, data } = await apiCall('GET', '/api/v1/iam/users');
  if (!ok) return;

  const empty = document.getElementById('iam-users-empty');
  const table = document.getElementById('iam-users-table');
  const tbody = document.getElementById('iam-users-tbody');

  if (data.users.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';
  tbody.innerHTML = data.users.map(u => `
    <tr>
      <td><strong>${escHtml(u.username)}</strong></td>
      <td><code style="font-size:11px;">${escHtml(u.arn)}</code></td>
      <td>${new Date(u.created_at).toLocaleDateString()}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="openAttachModal('user','${escHtml(u.id)}','${escHtml(u.username)}')">Policies</button>
        <button class="btn btn-danger btn-sm" onclick="deleteIamUser('${escHtml(u.id)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function createIamUser() {
  const username = document.getElementById('iam-user-username').value.trim();
  if (!username) { _showError('iam-create-user-error', 'Username is required.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/iam/users', { username });
  if (!ok) { _showError('iam-create-user-error', data.message || 'Failed to create user.'); return; }

  document.getElementById('iam-create-user-modal').style.display = 'none';
  showToast('IAM user created.', 'success');
  loadIamUsers();
}

async function deleteIamUser(userId) {
  if (!await showConfirm('Delete this IAM user? They will be removed from all groups.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/iam/users/' + userId);
  if (!ok) { showToast(data.message || 'Failed to delete user.', 'error'); return; }
  showToast('IAM user deleted.', 'success');
  loadIamUsers();
}


// ── Groups ─────────────────────────────────────────────────────────────────────

async function loadIamGroups() {
  const { ok, data } = await apiCall('GET', '/api/v1/iam/groups');
  if (!ok) return;

  const empty = document.getElementById('iam-groups-empty');
  const table = document.getElementById('iam-groups-table');
  const tbody = document.getElementById('iam-groups-tbody');

  if (data.groups.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';
  tbody.innerHTML = data.groups.map(g => `
    <tr>
      <td><strong>${escHtml(g.name)}</strong></td>
      <td><code style="font-size:11px;">${escHtml(g.arn)}</code></td>
      <td>${g.member_count} member${g.member_count !== 1 ? 's' : ''}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="openMembersModal('${escHtml(g.id)}','${escHtml(g.name)}')">Members</button>
        <button class="btn btn-ghost btn-sm" onclick="openAttachModal('group','${escHtml(g.id)}','${escHtml(g.name)}')">Policies</button>
        <button class="btn btn-danger btn-sm" onclick="deleteIamGroup('${escHtml(g.id)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function createIamGroup() {
  const name = document.getElementById('iam-group-name').value.trim();
  if (!name) { _showError('iam-create-group-error', 'Group name is required.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/iam/groups', { name });
  if (!ok) { _showError('iam-create-group-error', data.message || 'Failed to create group.'); return; }

  document.getElementById('iam-create-group-modal').style.display = 'none';
  showToast('IAM group created.', 'success');
  loadIamGroups();
}

async function deleteIamGroup(groupId) {
  if (!await showConfirm('Delete this group? All member associations will be removed.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/iam/groups/' + groupId);
  if (!ok) { showToast(data.message || 'Failed to delete group.', 'error'); return; }
  showToast('IAM group deleted.', 'success');
  loadIamGroups();
}

// Members modal — opened from the Groups table
async function openMembersModal(groupId, groupName) {
  _membersGroupId   = groupId;
  _membersGroupName = groupName;
  document.getElementById('iam-members-group-name').textContent = groupName;
  document.getElementById('iam-members-modal').style.display = 'flex';
  await _refreshMembersModal();
}

async function _refreshMembersModal() {
  const [membersRes, usersRes] = await Promise.all([
    apiCall('GET', '/api/v1/iam/groups/' + _membersGroupId + '/members'),
    apiCall('GET', '/api/v1/iam/users'),
  ]);
  if (!membersRes.ok || !usersRes.ok) return;

  const members   = membersRes.data.members;
  const allUsers  = usersRes.data.users;
  const memberIds = new Set(members.map(m => m.id));

  // Render current member list with remove buttons
  const listEl = document.getElementById('iam-members-list');
  if (members.length === 0) {
    listEl.innerHTML = '<p style="font-size:12px;color:var(--gray-400);">No members yet.</p>';
  } else {
    listEl.innerHTML = members.map(m => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border);">
        <span style="font-size:13px;">${escHtml(m.username)}</span>
        <button class="btn btn-danger btn-sm" onclick="removeGroupMember('${escHtml(m.id)}')">Remove</button>
      </div>
    `).join('');
  }

  // Add-user dropdown shows only users NOT already in the group
  const select = document.getElementById('iam-members-user-select');
  select.innerHTML = '<option value="">Select a user...</option>';
  allUsers.filter(u => !memberIds.has(u.id)).forEach(u => {
    const opt = document.createElement('option');
    opt.value       = u.id;
    opt.textContent = u.username;
    select.appendChild(opt);
  });
}

async function addGroupMember() {
  const userId = document.getElementById('iam-members-user-select').value;
  if (!userId) { showToast('Select a user to add.', 'error'); return; }

  const { ok, data } = await apiCall(
    'POST', `/api/v1/iam/groups/${_membersGroupId}/members`, { user_id: userId }
  );
  if (!ok) { showToast(data.message || 'Failed to add member.', 'error'); return; }

  showToast('User added to group.', 'success');
  await _refreshMembersModal();
  loadIamGroups();  // refresh member count in the groups table
}

async function removeGroupMember(userId) {
  const { ok, data } = await apiCall(
    'DELETE', `/api/v1/iam/groups/${_membersGroupId}/members/${userId}`
  );
  if (!ok) { showToast(data.message || 'Failed to remove member.', 'error'); return; }

  showToast('User removed from group.', 'success');
  await _refreshMembersModal();
  loadIamGroups();
}


// ── Roles ──────────────────────────────────────────────────────────────────────

async function loadIamRoles() {
  const { ok, data } = await apiCall('GET', '/api/v1/iam/roles');
  if (!ok) return;

  const empty = document.getElementById('iam-roles-empty');
  const table = document.getElementById('iam-roles-table');
  const tbody = document.getElementById('iam-roles-tbody');

  if (data.roles.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';
  tbody.innerHTML = data.roles.map(r => `
    <tr>
      <td><strong>${escHtml(r.name)}</strong>${r.description ? `<br><span style="font-size:11px;color:var(--gray-500);">${escHtml(r.description)}</span>` : ''}</td>
      <td><code style="font-size:11px;">${escHtml(r.arn)}</code></td>
      <td><span class="badge badge-format">${escHtml(r.trusted_service)}</span></td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="openAttachModal('role','${escHtml(r.id)}','${escHtml(r.name)}')">Policies</button>
        <button class="btn btn-danger btn-sm" onclick="deleteIamRole('${escHtml(r.id)}')">Delete</button>
      </td>
    </tr>
  `).join('');
}

async function createIamRole() {
  const name            = document.getElementById('iam-role-name').value.trim();
  const description     = document.getElementById('iam-role-desc').value.trim();
  const trusted_service = document.getElementById('iam-role-service').value;

  if (!name)            { _showError('iam-create-role-error', 'Role name is required.'); return; }
  if (!trusted_service) { _showError('iam-create-role-error', 'Select a trusted service.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/iam/roles', { name, description, trusted_service });
  if (!ok) { _showError('iam-create-role-error', data.message || 'Failed to create role.'); return; }

  document.getElementById('iam-create-role-modal').style.display = 'none';
  showToast('IAM role created.', 'success');
  loadIamRoles();
}

async function deleteIamRole(roleId) {
  if (!await showConfirm('Delete this IAM role?')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/iam/roles/' + roleId);
  if (!ok) { showToast(data.message || 'Failed to delete role.', 'error'); return; }
  showToast('IAM role deleted.', 'success');
  loadIamRoles();
}


// ── Policies ───────────────────────────────────────────────────────────────────

async function loadIamPolicies() {
  const { ok, data } = await apiCall('GET', '/api/v1/iam/policies');
  if (!ok) return;

  const empty = document.getElementById('iam-policies-empty');
  const table = document.getElementById('iam-policies-table');
  const tbody = document.getElementById('iam-policies-tbody');

  if (data.policies.length === 0) {
    empty.style.display = 'block'; table.style.display = 'none'; return;
  }
  empty.style.display = 'none'; table.style.display = 'table';
  tbody.innerHTML = data.policies.map(p => `
    <tr>
      <td>
        <strong>${escHtml(p.name)}</strong>
        ${p.description ? `<br><span style="font-size:11px;color:var(--gray-500);">${escHtml(p.description)}</span>` : ''}
      </td>
      <td>
        <span class="badge ${p.type === 'managed' ? 'badge-blue' : 'badge-amber'}">
          ${p.type === 'managed' ? 'AWS Managed' : 'Customer'}
        </span>
      </td>
      <td><code style="font-size:11px;">${escHtml(p.arn)}</code></td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="openJsonModal('${escHtml(p.id)}','${escHtml(p.name)}')">View JSON</button>
        <button class="btn btn-ghost btn-sm" onclick="openAttachModal('policy','${escHtml(p.id)}','${escHtml(p.name)}')">Attach</button>
        ${p.type === 'customer'
          ? `<button class="btn btn-danger btn-sm" onclick="deleteIamPolicy('${escHtml(p.id)}')">Delete</button>`
          : ''}
      </td>
    </tr>
  `).join('');
}

async function createIamPolicy() {
  const name        = document.getElementById('iam-policy-name').value.trim();
  const description = document.getElementById('iam-policy-desc').value.trim();
  const policy_json = document.getElementById('iam-policy-json').value.trim();

  if (!name)        { _showError('iam-create-policy-error', 'Policy name is required.'); return; }
  if (!policy_json) { _showError('iam-create-policy-error', 'Policy document is required.'); return; }

  const { ok, data } = await apiCall('POST', '/api/v1/iam/policies', { name, description, policy_json });
  if (!ok) { _showError('iam-create-policy-error', data.message || 'Failed to create policy.'); return; }

  document.getElementById('iam-create-policy-modal').style.display = 'none';
  showToast('Customer policy created.', 'success');
  loadIamPolicies();
}

async function deleteIamPolicy(policyId) {
  if (!await showConfirm('Delete this customer policy? It will be detached from all entities.')) return;
  const { ok, data } = await apiCall('DELETE', '/api/v1/iam/policies/' + policyId);
  if (!ok) { showToast(data.message || 'Failed to delete policy.', 'error'); return; }
  showToast('Policy deleted.', 'success');
  loadIamPolicies();
}

// JSON viewer modal
async function openJsonModal(policyId, policyName) {
  document.getElementById('iam-json-policy-name').textContent = policyName;
  document.getElementById('iam-json-content').textContent = 'Loading...';
  document.getElementById('iam-json-modal').style.display = 'flex';

  const { ok, data } = await apiCall('GET', '/api/v1/iam/policies/' + policyId + '/json');
  if (!ok) {
    document.getElementById('iam-json-content').textContent = 'Failed to load policy document.';
    return;
  }
  try {
    // Re-parse and re-stringify for consistent indentation regardless of how it was stored
    document.getElementById('iam-json-content').textContent =
      JSON.stringify(JSON.parse(data.policy_json), null, 2);
  } catch {
    document.getElementById('iam-json-content').textContent = data.policy_json;
  }
}

// Attach / Detach modal — shows all policies with current attachment state for an entity
async function openAttachModal(entityType, entityId, entityName) {
  _attachEntityType = entityType;
  _attachEntityId   = entityId;
  _attachEntityName = entityName;
  document.getElementById('iam-attach-entity-name').textContent =
    `${entityName} (${entityType})`;
  document.getElementById('iam-attach-search').value = '';
  document.getElementById('iam-attach-list').innerHTML =
    '<p style="font-size:12px;color:var(--gray-400);padding:8px 0;">Loading...</p>';
  document.getElementById('iam-attach-modal').style.display = 'flex';
  await _refreshAttachModal();
}

async function _refreshAttachModal() {
  const [allRes, attachedRes] = await Promise.all([
    apiCall('GET', '/api/v1/iam/policies'),
    apiCall('GET', `/api/v1/iam/entities/${_attachEntityType}/${_attachEntityId}/policies`),
  ]);
  if (!allRes.ok) return;

  _allPoliciesCache = allRes.data.policies;
  const attachedIds = new Set(
    attachedRes.ok ? attachedRes.data.policies.map(p => p.id) : []
  );

  _renderAttachList(_allPoliciesCache, attachedIds);
}

function _renderAttachList(policies, attachedIds) {
  const listEl = document.getElementById('iam-attach-list');
  if (policies.length === 0) {
    listEl.innerHTML = '<p style="font-size:12px;color:var(--gray-400);padding:8px 0;">No policies available.</p>';
    return;
  }
  // Store attached state as data attributes so the search filter can re-render without another fetch
  listEl.innerHTML = policies.map(p => {
    const attached = attachedIds ? attachedIds.has(p.id) : p._attached;
    const badge    = p.type === 'managed' ? 'badge-blue' : 'badge-amber';
    const label    = p.type === 'managed' ? 'AWS Managed' : 'Customer';
    return `
      <div class="attach-row" style="display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:1px solid var(--border);"
           data-name="${escHtml(p.name.toLowerCase())}" data-attached="${attached ? '1' : '0'}" data-id="${escHtml(p.id)}">
        <div>
          <span style="font-size:13px;font-weight:500;">${escHtml(p.name)}</span>
          <span class="badge ${badge}" style="margin-left:8px;">${label}</span>
          ${p.description ? `<br><span style="font-size:11px;color:var(--gray-500);">${escHtml(p.description)}</span>` : ''}
        </div>
        ${attached
          ? `<button class="btn btn-ghost btn-sm" onclick="detachPolicyFromEntity('${escHtml(p.id)}')">Detach</button>`
          : `<button class="btn btn-primary btn-sm" onclick="attachPolicyToEntity('${escHtml(p.id)}')">Attach</button>`
        }
      </div>
    `;
  }).join('');
}

function _filterAttachList() {
  const query = document.getElementById('iam-attach-search').value.toLowerCase().trim();
  document.querySelectorAll('#iam-attach-list .attach-row').forEach(row => {
    row.style.display = row.dataset.name.includes(query) ? '' : 'none';
  });
}

async function attachPolicyToEntity(policyId) {
  const { ok, data } = await apiCall('POST', '/api/v1/iam/policies/' + policyId + '/attach', {
    entity_type: _attachEntityType,
    entity_id:   _attachEntityId,
  });
  if (!ok) { showToast(data.message || 'Failed to attach policy.', 'error'); return; }
  showToast('Policy attached.', 'success');
  _refreshAttachModal();
}

async function detachPolicyFromEntity(policyId) {
  const { ok, data } = await apiCall('POST', '/api/v1/iam/policies/' + policyId + '/detach', {
    entity_type: _attachEntityType,
    entity_id:   _attachEntityId,
  });
  if (!ok) { showToast(data.message || 'Failed to detach policy.', 'error'); return; }
  showToast('Policy detached.', 'success');
  _refreshAttachModal();
}


// ── Helpers ────────────────────────────────────────────────────────────────────

function _showError(elementId, message) {
  const el = document.getElementById(elementId);
  el.textContent    = message;
  el.style.display  = 'block';
}

function _hideError(elementId) {
  document.getElementById(elementId).style.display = 'none';
}

// Export to window so dashboard.js can call loadIam() and setupIam() by name
window.loadIam  = loadIam;
window.setupIam = setupIam;
