import subprocess
import ipaddress


def _run(cmd):
    # Prepend sudo -n — network ops need CAP_NET_ADMIN; user has passwordless sudo
    result = subprocess.run(['sudo', '-n'] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return result.stdout.strip()


def _run_soft(cmd):
    # Like _run but does not raise — used for idempotent/cleanup commands
    subprocess.run(['sudo', '-n'] + cmd, capture_output=True, text=True)


# ── Bridge / Network ──────────────────────────────────────────────────────────

def create_bridge(bridge_name, gateway, prefix_len):
    _run(['ip', 'link', 'add', bridge_name, 'type', 'bridge'])
    _run(['ip', 'addr', 'add', f'{gateway}/{prefix_len}', 'dev', bridge_name])
    _run(['ip', 'link', 'set', bridge_name, 'up'])


def start_dnsmasq(bridge_name, dhcp_start, dhcp_end):
    # dnsmasq serves DHCP on the bridge; PID stored so we can kill it on delete
    pid_file = f'/tmp/mc-dnsmasq-{bridge_name}.pid'
    _run([
        'dnsmasq',
        f'--interface={bridge_name}',
        '--bind-interfaces',
        f'--dhcp-range={dhcp_start},{dhcp_end},12h',
        f'--pid-file={pid_file}',
        '--log-facility=/dev/null',
        '--no-resolv',
        '--except-interface=lo',
    ])


def delete_bridge(bridge_name):
    pid_file = f'/tmp/mc-dnsmasq-{bridge_name}.pid'
    # Kill dnsmasq first — ignore errors if it was never started
    try:
        with open(pid_file) as f:
            pid = f.read().strip()
        _run(['kill', pid])
    except (FileNotFoundError, RuntimeError):
        pass

    _run_soft(['ip', 'link', 'set', bridge_name, 'down'])
    _run_soft(['ip', 'link', 'delete', bridge_name])


# ── Router / NAT ──────────────────────────────────────────────────────────────

def get_default_iface():
    # Parse "default via X.X.X.X dev <iface>" from ip route
    out = subprocess.run(
        ['ip', 'route', 'show', 'default'],
        capture_output=True, text=True,
    ).stdout
    for part in out.split():
        if part not in ('default', 'via', 'dev', 'proto', 'src', 'metric',
                        'onlink', 'static', 'dhcp'):
            # First token that is not a keyword after "dev" is the interface name
            pass
    # Simpler: split on 'dev' and take the next word
    if 'dev' in out:
        after_dev = out.split('dev')[1].strip().split()[0]
        return after_dev
    return None


def add_nat_rules(cidr, bridge_name, ext_iface):
    # Enable IP forwarding via sysctl — needs root
    subprocess.run(['sudo', '-n', 'sysctl', '-w', 'net.ipv4.ip_forward=1'],
                   capture_output=True, text=True)

    _run(['iptables', '-t', 'nat', '-A', 'POSTROUTING',
          '-s', cidr, '-o', ext_iface, '-j', 'MASQUERADE'])
    _run(['iptables', '-A', 'FORWARD',
          '-i', bridge_name, '-o', ext_iface, '-j', 'ACCEPT'])
    _run(['iptables', '-A', 'FORWARD',
          '-i', ext_iface, '-o', bridge_name,
          '-m', 'state', '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'])


def remove_nat_rules(cidr, bridge_name, ext_iface):
    _run_soft(['iptables', '-t', 'nat', '-D', 'POSTROUTING',
               '-s', cidr, '-o', ext_iface, '-j', 'MASQUERADE'])
    _run_soft(['iptables', '-D', 'FORWARD',
               '-i', bridge_name, '-o', ext_iface, '-j', 'ACCEPT'])
    _run_soft(['iptables', '-D', 'FORWARD',
               '-i', ext_iface, '-o', bridge_name,
               '-m', 'state', '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'])


# ── Floating IP / DNAT ────────────────────────────────────────────────────────

def ensure_fip_interface():
    # Idempotent — create the dummy interface once for floating IP aliases
    _run_soft(['ip', 'link', 'add', 'mc-fip', 'type', 'dummy'])
    _run_soft(['ip', 'link', 'set', 'mc-fip', 'up'])


def allocate_fip_on_host(fip):
    _run(['ip', 'addr', 'add', f'{fip}/32', 'dev', 'mc-fip'])


def release_fip_from_host(fip):
    _run_soft(['ip', 'addr', 'del', f'{fip}/32', 'dev', 'mc-fip'])


def add_fip_nat_rules(fip, private_ip):
    # PREROUTING DNAT:
    #   -t nat          → work in the NAT table
    #   -A PREROUTING   → append to the chain that runs BEFORE routing decisions
    #   -d fip          → match packets whose destination is the floating IP
    #   -j DNAT         → jump to the DNAT target (rewrite destination)
    #   --to-destination → replace destination address with the VM's private IP
    # Result: external traffic arriving for 192.168.0.225 gets its dst rewritten
    #         to 192.168.50.x before the kernel decides where to forward it.
    _run(['iptables', '-t', 'nat', '-A', 'PREROUTING',
          '-d', fip, '-j', 'DNAT', '--to-destination', private_ip])

    # POSTROUTING SNAT (inserted at position 1 so it fires BEFORE MASQUERADE):
    #   -t nat           → NAT table
    #   -I POSTROUTING 1 → INSERT at position 1 (head of chain) — critical: the
    #                      router's MASQUERADE rule was appended first; if SNAT
    #                      came after it, MASQUERADE would match first and win
    #   -s private_ip    → match packets whose source is the VM's private IP
    #   -j SNAT          → rewrite source address (stateful, unlike MASQUERADE)
    #   --to-source fip  → replace source with the floating IP
    # Result: replies FROM the VM appear to come from the floating IP, so the
    #         remote host sends its response back to fip (which DNAT handles).
    _run(['iptables', '-t', 'nat', '-I', 'POSTROUTING', '1',
          '-s', private_ip, '-j', 'SNAT', '--to-source', fip])

    # FORWARD ACCEPT for new inbound connections:
    #   -A FORWARD  → append to the FORWARD chain (packets being routed)
    #   -d private_ip → match after DNAT has rewritten the destination
    #   -j ACCEPT   → allow the packet through (default FORWARD policy may be DROP)
    # Without this rule, new TCP connections to the floating IP are dropped at
    # the FORWARD chain even though DNAT correctly rewrote the destination.
    _run(['iptables', '-A', 'FORWARD',
          '-d', private_ip, '-j', 'ACCEPT'])


def remove_fip_nat_rules(fip, private_ip):
    # Remove all three rules that add_fip_nat_rules installed.
    # _run_soft is used so a missing rule (e.g. partial failure during associate)
    # does not abort the disassociate operation.
    _run_soft(['iptables', '-t', 'nat', '-D', 'PREROUTING',
               '-d', fip, '-j', 'DNAT', '--to-destination', private_ip])
    _run_soft(['iptables', '-t', 'nat', '-D', 'POSTROUTING',
               '-s', private_ip, '-j', 'SNAT', '--to-source', fip])
    _run_soft(['iptables', '-D', 'FORWARD',
               '-d', private_ip, '-j', 'ACCEPT'])


# ── Network Interfaces — read VM NICs from libvirt ────────────────────────────

def get_vm_interfaces(libvirt_name):
    # Returns list of {mac, network, ip} for a given libvirt domain
    ifaces = {}

    # domiflist gives MAC + network/bridge per NIC
    result = subprocess.run(
        ['virsh', 'domiflist', libvirt_name],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 5:
                mac = parts[0]
                ifaces[mac] = {'mac': mac, 'network': parts[2], 'ip': None}

    # domifaddr gives MAC + IP from DHCP lease
    result = subprocess.run(
        ['virsh', 'domifaddr', libvirt_name],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines()[2:]:
            parts = line.split()
            # Format: name  mac  protocol  address/prefix
            if len(parts) >= 4 and parts[2] == 'ipv4':
                mac = parts[1]
                ip  = parts[3].split('/')[0]
                if mac in ifaces:
                    ifaces[mac]['ip'] = ip
                else:
                    ifaces[mac] = {'mac': mac, 'network': 'unknown', 'ip': ip}

    return list(ifaces.values())


# ── CIDR helpers ──────────────────────────────────────────────────────────────

def parse_cidr(cidr_str):
    # Returns (network, gateway, dhcp_start, dhcp_end, prefix_len)
    # Raises ValueError for invalid CIDR.
    net = ipaddress.IPv4Network(cidr_str, strict=False)
    hosts = list(net.hosts())
    if len(hosts) < 12:
        raise ValueError('CIDR too small — need at least /28 for a usable DHCP range')
    gateway    = str(hosts[0])
    dhcp_start = str(hosts[9])   # gateway+9 leaves room for static assignments
    dhcp_end   = str(hosts[-1])
    prefix_len = net.prefixlen
    return str(net), gateway, dhcp_start, dhcp_end, prefix_len
