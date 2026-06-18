# Test Guide — Local EC2 Replica (OpenStack)

---

## Section 1 — What is EC2?

**EC2** stands for **Elastic Compute Cloud**. It is a service made by Amazon (AWS) that lets you rent virtual computers (called **instances**) over the internet.

Think of it like this:

- You have a laptop. EC2 gives you a **virtual laptop** that lives on a server somewhere.
- You can turn it ON, turn it OFF, connect to it, install software, and delete it when you are done.
- You only pay for the time it is running.

**Key idea:** You do not buy a physical computer. You get a virtual one that behaves exactly like a real computer.

This project is a **local copy** of EC2 running on your own machine using a tool called **OpenStack**. It works the same way as real AWS EC2, but it runs on your laptop instead of Amazon's servers.

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

When you launch an instance, you pick how powerful it is. These size options are called **instance types** in AWS and **flavors** in OpenStack.

**AWS naming pattern:** `t3.micro`, `m5.large`, `c6i.xlarge`
- The letter(s) = family (t = general, m = memory, c = compute)
- The number = generation (newer = better)
- The word = size (nano < micro < small < medium < large < xlarge)

**Common instance types and what they mean:**

| AWS Type | OpenStack Flavor | vCPU | RAM | Disk | Use Case |
|----------|-----------------|------|-----|------|----------|
| t2.nano | m1.nano | 1 | 64 MB | 1 GB | Test and dev only |
| t2.micro | m1.tiny | 1 | 512 MB | 1 GB | Very small apps, free tier |
| t2.small | m1.small | 1 | 2 GB | 20 GB | Light web apps |
| t2.medium | m1.medium | 2 | 4 GB | 40 GB | Medium web servers |
| t2.large | m1.large | 4 | 8 GB | 80 GB | Databases, busier apps |

**Rule:** Pick the smallest size that meets your needs. You can always resize later.

---

### 4. Key Pairs — Secure SSH Login

A **key pair** is a pair of cryptographic keys used to log into instances securely instead of using a password.

- **Private key (.pem file)** — lives on your machine, never share it
- **Public key** — uploaded to AWS/OpenStack; installed on every instance at launch

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

**In this local system (OpenStack):**
- `private-network` = your VPC/private subnet
- `public` = the external network pool (where floating IPs come from)
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

> This local OpenStack system does not simulate Auto Scaling, but knowing the concept is important for working with real AWS EC2.

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

> This local OpenStack system has basic load balancing support via Octavia, but it is not configured in these tests.

---

### 12. IAM — Identity and Access Management (Users & Projects)

**IAM** controls who can do what inside your AWS account. In OpenStack, this is handled by **Users**, **Projects (Tenants)**, and **Roles**.

**Core concepts:**

| Concept | AWS Name | OpenStack Name | What It Is |
|---------|----------|----------------|-----------|
| Account | AWS Account | Project / Tenant | A container that owns resources |
| Person | IAM User | User | A human with login credentials |
| Permission set | IAM Policy | Role | A list of allowed actions |
| Assumed identity | IAM Role | Role assignment | Temporary permission to act as something |

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

Open a terminal and run this command to load credentials:

```bash
source /opt/stack/devstack/openrc admin admin
```

You should see no error. This loads your admin password so the system knows who you are.

Verify it works:

```bash
openstack token issue
```

If you see a table with a token ID, you are connected. If you see an error, stop and report it (see Section 5).

---

### Test 1 — View Running Instances

**What this tests:** Can the system list virtual computers?

```bash
openstack server list --all-projects
```

**Expected result:** A table showing instances. You should see:

| Name | Status | Networks |
|------|--------|----------|
| demo-instance-01 | ACTIVE | private-network=... |
| dev-vm-01 | ACTIVE | private-network=... |

**Pass:** Both instances show `ACTIVE`.
**Fail:** You see `ERROR` status, empty list, or a connection error.

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
# Stop it (like shutting down a computer)
openstack server stop demo-instance-01

# Wait 10 seconds, then check the status
openstack server show demo-instance-01 -f value -c status
```

**Expected result:** `SHUTOFF`

```bash
# Start it again
openstack server start demo-instance-01

