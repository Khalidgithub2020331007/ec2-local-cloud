# Project Implementation Plan
## Local EC2 Replica — Mini Cloud (Flask + libvirt/KVM + LVM + iptables)
### Machine: Acer TravelMate P215-53 | Ubuntu 24.04 LTS | 8GB RAM | 16 CPU | WiFi

> **Note:** This project was originally planned around DevStack (OpenStack). It was redesigned
> and implemented as a standalone mini-cloud system — no OpenStack, no DevStack, no MySQL,
> no RabbitMQ. Every feature is built directly on Linux kernel tools.

---

## Project Timeline Overview

| Phase | Title | Status |
|-------|-------|--------|
| Phase 1 | Environment Preparation | ✅ Complete |
| Phase 2 | Mini Cloud Core (Auth + Compute + Images) | ✅ Complete |
| Phase 3 | Networking (Bridges + Floating IPs + Security Groups) | ✅ Complete |
| Phase 4 | Storage (LVM Volumes + Snapshots) | ✅ Complete |
| Phase 5 | Advanced Features (Load Balancer + Autoscaling + IAM + Quotas) | ✅ Complete |
| Phase 6 | Monitoring + VNC Console | ✅ Complete |
| Phase 7 | Testing & Documentation | ✅ Complete |

---

## Architecture Summary

```
Browser → Flask API (port 5001) → {
  libvirt/KVM  → Virtual Machines
  LVM          → Block Volumes + Snapshots
  Linux Bridge → VM Networks (dnsmasq DHCP)
  iptables     → Security Groups + Floating IP NAT
  HAProxy      → Load Balancers
  SQLite       → All State (cloud.db)
}
```

---

# PHASE 1 — Environment Preparation
> **Goal:** Get the host machine 100% stable with all dependencies installed.
> **Rule:** Do NOT proceed to Phase 2 unless KVM, libvirt, LVM, and dnsmasq are all working.

---

## Step 1.1 — Full System Update
> **Why:** DevStack downloads packages during install. If apt cache is stale or there are held-back upgrades, the install breaks mid-way. Do this first, once.

### Sub-step 1.1.1 — Refresh package index
```bash
sudo apt update
```
- **Expected:** Lines like `Hit:1 http://... noble InRelease` — no errors
- **If fails:** Check internet connection. Run `ping 8.8.8.8`

### Sub-step 1.1.2 — Upgrade all installed packages
```bash
sudo apt full-upgrade -y
```
- **Expected:** Packages upgraded, no broken dependencies
- **If fails:** Run `sudo apt --fix-broken install` then retry

### Sub-step 1.1.3 — Remove orphaned packages
```bash
sudo apt autoremove -y
sudo apt autoclean
```
- **Expected:** Clean output, no errors

### Sub-step 1.1.4 — Confirm no upgrades remain
```bash
sudo apt list --upgradable 2>/dev/null | wc -l
```
- **Expected output:** `1` (just the header line means nothing left to upgrade)

---

## Step 1.2 — Install Required System Packages
> **Why:** DevStack expects Python dev headers, KVM, bridge-utils, and git to exist before it runs. Missing any one of these causes a cryptic mid-install failure.

### Sub-step 1.2.1 — Install build and Python tools
```bash
sudo apt install -y \
  git curl wget vim net-tools htop \
  python3 python3-pip python3-dev \
  build-essential libssl-dev libffi-dev
```
- **Verify:**
```bash
git --version       # git version 2.43.x
python3 --version   # Python 3.12.x
```

### Sub-step 1.2.2 — Install KVM and virtualization stack
```bash
sudo apt install -y \
  qemu-kvm libvirt-daemon-system \
  libvirt-clients cpu-checker virt-manager
```
- **Verify:**
```bash
kvm-ok
# INFO: /dev/kvm exists
# KVM acceleration can be used
```
- **If fails:** Reboot, enter BIOS, enable Intel VT-x or AMD-V

### Sub-step 1.2.3 — Install networking tools
```bash
sudo apt install -y bridge-utils iptables iputils-ping dnsutils
```
- **Verify:**
```bash
brctl --version     # bridge-utils v1.x
iptables --version  # iptables v1.8.x
```

### Sub-step 1.2.4 — Add current user to KVM/libvirt groups
```bash
sudo usermod -aG kvm $USER
sudo usermod -aG libvirt $USER
```
- **Note:** Log out and back in (or `newgrp libvirt`) for groups to take effect
- **Verify:**
```bash
groups $USER
# Should contain: kvm libvirt
```

---

## Step 1.3 — Stop and Disable Docker
> **Why:** Docker installs its own iptables chains and manages the `docker0` bridge. When DevStack starts Neutron, it also rewrites iptables rules. These two systems fight each other and silently break VM networking. Must be stopped before `stack.sh` runs.

### Sub-step 1.3.1 — Stop all Docker services
```bash
sudo systemctl stop docker
sudo systemctl stop docker.socket
sudo systemctl stop containerd
```

### Sub-step 1.3.2 — Disable Docker from auto-starting
```bash
sudo systemctl disable docker
sudo systemctl disable docker.socket
sudo systemctl disable containerd
```

### Sub-step 1.3.3 — Flush Docker's iptables rules
```bash
sudo iptables -t nat -F
sudo iptables -t filter -F
sudo iptables -t mangle -F
```
- **Why:** Even after stopping Docker, its iptables rules remain in memory. Flush them so Neutron starts with a clean firewall state.

### Sub-step 1.3.4 — Verify Docker is fully stopped
```bash
sudo systemctl is-active docker
sudo systemctl is-active containerd
# Both should output: inactive
```
- **Verify no docker processes:**
```bash
ps aux | grep docker | grep -v grep
# Should be empty
```

> **Note to self:** To restore Docker after project submission:
> `sudo systemctl enable --now docker`

---

## Step 1.4 — Create Swap Space
> **Why:** OpenStack services (Nova, Neutron, Keystone, Glance, Cinder, Horizon) together use ~4–5GB RAM. When you also run 2–3 VMs, the system will hit 8GB. Without swap, the Linux OOM killer randomly terminates OpenStack services mid-operation. Swap gives breathing room.

### Sub-step 1.4.1 — Check if swap already exists
```bash
free -h
swapon --show
```
- **If swap already shows:** skip to sub-step 1.4.5
- **If no swap row / empty output:** continue below

### Sub-step 1.4.2 — Allocate the swap file
```bash
sudo fallocate -l 8G /swapfile
```
- **If fallocate fails** (some filesystems): `sudo dd if=/dev/zero of=/swapfile bs=1G count=8`

### Sub-step 1.4.3 — Secure and format the swap file
```bash
sudo chmod 600 /swapfile
sudo mkswap /swapfile
```
- **Expected:** `Setting up swapspace version 1, size = 8 GiB`

### Sub-step 1.4.4 — Activate swap immediately
```bash
sudo swapon /swapfile
```

### Sub-step 1.4.5 — Make swap permanent across reboots
```bash
# Check if entry already exists to avoid duplicates
grep swapfile /etc/fstab
# If no output, add it:
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Sub-step 1.4.6 — Tune swappiness for performance
```bash
# Lower swappiness = use swap only when truly needed (better for SSD)
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Sub-step 1.4.7 — Verify final swap state
```bash
free -h
# Swap row should show: 8.0G total
swapon --show
# Should show /swapfile with size 8G
```

---

## Step 1.5 — Create the Dedicated `stack` User
> **Why:** DevStack explicitly checks that it is NOT running as root and exits if it is. It needs a home at `/opt/stack` with passwordless sudo access. This is non-negotiable — the installer is designed this way.

### Sub-step 1.5.1 — Create the stack user with correct home directory
```bash
sudo useradd -s /bin/bash -d /opt/stack -m stack
```
- **`-d /opt/stack`** sets the home directory
- **`-m`** creates the directory if it doesn't exist

### Sub-step 1.5.2 — Set a password for the stack user
```bash
sudo passwd stack
# Enter password: Stack@Project2024
```
- **Why:** Needed if you ever SSH directly into the stack user session

### Sub-step 1.5.3 — Grant passwordless sudo
```bash
echo "stack ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/stack
sudo chmod 440 /etc/sudoers.d/stack
```

### Sub-step 1.5.4 — Make /opt/stack executable
```bash
sudo chmod +x /opt/stack
```

### Sub-step 1.5.5 — Verify the stack user works correctly
```bash
id stack
# uid=1001(stack) gid=1001(stack) groups=1001(stack)

sudo su - stack -c "whoami"
# stack

sudo su - stack -c "sudo whoami"
# root   ← confirms passwordless sudo works
```

---

## Phase 1 Checklist

- [ ] **1.1** System fully updated, no pending upgrades
- [ ] **1.2.1** git, python3, build tools installed
- [ ] **1.2.2** kvm-ok confirms KVM works
- [ ] **1.2.3** bridge-utils, iptables installed
- [ ] **1.2.4** Current user added to kvm and libvirt groups
- [ ] **1.3.1** Docker stopped
- [ ] **1.3.2** Docker disabled from autostart
- [ ] **1.3.3** iptables flushed
- [ ] **1.3.4** No docker processes running
- [ ] **1.4.7** `free -h` shows 8GB swap
- [ ] **1.5.5** `stack` user created, passwordless sudo confirmed

---

---

# PHASE 2 — DevStack Installation
> **Goal:** Run `./stack.sh` and get all OpenStack services running stably.
> **Rule:** Always run as `stack` user. Never as root or your normal user.

---

