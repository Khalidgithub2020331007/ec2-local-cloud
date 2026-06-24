# Local EC2 Replica — Final Semester Project
### Platform: Mini Cloud (Flask + libvirt/KVM + LVM + iptables) | OS: Ubuntu 24.04 LTS | Scale: Single Node

---

## Project Overview

This project builds a local cloud computing environment that replicates the core features of **Amazon EC2 (Elastic Compute Cloud)** using Linux kernel tools directly — KVM runs the virtual machines, LVM manages block storage, Linux Bridge creates virtual networks, iptables enforces firewall rules and floating IPs. A Python Flask application provides the REST API and web dashboard. No cloud management framework is used — every feature is implemented from scratch on a single physical machine.

---

## System Requirements

### Hardware Requirements

| Component | Minimum | Recommended | Your Machine (Verified) |
|-----------|---------|-------------|--------------------------|
| CPU | 4 cores with VT-x/AMD-V | 6+ cores | 16 cores, VMX ✅ |
| RAM | 6 GB | 8–12 GB | 8 GB ⚠️ (add swap) |
| Storage | 80 GB free | 150+ GB | 526 GB ✅ |
| Network | 1 NIC | Wired preferred | WiFi only ⚠️ |
| KVM Support | Required | Required | `/dev/kvm` exists ✅ |
| Architecture | x86_64 | x86_64 | x86_64 ✅ |

**Verified system details:**
- **Machine:** Acer TravelMate P215-53
- **Host IP:** `10.200.194.146` (WiFi — `wlp0s20f3`)
- **Ethernet:** `enp43s0` — NO-CARRIER (unplugged)
- **Docker:** installed — stop Docker before running mini-cloud to avoid iptables conflicts

> **Note on WiFi:** Mini cloud works on WiFi. Floating IPs are only reachable from the same machine (no external routing). For the semester project demo this is fine — the dashboard and SSH to instances both work normally.

---

### Software Requirements

| Software | Version | Purpose |
|----------|---------|---------|
| Ubuntu | 24.04 LTS (Noble) ✅ | Host Operating System |
| Python | 3.12 (Ubuntu 24.04 default) ✅ | Flask API server and all business logic |
| Flask | 3.0.0 | REST API framework + web dashboard |
| PyJWT | 2.8.0 | JWT-based authentication |
| libvirt-python | 10.0.0 | Python bindings to call libvirt API |
| KVM / QEMU | Latest from apt ✅ | Hypervisor that runs the virtual machines |
| libvirt | Latest from apt ✅ | API layer between Flask and KVM |
| Linux Bridge | Kernel built-in ✅ | Virtual networking for VM subnets |
| dnsmasq | Latest from apt ✅ | DHCP server for each virtual network |
| iptables | Kernel built-in ✅ | Security group rules and floating IP NAT |
| LVM2 | Latest from apt ✅ | Block storage volumes and snapshots |
| HAProxy | Latest from apt ✅ | Load balancing |
| websockify | Latest from apt ✅ | VNC-to-WebSocket bridge for browser console |
| genisoimage | Latest from apt ✅ | Builds cloud-init seed ISOs for SSH key injection |
| SQLite | 3.x (Python built-in) ✅ | Database — stores all resource state |

---

## Mini Cloud Feature Map (EC2 Equivalent)

| Feature | EC2 / AWS Equivalent | Implementation |
|---|---|---|
| Virtual Machines | EC2 Instances | libvirt + KVM (QEMU) |
| OS Templates | AMIs | qcow2 files + SQLite metadata |
| Instance Sizes | Instance Types | Hardcoded flavor table (t1.nano … t1.medium) |
| Block Storage | EBS Volumes | LVM Logical Volumes |
| Storage Snapshots | EBS Snapshots | LVM CoW snapshots |
| Public IPs | Elastic IPs | iptables DNAT/SNAT on dummy interface |
| Private Networks | VPC Subnets | Linux Bridge + dnsmasq DHCP |
| Firewall Rules | Security Groups | Per-VM iptables chains (MC-SG-<id>) |
| SSH Keys | EC2 Key Pairs | RSA keys via cryptography library; cloud-init ISO injection |
| Identity | IAM | Custom SQLite-backed IAM layer |
| Web Console | AWS Management Console | Flask + vanilla JS dashboard (port 5001) |
| Load Balancing | ELB | HAProxy frontends/backends |
| Auto Scaling | Auto Scaling Groups | Python background thread with libvirt CPU metrics |
| Resource Monitoring | CloudWatch | /proc/stat + libvirt stats |
| Resource Limits | Service Quotas | SQLite quota tables with per-user overrides |

---

## Functional Requirements

