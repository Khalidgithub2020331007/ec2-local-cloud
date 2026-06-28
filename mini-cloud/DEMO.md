# Mini Cloud System — Teacher Demo

## What This Project Is

This project builds a local cloud computing platform equivalent to AWS EC2 — from scratch. Every feature is implemented in Python (Flask) using Linux kernel tools directly: KVM runs the virtual machines, LVM manages block storage, Linux Bridge creates virtual networks, iptables enforces security groups and floating IPs, and HAProxy distributes load. The result is a working cloud dashboard where users can launch VMs, manage storage, configure networking, and control access — demonstrating the same underlying mechanics that power production cloud platforms.

---

## Architecture Diagram (ASCII)

```
  Browser (Chrome / Firefox)
       │
       │  HTTP :5001
       ▼
  ┌─────────────────────────────────────────────────────────┐
  │               Flask Dashboard (port 5001)               │
  │                                                         │
  │  /api/v1/auth         →  JWT-based login / register     │
  │  /api/v1/compute      →  VM lifecycle (launch/stop)     │
  │  /api/v1/images       →  OS image store                  │
  │  /api/v1/network      →  VPC / floating IPs / routers   │
  │  /api/v1/security-groups  →  firewall rule sets         │
  │  /api/v1/keypairs     →  SSH RSA key management         │
  │  /api/v1/volumes      →  block storage + snapshots      │
  │  /api/v1/load-balancers   →  HAProxy frontends          │
  │  /api/v1/autoscaling  →  scale-up/down policy engine    │
  │  /api/v1/monitoring   →  host + VM metrics              │
  │  /api/v1/quotas       →  per-user resource limits       │
  │  /api/v1/iam          →  users / groups / roles         │
  │  /api/v1/instances/<id>/console  →  VNC via WebSocket   │
  └────────────────────┬────────────────────────────────────┘
                       │
       ┌───────────────┼────────────────────┐
       │               │                    │
       ▼               ▼                    ▼
  libvirt/KVM      HAProxy             SQLite DB
  (virtual         (load               (cloud.db —
   machines)        balancing)          all state)
       │
       ├── LVM (mini-cloud-vg)   → block volumes / snapshots
       ├── Linux Bridge (mcbr*)  → VM private networks
       ├── dnsmasq               → DHCP inside each network
       ├── iptables NAT chains   → floating IPs (DNAT/SNAT)
       ├── iptables MC-SG chains → per-VM security rules
       └── websockify            → VNC → WebSocket proxy
```

---

## Demo Steps (in order)

### Step 1 — Login to the Dashboard

Open `http://localhost:5001` in a browser.  
Enter: **admin / Admin1234**

**Explain:** Authentication uses JWT (JSON Web Token). When the user logs in, the server signs a token with a secret key and sends it back. Every subsequent API request includes this token in the `Authorization: Bearer <token>` header. The server verifies the signature on every request — no session is stored server-side. This is stateless authentication, the same model AWS uses for its STS tokens.

---

### Step 2 — Upload a CirrOS Image

Click **Images** in the sidebar → **Upload Image**.  
Upload the CirrOS file at `/tmp/cirros-0.6.2.img`.  
Set name: `CirrOS 0.6.2`.

**Explain:** The qcow2 file is copied to `storage/images/` on the server. Its metadata (name, format, size, path) is recorded in SQLite. When a VM is launched, the image file is used as the backing store for the VM's root disk — we use `qemu-img create` with `backing_file` so the original image is never modified; each VM gets a copy-on-write overlay.

---

### Step 3 — Launch a VM

Click **Instances** → **Launch Instance**.  
Set: name=`demo-vm`, flavor=`t1.nano` (1 vCPU, 512 MB RAM), image=`CirrOS 0.6.2`.

**Trace the full flow (explain each line):**

1. Flask validates the request and checks quotas (instances ≤ 5, vCPUs ≤ 10, RAM ≤ 10 GB).
2. A row is inserted in the `instances` table with `status=pending`.
3. `qemu-img create -f qcow2 -b <base-image> <disk-path>` creates the VM disk (CoW overlay).
4. A libvirt XML domain definition is built (vCPUs, RAM, disk path, VNC port).
5. `virsh define` registers it, `virsh start` launches it — KVM creates the VM process.
6. The VNC port is read from libvirt, status is updated to `running`.
7. An iptables chain `MC-SG-<vm-id>` is created for this VM's firewall rules.

