import io
import subprocess
from app.load_balancers.models import get_all_lbs_with_members

HAPROXY_CFG_PATH = '/etc/haproxy/haproxy.cfg'
HAPROXY_SOCK     = '/var/run/haproxy/admin.sock'


def generate_haproxy_config():
    # HAProxy reads exactly one config file. Every LB must be written together so
    # existing frontends are not lost when a new one is added.
    lbs  = get_all_lbs_with_members()
    buf  = io.StringIO()

    buf.write('''\
global
    log /dev/log local0
    daemon
    maxconn 4096
    # Admin socket lets Python query live health stats without restarting HAProxy
    stats socket /var/run/haproxy/admin.sock mode 660 level admin expose-fd listeners
    stats timeout 30s

defaults
    log     global
    mode    http
    option  httplog
    option  dontlognull
    timeout connect 5s
    timeout client  50s
    timeout server  50s

''')

    for lb in lbs:
        lb_id = lb['id']
        port  = lb['port']

        buf.write(f'frontend lb-{lb_id}\n')
        buf.write(f'    bind 0.0.0.0:{port}\n')
        buf.write(f'    default_backend backend-{lb_id}\n\n')

        buf.write(f'backend backend-{lb_id}\n')
        buf.write(f'    balance roundrobin\n')
        # httpchk sends GET / to each member every 5 seconds to detect failures
        buf.write(f'    option httpchk GET /\n')

        for m in lb['members']:
            vm_id = m['vm_id']
            ip    = m['vm_private_ip']
            mport = m['member_port']
            # inter 5s: check interval; fall 2: mark down after 2 failures; rise 2: mark up after 2 successes
            buf.write(f'    server vm-{vm_id} {ip}:{mport} check inter 5s fall 2 rise 2\n')

        buf.write('\n')

    return buf.getvalue()


def write_and_reload():
    # Write the new config first, then reload — HAProxy validates config before applying it
    config = generate_haproxy_config()
    with open(HAPROXY_CFG_PATH, 'w') as f:
        f.write(config)

    # reload (not restart) — HAProxy drains existing connections before switching to new config.
    # restart would immediately drop all active connections, causing client-visible errors.
    result = subprocess.run(
        ['systemctl', 'reload', 'haproxy'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'haproxy reload failed: {result.stderr.strip()}')


def get_member_health(lb_id):
    # Query the HAProxy stats socket to get live health status for each server in a backend.
    # The socket returns CSV where each row is one proxy+server combination.
    try:
        result = subprocess.run(
            ['socat', 'stdio', HAPROXY_SOCK],
            input='show stat\n',
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    if result.returncode != 0 or not result.stdout:
        return {}

    lines = result.stdout.strip().splitlines()
    if not lines:
        return {}

    # First line is: # pxname,svname,...  — strip the leading '#' to get column names
    header_line = lines[0].lstrip('# ')
    columns = header_line.split(',')

    try:
        col_pxname = columns.index('pxname')
        col_svname = columns.index('svname')
        col_status = columns.index('status')
        col_stot   = columns.index('stot')
    except ValueError:
        return {}

    backend_name = f'backend-{lb_id}'
    health = {}  # vm_id → { status, requests_served }

    for line in lines[1:]:
        if not line or line.startswith('#'):
            continue
        parts = line.split(',')
        if len(parts) <= max(col_pxname, col_svname, col_status, col_stot):
            continue
        if parts[col_pxname] != backend_name:
            continue
        svname = parts[col_svname]
        # Skip the synthetic BACKEND row — only care about individual server rows
        if svname in ('FRONTEND', 'BACKEND'):
            continue
        # Server names are "vm-{vm_id}" — strip the prefix to recover vm_id
        if not svname.startswith('vm-'):
            continue
        vm_id = svname[3:]
        raw_status = parts[col_status]
        # HAProxy reports UP/DOWN/NOLB/MAINT/no check — normalise to healthy/unhealthy
        is_healthy = raw_status.startswith('UP')
        try:
            requests = int(parts[col_stot])
        except (ValueError, IndexError):
            requests = 0
        health[vm_id] = {
            'haproxy_status':  raw_status,
            'status':          'healthy' if is_healthy else 'unhealthy',
            'requests_served': requests,
        }

    return health
