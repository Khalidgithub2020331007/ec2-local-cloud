# Dashboard Startup Guide
## Local EC2 Replica — OpenStack Dashboard

This guide explains exactly what to run every time you want to show the project, how to test every feature from the UI, and how to verify the system is working accurately.

---

## Quick Reference (TL;DR)

Every time you want to show the dashboard:

```
Step 1 → Run restart-fix.sh         (fixes network + services after reboot)
Step 2 → Run python3 app.py         (starts the web dashboard)
Step 3 → Open browser at localhost:8080
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

This fixes everything that breaks after a reboot: HOST_IP drift, OVN networking, floating IP routing, and stuck Nova workers.

```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh
```

Wait for it to finish. The last section should show all services as `running`.

---

### Step 3 — Verify OpenStack is Responding

```bash
source /opt/stack/devstack/openrc admin admin
openstack token issue
```

If you see a table with a token ID: **OpenStack is working. Move to Part 2.**
If you see an error: see Part 5 — Troubleshooting.

---

## Part 2 — Start the Dashboard

### Step 4 — Start the Web Dashboard

Open a terminal and run:

```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

You will see:
```
  Dashboard  →  http://localhost:8080
  Network    →  http://10.200.195.97:8080
  OpenStack  →  http://10.200.195.97/identity
```

**Leave this terminal open.** Do not press Ctrl+C — that stops the dashboard.

---

### Step 5 — Open in Browser

Open Firefox or Chrome and go to:
```
http://localhost:8080
```

You should see the **OpenStack EC2 Dashboard** with a dark header bar, sidebar, and stat cards.

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
source /opt/stack/devstack/openrc admin admin
openstack server show test-vm-01 -f value -c status
# Expected: ACTIVE
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
openstack server list --all-projects
# test-vm-01 should NOT appear
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
openstack volume show test-disk-01 -f value -c status
# Expected: available
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

## Part 4 — What to Show Your Teacher

Click through each sidebar section and explain:

| Section | What to say |
|---------|------------|
| **Overview** | "This is the summary — 2 VMs, 4 images, 1 volume, users, and projects. All resources at a glance." |
| **Instances** | "These are the virtual machines. I can launch, stop, start, and delete them from here. Same as EC2 on AWS." |
| **Images** | "These are OS templates — CirrOS (tiny test OS), Ubuntu 22.04, and two snapshots I made. Same as AMI on AWS." |
| **Volumes** | "Extra storage I can attach to any VM. Same as EBS on AWS. I can create and delete volumes from here." |
| **Networks** | "The virtual network layer — private-network is the VPC where VMs communicate, public is where floating IPs come from." |
| **Floating IPs** | "Public IPs I can assign to VMs — same as Elastic IP on AWS. I can allocate and release them from here." |
| **Security Groups** | "Firewall rules — ssh-only allows port 22 and ICMP. web-server also allows port 80." |
| **Users & Projects** | "Multi-tenant isolation — devuser only sees dev-project, opsuser only sees prod-project. Same as IAM on AWS." |

### Live proof — SSH into a running VM

Open a second terminal while the dashboard is visible:

```bash
ssh -i /home/khalid/ec2-local-cloud/configs/project-key.pem \
    -o StrictHostKeyChecking=no \
    cirros@10.200.195.153
```

Type `uname -a` inside the VM, then `exit`. This proves the VM is real and accessible.

---

## Part 5 — Troubleshooting

### Problem: Instances section shows an error

**Fix:**
```bash
echo "2923" | sudo -S systemctl restart devstack@n-api
sleep 4
```
Then click **Refresh** in the dashboard.

---

### Problem: `openstack token issue` shows connection error

**Fix:** Run the full restart script:
```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh
```

---

### Problem: Dashboard won't open in browser

**Fix:** Check if `python3 app.py` terminal is still open. If not, restart it:
```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

---

### Problem: Launch Instance says "Launch failed"

**Likely cause:** Nova API hit a transient error. Fix:
```bash
echo "2923" | sudo -S systemctl restart devstack@n-api
sleep 4
```
Then try launching again.

---

### Problem: Ping `10.200.195.153` fails

**Fix:**
```bash
echo "2923" | sudo -S bash /home/khalid/ec2-local-cloud/restart-fix.sh
```

---

### Problem: A service shows `failed` or `inactive`

```bash
# Check what's broken
systemctl list-units 'devstack@*' --no-pager --all | grep -v running

# Restart the specific service
echo "2923" | sudo -S systemctl restart devstack@SERVICE-NAME
```

---

## Part 6 — Pre-Presentation Checklist

Run this 5 minutes before you present:

```bash
# 1. Load credentials
source /opt/stack/devstack/openrc admin admin

# 2. Check all services running (output should be empty)
systemctl list-units 'devstack@*' --no-pager --all | grep -v running | grep -v Legend

# 3. Check instances are ACTIVE
openstack server list --all-projects

# 4. Ping the floating IP
ping -c 3 10.200.195.153

# 5. Dashboard is up
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/
# Expected: 200

# 6. Test Nova API is responding
curl -s http://localhost:8080/api/overview | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK —', d.get('instances',{}).get('total'), 'instances')"
```

If all 6 pass — you are ready to present.

---

## Part 7 — Full Startup Commands (Copy-Paste Ready)

### Terminal 1 — Fix services and verify

```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh

source /opt/stack/devstack/openrc admin admin
openstack server list --all-projects
ping -c 3 10.200.195.153
```

### Terminal 2 — Run the dashboard (keep this terminal open)

```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

**Browser:** `http://localhost:8080`

---

## Summary Table

| Task | Command / Location |
|------|--------------------|
| Fix services after reboot | `echo "2923" \| sudo -S bash restart-fix.sh` |
| Start the dashboard | `cd dashboard && python3 app.py` |
| Open in browser | `http://localhost:8080` |
| Launch a VM | Instances → Launch Instance button |
| Stop a VM | Instances → Stop button on that row |
| Start a VM | Instances → Start button on that row |
| Delete a VM | Instances → Delete button → confirm |
| Create a volume | Volumes → Create Volume button |
| Delete a volume | Volumes → Delete button (only if not attached) |
| Allocate a floating IP | Floating IPs → Allocate IP button |
| Release a floating IP | Floating IPs → Release button (only if unattached) |
| Fix stuck Nova workers | `echo "2923" \| sudo -S systemctl restart devstack@n-api` |
| Check all services | `systemctl list-units 'devstack@*' --all \| grep -v running` |
| SSH into demo VM | `ssh -i configs/project-key.pem cirros@10.200.195.153` |
