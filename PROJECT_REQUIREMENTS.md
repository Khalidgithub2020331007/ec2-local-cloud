# Local EC2 Replica — Final Semester Project
### Platform: DevStack (OpenStack Dalmatian) | OS: Ubuntu 24.04 LTS | Scale: Single Node

---

## Project Overview

This project builds a local cloud computing environment that replicates the core features of **Amazon EC2 (Elastic Compute Cloud)** using **DevStack** — the official single-node OpenStack installer — on a single physical machine. DevStack installs and configures all OpenStack services (Nova, Neutron, Glance, Cinder, Keystone, Horizon) automatically, giving a fully functional private cloud without needing multiple servers. The system allows users to launch, manage, and terminate virtual machines through both a web dashboard and a command-line interface — mirroring the real-world cloud experience.

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
- **Docker:** installed — must stop Docker before running DevStack to avoid iptables conflicts

> **Note on WiFi:** DevStack works on WiFi but floating IPs will only be reachable from the same machine. For the semester project demo this is fine — the dashboard and SSH to instances both work normally.

---

### Software Requirements

| Software | Version | Purpose |
|----------|---------|---------|
| Ubuntu | 24.04 LTS (Noble) ✅ | Host Operating System |
| DevStack | stable/2024.2 (Dalmatian) | Single-node OpenStack installer — chosen over manual OpenStack for speed and simplicity |
| Python | 3.12 (Ubuntu 24.04 default) | OpenStack services are written in Python |
| KVM / QEMU | Latest from apt | Hypervisor that runs the virtual machines |
| libvirt | Latest from apt | API layer between Nova and KVM |
| LinuxBridge | Kernel built-in | Virtual networking — used instead of OVS for WiFi compatibility |
| Git | 2.x | DevStack clones all OpenStack service repos during install |
| MySQL | 8.x | Stores all OpenStack service state (instances, volumes, images metadata) |
| RabbitMQ | 3.x | Message queue — Nova, Neutron, Cinder communicate through it |
| Apache2 | 2.4.x | Serves the Horizon dashboard and Keystone API |
| Memcached | Latest | Caches Keystone tokens to reduce auth overhead |

---

## DevStack Services Installed (EC2 Feature Map)

> DevStack installs and manages all of these as systemd units (`devstack@nova-api`, etc.).

| OpenStack Service | Service Code | EC2 / AWS Equivalent | Description |
|---|---|---|---|
| **Keystone** | `key` | IAM (Identity & Access Management) | User authentication, project/role management |
| **Nova** | `n-api, n-cpu, n-sch, n-cond` | EC2 Compute | Create, start, stop, terminate virtual machines |
| **Glance** | `g-api, g-reg` | AMI (Amazon Machine Images) | Store and manage VM disk images |
| **Neutron** | `q-svc, q-agt, q-dhcp, q-l3` | VPC + Security Groups | Virtual networking, floating IPs, firewall rules |
| **Cinder** | `c-api, c-vol, c-sch` | EBS (Elastic Block Store) | Persistent block storage volumes for VMs |
| **Horizon** | `horizon` | AWS Management Console | Web-based GUI dashboard |
| **Placement** | `placement-api` | EC2 Resource Scheduler | Tracks and allocates compute resources |
| ~~Swift~~ | ~~s-proxy~~ | ~~S3 Object Storage~~ | Disabled — saves ~1GB RAM on 8GB machine |
| ~~Heat~~ | ~~h-api~~ | ~~CloudFormation~~ | Disabled — saves RAM |
| ~~Ceilometer~~ | ~~ceilometer-*~~ | ~~CloudWatch~~ | Disabled — saves RAM |

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
- **FR-02.3** — User can create a snapshot of a running instance as a new image
- **FR-02.4** — Images can be set as `public` (available to all) or `private`
- **FR-02.5** — User can delete images they own

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
- **FR-07.1** — User can upload an existing public key to create a key pair
- **FR-07.2** — User can generate a new key pair and download the private key
- **FR-07.3** — Key pair must be injected into new instances at launch
- **FR-07.4** — User can delete key pairs
- **FR-07.5** — SSH access to instance must work using the associated private key

