# Dashboard Startup Guide
## Mini Cloud System — Dashboard

This guide explains exactly what to run every time you want to show the project, how to test every feature from the UI, and how to verify the system is working accurately.

---

## Quick Reference (TL;DR)

Every time you want to show the dashboard:

```
Step 1 → Run restart-fix.sh         (restores LVM loop, IP forwarding, floating IP rules)
Step 2 → Run python3 run.py         (starts mini-cloud API + dashboard on port 5001)
Step 3 → Open browser at localhost:5001
```

Full commands and testing instructions are in the sections below.

---

## Part 1 — Before Every Session (Required)

These steps must be done every time you turn on the laptop or reconnect to WiFi.
If you skip them, the dashboard will show errors or instances won't be reachable.

### Step 1 — Check your WiFi IP

Your WiFi IP can change every time you reconnect. Verify it first.

```bash
ip addr show wlp0s20f3 | grep 'inet '
```

Example output:
```
inet 10.200.195.97/22 brd 10.200.199.255 scope global dynamic wlp0s20f3
```

The IP is the number before the `/22`. Write it down.

---

### Step 2 — Run the Restart Fix Script

This restores everything that is lost on reboot: LVM loop device, IP forwarding, floating IP iptables rules, and the mc-fip dummy interface.

```bash
cd /home/khalid/ec2-local-cloud
bash restart-fix.sh
```

Wait for it to finish. The last section should show libvirtd as `active` and LVM VG as found.

---

### Step 3 — Verify Mini Cloud API is Responding

```bash
curl -s http://localhost:5001/api/v1/auth/health
```

If you see `{"status": "ok"}`: **mini-cloud is working. Move to Part 2.**
If you see an error: see Part 5 — Troubleshooting.

---

## Part 2 — Start the Dashboard

### Step 4 — Start the Web Dashboard

Open a terminal and run:

```bash
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

You will see:
```
  * Running on http://0.0.0.0:5001
  * Database initialized
