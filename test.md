# Test Guide — Local EC2 Replica (Mini Cloud)

---

## Section 1 — What is EC2?

**EC2** stands for **Elastic Compute Cloud**. It is a service made by Amazon (AWS) that lets you rent virtual computers (called **instances**) over the internet.

Think of it like this:

- You have a laptop. EC2 gives you a **virtual laptop** that lives on a server somewhere.
- You can turn it ON, turn it OFF, connect to it, install software, and delete it when you are done.
- You only pay for the time it is running.

**Key idea:** You do not buy a physical computer. You get a virtual one that behaves exactly like a real computer.

This project is a **local copy** of EC2 running on your own machine — built from scratch using Flask, libvirt/KVM, LVM, Linux Bridge, and iptables. It works the same way as real AWS EC2, but runs on your laptop instead of Amazon's servers.

---

## Section 1B — EC2 Features Explained (For First-Time Users)

This section explains every major EC2 concept in plain language, so you understand what you are working with before you run any tests.

---

### 1. Instances (Virtual Machines)

An **instance** is a virtual computer. It has a CPU, RAM, and storage — just like a real computer — but it runs inside a large physical server in a data center.

**What you can do with an instance:**
- **Launch** — create a new virtual computer from a template
- **Stop** — pause it (like sleep mode); the disk is kept but you stop paying for CPU
- **Start** — resume it again
- **Reboot** — restart the OS without deleting anything
- **Terminate/Delete** — permanently destroy it; all data is gone
- **Connect (SSH)** — log in to the terminal over the network

**Real-world analogy:** An instance is like a virtual laptop you rent by the hour. You can start it, log in, run programs, and return it when done.

**Instance states:**
| State | Meaning |
|-------|---------|
| `ACTIVE` / Running | Instance is on and running normally |
| `SHUTOFF` / Stopped | Instance is off; disk data is preserved |
| `BUILD` / Pending | Instance is still being created |
| `ERROR` | Something went wrong during launch |
| `PAUSED` | Frozen in memory; can be resumed instantly |
| `SHELVED` | Stored to disk to free up compute resources |

---

### 2. AMIs — Amazon Machine Images (called "Images" here)

An **image** is a pre-built template for an instance's hard drive. It contains the operating system and any pre-installed software.

**Think of it as:** A factory setting for your virtual computer. Every new instance starts from an image.

**Common images:**
- **CirrOS** — a tiny 12MB Linux OS used for testing; not for real apps
- **Ubuntu 22.04 LTS** — a full Linux OS suitable for real workloads
- **Amazon Linux 2** — AWS's own Linux, optimized for EC2

**What you can do with images:**
- **List images** — see what OS templates are available
- **Launch from an image** — pick one when creating a new instance
- **Create a custom image** — snapshot a running instance to save your installed software as a new template
- **Delete an image** — remove a template you no longer need

**Custom images (AMIs) are useful when:**
You have installed your app on an instance. You save it as an image. Now you can launch 10 identical instances in seconds.

---

### 3. Instance Types / Flavors — Choosing the Right Size

When you launch an instance, you pick how powerful it is. These size options are called **instance types** in AWS and **flavors** in mini-cloud.

**AWS naming pattern:** `t3.micro`, `m5.large`, `c6i.xlarge`
- The letter(s) = family (t = general, m = memory, c = compute)
- The number = generation (newer = better)
- The word = size (nano < micro < small < medium < large < xlarge)

**Common instance types and what they mean:**

| AWS Type | Mini Cloud Flavor | vCPU | RAM | Disk | Use Case |
|----------|-----------------|------|-----|------|----------|
| t2.nano | t1.nano | 1 | 512 MB | 5 GB | Test and dev only |
| t2.micro | t1.micro | 1 | 1 GB | 10 GB | Very small apps |
| t2.small | t1.small | 1 | 2 GB | 20 GB | Light web apps |
| t2.medium | t1.medium | 2 | 4 GB | 40 GB | Medium web servers |

**Rule:** Pick the smallest size that meets your needs. You can always resize later.

---

### 4. Key Pairs — Secure SSH Login

A **key pair** is a pair of cryptographic keys used to log into instances securely instead of using a password.

- **Private key (.pem file)** — lives on your machine, never share it
- **Public key** — uploaded to the server; injected into the instance via cloud-init at launch

**How it works:**
1. You create a key pair and download the `.pem` file
2. When you launch an instance, you attach the key pair
3. To log in: `ssh -i my-key.pem ubuntu@<instance-ip>`
4. The server checks your private key against its public key — if they match, you get in

**Why not passwords?** Passwords can be brute-forced. Cryptographic keys are practically unbreakable.

**What you can do:**
- **Create a key pair** — generates a new key pair; you download the private key once
- **Import a key pair** — upload your own existing public key
- **Delete a key pair** — removes it from the system (does not affect running instances)

---

### 5. Security Groups — The Firewall

A **security group** is a virtual firewall. It controls what network traffic is allowed into and out of your instances.

**Think of it as:** A set of rules on a bouncer's clipboard. Only traffic that matches a rule gets through.

**Rules have these parts:**
| Part | Example | Meaning |
|------|---------|---------|
| Protocol | TCP, UDP, ICMP | What type of traffic |
| Port | 22, 80, 443 | Which door it knocks on |
| Source | 0.0.0.0/0 or a specific IP | Who is allowed to knock |

**Common rule setups:**

| Rule | Port | Purpose |
|------|------|---------|
| SSH | TCP 22 | Log in from terminal |
| HTTP | TCP 80 | Serve a website |
| HTTPS | TCP 443 | Serve a website securely |
| Ping (ICMP) | — | Check if the instance is alive |
| MySQL | TCP 3306 | Database access |

**Important rules:**
- By default, all **inbound** traffic is blocked. You must add rules to allow it.
- All **outbound** traffic is allowed by default.
- Security groups are **stateful** — if you allow inbound on port 22, the response traffic is automatically allowed back out.

**What you can do:**
- **Create a security group** — a new empty firewall
- **Add rules** — allow specific traffic in
- **Attach to an instance** — apply the firewall to a VM
- **Remove rules** — tighten security after testing

---

### 6. Elastic IPs / Floating IPs — Public IP Addresses

By default, instances get a **private IP** (like `10.x.x.x`). That IP only works inside your private network. The outside world cannot reach it.

A **Floating IP** (called **Elastic IP** in AWS) is a real, routable public IP address that you attach to an instance so the outside world can connect to it.

**How it works:**
1. You allocate a floating IP from the public pool
2. You associate it with a specific instance
3. Now anyone can connect to your instance at that IP

**Key properties:**
- The floating IP is **yours until you release it** — it does not change when you stop/start the instance
- You can **move it** from one instance to another instantly (useful for zero-downtime deployments)
- If an instance fails, you point the IP at a replacement instance in seconds

**What you can do:**
- **Allocate** — reserve an IP from the pool
- **Associate** — attach it to an instance
- **Disassociate** — detach it (instance is unreachable from outside)
- **Release** — return the IP to the pool (you lose it)

---

### 7. EBS Volumes — Block Storage (Persistent Disk)

An **EBS Volume** (Elastic Block Store) is a virtual hard drive. It stores data independently from the instance.

**Why it matters:** The root disk of an instance is destroyed when you terminate the instance. A separate EBS volume persists — it keeps your data even after the instance is gone.

**Think of it as:** A USB hard drive you can plug into any virtual machine.

**Volume types (AWS):**
| Type | Speed | Use Case |
|------|-------|----------|
| gp3 (General Purpose SSD) | Fast | Most workloads — default choice |
| io2 (Provisioned IOPS SSD) | Very fast | Databases needing consistent speed |
| st1 (Throughput HDD) | Sequential read fast | Big data, log processing |
| sc1 (Cold HDD) | Slowest, cheapest | Archival data rarely accessed |

**What you can do:**
- **Create a volume** — specify size in GB and type
- **Attach to an instance** — shows up as `/dev/sdb` or similar inside the VM
- **Detach** — unmount it from one instance
- **Re-attach** — plug it into a different instance
- **Delete** — permanently destroy it (all data gone)
- **Resize** — increase size (you can never shrink a volume)

---

### 8. Snapshots — Point-in-Time Backups

A **snapshot** is a copy of a volume's data at a specific moment in time. It is saved to object storage (S3 in AWS).

**Think of it as:** Taking a photo of your hard drive. If something breaks later, you can restore from the photo.

**What snapshots are used for:**
- **Backups** — take a snapshot before a risky change
- **Migration** — copy data from one region to another
- **Creating images** — snapshot a root volume to make a custom AMI
- **Cloning volumes** — create a new volume from a snapshot

**What you can do:**
- **Create snapshot** — take a copy of a volume right now
- **List snapshots** — see all saved backups
- **Restore volume from snapshot** — create a new volume with the old data
- **Delete snapshot** — remove the backup (does not affect the original volume)

---

### 9. VPC — Virtual Private Cloud (Networking)

A **VPC** is your own private, isolated section of the cloud network. All your instances live inside it.

**Think of it as:** Your own private office building. The internet is outside. You control which doors open to the outside, which rooms talk to each other, and who has access.

**Key networking concepts:**

| Concept | What It Is | Analogy |
|---------|-----------|---------|
| **VPC** | Your entire private network | The office building |
| **Subnet** | A smaller segment of the VPC | A floor or department |
| **Private subnet** | Instances with no direct internet access | Back office |
| **Public subnet** | Instances that can reach the internet | Reception area |
| **Internet Gateway** | The door to the internet | The front door |
| **Route Table** | Rules for where traffic goes | The building directory |
| **NAT Gateway** | Lets private instances reach the internet without being reachable from it | Outgoing-only exit |

