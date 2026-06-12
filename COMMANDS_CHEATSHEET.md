# OpenStack CLI Cheatsheet — EC2 Replica Project
### Quick reference for all `openstack` commands used in this project

---

## Setup — Load Credentials

```bash
# Load admin credentials (required before any openstack command)
source /opt/stack/devstack/openrc admin admin

# Load as a specific project user
source /opt/stack/devstack/openrc devuser DevUser@123

# Verify which user/project is active
openstack token issue | grep -E 'project|user'
```

---

## Instances (EC2 Instances)

```bash
# List all instances in current project
openstack server list

# List instances across ALL projects (admin only)
openstack server list --all-projects

# Launch a new instance
openstack server create \
  --image "cirros-0.6.2-x86_64-disk" \
  --flavor m1.tiny \
  --network private-network \
  --key-name project-key \
  --security-group ssh-only \
  <instance-name>

# Show instance details (IP, status, flavor, image)
openstack server show <instance-name>

# Get instance console log (proves VM actually booted)
openstack console log show <instance-name>

# Stop instance (graceful shutdown → SHUTOFF)
openstack server stop <instance-name>

# Start a stopped instance
openstack server start <instance-name>

# Soft reboot (sends ACPI signal, OS restarts cleanly)
openstack server reboot <instance-name>

# Hard reboot (equivalent to power cycle)
openstack server reboot --hard <instance-name>

# Delete instance permanently
openstack server delete <instance-name>

# Create a snapshot image from a running instance (AMI equivalent)
openstack server image create --name "my-custom-ami" <instance-name>
```

---

## Images (AMI Equivalent — Glance)

```bash
# List all available images
openstack image list

# Show details of a specific image
openstack image show "Ubuntu-22.04-LTS"

# Upload a new image from a local file
openstack image create "Ubuntu-22.04-LTS" \
  --file /tmp/ubuntu-22.04-cloud.img \
  --disk-format qcow2 \
  --container-format bare \
  --public

# Delete an image
openstack image delete <image-name-or-id>
```

---

## Flavors (EC2 Instance Types)

```bash
# List all flavors
openstack flavor list

# Show details of a flavor
openstack flavor show m1.tiny

# Create a new flavor
openstack flavor create --id 1 --vcpus 1 --ram 512 --disk 5 m1.tiny

# Delete a flavor
openstack flavor delete m1.tiny
```

| Flavor | vCPU | RAM | Disk | EC2 Equivalent |
|--------|------|-----|------|----------------|
| m1.tiny | 1 | 512 MB | 5 GB | t2.nano |
| m1.small | 1 | 1 GB | 10 GB | t2.micro |
| m1.medium | 1 | 2 GB | 20 GB | t2.small |
| m1.large | 2 | 4 GB | 40 GB | t2.medium |

---

## Floating IPs (Elastic IP Equivalent)

```bash
# Allocate a floating IP from the public pool
openstack floating ip create public

# List all allocated floating IPs
openstack floating ip list

# Associate floating IP with an instance
openstack server add floating ip <instance-name> <floating-ip>

# Disassociate floating IP from an instance
openstack server remove floating ip <instance-name> <floating-ip>

# Release floating IP back to the pool
openstack floating ip delete <floating-ip>

# One-liner: allocate and capture the IP in a variable
FIP=$(openstack floating ip create public -f value -c floating_ip_address)
echo $FIP
```

---

## SSH Access

```bash
# SSH into CirrOS instance
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  cirros@<floating-ip>

# SSH into Ubuntu instance
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  ubuntu@<floating-ip>

# Run a single command over SSH (for testing)
ssh -i /opt/stack/project-key.pem \
  -o StrictHostKeyChecking=no \
  -o ConnectTimeout=10 \
  cirros@<floating-ip> "echo SSH_OK"
```

---

## Key Pairs (EC2 Key Pairs)

```bash
# List registered key pairs
openstack keypair list

# Create a new key pair (saves private key to file)
openstack keypair create project-key > /opt/stack/project-key.pem
chmod 600 /opt/stack/project-key.pem

# Show key pair fingerprint
openstack keypair show project-key

# Delete a key pair
openstack keypair delete project-key
```

---

## Volumes (EBS Equivalent — Cinder)

```bash
# List all volumes
openstack volume list

# Create a new volume
openstack volume create --size 5 <volume-name>

# Show volume details
openstack volume show <volume-name>

# Attach volume to an instance
openstack server add volume <instance-name> <volume-name> --device /dev/vdb

# Detach volume from an instance
openstack server remove volume <instance-name> <volume-name>

# Delete a volume (must be detached first)
openstack volume delete <volume-name>

# Create a volume snapshot
openstack volume snapshot create --volume <volume-name> <snapshot-name>

# List snapshots
openstack volume snapshot list

# Create a new volume from a snapshot
openstack volume create --snapshot <snapshot-name> --size 5 <new-volume-name>
```

