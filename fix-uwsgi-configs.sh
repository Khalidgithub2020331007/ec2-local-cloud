#!/bin/bash
# Mini Cloud health check — verifies all system dependencies are in place.
# Run any time you suspect something is broken before starting mini-cloud.

set -e

PASS=0
FAIL=0

check() {
    local label=$1
    local cmd=$2
    if eval "$cmd" &>/dev/null; then
        echo "  OK  $label"
        PASS=$((PASS+1))
    else
        echo " FAIL $label"
        FAIL=$((FAIL+1))
    fi
}

echo "=== Mini Cloud Health Check ==="
echo ""

echo "-- System Services --"
check "libvirtd running"       "sudo systemctl is-active libvirtd -q"
check "dnsmasq installed"      "which dnsmasq"
check "haproxy installed"      "which haproxy"

echo ""
echo "-- KVM / Virtualisation --"
check "KVM device exists"      "[ -e /dev/kvm ]"
check "virsh available"        "which virsh"
check "qemu-img available"     "which qemu-img"
check "genisoimage available"  "which genisoimage"

echo ""
echo "-- Networking --"
check "iptables available"     "which iptables"
check "IP forwarding on"       "[ \"\$(cat /proc/sys/net/ipv4/ip_forward)\" = '1' ]"

echo ""
echo "-- Storage --"
check "LVM tools installed"    "which lvcreate"
check "mini-cloud-vg exists"   "sudo vgdisplay mini-cloud-vg -q"

echo ""
echo "-- Mini Cloud App --"
check "Python venv exists"     "[ -f /home/khalid/ec2-local-cloud/mini-cloud/venv/bin/python3 ]"
check "Database file exists"   "[ -f /home/khalid/ec2-local-cloud/mini-cloud/database/cloud.db ]"
check "Port 5001 free"         "! lsof -i :5001 -t"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Fix failed checks, then run: bash restart-fix.sh"
    exit 1
else
    echo ""
    echo "All checks passed. Ready to start:"
    echo "   cd /home/khalid/ec2-local-cloud/mini-cloud"
    echo "   source venv/bin/activate && python3 run.py"
fi