**In this local system (mini-cloud):**
- Custom networks you create = your VPC/private subnet (Linux Bridge + dnsmasq)
- Floating IP pool = the external IP range (iptables DNAT/SNAT)
- Floating IPs = the bridge from private to public

---

### 10. Auto Scaling — Automatic Capacity Management

**Auto Scaling** watches your instances and automatically adds or removes them based on demand.

**Example:** You run a website. At 9am traffic spikes. Auto Scaling launches 5 more instances. At 2am traffic drops. Auto Scaling terminates the extra 5. You only pay for what you used.

**Key parts:**
- **Launch Template** — the blueprint for new instances (which image, type, key pair, etc.)
- **Auto Scaling Group (ASG)** — the group of instances managed together
- **Scaling Policies** — the rules that trigger scale-up or scale-down
  - *Target tracking* — keep CPU at 50%; add/remove instances to stay there
  - *Step scaling* — when CPU > 80%, add 2 instances
  - *Scheduled scaling* — at 8am every Monday, launch 4 extra instances

**Minimum, desired, and maximum:**
- Min: never go below this count (keep at least 1 instance alive)
- Desired: the target count under normal conditions
- Max: never go above this count (cost control)

> This local mini-cloud system implements Auto Scaling Groups — a Python background thread monitors CPU via libvirt and scales instances up/down based on configured thresholds.

---

### 11. Load Balancers — Distributing Traffic

A **Load Balancer** sits in front of multiple instances and spreads incoming requests evenly across them.

**Without a load balancer:**
- All traffic goes to one instance
- If that instance crashes, your app goes down

**With a load balancer:**
- Traffic is spread across 3 instances
- If one crashes, the other two keep running; users notice nothing

**AWS Load Balancer types:**
| Type | Use Case |
|------|----------|
| **ALB (Application Load Balancer)** | HTTP/HTTPS — routes based on URL path or hostname |
| **NLB (Network Load Balancer)** | TCP/UDP — ultra-low latency, static IP |
| **GLB (Gateway Load Balancer)** | Inspect traffic with virtual appliances |

**How ALB routing works:**
- `/api/*` → Route to backend instances
- `/static/*` → Route to CDN or file server instances
- `app.example.com` → Route to app instances
- `admin.example.com` → Route to admin instances

> This local mini-cloud system implements Load Balancers via HAProxy — you can create load balancer frontends and add VM instances as backend members through the dashboard.

---

### 12. IAM — Identity and Access Management (Users & Projects)

**IAM** controls who can do what inside your AWS account. In mini-cloud, this is handled by a custom IAM layer with **Users**, **Groups**, **Roles**, and **Policies** stored in SQLite.

**Core concepts:**

| Concept | AWS Name | Mini-Cloud Name | What It Is |
|---------|----------|----------------|-----------|
| Account | AWS Account | Login User | A person who can log in to the dashboard |
| Service identity | IAM User | IAM User | An identity for apps/services (has ARN, no password) |
| Permission set | IAM Policy | IAM Policy | JSON document defining Allow/Deny actions |
| Collection | IAM Group | IAM Group | A set of IAM users that share policies |
| Assumed identity | IAM Role | IAM Role | Temporary permission for a trusted service |

**Key principle — least privilege:**
Give a user only the permissions they absolutely need. Nothing more.

**Examples:**
- A developer gets read-only access to production; write access to staging only
- A CI/CD pipeline gets permission to push container images and update deployments only
- An on-call engineer gets permission to restart instances but not delete them

**In this system:**
- `admin` → full access to everything
- `devuser` → access to `dev-project` only
- `opsuser` → access to `prod-project` only

---

### 13. Regions and Availability Zones — Geographic Distribution

**Region:** A geographic location where AWS has data centers (e.g., `us-east-1` = North Virginia, `eu-west-1` = Ireland).

**Availability Zone (AZ):** A physically separate data center within a region. Each region has 2–6 AZs. They have separate power, cooling, and networking so a failure in one does not affect the others.

**Why this matters:**
- **Latency** — deploy in the region closest to your users
- **Redundancy** — spread instances across 2+ AZs; if one AZ has a power outage, the other keeps running
- **Compliance** — some laws require data to stay within a country

**Multi-AZ setup example:**
```
us-east-1a: instance-A, database-primary
us-east-1b: instance-B, database-replica
```
If `us-east-1a` goes down, `instance-B` keeps serving traffic. The replica is promoted to primary. Users see no downtime.

> This local system does not simulate multiple AZs, but the concept is core to production EC2 design.

---

### 14. Instance Metadata and User Data

**Instance Metadata:** Every running EC2 instance can query information about itself by hitting a special internal URL:
```bash
curl http://169.254.169.254/latest/meta-data/
```
This returns: instance ID, public IP, instance type, security groups, and more. Useful for scripts running inside the instance.

**User Data:** A script you attach to an instance at launch time. It runs automatically on first boot.

**Example user data script:**
```bash
#!/bin/bash
apt-get update -y
apt-get install -y nginx
systemctl start nginx
```

When the instance boots, it installs and starts nginx automatically — no manual SSH needed.

**Use cases for user data:**
- Install software on first boot
- Pull your app code from GitHub
- Register the instance with a monitoring system
- Configure environment variables

---

### 15. Pricing Models — How You Pay

AWS EC2 offers different ways to pay, each with a different cost/commitment trade-off.

| Model | How It Works | Savings vs On-Demand | Best For |
|-------|-------------|---------------------|---------|
| **On-Demand** | Pay per second, no commitment | 0% (baseline) | Unpredictable workloads, testing |
| **Reserved** | Pay upfront for 1 or 3 years | Up to 72% | Steady, predictable workloads |
| **Savings Plans** | Commit to $/hour for 1–3 years | Up to 66% | Flexible reserved pricing |
| **Spot** | Bid on unused AWS capacity | Up to 90% | Batch jobs, fault-tolerant workloads |
| **Dedicated Host** | Physical server just for you | varies | Compliance, licensing requirements |

**Spot instances warning:** AWS can terminate a spot instance with 2 minutes notice if it needs the capacity back. Only use for workloads that can handle interruption (data processing, rendering, CI jobs).

---

### 16. Elastic Network Interfaces (ENI)

An **ENI** is a virtual network card you can attach to an instance. Every instance has at least one ENI (its primary network interface).

**Why you would add a second ENI:**
- Separate management traffic from application traffic
- Move a network interface from a failed instance to a replacement
- Attach a fixed private IP that persists independently of the instance

---

### 17. Placement Groups — Controlling Where Instances Run

AWS normally places instances wherever hardware is available. **Placement Groups** let you control this.

| Type | What It Does | Use Case |
|------|-------------|---------|
| **Cluster** | All instances on same physical rack, low latency | High-performance computing, ML training |
| **Spread** | Each instance on different hardware | Critical apps needing maximum fault isolation |
| **Partition** | Groups of instances isolated from each other | Distributed databases like Cassandra, HDFS |

---

## Section 2 — What Features Are in This System?

This system simulates the following AWS services:

| Feature | What It Does | AWS Equivalent |
|---------|-------------|----------------|
| **Instances (VMs)** | Virtual computers you can start and stop | EC2 Instances |
| **Images** | Pre-built operating system templates (CirrOS, Ubuntu) | AMI (Amazon Machine Image) |
| **Flavors** | Size of the virtual computer (CPU, RAM, Disk) | Instance Types (t2.nano, t2.micro…) |
| **Floating IPs** | A public IP address you can attach to an instance | Elastic IP |
| **Private Network** | Internal network that VMs communicate on | VPC (Virtual Private Cloud) |
| **Security Groups** | Firewall rules — control who can connect | Security Groups |
| **Volumes** | Extra storage you can attach to a VM | EBS (Elastic Block Store) |
| **Snapshots** | Save a copy of a volume or instance at a point in time | Snapshots |
| **Key Pairs** | SSH keys to log into instances securely | Key Pairs |
| **Users & Projects** | Separate teams with their own resources | IAM Users & Accounts |

---

## Section 3 — How to Test It

### Before You Start

Open a terminal and get an auth token:

```bash
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
echo $TOKEN
```

You should see a long JWT string. This is your session token. If you see an error, make sure mini-cloud is running (`python3 run.py` in the mini-cloud folder).

---

### Test 1 — View Running Instances

**What this tests:** Can the system list virtual computers?

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -m json.tool
```

**Expected result:** A JSON list of instances with their status.

**Pass:** Instances appear with `"status": "running"`.
**Fail:** Empty list or connection error.

---

### Test 2 — Ping a Running Instance

**What this tests:** Can you reach the virtual computer over the network?

```bash
ping -c 4 10.200.195.153
```

**Expected result:**

```
4 packets transmitted, 4 received, 0% packet loss
```

**Pass:** 0% packet loss.
**Fail:** 100% packet loss or "Destination Host Unreachable".

---

### Test 3 — SSH into an Instance

**What this tests:** Can you log into the virtual computer like a real server?

```bash
ssh -i /home/khalid/ec2-local-cloud/configs/project-key.pem \
  -o StrictHostKeyChecking=no \
  cirros@10.200.195.153
