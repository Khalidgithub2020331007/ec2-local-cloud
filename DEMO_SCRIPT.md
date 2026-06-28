# Demo Script — Mini Cloud Presentation
### Flask + libvirt/KVM + LVM + iptables on Ubuntu 24.04 LTS
### Machine: Acer TravelMate P215-53 | 8GB RAM | 16 CPU | WiFi

---

## Before You Start (Pre-flight Checklist)

Run this **5 minutes before** your presentation:

```bash
# 1. Verify WiFi IP
ip addr show wlp0s20f3 | grep 'inet '

# 2. Run the startup fix script
cd /home/khalid/ec2-local-cloud
bash restart-fix.sh

# 3. Start mini-cloud
cd mini-cloud
source venv/bin/activate
python3 run.py &
sleep 3

# 4. Smoke test — get a token and list instances
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Instances:', d.get('count',0))"

# 5. Open dashboard in browser
# http://localhost:5001   (admin / Admin1234)
```

---

## Presentation Structure (Total: ~20 minutes)

| Section | Duration | What You Show |
|---------|----------|---------------|
| [1] Introduction | 2 min | What the project is and why |
| [2] Architecture Overview | 3 min | Diagram + how each feature maps to AWS |
| [3] Live Demo — Dashboard | 2 min | Login, overview cards |
| [4] Live Demo — Launch VM | 4 min | Create instance, floating IP, SSH |
| [5] Live Demo — Storage | 3 min | Create volume, attach, mount, write data |
| [6] Live Demo — IAM & Quotas | 2 min | Multi-user isolation, quota enforcement |
| [7] Comparison + Conclusion | 4 min | AWS vs mini-cloud table, what it proved |

---

## SECTION 1 — Introduction (2 minutes)

**What to say:**

> "This project builds a local private cloud that replicates the core features of Amazon EC2 —
> virtual machines, persistent storage, networking, floating IPs, and multi-user isolation —
> all on a single laptop using open-source Linux tools."

> "It is written entirely in Python using Flask, and talks directly to the Linux kernel — KVM
> for virtual machines, LVM for block storage, Linux Bridge for networking, and iptables for
> firewall rules and floating IPs. No cloud management framework is used."

**Key point to make:**
- These are real virtual machines running under KVM — the same hypervisor AWS uses under the hood.

---

## SECTION 2 — Architecture Overview (3 minutes)

**Show the ASCII diagram from mini-cloud/DEMO.md and explain each layer:**

```
Browser → Flask API (port 5001) → libvirt/KVM / LVM / iptables / HAProxy
```

**Map each feature to AWS:**

| Say this... | Implemented with... |
|-------------|---------------------|
| "EC2 compute engine" | libvirt + KVM (QEMU) |
| "AMI image store" | local filesystem + SQLite metadata |
| "EBS block storage" | LVM Logical Volumes |
| "Elastic IPs" | iptables DNAT/SNAT + dummy interface |
| "VPC networking" | Linux Bridge + dnsmasq DHCP |
| "Security Groups" | per-VM iptables chains |
| "IAM users/roles" | custom IAM layer in SQLite |
| "AWS Management Console" | Flask dashboard (port 5001) |

---

## SECTION 3 — Live Demo: Dashboard (2 minutes)

**Open browser → `http://localhost:5001`**

### Login
- Username: `admin`
- Password: `Admin1234`

**Say:** "This is our management console — same concept as logging into AWS at console.aws.amazon.com."

### Show Overview Cards
- Point to: instance count, volume count, image count, quota usage bars
- **Say:** "These pull from libvirt and SQLite in real time — no separate monitoring daemon."

---

## SECTION 4 — Live Demo: Launch a VM + SSH (4 minutes)

### Step 4.1 — Upload a CirrOS image (if not already uploaded)

```bash
# In the dashboard: Images → Upload Image → select /tmp/cirros-0.6.2-x86_64-disk.img
```