## Step 2.1 — Switch to Stack User and Prepare
> **Why:** Every action from here until the end of Phase 2 must be done as the `stack` user. Running DevStack commands as your normal user or root causes permission errors that are hard to debug.

### Sub-step 2.1.1 — Switch to the stack user
```bash
sudo su - stack
```
- **Verify:** `whoami` → `stack`, `pwd` → `/opt/stack`

### Sub-step 2.1.2 — Confirm internet access from stack user
```bash
ping -c 3 8.8.8.8
curl -s https://opendev.org | head -5
```
- **Why:** DevStack clones 15+ git repos during installation. No internet = failed install.

### Sub-step 2.1.3 — Check current directory and disk space
```bash
pwd
# /opt/stack

df -h /opt/stack
# Available should be at least 50GB
```

---

## Step 2.2 — Clone DevStack Repository
> **Why:** `stable/2024.2` (Dalmatian) is the release that officially supports Ubuntu 24.04 with Python 3.12. Earlier branches (`stable/2024.1`) fail on Noble because they have Python 3.10-era syntax incompatibilities.

### Sub-step 2.2.1 — Clone the stable branch
```bash
git clone https://opendev.org/openstack/devstack -b stable/2024.2
```
- **Expected:** `Cloning into 'devstack'...` then `Branch 'stable/2024.2' set up to track...`
- **Time:** 1–2 minutes

### Sub-step 2.2.2 — Confirm the correct branch was cloned
```bash
cd devstack
git branch
# * (HEAD detached at ...) or * stable/2024.2

git log --oneline -3
# Shows recent commits from the stable/2024.2 branch
```

### Sub-step 2.2.3 — Check the stack.sh script exists and is executable
```bash
ls -la stack.sh
# -rwxr-xr-x ... stack.sh
```

---

## Step 2.3 — Place and Verify local.conf
> **Why:** `local.conf` is the single file that tells DevStack what services to enable, what passwords to use, and how to configure networking. A wrong IP or interface name here means networking breaks silently after a 45-minute install.

### Sub-step 2.3.1 — Copy the prepared config file
```bash
cp /home/khalid/ec2-local-cloud/configs/local.conf /opt/stack/devstack/local.conf
```

### Sub-step 2.3.2 — Verify HOST_IP matches your live WiFi IP
```bash
# Check your current WiFi IP
ip addr show wlp0s20f3 | grep 'inet '
# inet 10.200.194.146/22 ...

# Check what local.conf has
grep HOST_IP /opt/stack/devstack/local.conf
# HOST_IP=10.200.194.146
```
- **If IP has changed** (DHCP reassigned): edit local.conf with `vim local.conf` and update HOST_IP

### Sub-step 2.3.3 — Verify FLAT_INTERFACE is correct
```bash
grep FLAT_INTERFACE /opt/stack/devstack/local.conf
# FLAT_INTERFACE=wlp0s20f3

# Confirm interface name is exactly right
ip link show wlp0s20f3
# Should show the interface without "Device not found" error
```

### Sub-step 2.3.4 — Verify disabled services are listed
```bash
grep "disable_service" /opt/stack/devstack/local.conf
# Should show swift, heat, ceilometer, tempest, ovn lines
```

### Sub-step 2.3.5 — Verify password is set
```bash
grep ADMIN_PASSWORD /opt/stack/devstack/local.conf
# Should not be empty
```

---

## Step 2.4 — Run the DevStack Installer
> **Why:** `stack.sh` is the master script. It installs Python packages, clones service repos, creates databases, configures Apache, and starts all services. Takes 30–60 minutes on first run.

### Sub-step 2.4.1 — Open a log monitoring terminal (second terminal)
```bash
# In a NEW terminal window (keep this open while stack.sh runs):
sudo su - stack
tail -f /opt/stack/logs/stack.sh.log
```

### Sub-step 2.4.2 — Run the installer
```bash
# In the FIRST terminal (as stack user in /opt/stack/devstack):
./stack.sh 2>&1 | tee /tmp/stack_install.log
```
- **Time:** 30–60 minutes
- **Do not interrupt** — CTRL+C mid-run leaves the system in a broken half-installed state

### Sub-step 2.4.3 — Monitor key installation milestones
Watch for these lines in the log (they confirm progress):

```
Installing from git:            ← downloading OpenStack source
Configuring keystone:           ← identity service being set up
Configuring nova:               ← compute being set up
Configuring neutron:            ← networking being set up
Creating initial OpenStack data ← databases and default data created
```

### Sub-step 2.4.4 — Confirm successful completion
```bash
# At the end of stack.sh output, look for:
tail -30 /tmp/stack_install.log
```

**Expected success block:**
```
=========================
DevStack Component Timing
=========================
...
This is your host IP address: 10.200.194.146
Horizon is now available at http://10.200.194.146/dashboard
Keystone is serving at http://10.200.194.146/identity/
The default users are: admin and demo
The password: Admin1234OpenStack
```

### Sub-step 2.4.5 — What to do if stack.sh fails
```bash
# Read the last error in the log
tail -50 /opt/stack/logs/stack.sh.log

# Common fix 1: Address already in use (Docker leftover)
sudo iptables -t nat -F && sudo iptables -F
./unstack.sh && ./stack.sh

# Common fix 2: Python package conflict
./unstack.sh
pip3 cache purge
./stack.sh

# Common fix 3: Network issue / git clone failed
./unstack.sh
# Check internet: ping opendev.org
./stack.sh   # just re-run, it resumes where it can
```

---

## Step 2.5 — Verify All Services Are Running
> **Why:** `stack.sh` finishing without error does not guarantee all services are healthy. Some services start after the script exits. Verify each one explicitly.

### Sub-step 2.5.1 — List all DevStack systemd units
```bash
sudo systemctl list-units 'devstack@*' --all --no-pager
```

### Sub-step 2.5.2 — Confirm each critical service is active

Run this check script:
```bash
SERVICES="key n-api n-cpu n-cond n-sch g-api c-api c-vol q-svc q-agt q-dhcp q-l3 placement-api"
for svc in $SERVICES; do
    STATUS=$(sudo systemctl is-active devstack@$svc 2>/dev/null)
    echo "$svc: $STATUS"
done
```
- **Expected:** All print `active`
- **If any prints `failed` or `inactive`:** restart it:
```bash
sudo systemctl restart devstack@<service-name>
sudo journalctl -u devstack@<service-name> -n 30
```

### Sub-step 2.5.3 — Verify API endpoints respond
```bash
source /opt/stack/devstack/openrc admin admin

# Keystone
openstack token issue
# Should return a token table

# Nova (compute)
openstack compute service list
# Should list nova-conductor, nova-scheduler, nova-compute

# Neutron (network)
openstack network agent list
# Should list linuxbridge agents

# Glance (images)
openstack image list
# Should list the CirrOS image

# Cinder (volumes)
openstack volume service list
# Should list cinder-scheduler, cinder-volume
```

---

## Step 2.6 — First Login to Horizon Dashboard
> **Why:** Horizon is the visual proof that OpenStack is working. It also lets you see resources graphically — important for screenshots in your final report.

### Sub-step 2.6.1 — Open the dashboard in your browser
```
URL: http://10.200.194.146/dashboard
```

### Sub-step 2.6.2 — Login with admin credentials

| Field | Value |
|-------|-------|
| Domain | Default |
| Username | admin |
| Password | Admin1234OpenStack |

### Sub-step 2.6.3 — Confirm the overview page loads
- You should see the **Project Overview** with usage stats (0 instances, 0 VCPUs used, etc.)
- Left sidebar should show: Compute, Network, Volumes sections

### Sub-step 2.6.4 — Verify the admin panel is accessible
- Click **Admin** in top navigation
- Should show system-wide usage, flavors, images, networks

### Sub-step 2.6.5 — Take Screenshot #1
- **File:** `screenshots/01_dashboard_overview.png`
- Shows: Horizon dashboard logged in as admin

---

## Phase 2 Checklist

- [ ] **2.1** Switched to stack user, internet working, disk space confirmed
- [ ] **2.2** DevStack cloned from `stable/2024.2`
- [ ] **2.3** `local.conf` placed, HOST_IP and FLAT_INTERFACE verified correct
- [ ] **2.4** `./stack.sh` completed — success message appeared
- [ ] **2.5.2** All 12 critical services show `active`
- [ ] **2.5.3** All 5 API endpoints respond without error
- [ ] **2.6.3** Horizon dashboard loads at `http://10.200.194.146/dashboard`
- [ ] **2.6.5** Screenshot #1 taken

---

---

# PHASE 3 — Core Infrastructure Setup
> **Goal:** Build the foundational cloud resources that every VM will depend on — networks, images, flavors, keys, and firewall rules.

---

## Step 3.1 — Create Custom Flavors (EC2 Instance Types)
> **Why:** Flavors define CPU, RAM, and disk sizes for VMs — exactly like EC2 instance types (t2.micro, t2.small, etc.). DevStack creates some defaults but they may not match your project's EC2 analogy. Create named ones that match EC2 naming so the comparison is clear.

### Sub-step 3.1.1 — Load admin credentials
```bash
source /opt/stack/devstack/openrc admin admin
```

### Sub-step 3.1.2 — List existing default flavors
```bash
openstack flavor list
```
Note what DevStack created. You may see `m1.tiny`, `m1.small`, etc. already.

