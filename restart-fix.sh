#!/bin/bash
# Run this after every reboot or WiFi reconnect before using mini-cloud.
# Restores runtime-only state: LVM loop device, IP forwarding, floating IPs.
# Run as khalid (uses passwordless sudo for the parts that need root).

set -e

# ── Step 1: Check WiFi IP ─────────────────────────────────────────────────────
CURRENT_IP=$(ip addr show wlp0s20f3 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
if [ -z "$CURRENT_IP" ]; then
    echo "ERROR: wlp0s20f3 has no IP — check WiFi connection"
    exit 1
fi
echo "Current IP : $CURRENT_IP"

# ── Step 2: LVM loop device ───────────────────────────────────────────────────
# The loop device backing the LVM VG is runtime-only — lost on every reboot.
LVM_IMG=/var/lib/mini-cloud-lvm.img
if [ -f "$LVM_IMG" ]; then
    if ! sudo losetup -j "$LVM_IMG" | grep -q loop; then
        LOOP=$(sudo losetup -f --show "$LVM_IMG")
        sudo pvscan --cache "$LOOP" 2>/dev/null || true
        sudo vgchange -ay mini-cloud-vg 2>/dev/null || true
        echo "LVM loop device re-attached: $LOOP"
    else
        echo "LVM loop device already active"
    fi
else
    echo "WARNING: $LVM_IMG not found — volumes will not work"
fi

# ── Step 3: Kernel routing ────────────────────────────────────────────────────
# Required for VM networking (bridges) and floating IP NAT (MASQUERADE/DNAT).
sudo sysctl -w net.ipv4.ip_forward=1 -q
sudo sysctl -w net.ipv4.conf.all.forwarding=1 -q
echo "IP forwarding enabled"

# ── Step 4: libvirtd ──────────────────────────────────────────────────────────
if ! sudo systemctl is-active libvirtd -q; then
    sudo systemctl start libvirtd
    echo "libvirtd started"
else
    echo "libvirtd already running"
fi

# ── Step 5: Restore floating IP state ────────────────────────────────────────
# mc-fip dummy interface and iptables DNAT/SNAT rules are lost on reboot.
# restore_fip.py reads the DB and re-applies all allocated/associated FIP state.
SCRIPT_DIR="$(dirname "$(realpath "$0")")/mini-cloud"
if [ -f "$SCRIPT_DIR/scripts/restore_fip.py" ]; then
    sudo "$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/scripts/restore_fip.py"
else
    echo "WARNING: restore_fip.py not found — floating IPs will not work"
fi

# ── Step 6: Verify ────────────────────────────────────────────────────────────
echo ""
echo "=== libvirtd ==="
sudo systemctl is-active libvirtd

echo ""
echo "=== KVM VMs ==="
sudo virsh list --all 2>/dev/null || echo "virsh not available"

echo ""
echo "=== mc-fip interface ==="
ip addr show mc-fip 2>/dev/null | grep inet || echo "no floating IPs allocated"

echo ""
echo "=== LVM volume group ==="
sudo vgdisplay mini-cloud-vg 2>/dev/null | grep -E "VG Name|VG Size|Free" || echo "VG not found"

echo ""
echo "=== Done. Start mini-cloud with: ==="
echo "   cd /home/khalid/ec2-local-cloud/mini-cloud"
echo "   source venv/bin/activate"
echo "   python3 run.py"
