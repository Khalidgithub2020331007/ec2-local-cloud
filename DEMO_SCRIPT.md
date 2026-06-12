# Demo Script — Local EC2 Replica Presentation
### DevStack (OpenStack Dalmatian) on Ubuntu 24.04 LTS
### Machine: Acer TravelMate P215-53 | 8GB RAM | 16 CPU | WiFi

---

## Before You Start (Pre-flight Checklist)

Run this **5 minutes before** your presentation:

```bash
# 1. Verify your WiFi IP hasn't changed (DHCP can reassign)
ip addr show wlp0s20f3 | grep 'inet '
# Must match HOST_IP in local.conf

# 2. Verify all OpenStack services are running
source /opt/stack/devstack/openrc admin admin
SERVICES="key n-api n-cpu n-cond n-sch g-api c-api c-vol q-svc q-agt q-dhcp q-l3 placement-api"
for svc in $SERVICES; do
    echo -n "$svc: "
    sudo systemctl is-active devstack@$svc
done
# All must print: active

# 3. Quick smoke test — launch a VM, ping it, delete it
openstack server create --image cirros-0.6.2-x86_64-disk --flavor m1.tiny --network private-network smoke-test
sleep 60
SMOKE_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip smoke-test $SMOKE_FIP
ping -c 3 $SMOKE_FIP && echo "ALL GOOD — ready to demo" || echo "NETWORKING ISSUE — check Neutron"
openstack server delete smoke-test
openstack floating ip delete $SMOKE_FIP

# 4. Open Horizon dashboard in browser
# http://10.200.194.146/dashboard  (login: admin / Admin@OpenStack1)
```

---

## Presentation Structure (Total: ~20 minutes)

| Section | Duration | What You Show |
|---------|----------|---------------|
| [1] Introduction | 2 min | What the project is and why |
| [2] Architecture Overview | 3 min | Diagram + service mapping to AWS |
| [3] Live Demo — Dashboard | 3 min | Login, overview, flavors, images |
| [4] Live Demo — Launch VM | 4 min | Create instance, floating IP, SSH |
| [5] Live Demo — Storage | 3 min | Create volume, attach, mount, read data |
| [6] Live Demo — Multi-User | 2 min | Two users, isolated views |
| [7] Comparison + Conclusion | 3 min | AWS vs DevStack feature table |

---

---

## SECTION 1 — Introduction (2 minutes)

**What to say:**

> "This project builds a local private cloud that replicates the core features of Amazon EC2 —
> virtual machines, persistent storage, networking, floating IPs, and multi-user isolation —
> all on a single laptop using open-source software called DevStack."

> "DevStack is the official single-node installer for OpenStack — the same open-source cloud
> platform that powers large public clouds like Rackspace and OVH. Using OpenStack means every
> feature we build has a direct equivalent in real AWS, and we can compare them side by side."

**Key point to make:**
- This is not a simulator. These are real virtual machines running under KVM hypervisor, the same hypervisor AWS uses under the hood.

---

## SECTION 2 — Architecture Overview (3 minutes)

**Show the diagram from PLAN.md and explain each layer:**

```
Physical host → OpenStack services → Virtual machines
```

**Map each service to AWS:**

| Say this... | Point to this... |
|-------------|-----------------|
| "Keystone is our IAM" | Keystone |
| "Nova is our EC2 compute engine" | Nova |
| "Glance stores our AMIs" | Glance |
| "Cinder is our EBS block storage" | Cinder |
| "Neutron is our VPC and networking" | Neutron |
| "Horizon is our AWS Management Console" | Horizon |

**Key talking point:**
> "All inter-service communication goes through RabbitMQ — just like in production OpenStack at scale. When you click 'Launch Instance', Nova calls Glance for the image, calls Neutron for a network port, calls Cinder if you want a volume, and then hands off to KVM to actually boot the VM."

---

## SECTION 3 — Live Demo: Dashboard (3 minutes)

**Open browser → `http://10.200.194.146/dashboard`**

### Step 3.1 — Login
- Domain: `Default`
- Username: `admin`
- Password: `Admin@OpenStack1`