### Sub-step 3.1.3 — Delete and recreate flavors to match EC2 analogy
```bash
# Remove defaults if they exist (ignore errors if they don't)
for f in m1.tiny m1.small m1.medium m1.large; do
    openstack flavor delete $f 2>/dev/null && echo "Deleted $f" || echo "$f not found, skipping"
done

# Create EC2-mapped flavors
openstack flavor create --id 1 --vcpus 1 --ram 512  --disk 5  m1.tiny    # → t2.nano
openstack flavor create --id 2 --vcpus 1 --ram 1024 --disk 10 m1.small   # → t2.micro
openstack flavor create --id 3 --vcpus 1 --ram 2048 --disk 20 m1.medium  # → t2.small
openstack flavor create --id 4 --vcpus 2 --ram 4096 --disk 40 m1.large   # → t2.medium
```

### Sub-step 3.1.4 — Verify all 4 flavors exist
```bash
openstack flavor list
```
| ID | Name | vCPUs | RAM | Disk | EC2 Equiv |
|----|------|-------|-----|------|-----------|
| 1 | m1.tiny | 1 | 512MB | 5GB | t2.nano |
| 2 | m1.small | 1 | 1GB | 10GB | t2.micro |
| 3 | m1.medium | 1 | 2GB | 20GB | t2.small |
| 4 | m1.large | 2 | 4GB | 40GB | t2.medium |

### Sub-step 3.1.5 — Take Screenshot #2
- **File:** `screenshots/02_flavor_list.png`
- Shows: Horizon Admin > Compute > Flavors OR `openstack flavor list` terminal output

---

## Step 3.2 — Upload VM Images (AMI Equivalent)
> **Why:** Images are the templates VMs are launched from — same role as AMIs in EC2. DevStack downloads CirrOS (tiny 15MB test image) automatically. We also need Ubuntu for the web server demo.

### Sub-step 3.2.1 — Confirm CirrOS image exists
```bash
openstack image list
# Should show: cirros-0.6.2-x86_64-disk | active
```

### Sub-step 3.2.2 — Download Ubuntu 22.04 minimal cloud image
```bash
wget -O /tmp/ubuntu-22.04-cloud.img \
  https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img
```
- **Size:** ~600MB — takes 5–10 minutes depending on connection
- **Verify:** `ls -lh /tmp/ubuntu-22.04-cloud.img` — should be ~600MB

### Sub-step 3.2.3 — Upload Ubuntu image to Glance
```bash
openstack image create "Ubuntu-22.04-LTS" \
  --file /tmp/ubuntu-22.04-cloud.img \
  --disk-format qcow2 \
  --container-format bare \
  --public
```
- **Expected:** Image starts in `queued` then moves to `active`

### Sub-step 3.2.4 — Wait for image to become active
```bash
watch openstack image list
# Wait until Ubuntu-22.04-LTS shows status: active
```

### Sub-step 3.2.5 — Verify both images are ready
```bash
openstack image show "Ubuntu-22.04-LTS" | grep status
openstack image show "cirros-0.6.2-x86_64-disk" | grep status
# Both: status | active
```

### Sub-step 3.2.6 — Take Screenshot #3
- **File:** `screenshots/03_image_list.png`
- Shows: Horizon > Project > Compute > Images with both images listed

---

## Step 3.3 — Set Up Private Network (VPC Equivalent)
> **Why:** VMs need a private network to boot into and communicate with each other. This is the equivalent of a VPC private subnet in AWS. Without this, `openstack server create` fails.

### Sub-step 3.3.1 — Create the private network
```bash
openstack network create private-network \
  --description "Private tenant network — VPC equivalent"
```
- **Verify:** `openstack network show private-network | grep status` → `ACTIVE`

### Sub-step 3.3.2 — Create a subnet within the network
```bash
openstack subnet create private-subnet \
  --network private-network \
  --subnet-range 192.168.100.0/24 \
  --gateway 192.168.100.1 \
  --dns-nameserver 8.8.8.8 \
  --dns-nameserver 8.8.4.4 \
  --allocation-pool start=192.168.100.10,end=192.168.100.200
```
- **`--allocation-pool`** defines the DHCP range VMs get IPs from

### Sub-step 3.3.3 — Verify the subnet
```bash
openstack subnet show private-subnet
# Check: cidr=192.168.100.0/24, gateway_ip=192.168.100.1
```

### Sub-step 3.3.4 — Verify DHCP agent is serving this network
```bash
openstack dhcp agent list --network private-network
# Should show at least one dhcp agent
```

---

## Step 3.4 — Set Up Router (Internet Gateway Equivalent)
> **Why:** The private network is isolated by default. The router connects it to the external/public network so VMs can reach the outside and floating IPs can route inbound traffic. This is AWS's Internet Gateway role.

### Sub-step 3.4.1 — Create the router
```bash
openstack router create main-router
```
- **Verify:** `openstack router show main-router | grep status` → `ACTIVE`

### Sub-step 3.4.2 — Attach router to the external/public network
```bash
openstack router set main-router --external-gateway public
```
- This gives the router a port on the public network (like attaching an IGW to a VPC)

### Sub-step 3.4.3 — Connect the private subnet to the router
```bash
openstack router add subnet main-router private-subnet
```

### Sub-step 3.4.4 — Verify full routing chain
```bash
openstack router show main-router
# Look for:
#   external_gateway_info: {..., "network_id": "..."} ← connected to public
#   interfaces_info: [...] ← connected to private-subnet
```

### Sub-step 3.4.5 — Take Screenshot #4
- **File:** `screenshots/04_network_topology.png`
- Shows: Horizon > Project > Network > Network Topology (visual diagram)

---

## Step 3.5 — Create SSH Key Pair (EC2 Key Pairs Equivalent)
> **Why:** Cloud VMs don't have passwords by default. SSH key injection at launch is the only way in. Without a key pair registered, you can launch VMs but never log into them.

### Sub-step 3.5.1 — Generate a new key pair and save private key
```bash
openstack keypair create project-key > /opt/stack/project-key.pem
```
- This generates the keypair server-side, prints the private key once, and saves it to `project-key.pem`

### Sub-step 3.5.2 — Secure the private key file
```bash
chmod 600 /opt/stack/project-key.pem
```
- **Why:** SSH refuses to use key files that are world-readable (returns "unprotected private key file" error)

### Sub-step 3.5.3 — Verify key pair is registered
```bash
openstack keypair list
# Should show: project-key

openstack keypair show project-key
# Shows fingerprint and type (ssh-rsa)
```

### Sub-step 3.5.4 — Confirm the private key file is valid
```bash
ls -la /opt/stack/project-key.pem
# -rw------- 1 stack stack ... project-key.pem

head -2 /opt/stack/project-key.pem
# -----BEGIN RSA PRIVATE KEY-----  or  -----BEGIN OPENSSH PRIVATE KEY-----
```

---

## Step 3.6 — Create Security Groups (EC2 Security Groups Equivalent)
> **Why:** By default, all inbound traffic to a VM is blocked — same as EC2. Security groups are stateful firewall rules. Without at least an SSH rule, you cannot connect to any instance you launch.

### Sub-step 3.6.1 — Create the SSH-only security group
```bash
openstack security group create ssh-only \
  --description "Allow SSH and ICMP only — for management VMs"
```

### Sub-step 3.6.2 — Add SSH inbound rule
```bash
openstack security group rule create ssh-only \
  --protocol tcp \
  --dst-port 22 \
  --remote-ip 0.0.0.0/0 \
  --description "SSH from anywhere"
```

### Sub-step 3.6.3 — Add ICMP (ping) rule
```bash
openstack security group rule create ssh-only \
  --protocol icmp \
  --remote-ip 0.0.0.0/0 \
  --description "Allow ping"
```

### Sub-step 3.6.4 — Create the web-server security group
```bash
openstack security group create web-server \
  --description "Allow HTTP, HTTPS, SSH — for public web servers"
```

### Sub-step 3.6.5 — Add all web server rules
```bash
# SSH
openstack security group rule create web-server \
  --protocol tcp --dst-port 22 --remote-ip 0.0.0.0/0

# HTTP
openstack security group rule create web-server \
  --protocol tcp --dst-port 80 --remote-ip 0.0.0.0/0

# HTTPS
openstack security group rule create web-server \
  --protocol tcp --dst-port 443 --remote-ip 0.0.0.0/0

# ICMP
openstack security group rule create web-server \
  --protocol icmp --remote-ip 0.0.0.0/0
```

### Sub-step 3.6.6 — Verify both security groups and their rules
```bash
openstack security group list
openstack security group rule list ssh-only
openstack security group rule list web-server
```

### Sub-step 3.6.7 — Take Screenshot #5
- **File:** `screenshots/05_security_groups.png`
- Shows: Horizon > Project > Network > Security Groups with both groups and their rules

---

## Phase 3 Checklist

- [ ] **3.1.4** All 4 flavors visible in `openstack flavor list`
- [ ] **3.2.5** Both images (CirrOS + Ubuntu) show `active` in Glance
- [ ] **3.3.3** Private network `192.168.100.0/24` created and active
- [ ] **3.4.4** Router connected to both public and private-subnet
- [ ] **3.5.3** Key pair `project-key` registered in DevStack
- [ ] **3.5.4** `project-key.pem` file exists, mode 600, contains private key
- [ ] **3.6.6** Security groups `ssh-only` (SSH+ICMP) and `web-server` (SSH+HTTP+HTTPS+ICMP) created
- [ ] Screenshots #2, #3, #4, #5 taken

---

---

# PHASE 4 — EC2 Feature Implementation & Demo
> **Goal:** Exercise every major EC2 feature using DevStack. Each sub-step is a demo-able feature.

---

## Step 4.1 — Launch First Instance
> **EC2 Equivalent:** Clicking "Launch Instance" in the AWS Console.