```

**Expected result:** You see a prompt like:

```
$ _
```

Type `exit` to leave.

**Pass:** You get a shell prompt inside the virtual machine.
**Fail:** "Connection refused", "Permission denied", or the command hangs with no output.

---

### Test 4 — Stop and Start an Instance

**What this tests:** Can you turn a virtual computer off and on again?

```bash
# Get the instance ID first
INSTANCE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['instances'][0]['id'])")

# Stop it (graceful ACPI shutdown)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances/$INSTANCE_ID/stop

# Wait 10 seconds, then check the status
sleep 10
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances/$INSTANCE_ID \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```

**Expected result:** `stopped`

```bash
# Start it again
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances/$INSTANCE_ID/start

# Wait 15 seconds, then check again
sleep 15
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances/$INSTANCE_ID \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```

**Expected result:** `running`

**Pass:** Status goes from `running` → `stopped` → `running`.
**Fail:** Status stays stuck, shows `error`, or never comes back to `running`.

---

### Test 5 — Launch a Brand New Instance

**What this tests:** Can you create a new virtual computer from scratch?

```bash
# Get an image ID first
IMAGE_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/images \
  | python3 -c "import sys,json; imgs=json.load(sys.stdin)['images']; print(imgs[0]['id'] if imgs else '')")

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:5001/api/v1/compute/instances \
  -d "{\"name\": \"my-test-vm\", \"flavor\": \"t1.nano\", \"image_id\": \"$IMAGE_ID\"}"
```

Wait 20–30 seconds, then check:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['instances'] if i['name']=='my-test-vm']"
```

**Expected result:** `running`

**Pass:** Instance reaches `running` within 30 seconds.
**Fail:** Status is `error`, or command fails.

---

### Test 6 — Assign a Floating IP

**What this tests:** Can you give a virtual computer a public IP address?

```bash
# Allocate a floating IP from the pool
FIP=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id'], d['ip_address'])")
echo "FIP: $FIP"

FIP_ID=$(echo $FIP | awk '{print $1}')

# Associate with an instance
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:5001/api/v1/network/floating-ips/$FIP_ID/associate \
  -d "{\"instance_id\": \"$INSTANCE_ID\"}"

# Verify
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/floating-ips \
  | python3 -m json.tool
```

**Expected result:** Floating IP appears with `"status": "associated"` and the instance's private IP.

**Pass:** Floating IP is linked to an instance.
**Fail:** Error message, or IP shows unassociated.

---

### Test 7 — Create and Attach a Volume (Storage)

**What this tests:** Can you add extra storage to a virtual computer?

```bash
# Create a 1GB volume
VOL_ID=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:5001/api/v1/storage/volumes \
  -d '{"name": "test-volume", "size_gb": 1}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Check it is ready
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/storage/volumes/$VOL_ID \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])"
```

**Expected result:** `available`

```bash
# Attach to an instance
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  http://localhost:5001/api/v1/storage/volumes/$VOL_ID/attach \
  -d "{\"instance_id\": \"$INSTANCE_ID\"}"

# Verify LVM device was created
sudo lvdisplay mini-cloud-vg | grep "LV Name"
```

**Expected result:** Volume LV appears in LVM output

Clean up:

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/storage/volumes/$VOL_ID/detach
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/storage/volumes/$VOL_ID
```

**Pass:** Volume is created as LVM LV, attaches to VM, detaches cleanly.
**Fail:** Status shows `error`, or attach command fails.

---

### Test 8 — Check Security Groups (Firewall)

**What this tests:** Does the firewall correctly block and allow connections?

```bash
# View existing security groups
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/network/security-groups \
  | python3 -m json.tool
```

**Expected result:** Security groups appear with their rules (TCP port 22, ICMP).

**Pass:** Rules appear as expected.
**Fail:** No security groups found, or empty rules list.

---

### Test 9 — Check Available Images

**What this tests:** Are the operating system templates available?

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/images \
  | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['images']]"
```

**Expected result:** At least one image listed with status `active`.

**Pass:** Images are listed and active.
**Fail:** Empty list or error.

---

### Test 10 — Multi-User Isolation

**What this tests:** Can different users only see their own resources?

```bash
# Login as a second user
TOKEN2=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"devuser","password":"DevUser@123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token','LOGIN FAILED'))")

# devuser should only see THEIR instances (not admin's)
curl -s -H "Authorization: Bearer $TOKEN2" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Instances visible:', d.get('count',0))"
```

**Expected result:** Only this user's own instances appear — not admin's.

**Pass:** Each user only sees what belongs to them (enforced at DB query level with `user_id` filter).
**Fail:** Users can see each other's instances.

---

## Section 3B — UI Tests: Create, Update, Delete from the Dashboard

Open the dashboard at `http://localhost:5001` before running these tests.
If the dashboard is not running, start it first:

```bash
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

---

### UI Test 1 — Launch a New Instance from the Browser

**What this tests:** Can you create a virtual machine from the web interface?

**Steps:**
1. Click **Instances** in the left sidebar
2. Click the orange **Launch Instance** button (top right)
3. Fill in the form:
   - Name: `ui-test-vm`
   - Image: `cirros-0.6.2-x86_64-disk`
   - Flavor: `m1.tiny`
   - Key Pair: `project-key`
4. Click **Launch**

**Expected result:**
- A green notification bar appears at the bottom right of the screen
- The instance table refreshes automatically after ~5 seconds
- After 20–30 seconds (click **Refresh**): `ui-test-vm` appears with status `ACTIVE`

**Verify from CLI:**
```bash
sudo virsh list --all | grep ui-test-vm
```
Expected: `running`

**Pass:** Instance appears in table with `running` status within 30 seconds.
**Fail:** Error notification appears, or instance never becomes running.

---

### UI Test 2 — Stop an Instance from the Browser

**What this tests:** Can you shut down a running VM from the UI?

**Steps:**
1. Find `ui-test-vm` in the Instances table (status: `running`)
2. Click the yellow **Stop** button on that row

**Expected result:**
- A toast notification appears: *"ui-test-vm is shutting down"*
- Click **Refresh** after 10 seconds — status changes to `stopped`
- The Stop button disappears; a green **Start** button appears in its place

**Verify from CLI:**
```bash
sudo virsh list --all | grep ui-test-vm
```
Expected: `shut off`

**Pass:** Status changes from `ACTIVE` to `SHUTOFF`.
**Fail:** Status stays `ACTIVE` or shows `ERROR`.

---

### UI Test 3 — Start a Stopped Instance from the Browser

**What this tests:** Can you resume a stopped VM from the UI?

**Steps:**
1. Find `ui-test-vm` with status `SHUTOFF`
2. Click the green **Start** button on that row

**Expected result:**
- Toast: *"ui-test-vm is booting up"*
- Click **Refresh** after 15 seconds — status returns to `ACTIVE`

**Pass:** Status changes from `SHUTOFF` back to `ACTIVE`.
**Fail:** Status stays `SHUTOFF` or shows `ERROR`.

---

### UI Test 4 — Delete an Instance from the Browser

**What this tests:** Can you permanently remove a VM from the UI?

**Steps:**
1. Find `ui-test-vm` in the Instances table
2. Click the red **Delete** button
3. A confirmation dialog appears — click **Delete** to confirm

**Expected result:**
- The row disappears from the table within a few seconds
- The Instances count in the Overview decreases by 1

**Verify from CLI:**
```bash
sudo virsh list --all | grep ui-test-vm || echo "confirmed: not found"
```
Expected: no output (VM is gone).

**Pass:** Instance is removed from the table and CLI confirms it no longer exists.
**Fail:** Instance still shows in the list, or an error toast appears.

---

### UI Test 5 — Create a Volume from the Browser

**What this tests:** Can you provision block storage (EBS equivalent) from the UI?

**Steps:**
1. Click **Volumes** in the sidebar
2. Click the orange **Create Volume** button
3. Fill in the form:
   - Name: `ui-test-disk`
   - Size: `2`
4. Click **Create**

**Expected result:**
- Toast: *"Creating volume — ui-test-disk (2 GB)"*
- Table refreshes after 3 seconds
- `ui-test-disk` appears with status `available` and size `2 GB`

**Verify from CLI:**
```bash
sudo lvdisplay mini-cloud-vg | grep "LV Name"
# ui-test-disk LV should appear
```

**Pass:** Volume appears with status `available`.
**Fail:** Error notification, or volume shows `error` status.

---

### UI Test 6 — Delete a Volume from the Browser

**What this tests:** Can you clean up storage that is not in use?

**Steps:**
1. Find `ui-test-disk` with status `available`
2. Click the red **Delete** button on that row
3. Confirm in the dialog

**Expected result:**
- `ui-test-disk` disappears from the table

**Note:** If a volume shows `in-use`, the Delete button is disabled — this is correct behavior. A volume must be detached from an instance before it can be deleted.

**Pass:** Volume row disappears from the table.
**Fail:** Error toast appears, or the volume stays in the list.

---

### UI Test 7 — Allocate a Floating IP from the Browser

**What this tests:** Can you request a new public IP from the pool?

**Steps:**
1. Click **Floating IPs** in the sidebar
2. Note the current count of IPs
3. Click the orange **Allocate IP** button

**Expected result:**
- Toast: *"Requesting a new floating IP from the public pool"*
- A new row appears with a new IP address and status `DOWN`
- The IP count increases by 1

**Pass:** New IP row appears in the table.
**Fail:** Error toast, or IP count stays the same.

---

### UI Test 8 — Release a Floating IP from the Browser

**What this tests:** Can you return an unattached IP to the pool?

**Steps:**
1. Find the newly allocated IP that shows **Not attached** in the Fixed IP column
2. Click the red **Release** button
3. Confirm in the dialog

**Expected result:**
- The IP row disappears from the table

**Note:** IPs that are attached to an instance show `in use` — the Release button is disabled until the IP is detached first. This prevents breaking a live instance.

**Pass:** Unattached IP is removed from the table.
**Fail:** Error toast, or IP row stays.

---

### UI Test 9 — Create AMI from a Running Instance

**What this tests:** Can you snapshot a running VM into a reusable image?

**Steps:**
1. Click **Instances** in the left sidebar
2. Find any instance with status `ACTIVE` or `SHUTOFF`
3. Click the teal **📷 AMI** button on that row
4. In the modal, edit the name if desired (default is `<instance-name>-ami`)
5. Click **Create AMI**

**Expected result:**
- Toast: *"Snapshotting… this may take 1–5 minutes"*
- After 2–5 minutes, click **Images** in the sidebar
- A new image with your chosen name appears with status `active`

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/images | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['images']]"
```
Expected: new image appears with `active` status.