# Wait 15 seconds, then check again
openstack server show demo-instance-01 -f value -c status
```

**Expected result:** `ACTIVE`

**Pass:** Status goes from `ACTIVE` → `SHUTOFF` → `ACTIVE`.
**Fail:** Status stays stuck, shows `ERROR`, or never comes back to `ACTIVE`.

---

### Test 5 — Launch a Brand New Instance

**What this tests:** Can you create a new virtual computer from scratch?

```bash
openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  my-test-vm
```

Wait 20–30 seconds, then check:

```bash
openstack server show my-test-vm -f value -c status
```

**Expected result:** `ACTIVE`

Clean up after the test:

```bash
openstack server delete my-test-vm
```

**Pass:** Instance reaches `ACTIVE` within 30 seconds.
**Fail:** Status is `ERROR`, `BUILD` for more than 2 minutes, or command fails.

---

### Test 6 — Assign a Floating IP

**What this tests:** Can you give a virtual computer a public IP address?

```bash
# Create a new floating IP
openstack floating ip create public

# Note the IP address printed. Then attach it to the test VM if you still have one:
openstack server add floating ip my-test-vm <THE-IP-SHOWN>

# Verify it was attached
openstack floating ip list
```

**Expected result:** Table shows the floating IP linked to the instance's private IP.

**Pass:** Floating IP appears in the list and is linked to an instance.
**Fail:** Error message, or floating IP shows "None" for fixed IP address.

---

### Test 7 — Create and Attach a Volume (Storage)

**What this tests:** Can you add extra storage to a virtual computer?

```bash
# Create a 1GB volume
openstack volume create --size 1 test-volume

# Check it is ready
openstack volume show test-volume -f value -c status
```

**Expected result:** `available`

```bash
# Attach to an instance
openstack server add volume demo-instance-01 test-volume

# Check it is attached
openstack volume show test-volume -f value -c status
```

**Expected result:** `in-use`

Clean up:

```bash
openstack server remove volume demo-instance-01 test-volume
openstack volume delete test-volume
```

**Pass:** Volume goes `available` → `in-use` → `available` after detach.
**Fail:** Status shows `error`, or attach command fails.

---

### Test 8 — Check Security Groups (Firewall)

**What this tests:** Does the firewall correctly block and allow connections?

```bash
# View existing security groups
openstack security group list

# View rules for ssh-only group
openstack security group rule list ssh-only
```

**Expected result:** You see rules for:
- TCP port 22 (SSH)
- ICMP (ping)

**Pass:** Rules appear as expected.
**Fail:** No rules found, or unexpected rules (e.g., port 80 open when it should not be).

---

### Test 9 — Check Available Images

**What this tests:** Are the operating system templates available?

```bash
openstack image list
```

**Expected result:** Table includes at least:
- `cirros-0.6.2-x86_64-disk` — status `active`
- `Ubuntu-22.04-LTS` — status `active`

**Pass:** Both images are listed and `active`.
**Fail:** Empty list, images show `killed` or `queued`.

---

### Test 10 — Multi-Project Isolation

**What this tests:** Can different users only see their own resources?

```bash
# Switch to devuser (developer account)
source /opt/stack/devstack/openrc devuser DevUser@123

# devuser should only see their own instances
openstack server list
```

**Expected result:** `dev-vm-01` appears. `demo-instance-01` does NOT appear.

```bash
# Switch to opsuser (operations account)
source /opt/stack/devstack/openrc opsuser OpsUser@123

# opsuser should see nothing (empty list)
openstack server list
```

**Expected result:** Empty table — `No servers found.`

Go back to admin when done:

```bash
source /opt/stack/devstack/openrc admin admin
```

**Pass:** Each user only sees what belongs to them.
**Fail:** Users can see each other's instances.

---

## Section 3B — UI Tests: Create, Update, Delete from the Dashboard

Open the dashboard at `http://localhost:8080` before running these tests.
If the dashboard is not running, start it first:

```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
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
source /opt/stack/devstack/openrc admin admin
openstack server show ui-test-vm -f value -c status
```
Expected: `ACTIVE`

**Pass:** Instance appears in table with `ACTIVE` status within 30 seconds.
**Fail:** Error notification appears, or instance stays in `BUILD` for more than 2 minutes.

---

### UI Test 2 — Stop an Instance from the Browser

**What this tests:** Can you shut down a running VM from the UI?

**Steps:**
1. Find `ui-test-vm` in the Instances table (status: `ACTIVE`)
2. Click the yellow **Stop** button on that row

**Expected result:**
- A toast notification appears: *"ui-test-vm is shutting down"*
- Click **Refresh** after 10 seconds — status changes to `SHUTOFF`
- The Stop button disappears; a green **Start** button appears in its place