---

### Step 4 — Show VM becomes ACTIVE

In the Instances tab, the status badge shows **Running**.

**Explain:** The dashboard polls `GET /api/v1/compute/instances` every few seconds. Each call syncs the status from libvirt (calling `domain.state()`) — so if a VM crashes or is stopped outside the dashboard, the status updates automatically. The status lifecycle is: `pending → running → stopped → terminated`.

---

### Step 5 — Allocate a Floating IP

Click **Network** → **Floating IPs** → **Allocate IP**.

**Explain:** Floating IPs are public-routable IPs assigned to VMs, equivalent to AWS Elastic IPs. We pre-define a pool: `192.168.0.224/27` (30 IPs). When allocating, the next free IP is chosen from the pool, assigned to the host's loopback-alias interface (`ip addr add 192.168.0.225/27 dev lo`), and recorded in the DB with `status=allocated`.

---

### Step 6 — Associate Floating IP to a VM

Click **Associate** next to the floating IP, select `demo-vm`.

**Show the iptables rule:**
```bash
sudo iptables -t nat -L -n
```

Expected output includes:
```
DNAT  tcp  --  0.0.0.0/0  192.168.0.225  to:<vm-private-ip>
SNAT  all  --  <vm-private-ip>  0.0.0.0/0  to:192.168.0.225
```

**Explain:** Two iptables NAT rules are created:
- **DNAT** (Destination NAT): Incoming packets destined for the floating IP get their destination rewritten to the VM's private IP.
- **SNAT** (Source NAT): Outgoing packets from the VM's private IP get their source rewritten to the floating IP.

The VM itself never knows it has a floating IP — it only sees its private IP. This is exactly how AWS Elastic IPs work.

---

### Step 7 — Open VNC Console

Click **Instances** → **Console** next to `demo-vm`.

A noVNC window opens in the browser showing the VM's terminal.

**Explain:** VNC is a remote framebuffer protocol — it works over raw TCP. Browsers cannot open raw TCP connections, only WebSockets. We use **websockify** as a bridge: it listens on a WebSocket port and forwards traffic to the VNC TCP port. The `GET /api/v1/instances/<id>/console` endpoint starts websockify, returns the `ws://` URL. The browser loads noVNC (an HTML5 VNC client) and connects to that URL.

---

### Step 8 — Add SSH Rule to Security Group

Click **Security Groups** → **Create Group** → add rule:  
Direction: Inbound, Protocol: TCP, Port: 22, CIDR: 0.0.0.0/0.

**Explain:** Security groups are named sets of firewall rules, equivalent to AWS Security Groups. Each rule becomes one `iptables -A MC-SG-<vm-id> -p tcp --dport 22 -j ACCEPT` command. A default-deny rule at the end of each chain drops everything not explicitly allowed. When a group is attached to a VM, all its rules are applied to the VM's tap device (`vnet0`, `vnet1`, etc.).

---

### Step 9 — SSH into VM Using Key Pair

Click **Key Pairs** → **Generate Key Pair**, name: `demo-key`.  
Save the private key to `~/.ssh/demo-key.pem`.  
```bash
chmod 600 ~/.ssh/demo-key.pem
ssh -i ~/.ssh/demo-key.pem cirros@<floating-ip>
```

**Explain:** When a key pair is generated, an RSA-4096 key is generated in Python using the `cryptography` library. Only the public key is stored in the DB — the private key is shown exactly once and never persisted. At VM launch, if a keypair is selected, a cloud-init ISO is built with the public key embedded in `user-data`. CirrOS reads this ISO on first boot and writes the key to `/home/cirros/.ssh/authorized_keys` inside the VM.

---

### Step 10 — Create a Volume

Click **Volumes** → **Create Volume**, name: `demo-vol`, size: 1 GB.

**Show LVM:**
```bash
sudo lvdisplay /dev/mini-cloud-vg/
```

**Explain:** Volumes are LVM Logical Volumes. The command runs `lvcreate -L 1G -n <volume-id> mini-cloud-vg`. LVM manages the raw block device. The volume starts with `status=available` in the DB, meaning it exists but is not attached to any VM. This is equivalent to an unattached EBS volume in AWS.

---

### Step 11 — Attach Volume to VM