**Say:** "This is our Management Console — equivalent to logging into AWS at console.aws.amazon.com."

### Step 3.2 — Show Project Overview
- Point to: RAM usage, vCPU usage, instance count
- **Say:** "This is the same resource quota view you'd see in EC2 limits."

### Step 3.3 — Show Flavors (Horizon → Admin → Compute → Flavors)
- Point out the 4 flavors: m1.tiny, m1.small, m1.medium, m1.large
- **Say:** "These are our instance types — the equivalent of t2.nano, t2.micro, t2.small, t2.medium in EC2."

### Step 3.4 — Show Images (Horizon → Project → Compute → Images)
- Point to CirrOS and Ubuntu-22.04-LTS both in `active` state
- **Say:** "These are our AMIs — CirrOS is a tiny 15MB test image, Ubuntu is the real OS we use for the web server demo."

---

## SECTION 4 — Live Demo: Launch a VM + SSH (4 minutes)

**Switch to terminal. Load credentials:**

```bash
source /opt/stack/devstack/openrc admin admin
```

### Step 4.1 — Launch an instance

```bash
openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  live-demo-vm
```

**Say:** "This is the equivalent of `aws ec2 run-instances`. We're specifying the image, the instance type, the network, our SSH key, and the firewall rules."

### Step 4.2 — Watch it go ACTIVE

```bash
watch -n 2 openstack server list
```

**Say:** "The status goes BUILD → ACTIVE — same as EC2's pending → running. On CirrOS this takes under 30 seconds."

Wait for `ACTIVE`, then press Ctrl+C.

### Step 4.3 — Assign a Floating IP (Elastic IP)

```bash
DEMO_FIP=$(openstack floating ip create public -f value -c floating_ip_address)
openstack server add floating ip live-demo-vm $DEMO_FIP
echo "Floating IP: $DEMO_FIP"
```

**Say:** "A floating IP is OpenStack's Elastic IP. It's a public-facing IP that we can associate and disassociate from any instance."

### Step 4.4 — Ping it

```bash
ping -c 4 $DEMO_FIP
```

**Say:** "ICMP is reaching the VM through the security group rule we added — same as an EC2 security group with an Allow ICMP inbound rule."

### Step 4.5 — SSH into the VM

```bash
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  cirros@$DEMO_FIP
```

**Inside the VM, run:**

```bash
whoami          # cirros
hostname        # live-demo-vm
uname -a        # Linux kernel version
ip addr show    # shows private IP 192.168.100.XX
df -h           # disk layout
free -m         # memory — shows 512MB (m1.tiny)
exit
```

**Say:** "We're SSH'd into a real virtual machine — same private key workflow as EC2. The `ip addr` output shows the private IP from our 192.168.100.0/24 subnet, which is our VPC subnet equivalent."

### Step 4.6 — Show VNC Console (EC2 Instance Connect equivalent)

- Open Horizon → Instances → click `live-demo-vm` → Console tab
- **Say:** "This is browser-based console access — the equivalent of EC2 Instance Connect. No SSH needed. You get a terminal directly in the browser."

---

## SECTION 5 — Live Demo: Block Storage (3 minutes)

### Step 5.1 — Create a volume

```bash
openstack volume create --size 5 live-demo-volume
sleep 5
openstack volume list
# status: available
```

**Say:** "This is our EBS volume — 5 gigabytes of persistent block storage."

### Step 5.2 — Attach to the running instance

```bash
openstack server add volume live-demo-vm live-demo-volume --device /dev/vdb
openstack volume show live-demo-volume | grep status
# status: in-use
```

**Say:** "Just like attaching an EBS volume to an EC2 instance. It shows up as a block device inside the OS."

### Step 5.3 — SSH in and format + mount it

```bash
ssh -i /opt/stack/project-key.pem -o StrictHostKeyChecking=no cirros@$DEMO_FIP

# Inside VM:
sudo fdisk -l            # see /dev/vdb listed
sudo mkfs.ext4 /dev/vdb  # format it
sudo mkdir /data
sudo mount /dev/vdb /data
df -h                    # /data now shows 4.8G available
echo "Persistent storage demo" | sudo tee /data/proof.txt
cat /data/proof.txt
exit
```