```

**Leave this terminal open.** Do not press Ctrl+C — that stops the dashboard.

---

### Step 5 — Open in Browser

Open Firefox or Chrome and go to:
```
http://localhost:5001
```

You should see the **Mini Cloud Dashboard** with a dark header bar, sidebar, and stat cards.

---

## Part 3 — Testing: Create, Update, Delete from the UI

The dashboard lets you create, stop, start, and delete resources directly from the browser. Use these tests to prove the system is fully working.

---

### Test A — Launch a New Instance

**What it proves:** The compute engine (Nova) can create virtual machines on demand.

**Steps:**
1. Click **Instances** in the sidebar
2. Click the orange **Launch Instance** button (top right)
3. Fill in the form:
   - **Name:** `test-vm-01`
   - **Image:** `cirros-0.6.2-x86_64-disk`
   - **Flavor:** `m1.tiny — 1 vCPU · 512MB RAM · 1GB Disk`
   - **Key Pair:** `project-key`
4. Click **Launch**

**What happens immediately:**
- A green toast notification appears: *"Instance created — will be ACTIVE in ~20 seconds"*
- The table automatically refreshes after 5 seconds

**How to verify it worked:**
- After 20–30 seconds, click **Refresh** — the new instance appears with status `ACTIVE`
- The Overview card updates: Instances count increases by 1

**CLI verification (optional — in a second terminal):**
```bash
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; [print(i['name'], i['status']) for i in json.load(sys.stdin)['instances']]"
```

---

### Test B — Stop a Running Instance

**What it proves:** Power management works — instances can be shut down without deleting them.

**Steps:**
1. In the **Instances** section, find `test-vm-01` (status: `ACTIVE`)
2. Click the yellow **Stop** button on that row
3. A toast notification appears: *"test-vm-01 is shutting down"*

**How to verify it worked:**
- Click **Refresh** after 10 seconds — status changes from `ACTIVE` to `SHUTOFF`
- The Stop button disappears and a green **Start** button appears instead

---

### Test C — Start a Stopped Instance

**What it proves:** Instances can be resumed from SHUTOFF state, just like in AWS.

**Steps:**
1. Find `test-vm-01` with status `SHUTOFF`
2. Click the green **Start** button
3. Toast notification: *"test-vm-01 is booting up"*

**How to verify it worked:**
- Click **Refresh** after 15 seconds — status returns to `ACTIVE`

---

### Test D — Delete an Instance

**What it proves:** Resources can be cleaned up — no orphaned VMs left running.

**Steps:**
1. Find `test-vm-01`
2. Click the red **Delete** button
3. A confirmation dialog appears: *"Delete instance test-vm-01? This cannot be undone."*
4. Click **Delete** to confirm

**How to verify it worked:**
- The instance disappears from the table within seconds
- Overview card: Instances count decreases by 1

**CLI verification:**
```bash
# VM's libvirt domain should be gone
sudo virsh list --all | grep test-vm-01 || echo "confirmed: not found"
```

---

### Test E — Create a Volume (Block Storage)

**What it proves:** Block storage (EBS equivalent) can be provisioned on demand.

**Steps:**
1. Click **Volumes** in the sidebar
2. Click the orange **Create Volume** button
3. Fill in the form:
   - **Name:** `test-disk-01`
   - **Size:** `2` (GB)
4. Click **Create**

**What happens:**
- Toast: *"Creating volume — test-disk-01 (2 GB)"*
- Table refreshes after 3 seconds

**How to verify it worked:**
- `test-disk-01` appears with status `available` and size `2 GB`
- Overview card: Volumes count increases by 1

**CLI verification:**
```bash
sudo lvdisplay mini-cloud-vg | grep "LV Name"
# test-disk-01's LVM LV should appear in the list
```

---

### Test F — Delete a Volume

**What it proves:** Storage can be released cleanly (only when not in use).

**Steps:**
1. Find `test-disk-01` with status `available`
2. Click **Delete** on that row
3. Confirm in the dialog

**Note:** Volumes that are attached to an instance show `in-use` and the Delete button is disabled — this prevents accidental data loss, exactly like AWS.

**How to verify it worked:**
- `test-disk-01` disappears from the table
- Overview card: Volumes count decreases by 1

---

### Test G — Allocate a Floating IP

**What it proves:** Public IPs can be provisioned from the external network pool.

**Steps:**
1. Click **Floating IPs** in the sidebar
2. Click the orange **Allocate IP** button
3. Toast: *"Requesting a new floating IP from the public pool"*

**How to verify it worked:**
- A new row appears with a new IP address (e.g. `10.200.195.xxx`) and status `DOWN`
- The IP pool count increases in the header

---

### Test H — Release a Floating IP

**What it proves:** Unused IPs can be returned to the pool cleanly.

**Steps:**
1. Find the newly allocated IP that shows `Not attached` in the Fixed IP column
2. Click the red **Release** button on that row
3. Confirm in the dialog

**How to verify it worked:**
- The IP row disappears from the table
- **Note:** Floating IPs that are attached to an instance show `in use` — the Release button is disabled until you detach the IP first.

---

### Test I — Monitoring: Resource Utilization and Instance Metrics

**What it proves:** The dashboard can report live compute resource usage — reading `/proc/stat`, `/proc/meminfo`, and libvirt stats directly (no separate monitoring daemon).

**Steps:**
1. Click **Monitoring** in the sidebar (under the Monitoring group)
2. The **Hypervisor Resource Utilization** panel loads automatically showing three bars:
   - **vCPU** — cores used vs. total
   - **RAM** — GB used vs. total
   - **Disk** — GB used vs. total

**What to look for:**
- Bars turn **orange** above 60% utilization and **red** above 80%
- Current machine has 8 vCPUs and ~7.5 GB RAM — with no VMs running, bars will show near-zero

**Instance Metrics table:**
- Launch an instance (ACTIVE) and return to Monitoring → click Refresh
- The table shows for each ACTIVE instance: CPU time (nanoseconds of CPU consumed), memory allocated, total disk read/write bytes, and total network RX/TX bytes

**CLI verification:**
```bash
# Check the backend directly
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/monitoring/host | python3 -m json.tool
# Expected: cpu_percent, ram_total_mb, ram_used_mb, etc.
```

**Note:** All values are cumulative counters from boot — not rates. Disk read `5.2 MB` means the VM has read 5.2 MB total since it started, not per second.

---

### Test J — IAM: Create a User and Attach a Policy

**What it proves:** The dashboard has a full AWS-style IAM layer — users, groups, roles, and JSON permission policies.

**Steps:**
1. Click **IAM** in the sidebar (under Identity)
2. The **Users** sub-tab is active by default — click **Create User**
3. Enter username `alice` and click **Create User**
4. The new user appears in the table with an ARN `arn:aws:iam::123456789012:user/alice`
5. Click **Attach Policy** on Alice's row
6. In the searchable policy list, find `AmazonEC2ReadOnlyAccess` and click **Attach**
7. Close the modal — Alice's row now shows the attached policy badge

**How to verify it worked:**
- Alice's row shows `AmazonEC2ReadOnlyAccess` in the Direct Policies column
- Click **Attach Policy** again — Alice's policy shows a **Detach** button; other policies show **Attach**

---

### Test K — IAM: Create a Group and Add a Member

**Steps:**
1. In the IAM section, click the **Groups** tab
2. Click **Create Group**, enter name `Developers`, click **Create Group**
3. Click **Members** on the Developers row
4. In the "Add User" dropdown, select `alice` and click **Add to Group**
5. Alice appears in the "Current Members" list

**How to verify it worked:**
- Close the modal — the Developers row shows "1 (alice)" in the Members column
- Go back to the **Users** tab — Alice's row now shows the `Developers` group badge

---

### Test L — IAM: Create a Role

**Steps:**
1. Click the **Roles** tab in IAM
2. Click **Create Role**
3. Fill in:
   - **Name:** `EC2ServiceRole`
   - **Description:** `Allows EC2 to read S3 on behalf of this service`
   - **Trusted Service:** `EC2 — ec2.amazonaws.com`
4. Click **Create Role**

**How to verify it worked:**
- `EC2ServiceRole` appears in the table with ARN `arn:aws:iam::123456789012:role/EC2ServiceRole`
- Trusted Service column shows `ec2.amazonaws.com`

---

### Test M — IAM: Create a Custom Policy

**Steps:**
1. Click the **Policies** tab in IAM
2. Click **Create Policy**
3. Fill in:
   - **Name:** `EC2StartStopOnly`
   - **Description:** `Allows starting and stopping instances only`
   - **Policy Document:**
     ```json
     {
       "Version": "2012-10-17",
       "Statement": [
         {
           "Sid": "AllowStartStop",
           "Effect": "Allow",
           "Action": ["ec2:StartInstances", "ec2:StopInstances"],
           "Resource": "*"
         }
       ]
     }
     ```
4. Click **Create Policy**

**How to verify it worked:**
- `EC2StartStopOnly` appears in the table with an amber **Customer** badge
- Click **View JSON** — the formatted policy document is displayed in a modal
- The 7 pre-seeded AWS policies show a blue **AWS Managed** badge and have no Delete button

---

## Part 4 — What to Show Your Teacher

Click through each sidebar section and explain:

| Section | What to say |
|---------|------------|
| **Overview** | "This is the summary — VMs, images, volumes, users, projects. The Resource Utilization panel shows vCPU, RAM, and disk usage from the hypervisor in real time." |
| **Monitoring** | "This is my CloudWatch equivalent — reads /proc/stat, /proc/meminfo, and libvirt stats directly. Shows hypervisor utilization bars and per-instance CPU time, memory, disk I/O, and network bytes." |
| **Instances** | "These are the virtual machines — running under KVM via libvirt. I can launch, stop, start, and delete them from here. Same as EC2 on AWS." |
| **Images** | "These are OS templates stored as qcow2 files. Same as AMI on AWS." |
| **Volumes** | "Extra storage backed by LVM logical volumes. I can attach and detach them from VMs without rebooting. Same as EBS on AWS." |
| **Networks** | "The virtual network layer — Linux Bridge acts as the switch, dnsmasq provides DHCP. Equivalent to a VPC subnet." |
| **Floating IPs** | "Public IPs from our pool — implemented with iptables DNAT/SNAT. Same as Elastic IP on AWS." |
| **Security Groups** | "Per-VM firewall rules implemented as dedicated iptables chains (MC-SG-<vm-id>). ssh-only allows port 22 and ICMP." |
| **IAM** | "Full AWS IAM replica — users, groups, roles, and JSON permission policies. The 7 pre-seeded policies mirror real AWS managed policies. Custom policies use the same Allow/Deny/Action/Resource syntax." |

### Live proof — SSH into a running VM

Open a second terminal while the dashboard is visible:

```bash
ssh -i ~/.ssh/demo-key.pem \
    -o StrictHostKeyChecking=no \
    cirros@<floating-ip>