**Pass:** Image appears in Images section with `active` status within 5 minutes.
**Fail:** Error toast appears, or image stays in `saving` indefinitely.

---

### UI Test 10 — Launch an Instance from the Images Table (Launch from AMI)

**What this tests:** Can you start a new VM directly from the Images section?

**Steps:**
1. Click **Images** in the left sidebar
2. Find any `active` image (e.g. `cirros-0.6.2-x86_64-disk`)
3. Click the green **▶ Launch** button on that row
4. The Launch Instance modal opens with that image already selected
5. Fill in the remaining fields (name, flavor, network, security group)
6. Click **Launch**

**Expected result:**
- The image dropdown in the modal is pre-filled with the image you clicked
- Instance launches and reaches `ACTIVE` within 30 seconds (visible in Instances section)

**Pass:** Modal opens with image pre-selected; instance reaches `ACTIVE`.
**Fail:** Modal opens with wrong image selected, or launch fails.

---

### UI Test 11 — Copy an AMI

**What this tests:** Can you duplicate an image under a new name?

**Steps:**
1. Click **Images** in the left sidebar
2. Find `cirros-0.6.2-x86_64-disk` (small image — copies in seconds)
3. Click the purple **⛧ Copy** button on that row
4. In the modal, change the name to `cirros-copy-test`
5. Click **Copy**

**Expected result:**
- Toast: *"Copying AMI… Streaming image data"*
- After a few seconds, click **Refresh**
- `cirros-copy-test` appears in the Images table with status `active`

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/images | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['images']]"
```
Expected: `cirros-copy-test` appears with `active` status.

**Pass:** New image appears with `active` status and correct name.
**Fail:** Error toast, or image stays in `queued`/`saving` state.

---

### UI Test 12 — Delete an AMI

**What this tests:** Can you remove an image from the system?

**Steps:**
1. Click **Images** in the left sidebar
2. Find `cirros-copy-test` created in UI Test 11
3. Click the red **🗑 Delete** button on that row
4. Read the confirmation dialog — note it says running instances are not affected
5. Click **Delete** to confirm

**Expected result:**
- `cirros-copy-test` disappears from the Images table
- Image count in the sidebar badge decreases by 1

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/images | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['images']]"
```
Expected: `cirros-copy-test` does NOT appear.

**Pass:** Image is removed from the table.
**Fail:** Error toast appears, or image remains in the list.

---

### UI Test 13 — View Key Pairs from the Dashboard

**What this tests:** Are existing key pairs listed with their details?

**Steps:**
1. Click **Key Pairs** in the left sidebar (under Networking)
2. The table loads automatically

**Expected result:**
- Each key pair row shows: Name, Fingerprint, Creation date, SSH command hint
- The SSH command column shows: `ssh -i <name>.pem <user>@<floating-ip>`
- An info bar at the top reminds you that private keys are one-time only

**Pass:** Key pairs table loads with at least `project-key` visible.
**Fail:** Error message, or empty table when key pairs exist in CLI (`curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/keypairs | python3 -m json.tool`).

---

### UI Test 14 — Create a Key Pair and Download Private Key

**What this tests:** Can you generate a new SSH key pair and get the private key file?

**Steps:**
1. Click **Key Pairs** in the left sidebar
2. Click the orange **Create Key Pair** button
3. Enter name: `ui-test-key`
4. Click **Create & Download**

**Expected result:**
- A `.pem` file named `ui-test-key.pem` downloads automatically to your Downloads folder
- A success toast appears: *"ui-test-key.pem downloaded — store it safely"*
- After 2 seconds the table refreshes and `ui-test-key` appears in the list with its fingerprint

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/keypairs | python3 -m json.tool
```
Expected: `ui-test-key` appears.

**Pass:** `.pem` file downloaded and key pair appears in the table.
**Fail:** No file download, error toast, or key does not appear in the table.

---

### UI Test 15 — Use the New Key Pair When Launching an Instance

**What this tests:** Does the newly created key pair appear in the launch wizard?

**Steps:**
1. Click **Instances** in the sidebar
2. Click **Launch Instance**
3. Open the **Key Pair** dropdown

**Expected result:**
- `ui-test-key` appears in the dropdown alongside any other key pairs

**Steps (continued):**
4. Select `ui-test-key`
5. Fill in the remaining fields and launch an instance
6. SSH into the instance using the downloaded key:
```bash
ssh -i ~/Downloads/ui-test-key.pem cirros@<floating-ip>
```

**Pass:** Key pair appears in dropdown; SSH login works with the downloaded `.pem` file.
**Fail:** Key pair missing from dropdown, or SSH fails with `Permission denied`.

---

### UI Test 16 — Delete a Key Pair from the Dashboard

**What this tests:** Can you remove a key pair that is no longer needed?

**Steps:**
1. Click **Key Pairs** in the left sidebar
2. Find `ui-test-key` in the table
3. Click the red **Delete** button on that row
4. Read the confirmation dialog — note it says running instances are not affected
5. Click **Delete** to confirm

**Expected result:**
- `ui-test-key` disappears from the table
- The Key Pairs count badge decreases by 1

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/keypairs | python3 -m json.tool
```
Expected: `ui-test-key` does NOT appear.

**Pass:** Key pair is removed from the table.
**Fail:** Error toast appears, or key pair remains in the list.

---

### UI Test 17 — Create a Security Group from the Browser

**What this tests:** Can you add a new firewall rule set?

**Steps:**
1. Click **Security Groups** in the left sidebar
2. Click the orange **Create Security Group** button
3. Fill in the form:
   - Name: `ui-test-sg`
   - Description: `Test security group`
4. Click **Create**

**Expected result:**
- Toast: *"Created security group ui-test-sg"*
- `ui-test-sg` appears in the Security Groups table with 0 rules

**Pass:** New group row appears in the table.
**Fail:** Error toast, or group does not appear.

---

### UI Test 18 — Add Inbound Rules to a Security Group

**What this tests:** Can you open specific ports in a firewall?

**Steps:**
1. In the Security Groups table, find `ui-test-sg`
2. Click the blue **+ Rule** button
3. In the modal, add an HTTP rule:
   - Protocol: `TCP`
   - Port From: `80`
   - Port To: `80`
   - Remote IP: `0.0.0.0/0`
4. Click **Add Rule**
5. Repeat for SSH: Protocol `TCP`, Port `22`, Remote IP `0.0.0.0/0`

**Expected result:**
- After each addition, a toast confirms the rule was added
- The rule count badge on `ui-test-sg` increases

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/network/security-groups | python3 -m json.tool
```
Expected: TCP port 22 and TCP port 80 rules appear.

**Pass:** Both rules visible in CLI output.
**Fail:** Error toast, or rules missing from CLI.

---

### UI Test 19 — Attach a Security Group to a Running Instance

**What this tests:** Can you apply a different firewall to an existing VM without restarting it?

**Steps:**
1. Click **Instances** in the sidebar
2. Find an `ACTIVE` instance
3. Click the **🛡 SG** button on that row
4. In the modal, check the box next to `ui-test-sg`
5. Click **Save**

**Expected result:**
- Toast: *"Security groups updated"*
- The instance now has `ui-test-sg` applied (verify below)

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/compute/instances | python3 -m json.tool
```
Expected: `ui-test-sg` appears alongside any previous groups.

**Pass:** Instance now has the new security group attached.
**Fail:** Error toast, or CLI shows old groups only.

---

### UI Test 20 — Delete a Security Group Rule

**What this tests:** Can you remove a specific firewall rule without deleting the whole group?

**Steps:**
1. Click **Security Groups** in the sidebar
2. Find `ui-test-sg` and click its **+ Rule** button to open the rules view
3. Find the TCP port 80 rule
4. Click the red **🗑** delete button on that rule row
5. Confirm in the dialog

**Expected result:**
- Toast: *"Rule deleted"*
- The port 80 rule disappears; port 22 rule remains

**Pass:** Port 80 rule gone; port 22 rule still present.
**Fail:** Error toast, or both rules disappear, or neither disappear.

---

### UI Test 21 — Delete a Security Group

**What this tests:** Can you remove an entire security group when it is no longer needed?

**Steps:**
1. Click **Security Groups** in the sidebar
2. Find `ui-test-sg`
3. Click the red **Delete** button on that row
4. Confirm in the dialog