### FR-01: Virtual Machine Lifecycle Management
- **FR-01.1** — User can launch a new virtual machine (instance) by selecting image, flavor, network, security group(s), key pair, instance count (1–5), and optional user data (cloud-init script)
- **FR-01.2** — User can start a stopped instance
- **FR-01.3** — User can stop a running instance (graceful shutdown)
- **FR-01.4** — User can hard reboot a running instance
- **FR-01.5** — User can terminate (permanently delete) an instance
- **FR-01.6** — System shall display real-time instance status: `BUILD`, `ACTIVE`, `SHUTOFF`, `ERROR`

### FR-02: Machine Images (AMI Equivalent)
- **FR-02.1** — System shall provide a default CirrOS test image pre-loaded on setup
- **FR-02.2** — Admin can upload custom disk images (qcow2, raw, vmdk formats)
- **FR-02.3** — User can create a snapshot of a running or stopped instance as a new image (Create AMI) — via dashboard AMI button on any instance row
- **FR-02.4** — Images can be set as `public` (available to all) or `private`
- **FR-02.5** — User can delete images they own — via dashboard Delete button in Images table
- **FR-02.6** — User can duplicate an existing image with a new name (Copy AMI) — qcow2 file is copied on disk; CirrOS copies in seconds, Ubuntu in several minutes
- **FR-02.7** — User can launch a new instance directly from the Images table (Launch from AMI) — opens the launch wizard with the selected image pre-filled

### FR-03: Instance Types / Flavors (EC2 Instance Types Equivalent)
- **FR-03.1** — Admin can create custom flavors defining vCPU count, RAM, and disk size
- **FR-03.2** — System shall provide these default flavors:

  | Flavor | vCPU | RAM | Disk | EC2 Analogy |
  |--------|------|-----|------|-------------|
  | m1.tiny | 1 | 512 MB | 1 GB | t2.nano |
  | m1.small | 1 | 2 GB | 20 GB | t2.small |
  | m1.medium | 2 | 4 GB | 40 GB | t2.medium |

- **FR-03.3** — Admin can delete or modify flavors

### FR-04: Networking (VPC Equivalent)
- **FR-04.1** — Admin can create virtual networks and subnets
- **FR-04.2** — System shall support an isolated private network per project
- **FR-04.3** — System shall provide a public/external network for floating IPs
- **FR-04.4** — User can create a virtual router and attach it to subnets
- **FR-04.5** — System shall support DHCP-based IP assignment within private networks
- **FR-04.6** — System shall support DNS resolution for instances

### FR-05: Floating IPs (Elastic IP Equivalent)
- **FR-05.1** — User can allocate a floating IP from the public pool
- **FR-05.2** — User can associate a floating IP with a running instance
- **FR-05.3** — User can disassociate a floating IP from an instance
- **FR-05.4** — User can release (return) a floating IP to the pool
- **FR-05.5** — Associated floating IP must allow SSH and other permitted traffic to reach the instance

### FR-06: Security Groups (EC2 Security Groups Equivalent)
- **FR-06.1** — User can create named security groups
- **FR-06.2** — User can add inbound rules: protocol (TCP/UDP/ICMP), port range, source CIDR
- **FR-06.3** — User can add outbound rules
- **FR-06.4** — User can attach/detach security groups to running instances
- **FR-06.5** — System shall deny all inbound traffic by default (whitelist model)
- **FR-06.6** — User can delete security group rules individually

### FR-07: SSH Key Pairs (EC2 Key Pairs Equivalent)
- **FR-07.1** — User can upload an existing public key to create a key pair (CLI)
- **FR-07.2** — User can generate a new key pair from the dashboard; the private key downloads automatically as a `.pem` file immediately on creation — it is not stored and cannot be retrieved again
- **FR-07.3** — Key pair must be injected into new instances at launch (supported in both CLI and launch wizard)
- **FR-07.4** — User can delete key pairs from the dashboard; running instances using the key are not affected
- **FR-07.5** — SSH access to instance must work using the downloaded private key: `ssh -i <name>.pem <user>@<floating-ip>`
- **FR-07.6** — Dashboard Key Pairs section displays: name, fingerprint, creation date, SSH command hint, and delete action per row

### FR-08: Block Storage / Volumes (EBS Equivalent)
- **FR-08.1** — User can create a persistent volume with a specified size (GB)
- **FR-08.2** — User can attach a volume to a running or stopped instance
- **FR-08.3** — Volume appears as a block device inside the instance (e.g., `/dev/vdb`)
- **FR-08.4** — User can detach a volume from an instance without data loss
- **FR-08.5** — User can delete a volume (only when detached)
- **FR-08.6** — User can create a snapshot of a volume
- **FR-08.7** — User can create a new volume from an existing snapshot

### FR-09: Identity & Multi-User Management (IAM Equivalent)

