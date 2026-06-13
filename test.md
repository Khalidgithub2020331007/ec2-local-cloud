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