Click **Attach**, select `demo-vm`.  
Inside the VM console:
```bash
ls /dev/vd*
```
Expected: `/dev/vda` (root) and `/dev/vdb` (our attached volume).

**Explain:** Attachment calls libvirt's `domain.attachDevice()` with an XML disk definition that references the LVM device path `/dev/mini-cloud-vg/<volume-id>`. libvirt adds a new virtual disk to the running VM without rebooting — this is hot-attach. The device appears as `/dev/vdb` inside the VM. The DB records `status=in-use`, `vm_id`, and `device_name`.

---

### Step 12 — Create Load Balancer

Click **Load Balancers** → **Create LB**, name: `demo-lb`, port: 8080.

**Show haproxy.cfg:**
```bash
cat /etc/haproxy/haproxy.cfg
```

**Explain:** Each load balancer is a HAProxy frontend+backend pair. The `frontend demo-lb` binds port 8080. The `backend demo-lb-backend` is initially empty. When we write the config and call `systemctl reload haproxy`, HAProxy picks up the change without dropping existing connections — this is HAProxy's graceful reload feature. Each LB port must be unique across the system (enforced at the DB level with a UNIQUE constraint).

---

### Step 13 — Add VM to Load Balancer

Click **Add Member**, select `demo-vm`, backend port: 80.

**Explain:** Adding a member appends a `server vm-<id> <private-ip>:80 check` line to the backend in haproxy.cfg and triggers a reload. If you had multiple VMs, HAProxy would use round-robin by default — each request goes to the next server in the list. Run `curl http://localhost:8080` multiple times to show the round-robin in action.

---

### Step 14 — Create Autoscaling Group

Click **Autoscaling** → **Create Group**, name: `demo-asg`, flavor: `t1.nano`, min: 1, max: 3, scale-up at 70% CPU.

**Explain:** The autoscaling monitor is a Python background thread that runs every 30 seconds. It reads CPU metrics from libvirt for every VM in each group. If average CPU > 70% and we're below `max_instances`, it launches a new VM using the group's template. If average CPU < 30% and we're above `min_instances`, it terminates one VM. A `cooldown_seconds` (default 120 s) prevents thrashing between scale-up and scale-down decisions. All scale events are logged to the `asg_events` table.

---

### Step 15 — Show Monitoring

Click **Monitoring** in the sidebar.

The dashboard shows CPU bars and RAM bars that auto-refresh every 10 seconds.

**Explain:** Host metrics are read from `/proc/stat` (CPU), `/proc/meminfo` (RAM), and `/proc/net/dev` (network I/O). VM metrics are read from libvirt's `domain.getCPUStats()` and `domain.memoryStats()`. These are the same data sources that tools like `top` and `htop` use. The dashboard polls `GET /api/v1/monitoring/host` and `GET /api/v1/monitoring/vms` in a `setInterval()` loop.

---

### Step 16 — Show Quotas

Click **Quotas** in the sidebar.

The table shows: Instances 2/5, vCPUs 2/10, RAM 1024/10240 MB, Volumes 1/10, etc.

**Explain:** Quotas are checked before any resource-creating operation. The `check_quota()` function counts current resources from the DB and compares against the limit in `quota_defaults`. If an admin sets a per-user override in `quota_user_overrides`, that takes precedence. This prevents a single user from consuming all system resources — the same quota model AWS uses per account.

---

### Step 17 — Show IAM

Click **IAM** in the sidebar. Show the four tabs:  
- **Users** — service identities (not login accounts)  
- **Groups** — collections of users that share policies  
- **Roles** — assumed by services (EC2 role, Lambda role)  
- **Policies** — JSON permission documents (7 AWS-managed policies pre-seeded)

**Explain:** IAM is decoupled from login accounts. A login `admin` is a cloud account that can log in to the dashboard. An IAM user represents a service identity (like a CI/CD pipeline). Policies define what actions are allowed. Groups make it easy to assign the same policy to many users at once. Roles are assumed by trusted services — for example, an EC2 instance can assume a role to call S3 without needing a password.

---

## Questions the Teacher May Ask — With Answers

### Q1: What does libvirt do? Why not call KVM directly?