---

## Inside the VM — Volume Operations

```bash
# After attaching a volume, run these INSIDE the VM (via SSH):

# See the attached block device
sudo fdisk -l

# Format as ext4 (first time only)
sudo mkfs.ext4 /dev/vdb

# Create mount point and mount
sudo mkdir /data
sudo mount /dev/vdb /data

# Verify mount
df -h

# Write test data
echo "Hello from EBS-like volume" | sudo tee /data/test.txt
cat /data/test.txt
```

---

## Networks (VPC Equivalent — Neutron)

```bash
# List networks
openstack network list

# Create a private network
openstack network create private-network

# Create a subnet
openstack subnet create private-subnet \
  --network private-network \
  --subnet-range 192.168.100.0/24 \
  --gateway 192.168.100.1 \
  --dns-nameserver 8.8.8.8 \
  --allocation-pool start=192.168.100.10,end=192.168.100.200

# List subnets
openstack subnet list

# Show network details
openstack network show private-network
```

---

## Router (Internet Gateway Equivalent)

```bash
# Create a router
openstack router create main-router

# Attach router to external/public network (gives internet access)
openstack router set main-router --external-gateway public

# Connect private subnet to the router
openstack router add subnet main-router private-subnet

# Show router details
openstack router show main-router

# Remove subnet from router
openstack router remove subnet main-router private-subnet
```

---

## Security Groups (EC2 Security Groups)

```bash
# List security groups
openstack security group list

# Create a security group
openstack security group create ssh-only \
  --description "Allow SSH and ICMP only"

# Add SSH inbound rule (port 22)
openstack security group rule create ssh-only \
  --protocol tcp --dst-port 22 --remote-ip 0.0.0.0/0

# Add ICMP (ping) rule
openstack security group rule create ssh-only \
  --protocol icmp --remote-ip 0.0.0.0/0

# Add HTTP rule (port 80)
openstack security group rule create web-server \
  --protocol tcp --dst-port 80 --remote-ip 0.0.0.0/0

# List rules for a security group
openstack security group rule list ssh-only

# Delete a specific rule (get rule ID from rule list)
openstack security group rule delete <rule-id>

# Delete a security group
openstack security group delete ssh-only

# Add security group to a running instance
openstack server add security group <instance-name> <sg-name>

# Remove security group from an instance
openstack server remove security group <instance-name> <sg-name>
```

---

## Users & Projects (IAM Equivalent — Keystone)

```bash
# List all users
openstack user list

# Create a new user
openstack user create \
  --domain Default \
  --password DevUser@123 \
  devuser

# List all projects
openstack project list

# Create a new project
openstack project create \
  --domain Default \
  --description "Development team" \
  dev-project

# List available roles
openstack role list

# Assign a user to a project with a role
openstack role add --project dev-project --user devuser member

# List role assignments in a project
openstack role assignment list --project dev-project

# Disable a user account
openstack user set --disable devuser

# Delete a user
openstack user delete devuser
```

---

## Services & System Status

```bash
# List all registered OpenStack services
openstack service list

# List compute services (nova-compute, nova-scheduler, etc.)
openstack compute service list

# List network agents (Neutron linuxbridge, dhcp, l3)
openstack network agent list

# List volume services (cinder-scheduler, cinder-volume)
openstack volume service list

# Check all DevStack systemd services
sudo systemctl list-units 'devstack@*' --all --no-pager

# Check a specific service status
sudo systemctl status devstack@n-cpu

# Restart a specific service
sudo systemctl restart devstack@n-cpu

# View logs for a service
sudo journalctl -u devstack@n-cpu -n 50 --no-pager
```

---

## Output Formatting

```bash
# Default output: table format
openstack server list

# JSON output (for scripting)
openstack server list -f json

# YAML output
openstack server list -f yaml

# Extract a single field value (useful in scripts)
openstack server show demo-instance-01 -f value -c status

# Extract floating IP in a script
FIP=$(openstack floating ip create public -f value -c floating_ip_address)
```

---

## Useful Diagnostic Commands

```bash
# Check which user/project credentials are loaded
env | grep OS_

# Verify API connectivity
openstack token issue

# Check quota usage
openstack quota show

# List all resources in a quick summary
openstack server list
openstack volume list
openstack image list
openstack floating ip list
openstack network list
openstack keypair list
```

---

*Project: Local EC2 Replica | DevStack stable/2024.2 | Ubuntu 24.04 LTS*