**Expected result:**
- `ui-test-sg` disappears from the table

**Note:** If the security group is still attached to a running instance, the API will refuse the delete with a 409 error. Detach it from all instances first.

**Pass:** Group removed from the table.
**Fail:** Error toast about the group being in use (expected if still attached — detach first).

---

### UI Test 22 — Create a Volume Snapshot

**What this tests:** Can you take a point-in-time backup of a volume?

**Steps:**
1. Click **Snapshots** in the left sidebar (under Storage)
2. Click the orange **Create Snapshot** button
3. Fill in the form:
   - Source Volume: select any existing volume from the dropdown
   - Snapshot Name: `ui-test-snapshot`
   - Description: `Before config change`
4. Click **Create**

**Expected result:**
- Toast: *"Snapshot ui-test-snapshot is being created"*
- After a few seconds, click **Refresh**
- `ui-test-snapshot` appears in the Snapshots table with status `available`

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/storage/snapshots | python3 -m json.tool
```
Expected: `ui-test-snapshot` appears with `available` status.

**Pass:** Snapshot appears with `available` status.
**Fail:** Error toast, or snapshot shows `error` status.

---

### UI Test 23 — Restore a Volume from a Snapshot

**What this tests:** Can you create a new volume from a snapshot backup?

**Steps:**
1. Click **Snapshots** in the sidebar
2. Find `ui-test-snapshot` with status `available`
3. Click the **↩ Restore** button on that row
4. Fill in the form:
   - New Volume Name: `restored-from-snap`
   - Size (GB): `2` (must be ≥ original snapshot size)
5. Click **Restore**

**Expected result:**
- Toast: *"Creating volume restored-from-snap from snapshot"*
- Click **Volumes** in the sidebar
- `restored-from-snap` appears with status `available`

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/storage/volumes | python3 -m json.tool
```
Expected: `restored-from-snap` appears with `available` status.

**Pass:** New volume appears in Volumes section.
**Fail:** Error toast (check if size entered is smaller than the original snapshot — increase it).

---

### UI Test 24 — Delete a Snapshot

**What this tests:** Can you remove a snapshot backup that is no longer needed?

**Steps:**
1. Click **Snapshots** in the sidebar
2. Find `ui-test-snapshot`
3. Click the red **🗑 Delete** button
4. Confirm in the dialog

**Expected result:**
- `ui-test-snapshot` disappears from the table
- The original volume is not affected (the snapshot was a copy)

**Pass:** Snapshot row removed from the table.
**Fail:** Error toast, or snapshot remains.

---

### UI Test 25 — Open the Instance Console (Serial Log)

**What this tests:** Can you view the boot log and serial output of a running VM?

**Steps:**
1. Click **Instances** in the sidebar
2. Find an `ACTIVE` instance
3. Click the **💻 Console** button on that row
4. The Console modal opens

**Expected result:**
- The modal shows a dark terminal-style output area
- Text from the VM's serial port appears (Linux boot messages, login prompt, etc.)
- The VNC Console URL appears at the top as a clickable link
- The line count selector (50/100/250/500) lets you load more history

**Actions to test inside the modal:**
- Change the line selector to `100` — the output refreshes automatically
- Click **↻ Refresh** — output reloads with fresh content
- Click the VNC URL link — it opens in a new browser tab showing the graphical console

**Pass:** Console output shows boot messages or login prompt; VNC link is valid.
**Fail:** Console shows blank or error; VNC link is missing or broken.

---

### UI Test 26 — Attach a Network Interface to an Instance

**What this tests:** Can you add a second virtual network card (ENI) to a running instance?

**Steps:**
1. Click **Instances** in the sidebar
2. Find an `ACTIVE` instance
3. Click the **🔌 NIC** button on that row
4. In the Attach Interface modal:
   - Either select an existing free port from the dropdown
   - Or leave that empty and select a network from the "New port on Network" dropdown
5. Click **Attach**

**Expected result:**
- Toast: *"Interface attached — NIC added to instance"*

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/network/floating-ips | python3 -m json.tool
```
Expected: A second IP address appears in the output.

**Pass:** New IP/interface visible in server details.
**Fail:** Error toast (check if the selected port is already in use by another instance).

---

### UI Test 27 — Create a Standalone Network Interface (Port)

**What this tests:** Can you pre-create a port on a network before attaching it to an instance?

**Steps:**
1. Click **Network Interfaces** in the left sidebar (under Networking)
2. Click the orange **Create Interface** button
3. Fill in the form:
   - Network: `private-network`
   - Name: `ui-test-eni`
4. Click **Create**

**Expected result:**
- Toast: *"Interface ui-test-eni is ready"*
- `ui-test-eni` appears in the Network Interfaces table with status `DOWN` and a MAC address

**Verify from CLI:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/network/networks | python3 -m json.tool
```
Expected: `ui-test-eni` appears with `DOWN` status.

**Pass:** Port appears in the table with a MAC address.
**Fail:** Error toast, or port does not appear.

---

### UI Test 28 — Delete a Network Interface (Port)

**What this tests:** Can you remove an unattached network interface?

**Steps:**
1. Click **Network Interfaces** in the sidebar
2. Find `ui-test-eni` with status `DOWN` and no device owner shown
3. Click the red **🗑 Delete** button
4. Confirm in the dialog

**Expected result:**
- `ui-test-eni` disappears from the table

**Note:** Ports that show a device owner (e.g. `compute:libvirt` or `network:dhcp`) have "In use" text instead of a Delete button — they are managed by the network layer and cannot be manually deleted.

**Pass:** Port removed from the table.
**Fail:** Error toast, or port remains.

---

### UI Test 29 — View Resource Quotas by Project

**What this tests:** Can you see how much of each resource limit each project has consumed?

**Steps:**
1. Click **Quotas** in the left sidebar (under Identity)
2. The page loads quota cards for each project automatically

**Expected result:**
- One card per project (e.g., `admin`, `demo`, `dev-project`, `prod-project`)
- Each card shows progress bars for:
  - **Compute:** Instances, vCPUs, RAM, Key Pairs
  - **Storage:** Volumes, Snapshots, Storage GB
  - **Network:** Networks, Subnets, Routers, Floating IPs, Security Groups, Ports
- Progress bars are color coded:
  - Green — under 70% used
  - Amber — 70–89% used
  - Red — 90%+ used (approaching limit)
- Unlimited quotas show "Unlimited" text instead of a bar

**Pass:** All projects have cards; bars show correct used/limit numbers.
**Fail:** Error message, blank page, or bars show 0/0 for all resources.

---

### UI Test 30 — Create a Network

**What this tests:** Can you add a new private network (VPC equivalent)?

**Steps:**
1. Click **Networks** in the left sidebar
2. Click the orange **Create Network** button
3. Fill in the form:
   - Name: `ui-test-net`
4. Click **Create**

**Expected result:**
- Toast: *"Network ui-test-net created"*
- `ui-test-net` appears in the Networks table

**Pass:** Network row appears in the table.
**Fail:** Error toast.

---

### UI Test 31 — Create a Subnet on a Network

**What this tests:** Can you define an IP address range within a network?

**Steps:**
1. Click **Networks** in the sidebar
2. Find `ui-test-net` and click its **+ Subnet** button
3. Fill in the form:
   - Subnet Name: `ui-test-subnet`
   - CIDR: `10.99.0.0/24`
   - Gateway IP: `10.99.0.1`
   - DNS: `8.8.8.8`
4. Click **Create**

**Expected result:**
- Toast: *"Subnet ui-test-subnet created"*
- The subnet count badge on `ui-test-net` increases by 1

**Pass:** Subnet badge increments; subnet visible in mini-cloud dashboard → Networks.
**Fail:** Error toast (check if CIDR overlaps an existing subnet).

---

### UI Test 32 — Create a Router and Set Its Gateway

**What this tests:** Can you create an internet gateway for a private network?

**Steps:**
1. Click **Routers** in the left sidebar
2. Click the orange **Create Router** button
3. Fill in the form:
   - Name: `ui-test-router`
4. Click **Create**
5. Find `ui-test-router` in the Routers table
6. Click the **Set Gateway** button
7. Select `public` as the external network
8. Click **Set Gateway**

**Expected result:**
- Router appears with a gateway IP from the public network

**Pass:** Router has an external gateway IP in the table.
**Fail:** Error setting gateway (check networks exist in dashboard → Networks).

---

### UI Test 33 — Attach a Subnet to a Router

**What this tests:** Can you connect a private subnet through a router so its VMs can reach the internet?

**Steps:**
1. In the Routers table, find `ui-test-router`
2. Click the **+ Subnet** button
3. Select `ui-test-subnet` from the dropdown
4. Click **Attach**

**Expected result:**
- Toast: *"Subnet attached to router"*
- The interface/subnet count on the router increases

**Pass:** Subnet listed in the router's interface count.
**Fail:** Error toast.

---

### UI Test 34 — Allocate and Associate a Floating IP

**What this tests:** Can you give an instance a reachable public IP from the UI?

**Steps:**
1. Click **Floating IPs** in the left sidebar
2. Click the orange **Allocate IP** button — a new unattached IP appears
3. On that new IP row, click the green **Associate** button
4. Select a running instance from the dropdown
5. Click **Associate**

**Expected result:**
- Toast: *"IP associated with [instance]"*
- The row now shows the instance name and its private IP in the Fixed IP column

**Pass:** IP row shows instance name; ping to that IP succeeds from the host.
**Fail:** Error toast; IP row stays unattached.