### Step 4.2 — Launch an instance

In the dashboard: **Instances → Launch Instance**

Fill in:
- Name: `live-demo-vm`
- Flavor: `t1.nano — 1 vCPU · 512MB RAM`
- Image: `CirrOS 0.6.2`
- Key Pair: `demo-key` (generate one first if needed)

Click **Launch**.

**Say:** "This is equivalent to `aws ec2 run-instances`. Flask validates the request, checks quotas, creates a qcow2 overlay disk with qemu-img, builds a libvirt XML domain definition, and calls `virsh define` + `virsh start`."

### Step 4.3 — Watch it go Running

**Say:** "Status goes pending → running — same as EC2's pending → running. CirrOS takes under 30 seconds."

Refresh until `running`.

### Step 4.4 — Allocate a Floating IP

In the dashboard: **Network → Floating IPs → Allocate IP**

**Say:** "A floating IP is our Elastic IP. When we allocate one, the IP is added to a dummy interface on the host. When we associate it with a VM, two iptables rules are added: DNAT for inbound traffic and SNAT for replies."

### Step 4.5 — Associate the Floating IP to the VM

Click **Associate** → select `live-demo-vm`.

Show the iptables rule:
```bash
sudo iptables -t nat -L -n | grep DNAT
# Expected: DNAT ... to:<vm-private-ip>
```

### Step 4.6 — SSH into the VM

```bash
ssh -i ~/.ssh/demo-key.pem \
  -o StrictHostKeyChecking=no \
  cirros@<floating-ip>
```

Inside the VM:
```bash
whoami          # cirros
hostname        # live-demo-vm
ip addr show    # shows private IP from Linux bridge DHCP
free -m         # 512MB RAM (t1.nano)
exit
```

**Say:** "We're SSH'd into a real virtual machine. The private key was injected via a cloud-init seed ISO — the same mechanism AWS uses. The VM got its IP from our dnsmasq DHCP server running on the Linux bridge."

### Step 4.7 — Open VNC Console (EC2 Instance Connect equivalent)

In the dashboard: **Instances → Console** on `live-demo-vm`.

**Say:** "VNC is a TCP protocol — browsers can only open WebSockets. We use websockify as a bridge. The console endpoint starts websockify, returns a ws:// URL, and noVNC renders the VM screen in the browser."

---

## SECTION 5 — Live Demo: Block Storage (3 minutes)

### Step 5.1 — Create a volume

In the dashboard: **Volumes → Create Volume**, name: `demo-vol`, size: `1 GB`.

**Say:** "This runs `lvcreate -L 1G -n <id> mini-cloud-vg`. LVM creates a block device at `/dev/mini-cloud-vg/<id>`."

```bash
# Prove it with:
sudo lvdisplay /dev/mini-cloud-vg/
```

### Step 5.2 — Attach to the VM

Click **Attach** → select `live-demo-vm`.

**Say:** "Attachment calls libvirt's `attachDevice()` — the block device appears inside the VM without a reboot. This is hot-attach, same as EBS."

### Step 5.3 — SSH in and format it

```bash
ssh -i ~/.ssh/demo-key.pem cirros@<floating-ip>

sudo fdisk -l            # see /dev/vdb listed
sudo mkfs.ext4 /dev/vdb
sudo mkdir /data
sudo mount /dev/vdb /data
echo "Persistent storage demo" | sudo tee /data/proof.txt
cat /data/proof.txt
exit
```

**Say:** "Data written here survives the VM being deleted — the volume is independent of the instance lifecycle, exactly like EBS."

### Step 5.4 — Volume Snapshot

```bash
# In dashboard: Volumes → Snapshots → Create Snapshot
# Or via API:
curl -s -X POST http://localhost:5001/api/v1/storage/snapshots \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "demo-snap", "volume_id": "<volume-id>"}'
```