### Sub-step 4.1.1 — Launch CirrOS instance via CLI
```bash
source /opt/stack/devstack/openrc admin admin

openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  demo-instance-01
```

### Sub-step 4.1.2 — Watch status change from BUILD to ACTIVE
```bash
watch -n 2 openstack server list
# Status should go: BUILD → ACTIVE within 60 seconds
```

### Sub-step 4.1.3 — Get the instance's private IP
```bash
openstack server show demo-instance-01 | grep addresses
# addresses | private-network=192.168.100.XX
```

### Sub-step 4.1.4 — View the boot console log (proves VM is alive)
```bash
openstack console log show demo-instance-01
# Should show Linux boot messages
# Last lines should show login prompt: "login as 'cirros' user"
```

### Sub-step 4.1.5 — Launch same instance from Horizon dashboard (for screenshots)
- Go to: Project > Compute > Instances > Launch Instance
- Fill in: Instance Name, Source (cirros image), Flavor (m1.tiny), Networks, Key Pair, Security Groups
- **File:** `screenshots/06_launch_instance_wizard.png`
- **File:** `screenshots/07_instance_active.png`

---

## Step 4.2 — Assign Floating IP (Elastic IP Equivalent)
> **EC2 Equivalent:** Allocating and associating an Elastic IP.

### Sub-step 4.2.1 — Allocate a floating IP from the public pool
```bash
FLOATING_IP=$(openstack floating ip create public -f value -c floating_ip_address)
echo "Allocated floating IP: $FLOATING_IP"
```

### Sub-step 4.2.2 — Associate floating IP with the instance
```bash
openstack server add floating ip demo-instance-01 $FLOATING_IP
```

### Sub-step 4.2.3 — Verify the association
```bash
openstack server show demo-instance-01 | grep addresses
# Should show: private-network=192.168.100.XX, 10.200.195.XXX
```

### Sub-step 4.2.4 — Ping the floating IP
```bash
ping -c 4 $FLOATING_IP
# Should get replies
```
- **If ping fails:** Check security group has ICMP rule. Check `openstack floating ip list`.

### Sub-step 4.2.5 — Take Screenshot #6
- **File:** `screenshots/08_floating_ip_assigned.png`
- Shows: Instance details with both private IP and floating IP visible

---

## Step 4.3 — SSH Into the Instance
> **EC2 Equivalent:** EC2 Instance Connect or SSH with a PEM key.
> **This is the most important demo moment of the whole project.**

### Sub-step 4.3.1 — SSH into the CirrOS instance
```bash
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  cirros@$FLOATING_IP
```

### Sub-step 4.3.2 — Run commands inside the VM to prove it's a real machine
```bash
# Inside the VM:
whoami           # cirros
hostname         # demo-instance-01
uname -a         # Linux kernel info
ip addr show     # shows private IP 192.168.100.XX
cat /etc/os-release
df -h            # disk usage
free -m          # memory usage
exit
```

### Sub-step 4.3.3 — Take Screenshot #7
- **File:** `screenshots/09_ssh_into_vm.png`
- Shows: Terminal with SSH session open, `uname -a` and `ip addr` output visible

### Sub-step 4.3.4 — Access VNC console from Horizon (no SSH needed)
- Go to: Horizon > Instances > Click instance name > Console tab
- You get a browser-based terminal — exactly like EC2 Instance Connect
- **File:** `screenshots/10_vnc_console.png`

---

## Step 4.4 — Instance Lifecycle Operations
> **EC2 Equivalent:** Stop, Start, Reboot buttons in the EC2 console.

### Sub-step 4.4.1 — Stop the instance (graceful shutdown)
```bash
openstack server stop demo-instance-01
sleep 5
openstack server show demo-instance-01 | grep status
# status | SHUTOFF
```

### Sub-step 4.4.2 — Verify SSH is refused while stopped
```bash
ssh -i /opt/stack/project-key.pem cirros@$FLOATING_IP
# Should fail: Connection refused — proves VM is really off
```

### Sub-step 4.4.3 — Start the instance again
```bash
openstack server start demo-instance-01
watch openstack server list
# Status: ACTIVE again
```

### Sub-step 4.4.4 — Soft reboot (graceful OS restart)
```bash
openstack server reboot demo-instance-01
# Sends ACPI shutdown signal to OS — OS restarts cleanly
```

### Sub-step 4.4.5 — Hard reboot (equivalent to power cycle)
```bash
openstack server reboot --hard demo-instance-01
# Forces immediate restart — like pulling the power plug and reconnecting
```

### Sub-step 4.4.6 — Take Screenshot #8
- **File:** `screenshots/11_instance_lifecycle.png`
- Shows: Horizon instance actions dropdown (Stop, Start, Reboot options)

---

## Step 4.5 — Block Storage Volume (EBS Equivalent)
> **EC2 Equivalent:** Create EBS Volume → Attach to EC2 instance → Format and mount inside OS.

### Sub-step 4.5.1 — Create a 5GB persistent volume
```bash
openstack volume create --size 5 demo-volume-01
```

### Sub-step 4.5.2 — Wait for volume to become available
```bash
watch openstack volume list
# Status: available
```

### Sub-step 4.5.3 — Attach volume to the running instance
```bash
openstack server add volume demo-instance-01 demo-volume-01 --device /dev/vdb
```

### Sub-step 4.5.4 — Verify volume is in-use
```bash
openstack volume show demo-volume-01 | grep status
# status | in-use
openstack volume show demo-volume-01 | grep attachments
# Shows instance ID and /dev/vdb
```

### Sub-step 4.5.5 — SSH in and format + mount the volume
```bash
ssh -i /opt/stack/project-key.pem cirros@$FLOATING_IP

# Inside VM:
sudo fdisk -l           # see /dev/vdb with 5GB unpartitioned
sudo mkfs.ext4 /dev/vdb # format as ext4
sudo mkdir /data
sudo mount /dev/vdb /data
df -h                   # see /data mounted with 4.8G available
echo "Persistent data from EBS-like volume" | sudo tee /data/proof.txt
cat /data/proof.txt
exit
```

### Sub-step 4.5.6 — Detach the volume
```bash
openstack server remove volume demo-instance-01 demo-volume-01
openstack volume show demo-volume-01 | grep status
# status | available  ← data is preserved even though detached
```

### Sub-step 4.5.7 — Prove data persists: attach to a different instance
```bash
# Create a second VM
openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  demo-instance-02

# Assign floating IP
FIP2=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip demo-instance-02 $FIP2

# Attach the same volume to the new VM
openstack server add volume demo-instance-02 demo-volume-01 --device /dev/vdb

# SSH into second VM and read the file
ssh -i /opt/stack/project-key.pem cirros@$FIP2
  sudo mount /dev/vdb /mnt
  cat /mnt/proof.txt
  # Persistent data from EBS-like volume  ← SAME DATA! ✅
exit
```

### Sub-step 4.5.8 — Take Screenshot #9
- **File:** `screenshots/12_volume_mounted.png`
- Shows: Terminal inside VM with `df -h` showing /data mounted and `cat /data/proof.txt`

---

## Step 4.6 — Volume Snapshot (EBS Snapshot Equivalent)
> **EC2 Equivalent:** "Create Snapshot" from an EBS volume.

### Sub-step 4.6.1 — Detach volume before snapshotting (best practice)
```bash
openstack server remove volume demo-instance-02 demo-volume-01
```

### Sub-step 4.6.2 — Create snapshot
```bash
openstack volume snapshot create \
  --volume demo-volume-01 \
  --description "Snapshot before major changes" \
  demo-snapshot-01
```

### Sub-step 4.6.3 — Wait for snapshot to complete
```bash
watch openstack volume snapshot list
# Status: available
```

### Sub-step 4.6.4 — Restore a new volume from snapshot
```bash
openstack volume create \
  --snapshot demo-snapshot-01 \
  --size 5 \
  restored-from-snapshot
```

### Sub-step 4.6.5 — Verify restored volume has the data
```bash
openstack server add volume demo-instance-01 restored-from-snapshot
ssh -i /opt/stack/project-key.pem cirros@$FLOATING_IP
  sudo mount /dev/vdb /mnt
  cat /mnt/proof.txt     # ← same content from original volume ✅
exit
```

---

## Step 4.7 — Instance Snapshot / Custom Image (AMI Equivalent)
> **EC2 Equivalent:** "Create Image" from a running EC2 instance, then launch new instances from it.

### Sub-step 4.7.1 — Create a custom image from running instance
```bash
openstack server image create \
  --name "my-custom-ami-v1" \
  demo-instance-01
```

### Sub-step 4.7.2 — Wait for image to become active
```bash
watch openstack image list
# my-custom-ami-v1 status: saving → active (takes 2–5 min)
```

### Sub-step 4.7.3 — Launch a brand new instance from the custom image
```bash
openstack server create \
  --image "my-custom-ami-v1" \
  --flavor m1.small \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  launched-from-custom-ami
```

### Sub-step 4.7.4 — Verify it booted correctly
```bash
openstack console log show launched-from-custom-ami
# Should show same boot sequence as original
```

---

## Step 4.8 — Deploy a Web Server (Real-World Use Case)
> **EC2 Equivalent:** Launching an Ubuntu EC2 instance and deploying nginx as a web server.
> **This is the headline demo feature for your presentation.**

### Sub-step 4.8.1 — Launch Ubuntu 22.04 instance
```bash
openstack server create \
  --image "Ubuntu-22.04-LTS" \
  --flavor m1.medium \
  --network private-network \
  --key-name project-key \
  --security-group web-server \
  web-server-01
```