---

### UI Test 35 — Disassociate and Release a Floating IP

**What this tests:** Can you detach a public IP from an instance and return it to the pool?

**Steps:**
1. Click **Floating IPs** in the sidebar
2. Find the IP associated in UI Test 34
3. Click the orange **Disassociate** button on that row — IP stays in pool but is now unattached
4. Find the same IP (now unattached) and click the red **Release** button
5. Confirm in the dialog

**Expected result:**
- After Disassociate: Fixed IP column shows "Not attached"
- After Release: IP row disappears from the table

**Pass:** IP detached then removed.
**Fail:** Disassociate or Release throws an error.

---

### UI Test 36 — Create a Load Balancer

**What this tests:** Can you provision a load balancer to distribute traffic across multiple instances?

**Steps:**
1. Click **Load Balancers** in the left sidebar
2. Click the orange **Create Load Balancer** button
3. Fill in the form:
   - Name: `ui-test-lb`
   - Subnet: select `private-subnet` (or any existing subnet)
4. Click **Create**

**Expected result:**
- Toast: *"Load balancer ui-test-lb is provisioning"*
- `ui-test-lb` appears in the table with status `PENDING_CREATE`, then `ACTIVE` after 10–30 seconds
- Click **Refresh** to update

**Pass:** LB reaches `ACTIVE` within 30 seconds.
**Fail:** Stays `PENDING_CREATE` for over 2 minutes, or shows `ERROR`.

---

### UI Test 37 — Add a Listener to a Load Balancer

**What this tests:** Can you define what port the load balancer listens on?

**Steps:**
1. In the Load Balancers table, find `ui-test-lb` (must be `ACTIVE`)
2. Click the **Listeners** button on that row
3. In the Listeners modal, click **Add Listener**
4. Fill in:
   - Name: `ui-test-lb-http`
   - Protocol: `HTTP`
   - Port: `80`
5. Click **Add**

**Expected result:**
- Toast: *"Listener created"*
- The listener list in the modal shows `ui-test-lb-http` on port 80

**Pass:** Listener row appears in the modal.
**Fail:** Error toast; check if LB is in `ACTIVE` state first.

---

### UI Test 38 — Add Backend Members to a Load Balancer

**What this tests:** Can you register instances as targets behind the load balancer?

**Steps:**
1. In the Load Balancers table, find `ui-test-lb`
2. Click the **Members** button on that row
3. In the Members modal, each active instance is listed with a checkbox
4. Check any running instance and set its port to `80`
5. Click **Add Members**

**Expected result:**
- Toast: *"Member(s) added"*
- The selected instance(s) appear as members

**Pass:** Member row appears in the members list.
**Fail:** Error toast; check if the instance is in the same subnet as the LB.

---

### UI Test 39 — Configure a Health Monitor on a Load Balancer

**What this tests:** Does the load balancer automatically stop sending traffic to unhealthy instances?

**Steps:**
1. In the Load Balancers table, find `ui-test-lb`
2. Click the **Health** button on that row
3. In the Health Monitor modal, fill in:
   - Type: `HTTP`
   - Delay: `10` (seconds between checks)
   - Timeout: `5`
   - Max Retries: `3`
4. Click **Create**

**Expected result:**
- Toast: *"Health monitor created"*
- The Health button row shows current monitor type, delay, and status

**Pass:** Monitor details appear in the modal.
**Fail:** Error toast.

---

### UI Test 40 — Delete a Load Balancer

**What this tests:** Can you remove a load balancer and all its components?

**Steps:**
1. In the Load Balancers table, find `ui-test-lb`
2. Click the red **Delete** button
3. Confirm in the dialog

**Note:** Delete all members before deleting the load balancer. If the delete fails, check that HAProxy has no running operations on that backend.

**Expected result:**
- `ui-test-lb` disappears from the table

**Pass:** LB row removed.
**Fail:** Error toast (wait until LB is `ACTIVE`, then retry).

---

### UI Test 41 — Create an Auto Scaling Group

**What this tests:** Can you define a group of instances that scales automatically?

**Steps:**
1. Click **Auto Scaling** in the left sidebar
2. Click the orange **Create ASG** button
3. Fill in the form:
   - Group Name: `ui-test-asg`
   - Image: `cirros-0.6.2-x86_64-disk`
   - Flavor: `m1.tiny`
   - Network: `private-network`
   - Min Instances: `1`
   - Desired Instances: `2`
   - Max Instances: `3`
4. Click **Create**

**Expected result:**
- `ui-test-asg` appears in the Auto Scaling table
- After ~30 seconds, 2 instances launch (Desired = 2)
- Click **Instances** section — 2 new instances with ASG-prefixed names appear

**Pass:** ASG row appears; correct instance count reaches `ACTIVE`.
**Fail:** Error toast, or instance count does not match Desired.

---

### UI Test 42 — Manually Scale an Auto Scaling Group

**What this tests:** Can you manually change the number of running instances in a group?

**Steps:**
1. In the Auto Scaling table, find `ui-test-asg`
2. Click the blue **Scale** button
3. In the modal, change Desired to `3`
4. Click **Scale**

**Expected result:**
- Toast: *"Scaling ui-test-asg to 3 instances"*
- After ~30 seconds, a 3rd instance appears in the Instances section with the ASG prefix

**Pass:** Instance count goes from 2 → 3.
**Fail:** Instance count does not change, or an instance shows `ERROR`.

---

### UI Test 43 — Add a Scaling Policy to an Auto Scaling Group

**What this tests:** Can you define a rule to automatically trigger scaling?

**Steps:**
1. In the Auto Scaling table, find `ui-test-asg`
2. Click the purple **Policies** button
3. In the modal, click **Add Policy**
4. Fill in:
   - Policy Name: `scale-up-policy`
   - Adjustment Type: `change_in_capacity`
   - Scaling Adjustment: `1`
   - Cooldown: `60`
5. Click **Add**

**Expected result:**
- Toast: *"Policy scale-up-policy added"*
- Policy appears in the policies list

**Pass:** Policy row appears with correct values.
**Fail:** Error toast.

---

### UI Test 44 — Delete an Auto Scaling Group

**What this tests:** Can you remove an ASG and all its managed instances?

**Steps:**
1. In the Auto Scaling table, find `ui-test-asg`
2. Click the red **Delete** button
3. Confirm in the dialog

**Expected result:**
- `ui-test-asg` disappears from the table
- All ASG-managed instances are also terminated (visible in Instances section)

**Pass:** ASG and its instances removed.
**Fail:** Error toast, or ASG remains with partial instance count.

---

### UI Test 45 — Resize an Instance

**What this tests:** Can you change the CPU/RAM allocation of a stopped instance?

**Steps:**
1. Click **Instances** in the sidebar
2. Find an instance with status `SHUTOFF`
3. Click the **⚙ Modify** button on that row
4. In the modal, select a larger flavor (e.g. change from `m1.tiny` to `m1.small`)
5. Click **Resize**

**Expected result:**
- Toast: *"Resize initiated for [name]"*
- Instance status changes to `VERIFY_RESIZE`
- A yellow **✓ Confirm** button appears on the row

**Steps to confirm:**
6. Click the **✓ Confirm** button on the instance row
7. Toast: *"Resize confirmed"*
8. Status returns to `SHUTOFF`

**Pass:** Instance changes flavor; status goes SHUTOFF → VERIFY_RESIZE → SHUTOFF.
**Fail:** Error toast; resize may fail if host lacks resources.

---

### UI Test 46 — Attach a Volume to an Instance

**What this tests:** Can you connect a disk to a running VM?

**Steps:**
1. Create a volume first: Click **Volumes** → **Create Volume**, name `attach-test-vol`, size `1`
2. Wait for status `available`
3. Click the green **Attach** button on `attach-test-vol`
4. In the modal, select a running instance
5. Click **Attach**

**Expected result:**
- Toast: *"Volume attached"*
- Volume status changes from `available` to `in-use`
- The Attached To column shows the instance name

**Pass:** Status changes to `in-use`; instance name shown in table.
**Fail:** Error toast (check if instance is `ACTIVE` — cannot attach to stopped instances in some configurations).

---

### UI Test 47 — Detach a Volume from an Instance

**What this tests:** Can you safely unmount a disk from a VM?

**Steps:**
1. Click **Volumes** in the sidebar
2. Find `attach-test-vol` with status `in-use`
3. Click the orange **Detach** button
4. Confirm in the dialog

**Expected result:**
- Toast: *"Volume detached"*
- Status changes from `in-use` back to `available`

**Pass:** Status returns to `available`.
**Fail:** Error toast; make sure the volume is unmounted inside the VM before detaching.

---

### UI Test 48 — Resize a Volume

**What this tests:** Can you increase the storage capacity of an existing volume?

**Steps:**
1. Click **Volumes** in the sidebar
2. Find any volume with status `available`
3. Click the blue **Resize** button
4. In the modal, enter a new size larger than the current size (e.g. if current is 1 GB, enter `2`)
5. Click **Resize**

**Expected result:**
- Toast: *"Resize request submitted"*
- After a few seconds, the size column updates to the new value

**Note:** Volumes can only grow, never shrink. Entering a smaller value than the current size will return an error.

**Pass:** Size column shows the new value.
**Fail:** Error toast (check if the new size is larger than current).

---

### UI Test 49 — Add a Static Route to a Router

**What this tests:** Can you manually define where specific network traffic should go?