**Say:** "LVM snapshots are instant copy-on-write — no data is copied at creation time. Only changed blocks are stored in the snapshot's reserved space."

---

## SECTION 6 — Live Demo: IAM & Quotas (2 minutes)

### Step 6.1 — Create an IAM user

Dashboard: **IAM → Users → Create User**, name: `devbot`.

**Say:** "IAM users are service identities — separate from login accounts. They get permissions through policies, not passwords."

### Step 6.2 — Attach a policy

Click **Attach Policy** on `devbot` → select `AmazonEC2ReadOnlyAccess`.

**Say:** "Seven AWS-managed policies are pre-seeded — AdministratorAccess, PowerUserAccess, ReadOnlyAccess, AmazonEC2FullAccess, etc. Custom policies use the same JSON document format as real AWS IAM."

### Step 6.3 — Show Quotas

Dashboard: **Quotas** sidebar.

**Say:** "Quotas are checked before every resource-creating call. The `check_quota()` function counts current usage in SQLite and rejects the request with 403 QUOTA_EXCEEDED if the limit would be breached."

---

## SECTION 7 — Comparison + Conclusion (4 minutes)

| AWS EC2 | Mini Cloud | Implementation |
|---------|-----------|----------------|
| EC2 Instances | Instances | libvirt + KVM |
| AMIs | Images | qcow2 files + SQLite |
| Instance Types | Flavors | hardcoded flavor table |
| EBS Volumes | Volumes | LVM Logical Volumes |
| EBS Snapshots | Snapshots | LVM snapshots (CoW) |
| Elastic IPs | Floating IPs | iptables DNAT/SNAT |
| VPC Subnets | Networks | Linux Bridge + dnsmasq |
| Security Groups | Security Groups | per-VM iptables chains |
| IAM | IAM | custom SQLite-backed layer |
| AWS CLI | REST API | Flask + JWT |
| AWS Console | Dashboard | Flask + vanilla JS |
| Auto Scaling | Autoscaling | Python background thread |
| ELB | Load Balancers | HAProxy |
| CloudWatch | Monitoring | /proc + libvirt stats |
| Service Quotas | Quotas | SQLite quota tables |

**Closing statement:**

> "This project demonstrates that the core architecture of commercial cloud platforms is not
> proprietary magic — it is a well-understood set of Linux kernel features: KVM for isolation,
> LVM for storage, bridges and iptables for networking. Python orchestrates all of it.
> Understanding these primitives is understanding how AWS works under the hood."

---

## Cleanup After Demo

```bash
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Disassociate and release floating IP
FIP_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips \
  | python3 -c "import sys,json; fips=json.load(sys.stdin)['floating_ips']; print(fips[0]['id'] if fips else '')")
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips/$FIP_ID/disassociate
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips/$FIP_ID

# Detach and delete volume
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/storage/volumes/<volume-id>

# Terminate instance
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances/<instance-id>
```

---

## If Something Goes Wrong During the Demo

### Instance stuck in pending / not going running

```bash
sudo systemctl restart libvirtd
sudo virsh list --all
```

### SSH connection refused

```bash
# Check floating IP is associated
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips

# Check iptables DNAT is in place
sudo iptables -t nat -L PREROUTING -n | grep DNAT

# Verify VM is actually running
sudo virsh list | grep live-demo-vm
```

### Dashboard won't load

```bash
# Check mini-cloud is running
curl -s http://localhost:5001/api/v1/auth/health

# Restart it if not
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

### Floating IP ping fails

```bash
# Restore FIP state
sudo python3 /home/khalid/ec2-local-cloud/mini-cloud/scripts/restore_fip.py

# Verify mc-fip interface has the IP
ip addr show mc-fip
```

---

*Project: Mini Cloud System | Flask + libvirt/KVM + LVM + iptables | Ubuntu 24.04 LTS*
*Machine: Acer TravelMate P215-53 | wlp0s20f3*