```

Type `uname -a` inside the VM, then `exit`. This proves the VM is real and accessible.

---

## Part 5 — Troubleshooting

### Problem: Instances section shows an error

**Fix:**
```bash
sudo systemctl restart libvirtd
sleep 3
```
Then click **Refresh** in the dashboard.

---

### Problem: Mini Cloud API not responding

**Fix:** Run the startup script, then restart mini-cloud:
```bash
cd /home/khalid/ec2-local-cloud
bash restart-fix.sh

cd mini-cloud
source venv/bin/activate
python3 run.py
```

---

### Problem: Dashboard won't open in browser

**Fix:** Check if the `python3 run.py` terminal is still open. If not, restart it:
```bash
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

---

### Problem: Launch Instance says "Launch failed"

**Likely cause:** libvirtd lost connection or LVM VG is not active. Fix:
```bash
sudo systemctl restart libvirtd
sudo vgchange -ay mini-cloud-vg
```
Then try launching again.

---

### Problem: Ping floating IP fails

**Fix:**
```bash
bash /home/khalid/ec2-local-cloud/restart-fix.sh
# Verify mc-fip has the IP
ip addr show mc-fip
```

---

### Problem: libvirtd shows `failed` or `inactive`

```bash
sudo systemctl start libvirtd
sudo systemctl status libvirtd
sudo journalctl -u libvirtd -n 30
```

