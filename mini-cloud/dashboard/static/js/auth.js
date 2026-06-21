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