<<<<<<< HEAD
**A:** libvirt is an abstraction API that sits between our Python code and the KVM hypervisor. KVM itself is a Linux kernel module — you interact with it through `/dev/kvm` using low-level `ioctl` system calls, which is very complex to use directly. libvirt wraps all of this with a clean API: `conn.createXML(domain_xml)` to launch a VM, `domain.state()` to check its status, `domain.destroy()` to terminate it. It also handles the libvirt daemon (`libvirtd`), which runs as a system service and manages the lifecycle of VMs.

---

### Q2: Why doesn't this project use a message queue?

**A:** A message queue (like RabbitMQ or Kafka) is needed when services run on different physical machines. In a multi-node cloud, the compute service and the storage service cannot call each other directly — they send messages through a queue and pick them up when ready. Our system runs entirely on one machine, so all modules are Python functions in the same Flask process. The compute service calling storage is just `from app.storage.models import create_volume`. No network hops, no queue needed. If this were scaled to multiple servers, a message queue would be the right addition.
=======
**A:** libvirt is an abstraction API that sits between our Python code and the KVM hypervisor. KVM itself is a Linux kernel module — you interact with it through `/dev/kvm` using low-level `ioctl` system calls, which is very complex to use directly. libvirt wraps all of this with a clean API: `conn.createXML(domain_xml)` to launch a VM, `domain.state()` to check its status, `domain.destroy()` to terminate it. It also handles the libvirt daemon (`libvirtd`), which runs as a system service and manages the lifecycle of VMs. The compute service in a larger cloud platform uses libvirt in exactly the same way — it is the standard interface to KVM in production systems.

---

### Q2: Why would a larger cloud platform use RabbitMQ but your project does not?

**A:** RabbitMQ is a message queue. Larger cloud platforms need it because their services run on different physical machines in a production cluster. When one service needs to tell another to create a volume, it cannot do a direct function call across machines. It sends a message to RabbitMQ, and the other service picks it up when it is ready. Our system runs entirely on one machine, so all modules are Python functions in the same Flask process. Direct calls are just `from app.storage.models import create_volume`. No network hops needed, no message queue needed. If we scaled this to multiple servers, we would add RabbitMQ (or Kafka) for the same reason a distributed cloud platform does.
>>>>>>> 337297b6727f1aff9138a2287614f11aa31eb3c2

---

### Q3: How does a floating IP work? Walk through the iptables rules.

**A:** When you associate floating IP `192.168.0.225` with a VM that has private IP `10.0.0.5`, two iptables rules are inserted in the `nat` table:

```
# DNAT: rewrite destination for incoming traffic
iptables -t nat -A PREROUTING -d 192.168.0.225 -j DNAT --to-destination 10.0.0.5

# SNAT: rewrite source for outgoing traffic
iptables -t nat -A POSTROUTING -s 10.0.0.5 -j SNAT --to-source 192.168.0.225
```

DNAT handles inbound: a packet arriving for `192.168.0.225` gets its destination IP changed to `10.0.0.5` before routing. SNAT handles outbound: a packet leaving from `10.0.0.5` gets its source IP changed to `192.168.0.225` before it exits the host. The VM only knows about `10.0.0.5` — it never sees `192.168.0.225`. This is identical to how AWS implements Elastic IPs at the hypervisor layer.

---

### Q4: How is a VM disk created? What is the difference between a base image and a VM disk?

**A:** The base image (e.g., CirrOS qcow2) is a read-only master. When we launch a VM, we do NOT copy it — instead we create a **copy-on-write overlay** disk:

```bash
qemu-img create -f qcow2 -b /path/to/cirros.img /path/to/vm-disk.qcow2
```

The overlay starts empty (a few KB). When the VM writes to any block, the write goes to the overlay — the base image is never touched. When the VM reads a block that has not been written, qemu reads it from the base image. This is fast (no 1 GB copy at launch) and space-efficient (multiple VMs share the same base image, only their diffs are stored). This is exactly the CoW mechanism AWS AMIs use — one AMI can back thousands of EC2 instances.

---

### Q5: How do security groups work at the iptables level?

**A:** Each VM gets its own iptables chain: `MC-SG-<vm-id>`. When the VM's tap device (`vnet0`) receives a packet, it jumps to this chain. The chain contains one `ACCEPT` rule per security group rule, and a final `DROP` for anything not matched.

Example after adding SSH rule:
```
Chain MC-SG-abc123 (1 references)
  ACCEPT tcp  --  0.0.0.0/0  0.0.0.0/0  tcp dpt:22
  DROP   all  --  0.0.0.0/0  0.0.0.0/0
```

