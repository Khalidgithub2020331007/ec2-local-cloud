# Dashboard Startup Guide
## Local EC2 Replica — OpenStack Dashboard

This guide explains exactly what to run every time you want to show the project dashboard, how to verify everything is working, and how to fix common problems.

---

## Quick Reference (TL;DR)

Every time you want to show the dashboard:

```
Step 1 → Run restart-fix.sh         (fixes network + services after reboot)
Step 2 → Run python3 app.py         (starts the web dashboard)
Step 3 → Open browser at localhost:8080
```

Full commands are in the sections below.

---

## Part 1 — Before Every Session (Required)

These steps must be done every time you turn on the laptop or reconnect to WiFi.
If you skip them, the dashboard will show errors or instances won't be reachable.

### Step 1 — Check your WiFi IP

Your WiFi IP can change every time you reconnect. You must verify it first.

```bash
ip addr show wlp0s20f3 | grep 'inet '
```

Example output:
```
inet 10.200.195.97/22 brd 10.200.199.255 scope global dynamic wlp0s20f3
```

The IP is the number before the `/22` — in this example: `10.200.195.97`

Write it down. You will need it to check Keystone in Step 3.

---

### Step 2 — Run the Restart Fix Script

This script fixes all the things that break after a reboot:
- Updates HOST_IP if your WiFi IP changed
- Restarts OVN networking
- Fixes floating IP routing
- Restarts Nova API and other services that get stuck

```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh
```

Wait for it to finish. The last lines should look like:

```
=== DevStack services ===
devstack@c-api.service     running
devstack@c-sch.service     running
devstack@c-vol.service     running
devstack@g-api.service     running
devstack@keystone.service  running
devstack@n-api.service     running
devstack@n-cond-cell1.service running
devstack@n-cpu.service     running
devstack@n-sch.service     running
devstack@n-super-cond.service running
devstack@placement-api.service running
devstack@q-meta.service    running
devstack@q-ovn-metadata-agent.service running
devstack@q-svc.service     running
```

All services must say `running`. If any say `failed` or `inactive`, see Part 4.

---

### Step 3 — Verify OpenStack is Responding

Run this to confirm the API is alive:

```bash
source /opt/stack/devstack/openrc admin admin
openstack token issue
```

Expected output — a table with a token ID:
```
+------------+----------------------------------------------------------+
| Field      | Value                                                    |
+------------+----------------------------------------------------------+
| expires    | 2026-06-14T...                                           |
| id         | gAAAAABq...                                              |
| project_id | 79b51eb5...                                              |
| user_id    | ...                                                      |
+------------+----------------------------------------------------------+
```

If you see a table: **OpenStack is working. Move to Part 2.**

If you see an error: see Part 4 — Troubleshooting.

---

## Part 2 — Start the Dashboard

### Step 4 — Start the Web Dashboard

Open a terminal and run:

```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

You will see this output:

```
  Dashboard  →  http://localhost:8080
  Network    →  http://10.200.195.97:8080
  OpenStack  →  http://10.200.195.97/identity
```

**Leave this terminal open.** The dashboard runs as long as this terminal is open.
Do not press Ctrl+C — that will stop the dashboard.

---

### Step 5 — Open the Dashboard in Browser

Open Firefox or Chrome and go to:

```
http://localhost:8080
```

You should see the **OpenStack EC2 Dashboard** with:
- A dark header bar showing `HOST: 10.200.195.97`
- A sidebar on the left with sections: Overview, Instances, Images, Volumes, etc.
- Cards showing counts: 2 Instances, 4 Images, 1 Volume, etc.

If the browser shows an error or blank page: see Part 4.

---

## Part 3 — What to Show Your Teacher

Once the dashboard is open, here is what to click through and explain.

### Overview (loads automatically)

Shows a summary of all resources:

| Card | What it means | AWS equivalent |
|------|--------------|----------------|
| Instances: 2 | 2 virtual computers running | EC2 Instances |
| Images: 4 | OS templates to boot from | AMI (Amazon Machine Image) |
| Volumes: 1 | Extra storage disk | EBS (Elastic Block Store) |
| Floating IPs: 1 | Public IP attached to a VM | Elastic IP |
| Users: 16 | Accounts in the system | IAM Users |
| Projects: 7 | Separate isolated environments | AWS Accounts |

Below the cards you will see a table of running instances.

---

### Instances (click in sidebar)

Shows both virtual machines:

| Name | Status | Private IP | Floating IP | Flavor | Project |
|------|--------|-----------|-------------|--------|---------|
| demo-instance-01 | ACTIVE | 192.168.100.40 | 10.200.195.153 | m1.tiny | admin |
| dev-vm-01 | ACTIVE | 192.168.100.139 | — | m1.tiny | dev-project |

**What to say:** "These are virtual machines running on this laptop, just like EC2 instances on AWS. They each have a private IP on an internal network, and one has a floating IP — that's the public IP, same as an Elastic IP on AWS."

---

### Images (click in sidebar)

Shows the OS templates available. You should see:
- `cirros-0.6.2-x86_64-disk` — the small test OS used for most VMs
- `Ubuntu-22.04-LTS` — the full Ubuntu image
- `demo-instance-snapshot` — a snapshot we created from a running VM
- `web-server-snapshot` — snapshot of the web server VM

**What to say:** "These are like AMIs on AWS — pre-built OS templates. We have CirrOS (a tiny test OS), Ubuntu 22.04, and two snapshots we made from running instances."

---

### Volumes (click in sidebar)

Shows block storage volumes (like extra hard drives for VMs).

**What to say:** "Volumes are like EBS on AWS — extra storage you can attach to a VM, detach, and move to another VM."

---

### Networks (click in sidebar)

Shows 3 networks:
- `private-network` — internal network (like a VPC) where VMs communicate
- `public` — external network where floating IPs come from
- `lb-mgmt-net` — management network (created by DevStack automatically)

**What to say:** "This is the virtual networking layer — equivalent to VPC on AWS. VMs are on the private network and reach the internet through the public network via floating IPs."

---

### Floating IPs (click in sidebar)

Shows `10.200.195.153` attached to `demo-instance-01`.

**What to say:** "This floating IP works exactly like an Elastic IP on AWS — a public address you assign to a specific instance. You can reassign it to a different instance without changing the instance's private IP."

---

### Security Groups (click in sidebar)

Shows firewall rules controlling which ports are open.

Key groups to point out:
- `ssh-only` — allows TCP port 22 (SSH) and ICMP (ping)
- `web-server` — allows TCP port 80 (HTTP) in addition to SSH
- `default` — default rules created by OpenStack

**What to say:** "Security Groups are identical to AWS Security Groups — stateful firewall rules. We control exactly which ports are open on each instance."

---

### Users & Projects (click in sidebar)

Shows multi-tenant isolation:

| Username | Projects |
|----------|---------|
| admin | admin |
| devuser | dev-project |
| opsuser | prod-project |
| devadmin | dev-project |

**What to say:** "This is equivalent to IAM users and AWS accounts. Each user can only see their own project's resources. If you log in as devuser, you only see dev-project's instances — you cannot see admin's instances. We tested this and proved it works."

---

### Live Proof: SSH into a Running Instance

To really impress the teacher, open a second terminal and SSH into the VM:

```bash
ssh -i /home/khalid/ec2-local-cloud/configs/project-key.pem \
    -o StrictHostKeyChecking=no \
    cirros@10.200.195.153