### Sub-step 4.8.2 — Assign a floating IP to the web server
```bash
WEB_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip web-server-01 $WEB_FIP
echo "Web server floating IP: $WEB_FIP"
```

### Sub-step 4.8.3 — Wait for Ubuntu to fully boot (3–5 minutes)
```bash
# Keep checking console log until you see "cloud-init finished" or login prompt
openstack console log show web-server-01 | tail -20
```

### Sub-step 4.8.4 — SSH in and install nginx
```bash
ssh -i /opt/stack/project-key.pem ubuntu@$WEB_FIP

# Inside the Ubuntu VM:
sudo apt update && sudo apt install -y nginx
echo "<h1>Welcome to My DevStack Cloud!</h1>
<p>This VM is running on a local EC2 replica built with DevStack.</p>
<p>Host: $(hostname) | IP: $(hostname -I)</p>" | sudo tee /var/www/html/index.html
sudo systemctl enable nginx
sudo systemctl start nginx
exit
```

### Sub-step 4.8.5 — Test web server from host machine
```bash
curl http://$WEB_FIP
# Expected:
# <h1>Welcome to My OpenStack Cloud!</h1>
# ...
```

### Sub-step 4.8.6 — Open in browser
```
http://<WEB_FIP>
```
- Browser should show the HTML page

### Sub-step 4.8.7 — Take Screenshot #10 and #11
- **File:** `screenshots/13_web_server_browser.png` — browser showing web page
- **File:** `screenshots/14_web_server_curl.png` — terminal `curl` output

---

## Phase 4 Checklist

- [ ] **4.1** CirrOS instance `ACTIVE`, console log shows boot
- [ ] **4.2** Floating IP assigned, ping works
- [ ] **4.3** SSH into VM works, hostname and IP confirmed inside VM
- [ ] **4.4** Stop → SHUTOFF, Start → ACTIVE, Reboot → ACTIVE all work
- [ ] **4.5** Volume created, attached, formatted, mounted, data written
- [ ] **4.5.7** Data persistence proven across two VMs
- [ ] **4.6** Snapshot created, restored, data verified in restored volume
- [ ] **4.7** Custom AMI created, new instance launched from it
- [ ] **4.8** Ubuntu web server running nginx, accessible from browser
- [ ] Screenshots #6 through #11 taken

---

---

# PHASE 5 — Multi-User & Project Setup (IAM Equivalent)
> **Goal:** Demonstrate that OpenStack is a proper multi-tenant cloud — users are isolated, just like AWS accounts.

---

## Step 5.1 — Plan the User Structure
> **Why:** Before creating anything, define the structure clearly. This mirrors how a real sysadmin would plan IAM before creating users.

### Sub-step 5.1.1 — Define the project and user plan

| Project | User | Role | Analogy |
|---------|------|------|---------|
| admin (default) | admin | admin | AWS root account |
| dev-project | devuser | member | Developer AWS account |
| prod-project | opsuser | member | Ops AWS account |
| dev-project | devadmin | admin | Dev team lead |

### Sub-step 5.1.2 — Confirm you are logged in as admin
```bash
source /opt/stack/devstack/openrc admin admin
openstack token issue | grep project_name
# project_name | admin
```

---

## Step 5.2 — Create Projects (AWS Organizational Units / Accounts)
> **EC2 Equivalent:** Separate AWS accounts or organizational units.

### Sub-step 5.2.1 — Create development project
```bash
openstack project create \
  --domain Default \
  --description "Development team — internal testing only" \
  dev-project
```

### Sub-step 5.2.2 — Create production project
```bash
openstack project create \
  --domain Default \
  --description "Production team — live deployments" \
  prod-project
```

### Sub-step 5.2.3 — Verify both projects exist
```bash
openstack project list
# Should show: admin, demo, dev-project, prod-project
```

---

## Step 5.3 — Create Users
> **EC2 Equivalent:** IAM Users.

### Sub-step 5.3.1 — Create developer user
```bash
openstack user create \
  --domain Default \
  --password DevUser@123 \
  --description "Developer — has access to dev-project" \
  devuser
```

### Sub-step 5.3.2 — Create ops user
```bash
openstack user create \
  --domain Default \
  --password OpsUser@123 \
  --description "DevOps engineer — has access to prod-project" \
  opsuser
```

### Sub-step 5.3.3 — Create a dev team lead (admin of dev-project only)
```bash
openstack user create \
  --domain Default \
  --password DevAdmin@123 \
  devadmin
```

### Sub-step 5.3.4 — Verify all users exist
```bash
openstack user list
# admin, demo, devuser, opsuser, devadmin
```

---

## Step 5.4 — Assign Roles and Test Isolation

### Sub-step 5.4.1 — Assign roles to users in their projects
```bash
# devuser → member of dev-project (can use resources, can't manage them)
openstack role add --project dev-project --user devuser member

# devadmin → admin of dev-project (can manage other users in the project)
openstack role add --project dev-project --user devadmin admin

# opsuser → member of prod-project
openstack role add --project prod-project --user opsuser member
```

### Sub-step 5.4.2 — Log in as devuser and create a VM
```bash
source /opt/stack/devstack/openrc devuser DevUser@123
# This now scopes all commands to dev-project

openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  dev-vm-01

openstack server list
# Shows dev-vm-01 only
```

### Sub-step 5.4.3 — Log in as opsuser and confirm they CANNOT see devuser's VM
```bash
source /opt/stack/devstack/openrc opsuser OpsUser@123

openstack server list
# Empty list — opsuser is in prod-project, cannot see dev-project VMs ✅
```

### Sub-step 5.4.4 — Log back in as admin and confirm admin sees everything
```bash
source /opt/stack/devstack/openrc admin admin

openstack server list --all-projects
# Shows ALL VMs from ALL projects ✅
```

### Sub-step 5.4.5 — Demonstrate login isolation in Horizon
- Open browser in a private/incognito window
- Login as `devuser` / `DevUser@123`
- Show: only dev-project's instances visible
- **File:** `screenshots/15_devuser_isolated_view.png`

### Sub-step 5.4.6 — List available roles and role assignments
```bash
openstack role list
openstack role assignment list --project dev-project
```

---

## Phase 5 Checklist

- [ ] **5.2.3** Both projects `dev-project` and `prod-project` created
- [ ] **5.3.4** Users `devuser`, `opsuser`, `devadmin` created
- [ ] **5.4.1** All role assignments made
- [ ] **5.4.2** devuser can launch VMs in dev-project
- [ ] **5.4.3** opsuser sees empty server list (isolation proven)
- [ ] **5.4.4** admin sees all VMs with `--all-projects`
- [ ] **5.4.5** Screenshot #15 taken showing devuser's isolated dashboard view

---

---

# PHASE 6 — Testing & Validation
> **Goal:** Formally verify every feature works. Record results for your report. Identify and fix any failures before the presentation.

---

## Step 6.1 — Functional Test Suite
> Run each test, record PASS or FAIL, document the evidence.

### Sub-step 6.1.1 — Set up test environment
```bash
source /opt/stack/devstack/openrc admin admin
# All tests run as admin for simplicity
```

### Sub-step 6.1.2 — Test T-01: Instance Launch and Boot
```bash
openstack server create \
  --image cirros-0.6.2-x86_64-disk \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  test-t01

sleep 60
openstack server show test-t01 | grep status
# PASS: status | ACTIVE
```

### Sub-step 6.1.3 — Test T-02: Console Log (VM actually booted)
```bash
openstack console log show test-t01 | tail -5
# PASS: shows Linux login prompt or cloud-init messages
```

### Sub-step 6.1.4 — Test T-03: Floating IP + Ping
```bash
T01_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip test-t01 $T01_FIP
sleep 10
ping -c 5 $T01_FIP
# PASS: 5 packets transmitted, 5 received, 0% packet loss
```

### Sub-step 6.1.5 — Test T-04: SSH Access
```bash
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  -o ConnectTimeout=10 \
  cirros@$T01_FIP "echo 'SSH_OK'"
# PASS: SSH_OK
```

### Sub-step 6.1.6 — Test T-05: Stop and Start
```bash
openstack server stop test-t01
sleep 10
openstack server show test-t01 | grep status   # SHUTOFF
openstack server start test-t01
sleep 30
openstack server show test-t01 | grep status   # ACTIVE
# PASS: both states observed
```

### Sub-step 6.1.7 — Test T-06: Volume Lifecycle
```bash
openstack volume create --size 2 test-vol
sleep 5
openstack volume show test-vol | grep status   # available
openstack server add volume test-t01 test-vol
openstack volume show test-vol | grep status   # in-use
openstack server remove volume test-t01 test-vol
openstack volume show test-vol | grep status   # available
# PASS: volume goes available → in-use → available
```

### Sub-step 6.1.8 — Test T-07: Volume Snapshot
```bash
openstack volume snapshot create --volume test-vol test-snap
sleep 10
openstack volume snapshot show test-snap | grep status   # available
# PASS: snapshot status is available
```

### Sub-step 6.1.9 — Test T-08: Custom Image from Instance
```bash
openstack server image create --name test-custom-img test-t01
sleep 120   # wait for image capture
openstack image show test-custom-img | grep status   # active
# PASS: image status is active
```

### Sub-step 6.1.10 — Test T-09: Launch from Custom Image
```bash
openstack server create \
  --image test-custom-img \
  --flavor m1.tiny \
  --network private-network \
  test-t09

sleep 60
openstack server show test-t09 | grep status
# PASS: ACTIVE
```