**Say:** "We formatted and mounted the volume inside the VM. The data written here survives the VM being deleted — the volume is independent of the instance lifecycle, exactly like EBS."

### Step 5.4 — Show volume snapshot (optional, if time allows)

```bash
openstack server remove volume live-demo-vm live-demo-volume
openstack volume snapshot create --volume live-demo-volume demo-snap
openstack volume snapshot list
```

**Say:** "And we can snapshot the volume at any point — same as creating an EBS snapshot for backup or migration."

---

## SECTION 6 — Live Demo: Multi-User Isolation (2 minutes)

**Say:** "One of the things that makes this a real cloud platform — not just a VM host — is multi-tenancy. Different users are completely isolated from each other."

### Step 6.1 — Show the user structure (CLI)

```bash
source /opt/stack/devstack/openrc admin admin
openstack user list
# admin, demo, devuser, opsuser, devadmin

openstack project list
# admin, demo, dev-project, prod-project
```

### Step 6.2 — Login as devuser in incognito browser

- Open a second browser window (incognito)
- URL: `http://10.200.194.146/dashboard`
- Domain: `Default`, Username: `devuser`, Password: `DevUser@123`

**Say:** "devuser is assigned to dev-project — same concept as an IAM user scoped to a specific AWS account."

- Show: only dev-project's instances visible (isolation from admin's VMs)

### Step 6.3 — Show admin sees everything

```bash
source /opt/stack/devstack/openrc admin admin
openstack server list --all-projects
# Shows VMs from ALL projects
```

**Say:** "Admin is the equivalent of the AWS root account — sees across all projects."

---

## SECTION 7 — Comparison + Conclusion (3 minutes)

**Show the comparison table from PROJECT_REQUIREMENTS.md:**

| AWS EC2 | This Project |
|---------|-------------|
| EC2 Instances | Nova Instances |
| AMIs | Glance Images |
| Instance Types | Flavors |
| EBS Volumes | Cinder Volumes |
| Elastic IPs | Floating IPs |
| VPC | Neutron Network |
| Security Groups | Security Groups |
| IAM Users | Keystone Users |
| AWS Management Console | Horizon Dashboard |
| AWS CLI | OpenStack CLI |

**Closing statement:**

> "This project demonstrates that the core architecture of commercial cloud platforms is not proprietary magic —
> it's a well-understood set of open-source components: a compute scheduler, a hypervisor,
> a network virtualization layer, a block storage system, and an identity service.
> DevStack ties all of these together in a way that's reproducible on a single laptop."

---

## Cleanup After Demo

```bash
source /opt/stack/devstack/openrc admin admin

# Delete demo resources
openstack server remove volume live-demo-vm live-demo-volume 2>/dev/null
openstack server delete live-demo-vm
openstack floating ip delete $DEMO_FIP
openstack volume snapshot delete demo-snap 2>/dev/null
openstack volume delete live-demo-volume
```

---

## If Something Goes Wrong During the Demo

### Instance stuck in BUILD (not going ACTIVE)

```bash
sudo systemctl restart devstack@n-cpu
openstack server delete <stuck-instance>
# Re-launch it
```

### SSH connection refused

```bash
# Check floating IP is assigned
openstack server show live-demo-vm | grep addresses

# Check security group has SSH rule
openstack security group rule list ssh-only | grep 22

# Re-ping to confirm network is up
ping -c 3 $DEMO_FIP
```

### Horizon not loading (502/500 error)

```bash
sudo systemctl restart apache2
# Wait 10 seconds, reload browser
```

### Neutron broken (no network to VMs)

```bash
sudo systemctl restart devstack@q-svc devstack@q-agt devstack@q-dhcp devstack@q-l3
# Wait 30 seconds before launching new VMs
```

### No floating IPs available

```bash
# Check if old ones are still allocated
openstack floating ip list
# Release unused ones
openstack floating ip delete <ip>
```

---

*Project: Local EC2 Replica | DevStack stable/2024.2 | Ubuntu 24.04 LTS*
*Machine: Acer TravelMate P215-53 | 10.200.194.146 | wlp0s20f3*
