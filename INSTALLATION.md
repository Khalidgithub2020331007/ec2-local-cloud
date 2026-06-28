# Installation Guide — Mini Cloud on Your Machine
### Machine: Acer TravelMate P215-53 | Ubuntu 24.04 LTS | 8GB RAM | WiFi only

---

## Pre-verified System Info

```
CPU:       16 cores, Intel VMX enabled ✅
KVM:       /dev/kvm exists ✅
OS:        Ubuntu 24.04.4 LTS (Noble) ✅
Host IP:   (check with: ip addr show wlp0s20f3 | grep 'inet ')
Interface: wlp0s20f3 (WiFi - active)
Ethernet:  enp43s0 (unplugged - ignore)
```

---

## STEP 1 — System Update and Dependencies

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt autoremove -y

sudo apt install -y \
  git curl wget vim net-tools htop \
  python3 python3-pip python3-venv build-essential \
  qemu-kvm libvirt-daemon-system libvirt-clients \
  cpu-checker bridge-utils iptables dnsmasq \
  lvm2 genisoimage haproxy websockify \
  setfacl acl
```

---

## STEP 2 — Verify KVM Support

```bash
kvm-ok
# Expected: INFO: /dev/kvm exists — KVM acceleration can be used

# Verify libvirt is running
sudo systemctl enable --now libvirtd
sudo systemctl is-active libvirtd
# Expected: active
```

---

## STEP 3 — Add Your User to the libvirt Group

```bash
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER

# Log out and back in (or use newgrp)
newgrp libvirt
```

---

## STEP 4 — Add Swap Space (Critical — 8GB RAM)

```bash
# Check if swap already exists
free -h

# If no swap, create 8GB swap file:
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Verify
free -h
# Should show ~8GB swap
```

---

## STEP 5 — Set Up LVM Volume Group for Block Storage

```bash
# Create a 20GB backing file for LVM (avoids needing a spare partition)
sudo fallocate -l 20G /var/lib/mini-cloud-lvm.img
LOOP_DEV=$(sudo losetup -f --show /var/lib/mini-cloud-lvm.img)
echo "Loop device: $LOOP_DEV"   # e.g. /dev/loop0

# Create the physical volume and volume group
sudo pvcreate $LOOP_DEV
sudo vgcreate mini-cloud-vg $LOOP_DEV

# Verify
sudo vgdisplay mini-cloud-vg
```

> The loop device is recreated on reboot by `mini-cloud-startup.sh`. See Step 9.

---

## STEP 6 — Clone the Project

```bash
# If the project is already on disk, skip this step
cd /home/khalid
git clone <your-repo-url> ec2-local-cloud
cd ec2-local-cloud/mini-cloud
```

---

## STEP 7 — Set Up Python Virtual Environment

```bash
cd /home/khalid/ec2-local-cloud/mini-cloud

python3 -m venv venv
source venv/bin/activate

pip install flask==3.0.0 pyjwt==2.8.0 werkzeug==3.0.1 \
            libvirt-python==10.0.0 cryptography
```

---

## STEP 8 — Configure Passwordless Sudo for Network Operations

Mini cloud needs to run `ip`, `iptables`, `dnsmasq`, `virsh`, and `lvcreate` as root.

```bash
sudo tee /etc/sudoers.d/mini-cloud > /dev/null <<'EOF'
khalid ALL=(ALL) NOPASSWD: /usr/sbin/ip, /usr/sbin/iptables, \
  /usr/sbin/dnsmasq, /usr/bin/virsh, /usr/sbin/lvcreate, \
  /usr/sbin/lvremove, /usr/sbin/lvdisplay, /usr/bin/qemu-img, \
  /usr/bin/genisoimage, /usr/bin/setfacl, /usr/sbin/sysctl, \
  /bin/kill, /usr/bin/systemctl
EOF