#### FR-09A: Login Accounts (SQLite-backed)
- **FR-09.1** — System shall have a default `admin` superuser
- **FR-09.2** — Admin can create new user accounts with username and password
- **FR-09.3** — Users are isolated — each can only see their own instances, volumes, and networks
- **FR-09.4** — Admin can disable or delete users

#### FR-09B: AWS-Style IAM Layer (SQLite-backed, managed via dashboard)
- **FR-09.7** — Dashboard shall provide an IAM section under the Identity sidebar group, reachable via the **IAM** nav item
- **FR-09.8** — IAM section shall have four sub-tabs: **Users**, **Groups**, **Roles**, and **Policies**
- **FR-09.9** — Admin can create **IAM Users** with a username; each user receives a unique ARN (`arn:aws:iam::123456789012:user/<name>`)
- **FR-09.10** — Admin can delete IAM users; deletion auto-removes the user from all groups
- **FR-09.11** — Admin can create **IAM Groups** (e.g. `Developers`, `ReadOnly`); each group receives a unique ARN
- **FR-09.12** — Admin can add and remove IAM users from groups via a "Members" modal
- **FR-09.13** — Admin can delete groups; deletion auto-removes the group from all user records
- **FR-09.14** — Admin can create **IAM Roles** with a name, optional description, and a trusted service principal (EC2, Lambda, S3, ECS Tasks, or EKS); the trust policy document is auto-generated as `sts:AssumeRole`
- **FR-09.15** — Admin can delete IAM roles
- **FR-09.16** — System shall provide 7 pre-seeded **AWS Managed Policies** that cannot be deleted:

  | Policy Name | Effect |
  |---|---|
  | `AdministratorAccess` | Allow `*` on `*` |
  | `PowerUserAccess` | Allow all except `iam:*` and `organizations:*` |
  | `ReadOnlyAccess` | Allow `ec2:Describe*`, `iam:Get*`, `iam:List*` |
  | `AmazonEC2FullAccess` | Allow `ec2:*` |
  | `AmazonEC2ReadOnlyAccess` | Allow `ec2:Describe*` |
  | `IAMFullAccess` | Allow `iam:*` |
  | `IAMReadOnlyAccess` | Allow `iam:Get*`, `iam:List*` |

- **FR-09.17** — Admin can create **customer-managed policies** by providing a name, description, and a JSON policy document with `Version` and `Statement` fields; the JSON is validated before saving
- **FR-09.18** — Customer-managed policies can be deleted; deletion auto-detaches the policy from all users, groups, and roles
- **FR-09.19** — Any policy (managed or customer) can be **attached to** or **detached from** a user, group, or role via a searchable Attach Policy modal; already-attached policies show a "Detach" button inline
- **FR-09.20** — Policy document JSON can be viewed in a formatted viewer modal via the **View JSON** action on any policy row
- **FR-09.21** — IAM data persists across dashboard restarts via `dashboard/iam_data.json` (same pattern as `asg_groups.json`)
- **FR-09.22** — AWS managed policies are visually distinguished from customer policies with a blue "AWS Managed" badge vs. an amber "Customer" badge

### FR-12: Monitoring (CloudWatch Equivalent)
- **FR-12.1** — Dashboard shall expose a **Monitoring** section in the sidebar under a dedicated "Monitoring" nav group
- **FR-12.2** — Monitoring section shall display hypervisor resource utilization: vCPU (used / total), RAM (used / total), and Disk (used / total), each with a visual progress bar that turns orange above 60% and red above 80%
- **FR-12.3** — Monitoring section shall display a per-instance metrics table for all instances; ACTIVE instances show live diagnostic counters (CPU time, memory allocated, disk read/write bytes, network RX/TX bytes); non-ACTIVE instances show a placeholder row
- **FR-12.4** — Overview page shall include a compact Resource Utilization panel (vCPU, RAM, Disk bars) with a "View full metrics →" link to the Monitoring section
- **FR-12.5** — Metrics are sourced from `/proc/stat` + `/proc/meminfo` (host) and libvirt `getCPUStats()` + `memoryStats()` (per-instance) — no external monitoring daemon required
- **FR-12.6** — All metric values are cumulative counters at time of request (not time-series rates); the page shows a note explaining this

---

### FR-10: Web Dashboard (AWS Management Console Equivalent)
- **FR-10.1** — Mini cloud dashboard accessible at `http://localhost:5001`
- **FR-10.2** — Login with username and password; JWT token returned for API access
- **FR-10.3** — Dashboard shall show instance list with status, IP, flavor, and image
- **FR-10.4** — User can perform all instance operations (launch, stop, reboot, delete) from GUI
- **FR-10.5** — Dashboard shall provide VNC console access to instances via websockify + noVNC
- **FR-10.6** — Dashboard shall show volume list, network list, floating IPs, and security group rules
- **FR-10.7** — Admin can manage quotas and see all users' resources