```

You will get a shell prompt inside the virtual machine:
```
$ _
```

Type `uname -a` to show it's a real Linux system, then `exit` to leave.

**What to say:** "This is a real virtual machine running on this laptop. I just SSH'd into it the same way you would SSH into an EC2 instance on AWS."

---

## Part 4 — Troubleshooting

### Problem: Dashboard shows "error" on Overview or Instances

**Cause:** Nova API workers are stuck.

**Fix:**
```bash
echo "2923" | sudo -S systemctl restart devstack@n-api
sleep 4
```

Then click **Refresh** in the dashboard header.

---

### Problem: `openstack token issue` returns connection error

**Cause:** Your WiFi IP changed and services are using the old IP.

**Fix:** Run the full restart script again:
```bash
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh
```

---

### Problem: Dashboard page won't open in browser

**Cause:** The dashboard server is not running.

**Check:** Is the terminal with `python3 app.py` still open and running?

**Fix:** Open a new terminal and start it:
```bash
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

---

### Problem: Ping to `10.200.195.153` fails

**Cause:** OVN networking broke after reboot.

**Fix:**
```bash
echo "2923" | sudo -S bash /home/khalid/ec2-local-cloud/restart-fix.sh
```

---

### Problem: A DevStack service shows `failed` or `inactive`

**Fix:** Restart that specific service:
```bash
echo "2923" | sudo -S systemctl restart devstack@SERVICENAME
# Example:
echo "2923" | sudo -S systemctl restart devstack@n-api
echo "2923" | sudo -S systemctl restart devstack@q-svc
```

Check all services at once:
```bash
systemctl list-units 'devstack@*' --no-pager --all | grep -v running
```

If the list is empty — all services are running.

---

### Problem: SSH gives "Connection refused" or "Permission denied"

**Check:** Is the instance actually running?
```bash
source /opt/stack/devstack/openrc admin admin
openstack server show demo-instance-01 -f value -c status
```

Should say `ACTIVE`. If it says `SHUTOFF`:
```bash
openstack server start demo-instance-01
sleep 20
```

Then try SSH again.

---

## Part 5 — Quick Verification Checklist

Run this before your presentation to confirm everything works:

```bash
# 1. Load credentials
source /opt/stack/devstack/openrc admin admin

# 2. Check all services running
systemctl list-units 'devstack@*' --no-pager --all | grep -v running | grep -v Legend
# Expected: empty output (all running)

# 3. Check instances are ACTIVE
openstack server list --all-projects
# Expected: demo-instance-01 and dev-vm-01 both ACTIVE

# 4. Ping the floating IP
ping -c 3 10.200.195.153
# Expected: 0% packet loss

# 5. Check dashboard is up
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/
# Expected: 200
```

If all 5 pass — you are ready to present.

---

## Part 6 — Full Startup Commands (Copy-Paste Ready)

Open **two terminals**:

### Terminal 1 — Fix services and verify

```bash
# Fix everything after reboot
cd /home/khalid/ec2-local-cloud
echo "2923" | sudo -S bash restart-fix.sh

# Verify OpenStack works
source /opt/stack/devstack/openrc admin admin
openstack server list --all-projects

# Verify network works
ping -c 3 10.200.195.153
```

### Terminal 2 — Run the dashboard

```bash
# Start the web dashboard (keep this terminal open)
cd /home/khalid/ec2-local-cloud/dashboard
python3 app.py
```

Then open browser: **http://localhost:8080**

---

## Summary

| When | What to run |
|------|------------|
| Every reboot / WiFi reconnect | `echo "2923" \| sudo -S bash restart-fix.sh` |
| To start the dashboard | `cd dashboard && python3 app.py` |
| To open in browser | `http://localhost:8080` |
| Nova is stuck (instances section errors) | `echo "2923" \| sudo -S systemctl restart devstack@n-api` |
| Check all services | `systemctl list-units 'devstack@*' --no-pager --all \| grep -v running` |
| SSH into demo VM | `ssh -i configs/project-key.pem cirros@10.200.195.153` |
