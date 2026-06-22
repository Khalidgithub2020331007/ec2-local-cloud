import os
import time
import libvirt

LIBVIRT_URI = 'qemu:///system'

# Map libvirt integer states → display labels
STATE_LABELS = {
    libvirt.VIR_DOMAIN_RUNNING:     'RUNNING',
    libvirt.VIR_DOMAIN_BLOCKED:     'RUNNING',   # blocked on I/O but still "running"
    libvirt.VIR_DOMAIN_PAUSED:      'STOPPED',
    libvirt.VIR_DOMAIN_SHUTDOWN:    'STOPPED',
    libvirt.VIR_DOMAIN_SHUTOFF:     'STOPPED',
    libvirt.VIR_DOMAIN_CRASHED:     'ERROR',
    libvirt.VIR_DOMAIN_PMSUSPENDED: 'STOPPED',
}

# Interface name to read host network counters from
HOST_IFACE = 'wlp0s20f3'


def get_host_cpu_percent():
    # /proc/stat is read twice 100 ms apart so we get a delta, not a lifetime total.
    # psutil would be simpler but adds an external dependency — /proc is always present.
    def _read():
        with open('/proc/stat') as f:
            parts = f.readline().split()  # "cpu  user nice sys idle iowait irq ..."
        vals = list(map(int, parts[1:]))
        idle  = vals[3] + vals[4]         # idle + iowait
        total = sum(vals)
        return total, idle

    t1, i1 = _read()
    time.sleep(0.1)
    t2, i2 = _read()

    total_delta = t2 - t1
    idle_delta  = i2 - i1
    if total_delta == 0:
        return 0.0
    return round(100.0 * (total_delta - idle_delta) / total_delta, 1)


def get_host_ram():
    # /proc/meminfo reports kilobytes; we convert to MB.
    # MemAvailable (not MemFree) is used for "free" — it includes reclaimable caches
    # and gives the same number that `free -m` shows in the "available" column.
    fields = {}
    with open('/proc/meminfo') as f:
        for line in f:
            parts = line.split()
            fields[parts[0].rstrip(':')] = int(parts[1])

    total_mb = fields['MemTotal']     // 1024
    free_mb  = fields['MemAvailable'] // 1024
    used_mb  = total_mb - free_mb
    return {'total_mb': total_mb, 'used_mb': used_mb, 'free_mb': free_mb}


def get_host_disk():
    # os.statvfs('/') is the stdlib way to get disk stats — no external deps needed.
    # f_bavail is blocks available to unprivileged users (not f_bfree which includes root-reserved).
    st = os.statvfs('/')
    total_gb = (st.f_blocks * st.f_frsize) // (1024 ** 3)
    free_gb  = (st.f_bavail * st.f_frsize) // (1024 ** 3)
    used_gb  = total_gb - free_gb
    return {'total_gb': int(total_gb), 'used_gb': int(used_gb), 'free_gb': int(free_gb)}


def get_host_network():
    # /proc/net/dev has two header lines then one line per interface:
    # "  iface: rx_bytes rx_pkts rx_errs ... tx_bytes tx_pkts ..."
    # Column 0 (after split on ':') = rx_bytes, column 8 = tx_bytes.
    with open('/proc/net/dev') as f:
        for line in f:
            if HOST_IFACE + ':' in line:
                cols = line.split(':')[1].split()
                return {'rx_bytes': int(cols[0]), 'tx_bytes': int(cols[8])}
    # Interface not found — machine may be on ethernet; return zeros rather than error.
    return {'rx_bytes': 0, 'tx_bytes': 0}


def get_all_host_metrics():
    return {
        'cpu_percent': get_host_cpu_percent(),
        'ram':         get_host_ram(),
        'disk':        get_host_disk(),
        'network':     get_host_network(),
    }


def _connect():
    conn = libvirt.open(LIBVIRT_URI)
    if conn is None:
        raise RuntimeError('Failed to connect to libvirt')
    return conn


def get_vm_metrics(libvirt_name, vm_id):
    # All I/O counters are cumulative since the VM started — libvirt exposes
    # no rate, only a running total. Stopped VMs return zeros for all stats
    # because libvirt raises libvirtError on stats calls for non-running domains.
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        info   = domain.info()   # [state, maxMem_kb, mem_kb, vcpus, cpu_time_ns]
        state  = info[0]
        status = STATE_LABELS.get(state, 'ERROR')
        is_running = state in (libvirt.VIR_DOMAIN_RUNNING, libvirt.VIR_DOMAIN_BLOCKED)

        ram_mb = info[1] // 1024   # maxMem (configured allocation) in KB → MB

        cpu_time_ns = disk_read = disk_write = net_rx = net_tx = 0

        if is_running:
            # getCPUStats(True) = total across all vCPUs; returns [{cpu_time, user_time, system_time}]
            cpu_stats   = domain.getCPUStats(True)
            cpu_time_ns = cpu_stats[0].get('cpu_time', 0)

            try:
                # blockStats tuple: (rd_req, rd_bytes, wr_req, wr_bytes, errs)
                bs = domain.blockStats('vda')
                disk_read  = bs[1]
                disk_write = bs[3]
            except libvirt.libvirtError:
                pass   # disk not present or inaccessible — leave at 0

            tap_name = f'tap-{vm_id[:8]}'
            try:
                # interfaceStats tuple: (rx_bytes, rx_pkts, rx_err, rx_drop, tx_bytes, tx_pkts, tx_err, tx_drop)
                ns     = domain.interfaceStats(tap_name)
                net_rx = ns[0]
                net_tx = ns[4]
            except libvirt.libvirtError:
                pass   # tap not yet attached — leave at 0

        return {
            'status':           status,
            'cpu_time_ns':      cpu_time_ns,
            'ram_mb':           ram_mb,
            'disk_read_bytes':  disk_read,
            'disk_write_bytes': disk_write,
            'net_rx_bytes':     net_rx,
            'net_tx_bytes':     net_tx,
        }

    except libvirt.libvirtError:
        # Domain was deleted from libvirt but still exists in our DB
        return {
            'status':           'ERROR',
            'cpu_time_ns':      0,
            'ram_mb':           0,
            'disk_read_bytes':  0,
            'disk_write_bytes': 0,
            'net_rx_bytes':     0,
            'net_tx_bytes':     0,
        }
    finally:
        conn.close()
