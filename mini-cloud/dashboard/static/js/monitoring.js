/* monitoring.js — Step 9: CloudWatch-style host + VM metrics
 * Auto-refreshes every 10 s when the Monitoring section is active.
 * All data comes from /api/v1/monitoring/* endpoints. */

(function () {
  'use strict';

  const REFRESH_MS  = 10_000;
  let   refreshTimer = null;

  // ── Helpers ──────────────────────────────────────────────────────

  function authHeaders() {
    const token = localStorage.getItem('token');
    return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
  }

  // Convert raw bytes to human-readable string (B / KB / MB / GB)
  function fmtBytes(bytes) {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
  }

  // Convert nanoseconds to a readable string
  function fmtNs(ns) {
    if (!ns) return '0 ns';
    if (ns < 1_000) return ns + ' ns';
    if (ns < 1_000_000) return (ns / 1_000).toFixed(1) + ' µs';
    if (ns < 1_000_000_000) return (ns / 1_000_000).toFixed(1) + ' ms';
    return (ns / 1_000_000_000).toFixed(2) + ' s';
  }

  // Return CSS class for a percentage (green < 60, orange 60-80, red > 80)
  function barColorClass(pct) {
    if (pct >= 80) return 'mon-bar-red';
    if (pct >= 60) return 'mon-bar-orange';
    return 'mon-bar-green';
  }

  function setBar(barId, pct) {
    const el = document.getElementById(barId);
    if (!el) return;
    // Remove old colour classes before applying the new one
    el.classList.remove('mon-bar-green', 'mon-bar-orange', 'mon-bar-red');
    el.classList.add(barColorClass(pct));
    el.style.width = Math.min(pct, 100) + '%';
  }

  function statusBadge(status) {
    const map = {
      RUNNING: 'badge-running',
      STOPPED: 'badge-stopped',
      ERROR:   'badge-error',
    };
    const cls = map[status] || 'badge-stopped';
    return `<span class="badge ${cls}">${status}</span>`;
  }

  // ── Host metrics ─────────────────────────────────────────────────

  async function loadHostMetrics() {
    const errEl = document.getElementById('mon-host-error');
    try {
      const resp = await fetch('/api/v1/monitoring/host', { headers: authHeaders() });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const d = await resp.json();

      // CPU
      const cpuPct = d.cpu_percent || 0;
      document.getElementById('mon-cpu-value').textContent = cpuPct.toFixed(1) + '%';
      setBar('mon-cpu-bar', cpuPct);
      document.getElementById('mon-cpu-sub').textContent = 'Sampled over 100 ms interval from /proc/stat';

      // RAM
      const ram = d.ram || {};
      const ramPct = ram.total_mb ? Math.round(ram.used_mb / ram.total_mb * 100) : 0;
      document.getElementById('mon-ram-value').textContent = ramPct + '%';
      setBar('mon-ram-bar', ramPct);
      document.getElementById('mon-ram-sub').textContent =
        `${ram.used_mb} MB used / ${ram.total_mb} MB total (${ram.free_mb} MB available)`;

      // Disk
      const disk = d.disk || {};
      const diskPct = disk.total_gb ? Math.round(disk.used_gb / disk.total_gb * 100) : 0;
      document.getElementById('mon-disk-value').textContent = diskPct + '%';
      setBar('mon-disk-bar', diskPct);
      document.getElementById('mon-disk-sub').textContent =
        `${disk.used_gb} GB used / ${disk.total_gb} GB total (${disk.free_gb} GB free)`;

      // Network
      const net = d.network || {};
      document.getElementById('mon-rx-val').textContent = fmtBytes(net.rx_bytes);
      document.getElementById('mon-tx-val').textContent = fmtBytes(net.tx_bytes);

      if (errEl) errEl.style.display = 'none';
    } catch (err) {
      if (errEl) {
        errEl.textContent = 'Could not load host metrics: ' + err.message;
        errEl.style.display = 'block';
      }
    }
  }

  // ── VM metrics ───────────────────────────────────────────────────

  async function loadVmMetrics() {
    const tbody   = document.getElementById('mon-vms-tbody');
    const emptyEl = document.getElementById('mon-vms-empty');
    const wrapEl  = document.getElementById('mon-vms-table-wrap');
    if (!tbody) return;

    try {
      const resp = await fetch('/api/v1/monitoring/vms', { headers: authHeaders() });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const vms  = data.vms || [];

      if (!vms.length) {
        emptyEl.style.display = 'block';
        wrapEl.style.display  = 'none';
        return;
      }

      emptyEl.style.display = 'none';
      wrapEl.style.display  = 'block';

      tbody.innerHTML = vms.map(vm => `
        <tr>
          <td><strong>${vm.name}</strong><br><span class="row-hint">${vm.vm_id.slice(0, 8)}</span></td>
          <td>${statusBadge(vm.status)}</td>
          <td style="font-variant-numeric:tabular-nums;">${fmtNs(vm.cpu_time_ns)}</td>
          <td>${vm.ram_mb} MB</td>
          <td>${fmtBytes(vm.disk_read_bytes)}</td>
          <td>${fmtBytes(vm.disk_write_bytes)}</td>
          <td>${fmtBytes(vm.net_rx_bytes)}</td>
          <td>${fmtBytes(vm.net_tx_bytes)}</td>
        </tr>
      `).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--red);padding:20px;">
        Could not load VM metrics: ${err.message}</td></tr>`;
      emptyEl.style.display = 'none';
      wrapEl.style.display  = 'block';
    }
  }

  // ── Refresh cycle ─────────────────────────────────────────────────

  async function refresh() {
    await Promise.all([loadHostMetrics(), loadVmMetrics()]);
    const ts = new Date().toLocaleTimeString();
    const el = document.getElementById('mon-last-updated');
    if (el) el.textContent = 'Updated ' + ts;
  }

  function startAutoRefresh() {
    refresh();
    // Clear any existing timer so navigating away and back doesn't stack timers
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(refresh, REFRESH_MS);
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  // ── Section visibility hook ──────────────────────────────────────
  // dashboard.js switches sections by toggling display. We watch for the
  // monitoring section becoming visible so we start/stop the refresh timer.

  function observeSection() {
    const section = document.getElementById('section-monitoring');
    if (!section) return;

    // MutationObserver on the display style change
    const obs = new MutationObserver(() => {
      if (section.style.display !== 'none') {
        startAutoRefresh();
      } else {
        stopAutoRefresh();
      }
    });
    obs.observe(section, { attributes: true, attributeFilter: ['style'] });
  }

  // ── Init ──────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', () => {
    const refreshBtn = document.getElementById('mon-refresh-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', refresh);

    observeSection();

    // If monitoring is the active section on first load, start immediately
    const section = document.getElementById('section-monitoring');
    if (section && section.style.display !== 'none') {
      startAutoRefresh();
    }
  });
})();