### FR-08: Block Storage / Volumes (EBS Equivalent)
- **FR-08.1** — User can create a persistent volume with a specified size (GB)
- **FR-08.2** — User can attach a volume to a running or stopped instance
- **FR-08.3** — Volume appears as a block device inside the instance (e.g., `/dev/vdb`)
- **FR-08.4** — User can detach a volume from an instance without data loss
- **FR-08.5** — User can delete a volume (only when detached)
- **FR-08.6** — User can create a snapshot of a volume
- **FR-08.7** — User can create a new volume from an existing snapshot

### FR-09: Identity & Multi-User Management (IAM Equivalent)
- **FR-09.1** — System shall have a default `admin` superuser
- **FR-09.2** — Admin can create new user accounts with username and password
- **FR-09.3** — Admin can create projects (like AWS accounts/namespaces)
- **FR-09.4** — Admin can assign users to projects with specific roles (`admin`, `member`, `reader`)
- **FR-09.5** — Users in different projects cannot see each other's instances or volumes
- **FR-09.6** — Admin can disable or delete users

### FR-10: Web Dashboard (AWS Management Console Equivalent)
- **FR-10.1** — Horizon dashboard accessible at `http://<HOST_IP>/dashboard`
- **FR-10.2** — Login with domain, username, and password
- **FR-10.3** — Dashboard shall show instance list with status, IP, flavor, and image
- **FR-10.4** — User can perform all instance operations (launch, stop, reboot, delete) from GUI
- **FR-10.5** — Dashboard shall provide VNC console access to instances (like EC2 Instance Connect)
- **FR-10.6** — Dashboard shall show volume list, network topology, and security group rules
- **FR-10.7** — Admin panel accessible to `admin` user for system-wide management
- **FR-10.8** — Launch wizard shall support: selectable network, multi-select security groups, instance count (1–5), and user data (cloud-init) input — matching the AWS EC2 launch wizard scope

### FR-11: Command Line Interface (AWS CLI Equivalent)
- **FR-11.1** — `openstack` CLI available for all operations
- **FR-11.2** — Credentials loaded via `source openrc admin admin`
- **FR-11.3** — CLI shall support all operations available in the dashboard
- **FR-11.4** — CLI shall return structured output (table/JSON/YAML formats)

---

## Non-Functional Requirements

### NFR-01: Performance
- Instance launch time: under 90 seconds for CirrOS image
- Dashboard page load time: under 5 seconds on local network
- System must support at least 3 simultaneous running instances

### NFR-02: Availability
- All DevStack services must auto-recover via systemd if they crash
- Stack must survive a `./rejoin-stack.sh` restart after host reboot without re-running `./stack.sh`

### NFR-03: Security
- All service communication uses token-based authentication via Keystone
- Default security group must deny all inbound traffic
- Dashboard login is protected by username/password
- SSH to instances requires a valid private key

### NFR-04: Usability
- Horizon dashboard must be accessible from any browser on the same LAN
- All CLI operations must work without memorizing API endpoints
- Error messages from failed operations must be human-readable

### NFR-05: Resource Constraints (Single Node Limits)
- Total RAM usage by OpenStack services: under 5 GB (leaving 3 GB for VMs)
- Disk usage by images and volumes: under 100 GB
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
- [x] Web dashboard (Horizon)
- [x] OpenStack CLI

### Out of Scope
- [ ] Object storage (S3 / Swift) — disabled for RAM constraints
- [ ] Load balancing (ELB / Octavia)
- [ ] Auto-scaling
- [ ] CloudFormation / Heat orchestration
- [ ] Monitoring/metrics (CloudWatch / Ceilometer)
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