When a security group is attached to a VM, we add its rules to the chain. When a rule is deleted, we remove the corresponding iptables rule with `-D`. When the VM is terminated, the entire chain is deleted. Outbound traffic is not filtered (no outbound rules in this implementation — same default as AWS where outbound is allow-all by default).

---

### Q6: What is LVM and why use it for volumes?

**A:** LVM (Logical Volume Manager) is a Linux subsystem that creates virtual block devices on top of physical storage. A Volume Group (VG) is a pool of storage. Logical Volumes (LVs) are named slices of that pool:

```bash
lvcreate -L 1G -n vol-abc123 mini-cloud-vg
```

This creates `/dev/mini-cloud-vg/vol-abc123` — a 1 GB block device. Advantages: volumes can be resized without reformatting, snapshots are instant (copy-on-write), and volumes can be moved between VMs by hot-attaching/detaching the block device. AWS EBS (Elastic Block Store) uses the same logical volume concept — except at scale with distributed storage.

---

### Q7: How do LVM snapshots work?

**A:** An LVM snapshot is a copy-on-write view of a logical volume at a specific point in time:

```bash
lvcreate -s -L 1G -n snap-abc123 /dev/mini-cloud-vg/vol-abc123
```

At snapshot creation, no data is copied — it is instant. The snapshot tracks only the blocks that have changed since the snapshot was taken. When you read from the snapshot, you get the original data. When the original LV writes a block, LVM first copies the original block to the snapshot's reserved space, then writes the new data. To restore: `lvconvert --merge snap-abc123`. This is the same CoW mechanism that enables fast EBS snapshots in AWS.

---

### Q8: How does the VNC console work? What is websockify?

**A:** KVM exposes each VM's display through VNC — a protocol that streams screen pixels over TCP. Browsers cannot open raw TCP connections (a security restriction), only WebSocket connections. `websockify` is a proxy that bridges the gap:

```
Browser (WebSocket) → websockify (port 6100) → VNC server (port 5910)
```

When the console endpoint is called, it:
1. Gets the VNC port from libvirt (`domain.graphics()`)
2. Starts a `websockify` process: `websockify 6100 127.0.0.1:5910`
3. Returns `ws://localhost:6100` to the browser

<<<<<<< HEAD
The browser runs noVNC — an HTML5 VNC client that connects to the WebSocket URL and renders the VM's screen.
=======
The browser runs noVNC — an HTML5 VNC client that connects to the WebSocket URL and renders the VM's screen. A larger cloud dashboard uses the exact same architecture for its console feature.
>>>>>>> 337297b6727f1aff9138a2287614f11aa31eb3c2

---

### Q9: How does cloud-init inject SSH keys into a VM?

**A:** cloud-init is a Linux service that runs on VM first boot and configures the instance. It reads configuration from a special data source. We use a **seed ISO**: a tiny CD-ROM image with two files — `meta-data` and `user-data`:

```
user-data:
  #cloud-config
  users:
    - name: cirros
      ssh_authorized_keys:
        - ssh-rsa AAAA...
```

The ISO is attached to the VM as a virtual CD-ROM. cloud-init reads it, writes the public key to `/home/cirros/.ssh/authorized_keys`, and never runs again. We build this ISO with `genisoimage`. This is why AWS says "the private key is only available at launch" — the key is injected at boot time and the private key is never sent to the VM.

---

### Q10: Why is the private key shown only once and never stored?