### Sub-step 6.1.11 — Test T-10: Security Group Rule Enforcement
```bash
# Remove SSH rule temporarily and verify SSH is blocked
openstack security group create test-block-sg
# No rules added — all inbound blocked

openstack server create \
  --image cirros-0.6.2-x86_64-disk \
  --flavor m1.tiny \
  --network private-network \
  --security-group test-block-sg \
  test-blocked

BLOCKED_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip test-blocked $BLOCKED_FIP
sleep 30

ssh -i /opt/stack/project-key.pem \
  -o ConnectTimeout=5 \
  cirros@$BLOCKED_FIP 2>&1
# PASS: "Connection timed out" or "Connection refused" — SSH is blocked ✅
```

### Sub-step 6.1.12 — Record test results in a table

| Test | Feature | Result | Notes |
|------|---------|--------|-------|
| T-01 | Instance Launch | ☐ PASS / ☐ FAIL | |
| T-02 | Boot (console log) | ☐ PASS / ☐ FAIL | |
| T-03 | Floating IP + Ping | ☐ PASS / ☐ FAIL | |
| T-04 | SSH Access | ☐ PASS / ☐ FAIL | |
| T-05 | Stop / Start | ☐ PASS / ☐ FAIL | |
| T-06 | Volume Attach/Detach | ☐ PASS / ☐ FAIL | |
| T-07 | Volume Snapshot | ☐ PASS / ☐ FAIL | |
| T-08 | Instance Snapshot | ☐ PASS / ☐ FAIL | |
| T-09 | Launch from Custom Image | ☐ PASS / ☐ FAIL | |
| T-10 | Security Group Enforcement | ☐ PASS / ☐ FAIL | |

### Sub-step 6.1.13 — Clean up test resources
```bash
openstack server delete test-t01 test-t09 test-blocked
openstack volume delete test-vol
openstack volume snapshot delete test-snap
openstack image delete test-custom-img
openstack floating ip delete $T01_FIP $BLOCKED_FIP
openstack security group delete test-block-sg
```

---

## Step 6.2 — Performance Benchmarks
> **Why:** Your report should include actual numbers. These prove the system is functional under load, not just in ideal conditions.

### Sub-step 6.2.1 — Measure instance launch time
```bash
START=$(date +%s)
openstack server create \
  --image cirros-0.6.2-x86_64-disk \
  --flavor m1.tiny \
  --network private-network \
  perf-vm-01

# Poll until ACTIVE
while true; do
  STATUS=$(openstack server show perf-vm-01 -f value -c status)
  if [ "$STATUS" = "ACTIVE" ]; then
    END=$(date +%s)
    echo "Launch time: $((END - START)) seconds"
    break
  fi
  sleep 2
done
# Record this number for your report
```

### Sub-step 6.2.2 — Measure resource usage with 3 VMs running
```bash
# Launch 2 more
openstack server create --image cirros-0.6.2-x86_64-disk --flavor m1.tiny --network private-network perf-vm-02
openstack server create --image cirros-0.6.2-x86_64-disk --flavor m1.tiny --network private-network perf-vm-03

sleep 30

# Record host resource usage
echo "=== Memory Usage with 3 VMs ==="
free -h

echo "=== CPU Usage ==="
top -bn1 | head -20

echo "=== Disk Usage ==="
df -h /opt/stack

# Cleanup
openstack server delete perf-vm-01 perf-vm-02 perf-vm-03
```

### Sub-step 6.2.3 — Record numbers for report

| Metric | Value |
|--------|-------|
| CirrOS instance launch time | ___ seconds |
| Ubuntu instance launch time | ___ seconds |
| RAM used (idle, no VMs) | ___ GB |
| RAM used (3 CirrOS VMs) | ___ GB |
| Disk used by DevStack | ___ GB |
| Max concurrent VMs tested | ___ |

---

## Step 6.3 — Pre-Presentation Smoke Test
> **Why:** Run this the morning of your presentation to confirm nothing broke since last test.

### Sub-step 6.3.1 — Verify all services still active
```bash
SERVICES="key n-api n-cpu g-api c-api c-vol q-svc q-agt q-dhcp q-l3"
for svc in $SERVICES; do
    echo -n "$svc: "
    sudo systemctl is-active devstack@$svc
done
```

### Sub-step 6.3.2 — Quick end-to-end smoke test
```bash
source /opt/stack/devstack/openrc admin admin

# Launch → floating IP → ping → delete (should complete in under 3 minutes)
openstack server create --image cirros-0.6.2-x86_64-disk --flavor m1.tiny --network private-network smoke-test
sleep 60
SMOKE_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip smoke-test $SMOKE_FIP
ping -c 3 $SMOKE_FIP && echo "SMOKE TEST PASSED" || echo "SMOKE TEST FAILED"
openstack server delete smoke-test
openstack floating ip delete $SMOKE_FIP
```

---

## Phase 6 Checklist

- [ ] **6.1.12** All 10 tests passed and results table filled in
- [ ] **6.2.3** Performance numbers recorded
- [ ] **6.3.2** Smoke test passes cleanly

---

---

# PHASE 7 — Documentation & Presentation
> **Goal:** Turn your working system into a submittable project with screenshots, diagrams, and comparison material.

---

## Step 7.1 — Collect Screenshots
> **Why:** Screenshots are the primary evidence that the system works. Take them while the system is running, not from memory.

### Sub-step 7.1.1 — Create the screenshots directory
```bash
mkdir -p /home/khalid/ec2-local-cloud/screenshots
```

### Sub-step 7.1.2 — Full screenshot list (take in order)

| # | Filename | What to Show | Where to Take |
|---|----------|-------------|--------------|
| 01 | `01_dashboard_overview.png` | Horizon dashboard, admin logged in, project overview | Browser |
| 02 | `02_flavor_list.png` | 4 custom flavors with vCPU/RAM/disk columns | Horizon > Admin > Compute > Flavors |
| 03 | `03_image_list.png` | CirrOS + Ubuntu images, both active | Horizon > Project > Compute > Images |
| 04 | `04_network_topology.png` | Visual network graph with router + subnets | Horizon > Project > Network > Topology |
| 05 | `05_security_groups.png` | Both security groups with rules expanded | Horizon > Project > Network > Security Groups |
| 06 | `06_launch_wizard.png` | Instance launch wizard page 1 (selecting image) | Horizon > Launch Instance dialog |
| 07 | `07_instance_active.png` | demo-instance-01 in ACTIVE state with IP | Horizon > Instances list |
| 08 | `08_floating_ip_assigned.png` | Instance details showing private + floating IP | Horizon > Instance detail page |
| 09 | `09_ssh_session.png` | SSH terminal open inside VM, `uname -a` visible | Terminal |
| 10 | `10_vnc_console.png` | Browser-based VNC console showing VM terminal | Horizon > Instance > Console tab |
| 11 | `11_stop_start.png` | Instance in SHUTOFF state | Horizon > Instances |
| 12 | `12_volume_attached.png` | Volume status `in-use`, linked to instance | Horizon > Volumes |
| 13 | `13_volume_inside_vm.png` | `df -h` in VM showing /dev/vdb mounted | SSH terminal |
| 14 | `14_volume_snapshot.png` | Volume snapshot with `available` status | Horizon > Volumes > Snapshots |
| 15 | `15_custom_image.png` | Custom AMI image in Glance with `active` status | Horizon > Images |
| 16 | `16_web_server.png` | Browser showing nginx page from floating IP | Browser at `http://<floating-ip>` |
| 17 | `17_devuser_isolated.png` | devuser logged in, empty/isolated instance list | Browser (incognito) |
| 18 | `18_multiproject_admin.png` | Admin view showing VMs from all projects | Horizon > Admin > Compute > Instances |
| 19 | `19_service_list_cli.png` | `openstack service list` output | Terminal |
| 20 | `20_all_instances_cli.png` | `openstack server list --all-projects` output | Terminal |

---

## Step 7.2 — Architecture Diagram
> Draw this for your report. Represents the complete system.

### Sub-step 7.2.1 — System architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHYSICAL HOST MACHINE                             │
│         Acer TravelMate P215-53 | Ubuntu 24.04 | 8GB RAM           │
│         16 CPU (VMX) | 526GB Storage | WiFi 10.200.194.146         │
│                                                                      │
│  ┌──────────────── OpenStack Services ─────────────────────────┐    │
│  │                                                              │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │    │
│  │  │ Keystone │  │   Nova   │  │  Glance  │  │  Cinder  │   │    │
│  │  │ :5000    │  │  :8774   │  │  :9292   │  │  :8776   │   │    │
│  │  │ (IAM)    │  │(Compute) │  │ (Images) │  │(Volumes) │   │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │    │
│  │       │              │             │              │          │    │
│  │  ─────┴──────────────┴─────────────┴──────────────┴──────   │    │
│  │              RabbitMQ Message Bus (AMQP)                     │    │
│  │  ─────────────────────────────────────────────────────────   │    │
│  │       │              │             │              │          │    │
│  │  ┌────┴─────┐  ┌─────┴──────┐  ┌──┴───────────────────┐    │    │
│  │  │  MySQL   │  │  Neutron   │  │   Horizon Dashboard  │    │    │
│  │  │  :3306   │  │   :9696   │  │  :80/dashboard       │    │    │
│  │  │  (DB)    │  │ (Network) │  │  (Web Console)       │    │    │
│  │  └──────────┘  └─────┬──────┘  └──────────────────────┘    │    │
│  │                       │                                      │    │
│  └───────────────────────┼──────────────────────────────────────┘    │
│                           │                                          │
│              ┌────────────┴────────────┐                            │
│              │    Virtual Network      │  LinuxBridge + VXLAN       │
│              │   192.168.100.0/24      │  (Neutron)                 │
│              └──────────┬─────────────┘                            │
│                          │                                          │
│          ┌───────────────┼───────────────┐                         │
│          │               │               │                          │
│   ┌──────┴───┐   ┌───────┴──┐   ┌───────┴──┐                      │
│   │  VM 1    │   │  VM 2    │   │  VM 3    │   KVM/QEMU Guests    │
│   │ CirrOS   │   │ Ubuntu   │   │ Custom   │                      │
│   │  .10     │   │  .11     │   │  .12     │                      │
│   └──────────┘   └──────────┘   └──────────┘                      │
│                                                                      │
└────────────────────────┬─────────────────────────────────────────────┘
                          │
                   WiFi wlp0s20f3
                   10.200.194.146
                          │
               ┌──────────┴──────────┐
               │    Home Network      │
               │   Browser / SSH      │
               └─────────────────────┘