sudo chmod 440 /etc/sudoers.d/mini-cloud
```

---

## STEP 9 — Create the Startup Script

This script runs before mini-cloud on every boot to restore runtime-only state (loop device, IP forwarding, floating IP rules).

```bash
sudo tee /usr/local/bin/mini-cloud-startup.sh > /dev/null <<'EOF'
#!/bin/bash
set -e

# Re-attach LVM loop device if missing
if ! losetup -j /var/lib/mini-cloud-lvm.img | grep -q loop; then
    LOOP=$(losetup -f --show /var/lib/mini-cloud-lvm.img)
    pvscan --cache "$LOOP"
    vgchange -ay mini-cloud-vg
fi

# Enable IP forwarding — required for NAT (floating IPs) and VM routing
sysctl -w net.ipv4.ip_forward=1

# Restore floating IP state (iptables DNAT/SNAT rules + mc-fip interface)
/home/khalid/ec2-local-cloud/mini-cloud/venv/bin/python3 \
    /home/khalid/ec2-local-cloud/mini-cloud/scripts/restore_fip.py

echo "[mini-cloud] startup complete"
EOF

sudo chmod +x /usr/local/bin/mini-cloud-startup.sh
```

Create the systemd unit:

```bash
sudo tee /etc/systemd/system/mini-cloud-startup.service > /dev/null <<'EOF'
[Unit]
Description=Mini Cloud pre-start (LVM loop + IP forwarding + floating IPs)
Before=mini-cloud.service
After=network-online.target libvirtd.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mini-cloud-startup.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mini-cloud-startup
```

---

## STEP 10 — Create the Mini Cloud systemd Service

```bash
sudo tee /etc/systemd/system/mini-cloud.service > /dev/null <<'EOF'
[Unit]
Description=Mini Cloud API Server
After=libvirtd.service mini-cloud-startup.service network-online.target
Requires=libvirtd.service mini-cloud-startup.service

[Service]
Type=simple
User=khalid
WorkingDirectory=/home/khalid/ec2-local-cloud/mini-cloud
ExecStart=/home/khalid/ec2-local-cloud/mini-cloud/venv/bin/python3 run.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mini-cloud
```

---

## STEP 11 — First Run

```bash
# Run the startup script once manually (before first boot cycle)
sudo bash /usr/local/bin/mini-cloud-startup.sh

# Start mini-cloud
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

Expected output:
```
 * Running on http://0.0.0.0:5001
 * Database initialized
```

Open browser: `http://localhost:5001`

Default login: `admin` / `Admin1234`

---

## After a Reboot

Everything is automatic if systemd services are enabled:

```bash
# Verify services started
sudo systemctl is-active mini-cloud-startup
sudo systemctl is-active mini-cloud
sudo systemctl is-active libvirtd

# Check the API is responding
curl -s http://localhost:5001/api/v1/auth/health
# Expected: {"status": "ok"}
```

---

## Service → Port Reference

| Service | URL | Purpose |
|---------|-----|---------|
| Mini Cloud API + Dashboard | http://localhost:5001 | Main web interface and REST API |
| VNC WebSocket proxy | ws://localhost:6100+ | Browser-based VM console |

---

## Troubleshooting

### libvirtd not running
```bash
sudo systemctl start libvirtd
sudo systemctl status libvirtd
```

### LVM volume group missing after reboot
```bash
sudo losetup -f --show /var/lib/mini-cloud-lvm.img
sudo vgchange -ay mini-cloud-vg
sudo vgdisplay mini-cloud-vg
```

### Floating IPs not working after reboot
```bash
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
sudo python3 scripts/restore_fip.py
```

### VM fails to launch (permission denied)
```bash
# libvirt-qemu user needs ACL access to disk files
sudo setfacl -m u:libvirt-qemu:rwx /home/khalid/ec2-local-cloud/mini-cloud/storage/instances/
```

### Port 5001 already in use
```bash
sudo lsof -i :5001
kill <PID>
```
