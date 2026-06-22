// Error message দেখানোর shared helper — সব auth pages ব্যবহার করে
function showError(el, msg) {
  el.textContent = msg;
  el.style.display = 'block';
}

// localStorage থেকে token বের করে — Bearer header তৈরির জন্য
function getToken() {
  return localStorage.getItem('mc_token');
}

// XSS prevent — user data কখনো raw HTML এ insert করা যাবে না
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Human-readable file size (1024-based)
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

// Authenticated API call — token automatic ভাবে header এ যোগ হয়
async function apiCall(method, path, body) {
  const token = getToken();
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (token) options.headers['Authorization'] = 'Bearer ' + token;
  if (body)  options.body = JSON.stringify(body);

  const res  = await fetch(path, options);
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

// Toast notification system — type: 'success' | 'error' | 'info'
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { success: '✓', error: '✗', info: 'ℹ' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || '•'}</span><span>${escHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast-fade-out');
    setTimeout(() => { if (toast.parentNode) toast.remove(); }, 310);
  }, 3500);
}

// Confirmation dialog — replaces native confirm(), returns Promise<boolean>
function showConfirm(message, okLabel = 'Confirm', danger = true) {
  return new Promise(resolve => {
    const modal     = document.getElementById('confirm-modal');
    const msgEl     = document.getElementById('confirm-message');
    // Fall back to native if HTML not loaded yet (login page)
    if (!modal) { resolve(window.confirm(message)); return; }

    msgEl.textContent = message;

    // Clone buttons to clear any stale listeners from prior calls
    const okOld     = document.getElementById('confirm-ok');
    const cancelOld = document.getElementById('confirm-cancel');
    const okBtn     = okOld.cloneNode(true);
    const cancelBtn = cancelOld.cloneNode(true);
    okBtn.textContent   = okLabel;
    okBtn.className     = danger ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
    okOld.replaceWith(okBtn);
    cancelOld.replaceWith(cancelBtn);

    modal.style.display = 'flex';

    function close(val) { modal.style.display = 'none'; resolve(val); }
    okBtn.addEventListener('click',     () => close(true));
    cancelBtn.addEventListener('click', () => close(false));
    // Close on backdrop click
    modal.onclick = e => { if (e.target === modal) close(false); };
  });
}