**Verify from CLI:**
```bash
openstack server show ui-test-vm -f value -c status
```
Expected: `SHUTOFF`

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
openstack server list --all-projects
```
Expected: `ui-test-vm` does NOT appear.

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
openstack volume show ui-test-disk -f value -c status
```
Expected: `available`

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
openstack image list
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
openstack image list
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
openstack image list
```
Expected: `cirros-copy-test` does NOT appear.

**Pass:** Image is removed from the table.
**Fail:** Error toast appears, or image remains in the list.

---

## Section 4 — What Exactly Should You Test?

Here is a complete checklist. Go through each item and write **PASS** or **FAIL** next to it.

### CLI Tests (run in terminal)

```
[ ] 1.  openstack token issue           → Shows a token (not an error)
[ ] 2.  openstack server list           → Shows ACTIVE instances
[ ] 3.  Ping 10.200.195.153             → 0% packet loss
[ ] 4.  SSH into demo-instance-01       → Shell prompt appears
[ ] 5.  Stop demo-instance-01           → Status becomes SHUTOFF
[ ] 6.  Start demo-instance-01          → Status returns to ACTIVE
[ ] 7.  Launch a new instance (CLI)     → Reaches ACTIVE in < 30 seconds
[ ] 8.  Create and attach a volume      → Status goes available → in-use
[ ] 9.  Assign a floating IP            → IP is linked in the list
[ ] 10. openstack image list            → CirrOS and Ubuntu images active
[ ] 11. Security group rules visible    → Port 22 and ICMP rules exist
[ ] 12. devuser sees only dev-vm-01     → No cross-project visibility
[ ] 13. opsuser sees empty list         → Isolation working
```

### UI Tests (run from browser at localhost:8080)

```
[ ] 14. Dashboard loads                 → Overview cards show correct counts
[ ] 15. Launch Instance button          → ui-test-vm reaches ACTIVE in < 30 seconds
[ ] 16. Stop button                     → ui-test-vm status changes to SHUTOFF
[ ] 17. Start button                    → ui-test-vm status returns to ACTIVE
[ ] 18. Delete button                   → ui-test-vm disappears from the table
[ ] 19. Create Volume button            → ui-test-disk appears with status available
[ ] 20. Delete Volume button            → ui-test-disk disappears from the table
[ ] 21. Allocate IP button              → New floating IP appears in the list
[ ] 22. Release IP button               → Unattached IP is removed from the list
[ ] 23. Images section                  → 4 images listed (CirrOS, Ubuntu, 2 snapshots)
[ ] 24. Security Groups section         → ssh-only shows TCP 22 and ICMP rules
[ ] 25. Users & Projects section        → devuser shows dev-project, opsuser shows prod-project
[ ] 26. Networks section                → 3 networks visible (private, public, lb-mgmt)
[ ] 27. Create AMI button (Instances)   → snapshot modal opens; image appears in Images within 5 min
[ ] 28. Launch from AMI (Images)        → launch modal opens with image pre-selected
[ ] 29. Copy AMI button (Images)        → copy modal; cirros-copy-test appears active within 30s
[ ] 30. Delete AMI button (Images)      → cirros-copy-test removed from Images table
```

---

## Section 5 — If You Find a Problem, How to Report It?

When something fails, collect the following information and share it:

### Step 1 — Copy the exact error message

Take a screenshot or copy-paste the full output from the terminal. Include the command you ran AND the output/error.

Example format:
```
Command I ran:
  openstack server list

Output I got:
  HTTPConnectionPool: Max retries exceeded
```

### Step 2 — Check the system status

Run these quick checks and copy the output:

```bash
# Check if all services are running
sudo systemctl list-units 'devstack@*' --all --no-pager | grep -v running

# Check your current IP
ip addr show wlp0s20f3 | grep 'inet '

# Check Keystone is responding
curl -s -o /dev/null -w "%{http_code}" http://10.200.195.97/identity/v3/
```

- If Keystone returns `200` → the API is up
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
| Output of `openstack server list` | (paste the table) |
| Output of `ip addr show wlp0s20f3` | `inet 10.200.195.97/22` |
| Keystone HTTP response code | `200` or `503` |

---

## Quick Reference

| Item | Value |
|------|-------|
| Admin username | `admin` |
| Admin password | `Admin1234OpenStack` |
| API endpoint | `http://10.200.195.97/identity` |
| Main instance floating IP | `10.200.195.153` |
| SSH key location | `/home/khalid/ec2-local-cloud/configs/project-key.pem` |
| SSH username (CirrOS) | `cirros` |
| SSH username (Ubuntu) | `ubuntu` |
| devuser password | `DevUser@123` |
| opsuser password | `OpsUser@123` |
| Restart script | `bash /home/khalid/ec2-local-cloud/restart-fix.sh` |
