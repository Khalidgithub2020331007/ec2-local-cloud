#!/usr/bin/env python3
"""
Re-apply floating IP state after a reboot.

Must run as root (or with passwordless sudo) because it calls ip and iptables.
Designed to be called by a systemd oneshot service on boot — before the Flask
app starts so the host already has the right IP/NAT state when requests arrive.

What it does:
  1. Enable IP forwarding (same as what the router does at runtime)
  2. Create the mc-fip dummy interface (lost on every reboot)
  3. Re-add each allocated FIP as /32 on mc-fip
  4. Re-add DNAT + SNAT + FORWARD rules for each associated FIP
"""

import os
import sys
import subprocess

# Allow running this script directly from the scripts/ folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import get_connection
from app.network.net_manager import (
    ensure_fip_interface,
    allocate_fip_on_host,
    add_fip_nat_rules,
)


def _enable_ip_forward():
    # Kernel drops forwarded packets by default — must be 1 for NAT to work.
    subprocess.run(
        ['sysctl', '-w', 'net.ipv4.ip_forward=1'],
        capture_output=True,
    )


def restore():
    print('[mini-cloud] restore_fip: starting')
    _enable_ip_forward()

    # Dummy interface is runtime-only — recreate it every boot.
    ensure_fip_interface()
    print('[mini-cloud] restore_fip: mc-fip interface ready')

    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT ip_address, private_ip, status FROM floating_ips'
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        fip        = row['ip_address']
        private_ip = row['private_ip']
        status     = row['status']

        # Every allocated/associated FIP must be bound to mc-fip so the host
        # kernel owns the IP and responds to ARP from the LAN router.
        try:
            allocate_fip_on_host(fip)
            print(f'[mini-cloud] restore_fip: bound {fip}/32 → mc-fip')
        except RuntimeError as exc:
            # "RTNETLINK answers: File exists" means it was already added —
            # harmless when re-running the script without a full reboot.
            print(f'[mini-cloud] restore_fip: skip {fip} ({exc})')

        if status == 'associated' and private_ip:
            try:
                add_fip_nat_rules(fip, private_ip)
                print(f'[mini-cloud] restore_fip: NAT {fip} → {private_ip}')
            except RuntimeError as exc:
                print(f'[mini-cloud] restore_fip: NAT failed {fip} ({exc})')

    print('[mini-cloud] restore_fip: done')


if __name__ == '__main__':
    restore()