---

## Part 6 — Pre-Presentation Checklist

Run this 5 minutes before you present:

```bash
# 1. Check libvirtd is running
sudo systemctl is-active libvirtd

# 2. Check LVM VG is active
sudo vgdisplay mini-cloud-vg | grep "VG Name"

# 3. Check IP forwarding
cat /proc/sys/net/ipv4/ip_forward
# Expected: 1

# 4. Dashboard health check
curl -s http://localhost:5001/api/v1/auth/health
# Expected: {"status": "ok"}

# 5. Get auth token and list instances
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/compute/instances \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK —', d.get('count',0), 'instances')"

# 6. Check monitoring API
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:5001/api/v1/monitoring/host \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK — CPU:', d.get('cpu_percent'), '%')"
```

If all pass — you are ready to present.

---

## Part 7 — Full Startup Commands (Copy-Paste Ready)

### Terminal 1 — Fix and verify

```bash
cd /home/khalid/ec2-local-cloud
bash restart-fix.sh

# Check running VMs
sudo virsh list --all

# Verify floating IPs are restored
ip addr show mc-fip
```

### Terminal 2 — Run the dashboard (keep this terminal open)

```bash
cd /home/khalid/ec2-local-cloud/mini-cloud
source venv/bin/activate
python3 run.py
```

**Browser:** `http://localhost:5001`

---

## Summary Table

| Task | Command / Location |
|------|--------------------|
| Fix after reboot | `bash restart-fix.sh` |
| Start the dashboard | `cd mini-cloud && source venv/bin/activate && python3 run.py` |
| Open in browser | `http://localhost:5001` |
| Launch a VM | Instances → Launch Instance button |
| Stop a VM | Instances → Stop button on that row |
| Start a VM | Instances → Start button on that row |
| Delete a VM | Instances → Delete button → confirm |
| Create a volume | Volumes → Create Volume button |
| Delete a volume | Volumes → Delete button (only if not attached) |
| Allocate a floating IP | Floating IPs → Allocate IP button |
| Release a floating IP | Floating IPs → Release button (only if unattached) |
| View resource utilization | Monitoring → Hypervisor Resource Utilization panel |
| View instance metrics | Monitoring → Instance Metrics table (running instances only) |
| Check metrics API | `curl -s -H "Authorization: Bearer $TOKEN" http://localhost:5001/api/v1/monitoring/host` |
| Create an IAM user | IAM → Users tab → Create User |
| Create an IAM group | IAM → Groups tab → Create Group |
| Add user to group | IAM → Groups tab → Members button |
| Create an IAM role | IAM → Roles tab → Create Role |
| Create a custom policy | IAM → Policies tab → Create Policy |
| Attach policy to user/group/role | IAM → Attach Policy button on any row |
| View a policy's JSON document | IAM → Policies tab → View JSON |
| Restart libvirtd | `sudo systemctl restart libvirtd` |
| Check all KVM VMs | `sudo virsh list --all` |
| SSH into demo VM | `ssh -i ~/.ssh/demo-key.pem cirros@<floating-ip>` |