**A:** If the server stored private keys in the database, a database breach would give an attacker full SSH access to every VM. The server only needs the public key to inject into VMs via cloud-init. The private key is only needed by the SSH client (the user's machine). So we generate the key pair, inject the public key, return the private key in the API response exactly once, and discard it. If the user loses the private key, they must generate a new key pair and re-launch the VM with it. This is the same design AWS EC2 uses — they cannot recover lost PEM keys.

---

### Q11: How does HAProxy implement round-robin load balancing?

**A:** HAProxy maintains a list of backend servers. With the `roundrobin` algorithm, each new connection goes to the next server in the list:

```
backend demo-lb-backend
    balance roundrobin
    server vm-1 10.0.0.5:80 check
    server vm-2 10.0.0.6:80 check
    server vm-3 10.0.0.7:80 check
```

Request 1 → `vm-1`, Request 2 → `vm-2`, Request 3 → `vm-3`, Request 4 → `vm-1`, and so on. The `check` flag enables health checking — HAProxy sends a TCP probe to each server every 2 seconds and stops sending traffic to servers that fail. When we add or remove members, we rewrite the config file and call `systemctl reload haproxy` — HAProxy completes current connections before applying the new config (graceful reload).

---

### Q12: How does the autoscaling monitor work? Is it a cron job?

**A:** It is a Python background thread started at application startup:

```python
thread = threading.Thread(target=_monitor_loop, daemon=True)
thread.start()
```

The `_monitor_loop` function runs an infinite loop with `time.sleep(30)` between iterations. Every 30 seconds it checks all active autoscaling groups. For each group, it reads CPU metrics for all member VMs via libvirt's `getCPUStats()`, calculates the average, and compares against the thresholds. A `cooldown_seconds` counter prevents scaling more than once per cooldown period. Scale events (scale-up, scale-down, ensure-min) are logged to the `asg_events` table so you can see the history. This is simpler than AWS Auto Scaling (which uses CloudWatch alarms and SNS notifications) but implements the same core logic.

---

### Q13: What is the difference between an IAM User and a login account?

**A:** A **login account** (in the `users` table) is a person who logs in to the dashboard with a username and password. It can launch VMs, create networks, etc.

An **IAM User** (in the `iam_users` table) is a **service identity** — it represents an application or service, not a person. In AWS, you would create an IAM user for your CI/CD pipeline and give it only the permissions it needs (principle of least privilege). An IAM user has an ARN (`arn:minicloud:iam::123456789012:user/deploy-bot`) and gets permissions through IAM policies, not by logging in to the dashboard.

The two systems are separate: one controls who can log in, the other controls what automated services are allowed to do.

---

### Q14: What are the 7 AWS managed IAM policies and what do they do?

**A:** These 7 policies are seeded automatically in the DB at startup:

| Policy Name               | What It Allows |
|---------------------------|----------------|
| `AdministratorAccess`     | Everything — `Action: *` on `Resource: *` |
| `PowerUserAccess`         | Everything except IAM operations (`NotAction: iam:*`) |
| `ReadOnlyAccess`          | Read-only — `ec2:Describe*`, `iam:Get*`, `iam:List*` |
| `AmazonEC2FullAccess`     | All EC2 operations — `ec2:*` |
| `AmazonEC2ReadOnlyAccess` | EC2 read-only — `ec2:Describe*` |
| `IAMFullAccess`           | All IAM operations — `iam:*` |
| `IAMReadOnlyAccess`       | IAM read-only — `iam:Get*`, `iam:List*` |

Each policy is a JSON document following AWS IAM policy syntax with `Version`, `Effect`, `Action`, and `Resource` fields. They are marked `type='managed'` so they cannot be deleted by users (same as AWS managed policies).

---

### Q15: How does the quota system work? Can an admin override it?

**A:** Quotas have two layers:

1. **System defaults** (in `quota_defaults` table): apply to all users unless overridden.
   - Default: 5 instances, 10 vCPUs, 10240 MB RAM, 10 volumes, 500 GB storage, 5 floating IPs.

2. **Per-user overrides** (in `quota_user_overrides` table): admin can grant a specific user a higher (or lower) limit.

Before any resource-creating API call, `check_quota(user_id, resource_type, amount)` runs:
1. Look up override for this user — if found, use it.
2. Otherwise use the system default.
3. Count current usage from the DB.
4. If `used + amount > limit`: return 403 QUOTA_EXCEEDED.

An admin can update defaults via `PUT /api/v1/quotas/defaults` or set per-user overrides via `PUT /api/v1/quotas/users/<user_id>`.

---

### Q16: What is a Linux Bridge and how does virtual networking work?

**A:** A Linux bridge is a software Ethernet switch created in the kernel. Each virtual network we create makes one bridge:

```bash
ip link add mcbr0 type bridge
ip addr add 192.168.200.1/24 dev mcbr0
ip link set mcbr0 up
```

When a VM is launched, KVM creates a tap device (`vnet0`) — a virtual network cable. One end connects to the VM's virtual NIC, the other connects to the bridge. Multiple VMs connected to the same bridge can talk to each other at Layer 2. The bridge acts as the default gateway (`192.168.200.1`). `dnsmasq` listens on the bridge interface and assigns IPs to VMs via DHCP. This is equivalent to an AWS VPC subnet — VMs on the same subnet can communicate directly.

---

### Q17: What happens when the host reboots? Are the VMs and iptables rules lost?

**A:** Yes — there are persistence challenges:

- **VMs**: libvirt-defined VMs survive reboot if they were defined (not just created with `createXML`). We use `conn.defineXML()` which persists the domain. With `virsh autostart <domain>`, VMs restart automatically.
- **iptables**: Rules are lost on reboot. Our `create_app()` function calls `restore_all_sg_chains()` on startup to re-apply all security group rules from the DB.
- **Floating IPs**: The `restore_fip.py` script (in `scripts/`) and the systemd service `mini-cloud-fip.service` re-apply the iptables DNAT/SNAT rules and re-add the floating IP addresses to the loopback interface.
- **Loop device for LVM**: The `mini-cloud-loop.service` systemd unit re-creates the loop device that backs the LVM VG.

This is the same problem data centres solve with configuration management tools (Ansible, Terraform) that re-apply desired state after a reboot.

---

### Q18: How does the project avoid SQL injection and other security vulnerabilities?

**A:** Every database query uses SQLite parameterized queries — user input is never concatenated into SQL strings:

```python
# SAFE — parameter binding
conn.execute("SELECT * FROM users WHERE username=?", (username,))

# NEVER done — would allow SQL injection
conn.execute(f"SELECT * FROM users WHERE username='{username}'")  # BAD
```

Other security measures:
- Passwords are hashed with **Werkzeug's `generate_password_hash`** (PBKDF2-SHA256) — never stored plain.
- JWT tokens are signed with HS256 — a forged token fails signature verification.
- Every protected route calls `@require_auth` which validates the JWT before executing any business logic.
- IDOR (Insecure Direct Object Reference) is prevented: every DB query includes `user_id=g.current_user['id']` so a user cannot read another user's resources by guessing IDs.
- The private key for key pairs is never stored — shown once and discarded.

---

### Q19: Why Flask instead of Django or FastAPI?

**A:** Flask was chosen for three reasons:

1. **Minimal footprint**: Flask is a micro-framework — no ORM, no admin panel, no auth system forced on you. We build exactly what we need (JWT auth, raw SQLite) without fighting the framework's defaults.

2. **Learning clarity**: With Flask, every line of code is explicit. There is no magic. This is intentional for a learning project — the teacher can follow the code from HTTP request to DB write without hunting through framework internals.

3. **Suitable for the scale**: This is a single-node system with one SQLite database. Django and FastAPI bring async handling, connection pools, and migration frameworks that are valuable at production scale but add complexity here without benefit.

FastAPI would give us async I/O and automatic OpenAPI docs — worth it if this were a production API. Django would give us a built-in admin panel — worth it for a larger team. For a single-developer demo project, Flask's simplicity is the right tradeoff.

---

### Q20: What would need to change to make this production-grade, like real AWS?

**A:** Several fundamental things:

| Component | Demo Implementation | Production Equivalent |
|-----------|--------------------|-----------------------|
| Database | SQLite (single file) | PostgreSQL with replication |
| Storage | Local LVM on one disk | Distributed block storage (Ceph) |
| Networking | Single Linux bridge | OVS (Open vSwitch) with VXLAN tunnels |
| Auth | JWT with a static secret | Dedicated auth service, short-lived tokens, MFA |
| Compute | Single KVM host | Hundreds of hypervisor nodes |
| Message queue | Direct function calls | Message queue (Kafka/RabbitMQ) for cross-node coordination |
| Config persistence | Python restart + restore scripts | Ansible / Terraform idempotent state |
| HA | Single point of failure everywhere | Active-active clusters with load balancers |
| Monitoring | `/proc` reading | Prometheus + Grafana + Alertmanager |
| API rate limiting | None | Per-IP and per-user rate limiting |

<<<<<<< HEAD
This project demonstrates that the concepts (VM launch, floating IPs, security groups, load balancing) are not mysterious — they are Linux tools orchestrated by Python.
=======
Going from this demo to production is essentially the architecture of a distributed cloud platform. This project demonstrates that the concepts (VM launch, floating IPs, security groups, load balancing) are not mysterious — they are Linux tools orchestrated by Python.
>>>>>>> 337297b6727f1aff9138a2287614f11aa31eb3c2