```

### Sub-step 7.2.2 — Data flow diagram for launching an instance

```
User clicks "Launch Instance"
         │
         ▼
    Horizon (Web UI)
         │  REST API call
         ▼
    Keystone ──── validates token
         │
         ▼
    Nova API ──── receives launch request
         │
         ├──► Glance  ──── fetches image
         │
         ├──► Neutron ──── creates network port, assigns IP
         │
         ├──► Cinder  ──── attaches volume (if requested)
         │
         ▼
    Nova Scheduler ──── picks compute host (only one in our setup)
         │
         ▼
    Nova Compute ──── calls libvirt
         │
         ▼
    KVM/QEMU ──── creates and boots the virtual machine
         │
         ▼
    VM boots, cloud-init runs, injects SSH key
         │
         ▼
    Status: ACTIVE ──► User can SSH in
```

---

## Step 7.3 — AWS vs DevStack Comparison Table

### Sub-step 7.3.1 — Feature comparison for report

| AWS EC2 Feature | AWS Service/Command | OpenStack Equivalent | OpenStack Command |
|---|---|---|---|
| Virtual Machines | EC2 Instances | Nova Instances | `openstack server create` |
| Machine Images | AMIs | Glance Images | `openstack image create` |
| Instance Types | t2.micro, m5.large | Flavors | `openstack flavor create` |
| Persistent Disk | EBS Volumes | Cinder Volumes | `openstack volume create` |
| Disk Backup | EBS Snapshots | Cinder Snapshots | `openstack volume snapshot create` |
| Public IPs | Elastic IPs | Floating IPs | `openstack floating ip create` |
| Private Network | VPC | Neutron Network | `openstack network create` |
| Subnets | VPC Subnet | Neutron Subnet | `openstack subnet create` |
| Internet Gateway | IGW | Neutron Router | `openstack router create` |
| Firewall Rules | Security Groups | Security Groups | `openstack security group create` |
| SSH Keys | Key Pairs | Key Pairs | `openstack keypair create` |
| User Accounts | IAM Users | Keystone Users | `openstack user create` |
| Account Groups | AWS Organizations | Projects | `openstack project create` |
| Permissions | IAM Roles/Policies | Keystone Roles | `openstack role add` |
| Web Console | AWS Management Console | Horizon Dashboard | http://IP/dashboard |
| CLI | AWS CLI | OpenStack CLI | `openstack` |
| VM Console Access | EC2 Instance Connect | VNC Console + Serial Log | `/api/instances/<id>/console` |
| Network Interfaces | Elastic Network Interface (ENI) | Neutron Ports | `/api/ports`, `os-interface` |
| Service Quotas | AWS Service Quotas | Nova/Cinder/Neutron Quota Sets | `/api/quotas` |

### Sub-step 7.3.2 — Architecture comparison for report

| Aspect | AWS EC2 | This Project (DevStack) |
|---|---|---|
| Hypervisor | KVM (AWS Nitro) | KVM (open source) |
| Networking | AWS VPC (proprietary) | Neutron + LinuxBridge |
| Image Storage | S3-backed | Glance (local disk) |
| Block Storage | AWS EBS (NVMe SSD) | Cinder (local LVM) |
| Identity | AWS IAM | Keystone |
| Dashboard | AWS Management Console | Horizon |
| API | AWS REST APIs | OpenStack REST APIs |
| Scale | Global, millions of nodes | Single machine |
| Redundancy | Multi-AZ, automatic failover | None (single node) |
| Network reach | Global internet | Local WiFi network |

---

## Step 7.4 — Final Project Folder Structure

### Sub-step 7.4.1 — Organize all files before submission
```
ec2-local-cloud/
├── PROJECT_REQUIREMENTS.md     ← System + feature requirements
├── INSTALLATION.md             ← Step-by-step install guide
├── PLAN.md                     ← This implementation plan
├── configs/
│   └── local.conf              ← DevStack configuration used
└── screenshots/
    ├── 01_dashboard_overview.png
    ├── 02_flavor_list.png
    ├── 03_image_list.png
    ├── 04_network_topology.png
    ├── 05_security_groups.png
    ├── 06_launch_wizard.png
    ├── 07_instance_active.png
    ├── 08_floating_ip_assigned.png
    ├── 09_ssh_session.png
    ├── 10_vnc_console.png
    ├── 11_stop_start.png
    ├── 12_volume_attached.png
    ├── 13_volume_inside_vm.png
    ├── 14_volume_snapshot.png
    ├── 15_custom_image.png
    ├── 16_web_server.png
    ├── 17_devuser_isolated.png
    ├── 18_multiproject_admin.png
    ├── 19_service_list_cli.png
    └── 20_all_instances_cli.png