**Steps:**
1. Click **Routers** in the left sidebar
2. Find `main-router` (or any router with a gateway)
3. Click the **Routes** button on that row
4. In the modal, click **Add Route**
5. Fill in:
   - Destination: `10.50.0.0/24`
   - Next Hop: `192.168.100.1`
6. Click **Add**

**Expected result:**
- Toast: *"Static route added"*
- The route appears in the route list for that router

**Pass:** Route row appears with the correct destination and next hop.
**Fail:** Error toast (check if the next hop IP is reachable from the router's subnet).

---

### UI Test 50 — Reboot an Instance

**What this tests:** Can you restart an instance OS without deleting it?

**Steps:**
1. Click **Instances** in the sidebar
2. Find an `ACTIVE` instance
3. Click the **↺ Reboot** button on that row
4. Confirm in the dialog (note: soft reboot — OS restarts cleanly)

**Expected result:**
- Toast: *"Rebooting [name]"*
- Status briefly changes to `REBOOT` then returns to `ACTIVE` within 30 seconds

**Pass:** Instance returns to `ACTIVE` after reboot.
**Fail:** Instance stays in `REBOOT` for more than 2 minutes or goes to `ERROR`.

---

## Section 3C — Complete Operation Reference (All Services)

This table covers every operation available in the dashboard — use it as a quick checklist.

### Instances (EC2 Compute)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List instances | Click **Instances** in sidebar | Shows all VMs with status, IP, flavor |
| Launch instance | **Launch Instance** button | Creates new VM from image + flavor |
| Stop instance | **■ Stop** button on row | Graceful shutdown — disk preserved |
| Start instance | **▶ Start** button on row | Powers on a stopped VM |
| Reboot instance | **↺ Reboot** button on row | Soft-restarts the OS |
| Resize instance | **⚙ Modify** on SHUTOFF row | Changes CPU/RAM allocation |
| Confirm resize | **✓ Confirm** on VERIFY_RESIZE row | Finalizes a pending resize |
| Delete instance | **🗑 Delete** button on row | Permanently destroys the VM |
| Create AMI | **📷 AMI** on ACTIVE/SHUTOFF row | Snapshots the VM into a reusable image |
| Open Console | **💻 Console** on ACTIVE row | Shows serial log + VNC link |
| Attach NIC | **🔌 NIC** on ACTIVE row | Adds a second network interface |
| Manage SGs | **🛡 SG** on ACTIVE row | Attach/detach security groups |

---

### Images (AMI — qcow2 + SQLite)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List images | Click **Images** in sidebar | Shows all OS templates with status |
| Launch from image | **▶ Launch** button on row | Opens launch wizard pre-filled with this image |
| Copy image | **⛧ Copy** button on row | Duplicates image under a new name |
| Delete image | **🗑 Delete** button on row | Removes the image template |

---

### Volumes (EBS — LVM)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List volumes | Click **Volumes** in sidebar | Shows all disks with status, size, attachment |
| Create volume | **Create Volume** button | Provisions a new empty disk |
| Attach to instance | **Attach** button on `available` row | Mounts disk to a VM as `/dev/vdX` |
| Detach from instance | **Detach** button on `in-use` row | Safely unmounts disk |
| Resize volume | **Resize** button on row | Increases disk size (never shrink) |
| Delete volume | **🗑 Delete** button on `available` row | Permanently destroys the disk |

---

### Snapshots (EBS Snapshot — LVM CoW)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List snapshots | Click **Snapshots** in sidebar | Shows all point-in-time backups |
| Create snapshot | **Create Snapshot** button | Takes a backup of a volume right now |
| Restore snapshot | **↩ Restore** button on row | Creates a new volume from the backup |
| Delete snapshot | **🗑 Delete** button on row | Removes the backup |

---

### Key Pairs (SSH Keys — cloud-init)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List key pairs | Click **Key Pairs** in sidebar | Shows all SSH keys with fingerprints |
| Create key pair | **Create Key Pair** button | Generates key + auto-downloads `.pem` file |
| Use in launch | Key Pair dropdown in launch wizard | Injects public key into new VM at boot |
| Delete key pair | **Delete** button on row | Removes key from system (running VMs unaffected) |

---

### Security Groups (Firewall — iptables)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List security groups | Click **Security Groups** in sidebar | Shows all firewall rule sets |
| Create security group | **Create Security Group** button | Adds a new empty firewall |
| Add inbound rule | **+ Rule** button on row | Opens specific port/protocol |
| Delete rule | **🗑** on rule row in modal | Removes a specific port rule |
| Attach to instance | **🛡 SG** button on instance row | Applies firewall to a running VM |
| Detach from instance | Uncheck in SG modal on instance row | Removes firewall from VM |
| Delete security group | **Delete** button on row | Removes the firewall (must detach first) |

---

### Floating IPs (Elastic IP — iptables NAT)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List floating IPs | Click **Floating IPs** in sidebar | Shows all public IPs and their attachments |
| Allocate IP | **Allocate IP** button | Reserves a new public IP from the pool |
| Associate to instance | **Associate** button on unattached IP row | Links public IP to a VM |
| Disassociate | **Disassociate** button on attached IP row | Detaches IP (VM loses public access) |
| Release IP | **Release** button on unattached row | Returns IP to pool permanently |

---

### Networks (VPC — Linux Bridge)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List networks | Click **Networks** in sidebar | Shows all private networks |
| Create network | **Create Network** button | Adds a new isolated network |
| Add subnet | **+ Subnet** button on row | Defines IP range within a network |
| Delete subnet | **Delete** on subnet row in modal | Removes subnet (must remove dependencies) |
| Delete network | **Delete** button on row | Removes the network |

---

### Routers (Internet Gateway — iptables)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List routers | Click **Routers** in sidebar | Shows all routers with gateway status |
| Create router | **Create Router** button | Adds a new virtual router |
| Set external gateway | **Set Gateway** button on row | Connects router to public network |
| Remove gateway | **Remove Gateway** button | Disconnects router from public network |
| Attach subnet | **+ Subnet** button on row | Connects a private subnet through the router |
| Detach subnet | **Remove** on interface row | Disconnects subnet from router |
| View static routes | **Routes** button on row | Shows custom routing table |
| Add static route | **Add Route** in routes modal | Defines where specific traffic goes |
| Delete static route | **Delete** on route row in modal | Removes a custom route |
| Delete router | **Delete** button on row | Removes the router (remove interfaces first) |

---

### Network Interfaces / Ports (ENI — Linux Bridge)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List ports | Click **Network Interfaces** in sidebar | Shows all virtual NICs |
| Create port | **Create Interface** button | Pre-creates a NIC on a network |
| Attach to instance | **🔌 NIC** on instance row | Adds NIC to a running VM |
| Delete port | **🗑 Delete** on unattached port row | Removes the virtual NIC |

---

### Load Balancers (ELB — Octavia)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List load balancers | Click **Load Balancers** in sidebar | Shows all LBs with VIP and status |
| Create load balancer | **Create Load Balancer** button | Provisions a new LB on a subnet |
| Add listener | **Listeners** button → **Add Listener** | Sets which port/protocol the LB accepts |
| Remove listener | **Delete** on listener row in modal | Removes a listen port |
| Add backend member | **Members** button → **Add Members** | Registers an instance as a traffic target |
| Remove member | **Remove** on member row in modal | Deregisters an instance |
| Create health monitor | **Health** button → **Create** | Enables health checking of members |
| Delete health monitor | **Delete** in health modal | Removes automatic health checking |
| Delete load balancer | **Delete** button on LB row | Removes the entire LB |

---

### Auto Scaling Groups (ASG — Python thread)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List ASGs | Click **Auto Scaling** in sidebar | Shows all groups with instance counts |
| Create ASG | **Create ASG** button | Defines a group with min/desired/max counts |
| Edit ASG | **Edit** button on row | Updates min, desired, max counts |
| Manual scale | **Scale** button on row | Immediately sets a new desired count |
| Add scaling policy | **Policies** button → **Add Policy** | Defines an auto-trigger rule |
| Execute policy | **Execute** on policy row in modal | Manually fires the scaling rule |
| Delete policy | **Delete** on policy row in modal | Removes the trigger rule |
| Delete ASG | **Delete** button on row | Removes group and terminates its instances |

---

### Resource Quotas (Service Quotas — SQLite)

| Operation | How | What It Does |
|-----------|-----|-------------|
| View all project quotas | Click **Quotas** in sidebar | Shows usage vs. limit for every resource |

---

### Users & Projects (IAM — SQLite)

| Operation | How | What It Does |
|-----------|-----|-------------|
| List users | Click **Users & Projects** in sidebar | Shows all users and their project assignments |

---

### System Monitor

| Operation | How | What It Does |
|-----------|-----|-------------|
| View libvirtd status | `sudo systemctl is-active libvirtd` | Confirms VM manager is running |
| View service log | `sudo journalctl -u mini-cloud -n 50` | Last 50 lines of mini-cloud log |
| View all KVM VMs | `sudo virsh list --all` | Shows all defined/running VMs |

---

## Section 4 — What Exactly Should You Test?

Here is a complete checklist. Go through each item and write **PASS** or **FAIL** next to it.

### CLI Tests (run in terminal)

```
[ ] 1.  curl -s http://localhost:5001/api/v1/auth/health → Shows {"status": "ok"}
[ ] 2.  GET /api/v1/compute/instances (with TOKEN) → Shows running instances
[ ] 3.  Ping 10.200.195.153             → 0% packet loss
[ ] 4.  SSH into demo-instance-01       → Shell prompt appears
[ ] 5.  Stop demo-instance-01           → Status becomes SHUTOFF
[ ] 6.  Start demo-instance-01          → Status returns to ACTIVE
[ ] 7.  Launch a new instance (CLI)     → Reaches ACTIVE in < 30 seconds
[ ] 8.  Create and attach a volume      → Status goes available → in-use
[ ] 9.  Assign a floating IP            → IP is linked in the list
[ ] 10. curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/images | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['images']]"            → CirrOS and Ubuntu images active
[ ] 11. Security group rules visible    → Port 22 and ICMP rules exist
[ ] 12. devuser sees only dev-vm-01     → No cross-project visibility
[ ] 13. opsuser sees empty list         → Isolation working
```

### UI Tests (run from browser at localhost:8080)

#### Instances
```
[ ] 14. Dashboard loads                   → Overview cards show correct counts
[ ] 15. Launch Instance button            → ui-test-vm reaches ACTIVE in < 30 seconds
[ ] 16. Stop button                       → ui-test-vm status changes to SHUTOFF
[ ] 17. Start button                      → ui-test-vm status returns to ACTIVE
[ ] 18. Reboot button (UI Test 50)        → status goes REBOOT → ACTIVE within 30s
[ ] 19. Resize + Confirm (UI Test 45)     → flavor changes; VERIFY_RESIZE → SHUTOFF
[ ] 20. Delete button                     → ui-test-vm disappears from the table
[ ] 21. Create AMI button                 → snapshot modal opens; image appears in Images within 5 min
[ ] 22. Console button (UI Test 25)       → boot log visible; VNC link present
[ ] 23. NIC button (UI Test 26)           → second interface attached; new IP visible in server details
[ ] 24. SG button (UI Test 19)            → attach ui-test-sg; visible in GET /api/v1/compute/instances response
```

#### Images (AMI)
```
[ ] 25. Images section loads              → CirrOS and Ubuntu images listed and active
[ ] 26. Launch from AMI (UI Test 10)      → launch modal opens with image pre-selected
[ ] 27. Copy AMI button (UI Test 11)      → cirros-copy-test appears active within 30s
[ ] 28. Delete AMI button (UI Test 12)    → cirros-copy-test removed from Images table
```

#### Volumes (EBS)
```
[ ] 29. Create Volume button              → ui-test-disk appears with status available
[ ] 30. Attach to instance (UI Test 46)   → status changes to in-use; instance shown
[ ] 31. Detach from instance (UI Test 47) → status returns to available
[ ] 32. Resize volume (UI Test 48)        → size column updates to new value
[ ] 33. Delete Volume button              → ui-test-disk disappears from the table
```

#### Snapshots (EBS Snapshot)
```
[ ] 34. Create Snapshot button (UI Test 22)        → ui-test-snapshot appears available
[ ] 35. Restore snapshot (UI Test 23)              → restored-from-snap appears in Volumes
[ ] 36. Delete snapshot (UI Test 24)               → ui-test-snapshot removed from table
```

#### Key Pairs
```
[ ] 37. Key Pairs section loads           → project-key visible with fingerprint and SSH hint
[ ] 38. Create Key Pair button            → ui-test-key.pem downloads; key appears in table
[ ] 39. Key pair in launch wizard         → ui-test-key appears in dropdown
[ ] 40. Delete Key Pair button            → ui-test-key removed from table
```

#### Security Groups
```
[ ] 41. Security Groups section loads     → ssh-only shows TCP 22 and ICMP rules
[ ] 42. Create Security Group (Test 17)   → ui-test-sg appears in table
[ ] 43. Add rules (UI Test 18)            → TCP 22 and TCP 80 rules appear in CLI
[ ] 44. Delete a rule (UI Test 20)        → TCP 80 removed; TCP 22 remains
[ ] 45. Delete Security Group (UI Test 21)→ ui-test-sg removed from table
```

#### Floating IPs (Elastic IP)
```
[ ] 46. Floating IPs section loads        → all IPs listed with attachment status
[ ] 47. Allocate IP button                → new IP row appears (DOWN, not attached)
[ ] 48. Associate IP (UI Test 34)         → IP linked to instance; instance name shown
[ ] 49. Disassociate IP (UI Test 35)      → IP shown as Not attached
[ ] 50. Release IP button                 → IP row removed from table
```

#### Networks & Subnets
```
[ ] 51. Networks section loads            → 3+ networks visible (private, public, lb-mgmt)
[ ] 52. Create Network (UI Test 30)       → ui-test-net appears in table
[ ] 53. Create Subnet (UI Test 31)        → subnet count badge on ui-test-net increases
[ ] 54. Delete Network                    → ui-test-net removed from table
```

#### Routers
```
[ ] 55. Routers section loads             → main-router listed with gateway and subnet count
[ ] 56. Create Router (UI Test 32)        → ui-test-router appears in table
[ ] 57. Set Gateway (UI Test 32)          → router shows external gateway IP
[ ] 58. Attach Subnet (UI Test 33)        → interface count increases
[ ] 59. Add static route (UI Test 49)     → route visible in Routes modal
[ ] 60. Delete Router                     → ui-test-router removed from table
```

#### Network Interfaces (ENI / Ports)
```
[ ] 61. Network Interfaces section loads  → all ports listed with MAC and IP
[ ] 62. Create Interface (UI Test 27)     → ui-test-eni appears with DOWN status
[ ] 63. Attach via NIC button (UI Test 26)→ port status changes to ACTIVE; device owner set
[ ] 64. Delete Interface (UI Test 28)     → ui-test-eni removed from table
```

#### Load Balancers
```
[ ] 65. Load Balancers section loads      → any existing LBs listed with VIP
[ ] 66. Create Load Balancer (Test 36)    → ui-test-lb reaches ACTIVE
[ ] 67. Add Listener (UI Test 37)         → listener on port 80 listed in modal
[ ] 68. Add Members (UI Test 38)          → instance registered as backend
[ ] 69. Create Health Monitor (Test 39)   → monitor details shown in Health modal
[ ] 70. Delete Load Balancer (Test 40)    → ui-test-lb removed from table
```

#### Auto Scaling Groups
```
[ ] 71. Auto Scaling section loads        → any existing ASGs listed with counts
[ ] 72. Create ASG (UI Test 41)           → ui-test-asg appears; 2 instances launch
[ ] 73. Manual scale (UI Test 42)         → instance count changes to 3
[ ] 74. Add Scaling Policy (UI Test 43)   → scale-up-policy appears in Policies modal
[ ] 75. Delete ASG (UI Test 44)           → ui-test-asg removed; instances terminated
```

#### Resource Quotas
```
[ ] 76. Quotas section loads              → project cards show progress bars for all resources
[ ] 77. Color coding correct              → green < 70%, amber 70–89%, red ≥ 90%
[ ] 78. Unlimited resources show text     → "Unlimited" label, not a broken bar
```

#### Users & Projects
```
[ ] 79. IAM section loads                 → Users, Groups, Roles, Policies tabs visible
```

#### System Status
```
[ ] 80. libvirtd is active                → sudo systemctl is-active libvirtd → active
[ ] 81. LVM VG is present                 → sudo vgdisplay mini-cloud-vg → shows VG info
```

---

## Section 5 — If You Find a Problem, How to Report It?

When something fails, collect the following information and share it:

### Step 1 — Copy the exact error message

Take a screenshot or copy-paste the full output from the terminal. Include the command you ran AND the output/error.

Example format:
```
Command I ran:
  curl -s -H "Authorization: Bearer " http://localhost:5001/api/v1/compute/instances | python3 -m json.tool

Output I got:
  HTTPConnectionPool: Max retries exceeded
```

### Step 2 — Check the system status

Run these quick checks and copy the output:

```bash
# Check libvirtd and mini-cloud service
sudo systemctl is-active libvirtd
sudo systemctl is-active mini-cloud

# Check your current IP
ip addr show wlp0s20f3 | grep 'inet '

# Check mini-cloud API is responding
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/v1/auth/health
```

- If mini-cloud returns `200` → the API is up
- If it returns `503` or `000` → services are down, run `restart-fix.sh`

### Step 3 — Run the restart script

If services are down, open a terminal and run:

```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh
```

Wait for it to finish, then try the test again.

### Step 4 — Report the problem

Share the following in your report:

| What to include | Example |
|----------------|---------|
| Test number that failed | Test 3 — SSH |
| Command you ran | `ssh -i ... cirros@10.200.195.153` |
| Exact error message | `ssh: connect to host... port 22: Connection refused` |
| Output of GET /api/v1/compute/instances | (paste the JSON) |
| Output of `ip addr show wlp0s20f3` | `inet 10.200.195.97/22` |
| Mini-cloud API HTTP response code | `200` or `503` |

---

## Quick Reference

| Item | Value |
|------|-------|
| Admin username | `admin` |
| Admin password | `Admin1234` |
| API endpoint | `http://10.200.195.97/identity` |
| Main instance floating IP | `10.200.195.153` |
| SSH key location | `/home/khalid/ec2-local-cloud/configs/project-key.pem` |
| SSH username (CirrOS) | `cirros` |
| SSH username (Ubuntu) | `ubuntu` |
| devuser password | `DevUser@123` |
| opsuser password | `OpsUser@123` |
| Restart script | `bash /home/khalid/ec2-local-cloud/restart-fix.sh` |
