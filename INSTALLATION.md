# Installation Guide — DevStack on Your Machine
### Machine: Acer TravelMate P215-53 | Ubuntu 24.04 LTS | 8GB RAM | WiFi only

---

## Pre-verified System Info

```
CPU:       16 cores, Intel VMX enabled ✅
KVM:       /dev/kvm exists ✅
OS:        Ubuntu 24.04.4 LTS (Noble) ✅
Host IP:   10.200.194.146
Interface: wlp0s20f3 (WiFi - active)
Ethernet:  enp43s0 (unplugged - ignore)
Docker:    Installed - must stop before DevStack
```

---

## STEP 1 — Stop Docker (Prevents iptables Conflicts)

Docker and DevStack both manage iptables/netfilter. Running both causes networking to break silently.

```bash
sudo systemctl stop docker
sudo systemctl stop docker.socket
sudo systemctl stop containerd

# Verify they are stopped
sudo systemctl is-active docker
# Should output: inactive
```

> Do NOT uninstall Docker. Just stop it. You can restart it after DevStack is running (though not recommended to run both simultaneously).

---

## STEP 2 — System Update and Dependencies

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt autoremove -y

sudo apt install -y \
  git curl wget vim net-tools htop \
  python3 python3-pip build-essential \
  libssl-dev libffi-dev python3-dev \
  bridge-utils qemu-kvm libvirt-daemon-system \
  libvirt-clients cpu-checker iptables
```

---

## STEP 3 — Add Swap Space (Critical — 8GB RAM)

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

## STEP 4 — Create the `stack` User

DevStack must NOT run as root. It needs its own user.

```bash
sudo useradd -s /bin/bash -d /opt/stack -m stack
echo "stack ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/stack
sudo chmod +x /opt/stack

# Set a password (useful for SSH login to stack user)
sudo passwd stack
# Enter: Stack@123 (or your choice)

# Switch to stack user
sudo su - stack
```

**From here onward, all commands run as the `stack` user.**

---

## STEP 5 — Clone DevStack

```bash
# You are now logged in as stack user at /opt/stack
git clone https://opendev.org/openstack/devstack -b stable/2024.2
cd devstack
```

> `stable/2024.2` is the **Dalmatian** release — compatible with Ubuntu 24.04.

---

## STEP 6 — Copy the Configuration File

```bash
# Copy the prepared config (from your project folder)
cp /home/khalid/ec2-local-cloud/configs/local.conf /opt/stack/devstack/local.conf

# Verify it looks correct
head -20 /opt/stack/devstack/local.conf
```

---

## STEP 7 — Run DevStack

```bash
cd /opt/stack/devstack
./stack.sh
```

**This will take 30–60 minutes.** It downloads, compiles, and starts all OpenStack services.

### What to watch for during installation:

```
# These lines confirm progress:
[Call Trace]          - Normal, shows what's running
+functions::...       - Function calls, normal
Creating network...   - Neutron starting up
Starting Nova...      - Compute service starting
```

### If it fails, check the log:
```bash
tail -100 /opt/stack/logs/stack.sh.log
```

---

## STEP 8 — Verify Successful Installation

### Expected output at the end of `stack.sh`:

```
=========================
DevStack Component Timing
=========================
...
This is your host IP address: 10.200.194.146
Horizon is now available at http://10.200.194.146/dashboard
Keystone is serving at http://10.200.194.146/identity/
The default users are: admin and demo
The password: Admin@OpenStack1
```

### Verify all services are running:
```bash
sudo systemctl list-units 'devstack@*' --all --no-pager
```

All services should show `active (running)`.

---

## STEP 9 — First Login

Open your browser and go to:

```
http://10.200.194.146/dashboard
```

| Field | Value |
|-------|-------|
| Domain | Default |
| Username | admin |
| Password | Admin@OpenStack1 |

---

## STEP 10 — Load CLI Credentials

```bash
# Still as stack user (or open new terminal and: sudo su - stack)
source /opt/stack/devstack/openrc admin admin

# Test it works
openstack service list
openstack server list
```

---

## After a Reboot

DevStack does not auto-start. After every reboot:

```bash
# 1. Stop docker first
sudo systemctl stop docker docker.socket containerd

# 2. Switch to stack user
sudo su - stack

# 3. Rejoin the stack
cd /opt/stack/devstack
./rejoin-stack.sh
```

---

## Troubleshooting

### Stack fails with "address already in use"
```bash
# Something is using a port (likely Docker)
sudo systemctl stop docker
sudo ./unstack.sh
./stack.sh
```

### Nova instances stuck in "spawning"
```bash
sudo systemctl restart devstack@n-cpu
sudo journalctl -u devstack@n-cpu -n 50
```

### No network inside VMs / can't ping
```bash
# Restart Neutron agents
sudo systemctl restart devstack@q-svc
sudo systemctl restart devstack@q-agt
sudo systemctl restart devstack@q-dhcp
sudo systemctl restart devstack@q-l3
```

### Dashboard shows 500 error
```bash
sudo systemctl restart apache2
```

### Redo from scratch (if something is badly broken)
```bash
cd /opt/stack/devstack
./unstack.sh          # stop everything
./clean.sh            # clean database and config
./stack.sh            # fresh start (re-runs full install, ~40 min)
```

---

## Service → Port Reference

| Service | URL | Purpose |
|---------|-----|---------|
| Horizon Dashboard | http://10.200.194.146/dashboard | Web GUI |
| Keystone API | http://10.200.194.146:5000 | Identity/Auth |
| Nova API | http://10.200.194.146:8774 | Compute |
| Glance API | http://10.200.194.146:9292 | Images |
| Cinder API | http://10.200.194.146:8776 | Volumes |
| Neutron API | http://10.200.194.146:9696 | Networking |
| Placement API | http://10.200.194.146:8778 | Placement |
| Nova VNC Proxy | http://10.200.194.146:6080 | Console access |