```

### Sub-step 7.4.2 — Initialize a git repo for submission (optional but professional)
```bash
cd /home/khalid/ec2-local-cloud
git init
git add PROJECT_REQUIREMENTS.md INSTALLATION.md PLAN.md configs/
git commit -m "Final semester project: Local EC2 replica using DevStack"
```
- Do NOT commit the `screenshots/` folder if file sizes are large

---

## Phase 7 Checklist

- [x] **7.1** All 20 screenshots taken and named correctly
- [x] **7.2** Architecture diagram and data flow diagram drawn/included
- [x] **7.3** AWS vs DevStack comparison tables completed
- [x] **7.4** Project folder organized and clean
- [x] **7.5** COMMANDS_CHEATSHEET.md created (full CLI quick reference)
- [x] **7.6** DEMO_SCRIPT.md created (presentation walkthrough with fallback steps)
- [ ] Report written using screenshots as evidence
- [ ] Presentation slides reference screenshots and diagrams

---

---

# Master Progress Tracker

## Phase 1 — Environment Preparation
| Sub-step | Task | Done |
|----------|------|------|
| 1.1.4 | apt upgrade, no pending updates | ✅ |
| 1.2.1 | git, python3, build tools installed | ✅ |
| 1.2.2 | kvm-ok confirmed | ✅ |
| 1.2.3 | bridge-utils, iptables installed | ✅ |
| 1.2.4 | User added to kvm + libvirt groups | ✅ |
| 1.3.4 | Docker stopped, disabled, no processes | ✅ |
| 1.3.3 | iptables flushed | ✅ |
| 1.4.7 | 8GB swap active, permanent, swappiness=10 | ✅ |
| 1.5.5 | stack user created, passwordless sudo works | ✅ |

## Phase 2 — DevStack Installation
| Sub-step | Task | Done |
|----------|------|------|
| 2.1.2 | Internet accessible from stack user | ✅ |
| 2.2.2 | DevStack stable/2024.2 cloned, correct branch | ✅ |
| 2.3.2 | HOST_IP=10.200.194.146 verified | ✅ |
| 2.3.3 | FLAT_INTERFACE=wlp0s20f3 verified | ✅ |
| 2.4.4 | stack.sh completed, success message seen | ✅ |
| 2.5.2 | All 12 services active | ✅ |
| 2.5.3 | All 5 APIs respond | ✅ |
| 2.6.3 | Horizon loads in browser | ✅ |
| 2.6.5 | Screenshot #1 taken | ✅ |

## Phase 3 — Core Infrastructure
| Sub-step | Task | Done |
|----------|------|------|
| 3.1.4 | 4 flavors (tiny/small/medium/large) | ✅ |
| 3.2.5 | CirrOS + Ubuntu images active in Glance | ✅ |
| 3.3.3 | private-network + private-subnet created | ✅ |
| 3.4.4 | main-router connected to public + private | ✅ |
| 3.5.4 | project-key.pem file exists, mode 600 | ✅ |
| 3.6.6 | ssh-only + web-server security groups created | ✅ |

## Phase 4 — EC2 Features
| Sub-step | Task | Done |
|----------|------|------|
| 4.1.4 | Instance ACTIVE, console log shows boot | ✅ |
| 4.2.4 | Floating IP assigned, ping works | ✅ |
| 4.3.3 | SSH into VM, uname + ip addr confirmed | ✅ |
| 4.4.6 | Stop/Start/Reboot all work | ✅ |
| 4.5.5 | Volume formatted, mounted, data written | ✅ |
| 4.5.7 | Data persists across 2 VMs | ✅ |
| 4.6.5 | Snapshot restored with same data | ✅ |
| 4.7.4 | Custom AMI boots new VM | ✅ |
| 4.8.6 | nginx web server accessible in browser | ✅ |

## Phase 5 — Multi-User
| Sub-step | Task | Done |
|----------|------|------|
| 5.2.3 | dev-project + prod-project created | ✅ |
| 5.3.4 | devuser, opsuser, devadmin created | ✅ |
| 5.4.1 | Roles assigned | ✅ |
| 5.4.3 | User isolation proven | ✅ |
| 5.4.5 | Screenshot of isolated dashboard | ✅ |

## Phase 6 — Testing
| Sub-step | Task | Done |
|----------|------|------|
| 6.1.12 | All 10 tests in table: PASS | ✅ |
| 6.2.3 | Performance numbers recorded | ✅ |
| 6.3.2 | Smoke test passes | ✅ |

## Phase 7 — Documentation
| Sub-step | Task | Done |
|----------|------|------|
| 7.1 | All 20 screenshots collected | ✅ |
| 7.2 | Architecture diagram complete | ✅ |
| 7.3 | Comparison tables complete | ✅ |
| 7.4 | Project folder organized | ✅ |
| 7.5 | COMMANDS_CHEATSHEET.md created | ✅ |
| 7.6 | DEMO_SCRIPT.md created | ✅ |

## Phase 8 — Dashboard Enhancement: Full Launch Wizard
| Sub-step | Task | Done |
|----------|------|------|
| 8.1 | Add `uuid` field to `/api/networks` response for Nova attachment | ✅ |
| 8.2 | Update `POST /api/instances` to accept `network_id`, `security_groups`, `count`, `user_data` | ✅ |
| 8.3 | Remove hardcoded `private-network` and `ssh-only` from instance creation | ✅ |
| 8.4 | Add network dropdown to launch modal (filtered to internal networks only) | ✅ |
| 8.5 | Add security group checkboxes to launch modal (multi-select, ssh-only default) | ✅ |
| 8.6 | Add instance count field (1–5) to launch modal | ✅ |
| 8.7 | Add collapsible user data textarea (cloud-init script) to launch modal | ✅ |
| 8.8 | Update `openLaunchModal()` to fetch networks and security groups in parallel | ✅ |
| 8.9 | Update `submitLaunch()` to validate and send all new fields | ✅ |
| 8.10 | Update FR-01.1 and add FR-10.8 in PROJECT_REQUIREMENTS.md | ✅ |

## Phase 9 — AMI Operations (Create, Launch, Copy, Delete)
| Sub-step | Task | Done |
|----------|------|------|
| 9.1 | Add `POST /api/instances/<server_id>/image` — Nova createImage action (microversion 2.45) | ✅ |
| 9.2 | Add `DELETE /api/images/<image_id>` — Glance image delete | ✅ |
| 9.3 | Add `POST /api/images/<image_id>/copy` — duplicate image by streaming data via Glance | ✅ |
| 9.4 | Add CSS button styles: `btn-snapshot`, `btn-copy`, `btn-launch-ami` | ✅ |
| 9.5 | Add Actions column to Images table (Launch, Copy, Delete per row) | ✅ |
| 9.6 | Add AMI button to Instances table rows (ACTIVE and SHUTOFF states) | ✅ |
| 9.7 | Add `preselectedImageId` param to `openLaunchModal()` for Launch-from-AMI flow | ✅ |
| 9.8 | Add Create AMI modal with source instance name + image name input | ✅ |
| 9.9 | Add Copy AMI modal with new name input and size warning | ✅ |
| 9.10 | Add JS functions: `launchFromAmi`, `openCreateAmiModal`, `submitCreateAmi`, `openCopyAmiModal`, `submitCopyAmi`, `deleteImage` | ✅ |
| 9.11 | Update FR-02 in PROJECT_REQUIREMENTS.md to reflect dashboard AMI operations | ✅ |
| 9.12 | Add UI Tests 9–12 in test.md for AMI operations | ✅ |

## Phase 10 — Key Pair Management (Create, Download, Use in SSH, Delete)
| Sub-step | Task | Done |
|----------|------|------|
| 10.1 | Expand `GET /api/keypairs` to return full objects (name, fingerprint, public_key, created_at) instead of names only | ✅ |
| 10.2 | Add `POST /api/keypairs` — Nova key pair creation; returns private_key in response (only at creation time) | ✅ |
| 10.3 | Add `DELETE /api/keypairs/<name>` — remove a key pair by name | ✅ |
| 10.4 | Add Key Pairs nav item under Networking in the sidebar with a count badge | ✅ |
| 10.5 | Add Key Pairs section with table (Name, Fingerprint, Created, SSH Usage, Actions) | ✅ |
| 10.6 | Add Create Key Pair modal with name input and one-time-download warning | ✅ |
| 10.7 | Auto-download `.pem` file via Blob URL immediately after successful creation (Nova private key is one-time only) | ✅ |
| 10.8 | Add `deleteKeypair()` with confirmation dialog explaining running instances are not affected | ✅ |
| 10.9 | Fix `openLaunchModal()` keypair dropdown to map `kp.name` after API response shape change | ✅ |
| 10.10 | Update FR-07 in PROJECT_REQUIREMENTS.md to reflect dashboard key pair operations | ✅ |
| 10.11 | Add UI Tests 13–16 in test.md for key pair operations | ✅ |

## Phase 11 — Missing EC2 Services: Backend (Snapshots, Console, Ports, Quotas)
| Sub-step | Task | Done |
|----------|------|------|
| 11.1 | `GET /api/snapshots` — list all Cinder snapshots with project name resolution | ✅ |
| 11.2 | `POST /api/snapshots` — create snapshot from volume (`force: True` for in-use volumes) | ✅ |
| 11.3 | `DELETE /api/snapshots/<id>` — delete snapshot | ✅ |
| 11.4 | `POST /api/volumes/from-snapshot` — restore Cinder volume from snapshot | ✅ |
| 11.5 | `POST /api/instances/<id>/console` — get Nova VNC console URL (`os-getVNCConsole`) | ✅ |
| 11.6 | `GET /api/instances/<id>/console-output` — get serial console log (`os-getConsoleOutput`, max 500 lines) | ✅ |
| 11.7 | `GET /api/ports` — list Neutron ports with subnet and IP info | ✅ |
| 11.8 | `POST /api/ports` — create standalone Neutron port on a network | ✅ |
| 11.9 | `DELETE /api/ports/<id>` — delete port | ✅ |
| 11.10 | `GET /api/instances/<id>/interfaces` — list ports attached to an instance (`os-interface`) | ✅ |
| 11.11 | `POST /api/instances/<id>/interfaces` — attach port or auto-create on network (`os-interface`) | ✅ |
| 11.12 | `DELETE /api/instances/<id>/interfaces/<port_id>` — detach interface from instance | ✅ |
| 11.13 | `GET /api/quotas` — aggregate compute+volume+network quotas per project with usage | ✅ |
| 11.14 | `PUT /api/quotas/<project_id>` — update a single quota key (value -1 = unlimited) | ✅ |

## Phase 12 — Missing EC2 Services: UI (Snapshots, Console, Ports, Quotas)
| Sub-step | Task | Done |
|----------|------|------|
| 12.1 | Add Snapshots nav item under Storage (after Volumes) | ✅ |
| 12.2 | Add Network Interfaces nav item under Networking (after Key Pairs) | ✅ |
| 12.3 | Add Quotas nav item under Identity (after Users) | ✅ |
| 12.4 | Add `section-snapshots` HTML section with table (ID, Name, Status, Size, Source Volume, Project, Created, Actions) | ✅ |
| 12.5 | Add `section-ports` HTML section with table (ID, Name, Status, MAC, IPs, Device/Owner, Actions) | ✅ |
| 12.6 | Add `section-quotas` HTML section with `quotas-grid` div for JS-rendered quota cards | ✅ |
| 12.7 | Add Create Snapshot modal (volume dropdown, name, description) | ✅ |
| 12.8 | Add Restore Snapshot modal (snapshot name disabled, new volume name, size ≥ original) | ✅ |
| 12.9 | Add Create Port modal (network dropdown, port name) | ✅ |
| 12.10 | Add Attach Interface modal (free-port dropdown OR network dropdown for auto-create) | ✅ |
| 12.11 | Add Console modal XL (VNC link, line count selector, scrollable log output, XSS-safe) | ✅ |
| 12.12 | Register all 5 new modals in `bootstrap.Modal(...)` initialization block | ✅ |
| 12.13 | Update `loadSection` map with `snapshots → fetchSnapshots`, `ports → fetchPorts`, `quotas → fetchQuotas` | ✅ |
| 12.14 | Add Console and NIC buttons to ACTIVE instance rows in `fetchInstances()` | ✅ |
| 12.15 | Add `fetchSnapshots`, `openCreateSnapshotModal`, `submitCreateSnapshot`, `openRestoreSnapshotModal`, `submitRestoreSnapshot`, `deleteSnapshot` JS functions | ✅ |
| 12.16 | Add `openConsoleModal`, `loadConsoleOutput`, `renderConsoleOutput`, `_consoleServerId` JS functions | ✅ |
| 12.17 | Add `fetchPorts`, `openCreatePortModal`, `submitCreatePort`, `deletePort`, `openAttachInterfaceModal`, `submitAttachInterface` JS functions | ✅ |
| 12.18 | Add `fetchQuotas` and `quotaSection` JS functions (progress bars, green/amber/red by % used) | ✅ |

---

*Project: Local EC2 Replica | DevStack 2024.2 | Ubuntu 24.04 | Final Semester*
*Machine: Acer TravelMate P215-53 | 10.200.194.146 | wlp0s20f3*