### FR-11: REST API (AWS CLI Equivalent)
- **FR-11.1** — All operations available via REST API at `http://localhost:5001/api/v1/`
- **FR-11.2** — Authentication via JWT Bearer token (`Authorization: Bearer <token>`)
- **FR-11.3** — API returns JSON with consistent envelope shape (`{data, error, statusCode}`)
- **FR-11.4** — All list endpoints support pagination (`page`, `limit`, `total`)

---

## Non-Functional Requirements

### NFR-01: Performance
- Instance launch time: under 90 seconds for CirrOS image
- Dashboard page load time: under 5 seconds on local network
- System must support at least 3 simultaneous running instances

### NFR-02: Availability
- libvirtd must be set to auto-restart via systemd
- Floating IP state (iptables rules + mc-fip interface) must be restored on boot via `restore_fip.py`
- LVM loop device must be re-attached on boot via startup script

### NFR-03: Security
- All API endpoints require JWT Bearer token authentication
- Default security group must deny all inbound traffic
- Dashboard login is protected by username/password (Werkzeug PBKDF2-SHA256 hashing)
- SSH to instances requires a valid private key (injected via cloud-init seed ISO)
- Private keys are never stored — shown once and discarded

### NFR-04: Usability
- Dashboard accessible from any browser on the same LAN at port 5001
- All operations available via REST API with curl
- Error messages must include `error` code, `message`, and `statusCode`

### NFR-05: Resource Constraints (Single Node Limits)
- Flask + SQLite use under 200 MB RAM (leaving the rest for VMs)
- Disk usage by images and volumes managed by LVM VG (20 GB backing file by default)
- Swap space: 8 GB configured and active

---

## Project Scope

### In Scope
- [x] VM launch, stop, start, reboot, terminate
- [x] Custom images upload and snapshot
- [x] Custom flavors (instance types)
- [x] Private networking with subnets
- [x] Floating IPs (Elastic IP equivalent)
- [x] Security groups with inbound/outbound rules
- [x] SSH key pair management
- [x] Persistent block storage (volumes + snapshots)
- [x] Multi-user and multi-project setup
- [x] Web dashboard (Flask + vanilla JS, port 5001)
- [x] REST API (JWT-authenticated, full CRUD for all resources)
- [x] Monitoring/metrics — hypervisor + per-instance diagnostics via /proc and libvirt (CloudWatch equivalent)

### Out of Scope
- [ ] Object storage (S3 / Swift) — disabled for RAM constraints
- [ ] CloudFormation / Heat orchestration
- [ ] High availability (multi-node cluster)
- [ ] Production-grade TLS/HTTPS for API endpoints

---

## Directory Structure

```
ec2-local-cloud/
├── PROJECT_REQUIREMENTS.md     ← This file
├── INSTALLATION.md             ← Step-by-step DevStack setup
├── COMMANDS_CHEATSHEET.md      ← Quick reference for all openstack commands
├── DEMO_SCRIPT.md              ← Presentation walkthrough
├── screenshots/                ← Dashboard and CLI screenshots
│   ├── dashboard_login.png
│   ├── launch_instance.png
│   ├── floating_ip.png
│   └── ssh_access.png
└── configs/
    └── local.conf              ← DevStack configuration file used
```

---

## Comparison: This Project vs Real AWS EC2

| Feature | AWS EC2 | This Project (DevStack) |
|---|---|---|
| Installer / Platform | AWS proprietary | **DevStack** (single-node OpenStack installer) |
| Compute Engine | KVM (AWS Nitro) | Nova + KVM (open source) |
| Image Store | S3-backed AMIs | Glance (stored on local disk) |
| Networking | AWS VPC | Neutron + **LinuxBridge** (WiFi-compatible) |
| Block Storage | EBS (NVMe SSD) | Cinder (local disk, LVM backend) |
| Identity | IAM | Keystone |
| Dashboard | AWS Management Console | Horizon |
| CLI | AWS CLI (`aws`) | OpenStack CLI (`openstack`) |
| Monitoring | CloudWatch (Ceilometer) | Nova diagnostics API — no extra services needed |
| Scale | Global, millions of nodes | Single machine (your laptop) |
| HA / Redundancy | Multi-AZ, automatic failover | None — single node |
| Setup time | Instant (managed service) | ~1 hour (`./stack.sh`) |
| Cost | Pay-per-use | Free (your own hardware) |

---

## Team / Author

- **Project Title:** Local Cloud Infrastructure — EC2 Replica Using DevStack
- **Platform:** DevStack stable/2024.2 (Dalmatian) on Ubuntu 24.04 LTS
- **Machine:** Acer TravelMate P215-53 | 8GB RAM | 16 CPU | WiFi
- **Semester:** Final Semester
- **Course:** Cloud Computing / Distributed Systems

---

*Last updated: June 2026*
