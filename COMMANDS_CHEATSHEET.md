# Mini Cloud API Cheatsheet
### Quick reference for all REST API calls — curl examples with JWT auth

---

## Setup — Get an Auth Token

```bash
# Login and capture the token
TOKEN=$(curl -s -X POST http://localhost:5001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "Admin1234"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo $TOKEN

# Shorthand alias for curl with auth header
alias mc='curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json"'
```

---

## Instances (EC2 Instances)

```bash
# List all instances
mc http://localhost:5001/api/v1/compute/instances | python3 -m json.tool

# Launch a new instance
mc -X POST http://localhost:5001/api/v1/compute/instances \
  -d '{
    "name": "demo-vm",
    "flavor": "t1.nano",
    "image_id": "<image-id>",
    "keypair_id": "<keypair-id>"
  }'

# Get instance details
mc http://localhost:5001/api/v1/compute/instances/<instance-id>

# Stop instance (graceful ACPI shutdown)
mc -X POST http://localhost:5001/api/v1/compute/instances/<instance-id>/stop

# Start a stopped instance
mc -X POST http://localhost:5001/api/v1/compute/instances/<instance-id>/start

# Reboot instance
mc -X POST http://localhost:5001/api/v1/compute/instances/<instance-id>/reboot

# Delete instance permanently
mc -X DELETE http://localhost:5001/api/v1/compute/instances/<instance-id>

# List available flavors (instance types)
mc http://localhost:5001/api/v1/compute/flavors
```

### Flavor Reference

| Flavor | vCPU | RAM | Disk | AWS Equivalent |
|--------|------|-----|------|----------------|
| t1.nano | 1 | 512 MB | 5 GB | t2.nano |
| t1.micro | 1 | 1 GB | 10 GB | t2.micro |
| t1.small | 1 | 2 GB | 20 GB | t2.small |
| t1.medium | 2 | 4 GB | 40 GB | t2.medium |

---

## Images (AMI Equivalent)

```bash
# List all images
mc http://localhost:5001/api/v1/images | python3 -m json.tool

# Upload an image (multipart form)
curl -s -H "Authorization: Bearer $TOKEN" \
  -F "name=CirrOS 0.6.2" \
  -F "file=@/tmp/cirros-0.6.2-x86_64-disk.img" \
  http://localhost:5001/api/v1/images

# Get image details
mc http://localhost:5001/api/v1/images/<image-id>

# Delete an image
mc -X DELETE http://localhost:5001/api/v1/images/<image-id>
```

---

## Key Pairs (SSH Key Management)

```bash
# List key pairs
mc http://localhost:5001/api/v1/keypairs

# Generate a new key pair (private key shown ONCE — save it immediately)
mc -X POST http://localhost:5001/api/v1/keypairs \
  -d '{"name": "my-key"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['private_key'])" \
  > ~/.ssh/my-key.pem

chmod 600 ~/.ssh/my-key.pem

# Import an existing public key
mc -X POST http://localhost:5001/api/v1/keypairs \
  -d "{\"name\": \"my-existing-key\", \"public_key\": \"$(cat ~/.ssh/id_rsa.pub)\"}"

# Delete a key pair
mc -X DELETE http://localhost:5001/api/v1/keypairs/<keypair-id>
```

---

## Networks (VPC Equivalent)

```bash
# List networks
mc http://localhost:5001/api/v1/network/networks

# Create a private network
mc -X POST http://localhost:5001/api/v1/network/networks \
  -d '{
    "name": "my-network",
    "cidr": "10.10.0.0/24"
  }'

# Get network details
mc http://localhost:5001/api/v1/network/networks/<network-id>

# Delete a network (must have no instances attached)
mc -X DELETE http://localhost:5001/api/v1/network/networks/<network-id>
```

---

## Floating IPs (Elastic IP Equivalent)

```bash
# List all floating IPs
mc http://localhost:5001/api/v1/network/floating-ips

# Allocate a floating IP from the pool
mc -X POST http://localhost:5001/api/v1/network/floating-ips

# Associate floating IP with an instance
mc -X POST http://localhost:5001/api/v1/network/floating-ips/<fip-id>/associate \
  -d '{"instance_id": "<instance-id>"}'

# Disassociate floating IP from an instance
mc -X POST http://localhost:5001/api/v1/network/floating-ips/<fip-id>/disassociate

# Release floating IP back to the pool
mc -X DELETE http://localhost:5001/api/v1/network/floating-ips/<fip-id>
```

---

## Security Groups (Firewall Rules)

```bash
# List security groups
mc http://localhost:5001/api/v1/network/security-groups

# Create a security group
mc -X POST http://localhost:5001/api/v1/network/security-groups \
  -d '{"name": "ssh-only", "description": "Allow SSH and ICMP"}'

# Add a rule (SSH inbound)
mc -X POST http://localhost:5001/api/v1/network/security-groups/<sg-id>/rules \
  -d '{
    "direction": "inbound",
    "protocol": "tcp",
    "port_min": 22,
    "port_max": 22,
    "cidr": "0.0.0.0/0"
  }'

# Add ICMP (ping) rule
mc -X POST http://localhost:5001/api/v1/network/security-groups/<sg-id>/rules \
  -d '{"direction": "inbound", "protocol": "icmp", "cidr": "0.0.0.0/0"}'

# Add HTTP rule (port 80)
mc -X POST http://localhost:5001/api/v1/network/security-groups/<sg-id>/rules \
  -d '{"direction": "inbound", "protocol": "tcp", "port_min": 80, "port_max": 80, "cidr": "0.0.0.0/0"}'

# Delete a security group rule
mc -X DELETE http://localhost:5001/api/v1/network/security-groups/<sg-id>/rules/<rule-id>

# Delete a security group
mc -X DELETE http://localhost:5001/api/v1/network/security-groups/<sg-id>

# Attach security group to an instance
mc -X POST http://localhost:5001/api/v1/compute/instances/<instance-id>/security-groups \
  -d '{"security_group_id": "<sg-id>"}'
```

---

## Volumes (EBS Equivalent)

```bash
# List all volumes
mc http://localhost:5001/api/v1/storage/volumes

# Create a new volume
mc -X POST http://localhost:5001/api/v1/storage/volumes \
  -d '{"name": "my-volume", "size_gb": 5}'

# Get volume details
mc http://localhost:5001/api/v1/storage/volumes/<volume-id>

# Attach volume to an instance
mc -X POST http://localhost:5001/api/v1/storage/volumes/<volume-id>/attach \
  -d '{"instance_id": "<instance-id>"}'

# Detach volume from an instance
mc -X POST http://localhost:5001/api/v1/storage/volumes/<volume-id>/detach

# Delete a volume (must be detached first)
mc -X DELETE http://localhost:5001/api/v1/storage/volumes/<volume-id>

# Create a volume snapshot
mc -X POST http://localhost:5001/api/v1/storage/snapshots \
  -d '{"name": "my-snap", "volume_id": "<volume-id>"}'

# List snapshots
mc http://localhost:5001/api/v1/storage/snapshots

# Create a volume from a snapshot
mc -X POST http://localhost:5001/api/v1/storage/volumes \
  -d '{"name": "restored-vol", "size_gb": 5, "snapshot_id": "<snapshot-id>"}'
```

---

## Inside the VM — Volume Operations (via SSH)

```bash
# After attaching, SSH in and run:

# See the new block device
sudo fdisk -l

# Format as ext4 (first time only)
sudo mkfs.ext4 /dev/vdb

# Mount it
sudo mkdir /data
sudo mount /dev/vdb /data

# Verify
df -h

# Write test data
echo "Persistent volume demo" | sudo tee /data/test.txt
cat /data/test.txt
```

---

## Load Balancers (HAProxy)

```bash
# List load balancers
mc http://localhost:5001/api/v1/load-balancers

# Create a load balancer
mc -X POST http://localhost:5001/api/v1/load-balancers \
  -d '{"name": "my-lb", "port": 8080}'

# Add a backend member (instance + port)
mc -X POST http://localhost:5001/api/v1/load-balancers/<lb-id>/members \
  -d '{"instance_id": "<instance-id>", "port": 80}'

# Remove a member
mc -X DELETE http://localhost:5001/api/v1/load-balancers/<lb-id>/members/<member-id>

# Delete a load balancer
mc -X DELETE http://localhost:5001/api/v1/load-balancers/<lb-id>
```

---

## IAM Users & Projects

```bash
# List IAM users
mc http://localhost:5001/api/v1/iam/users

# Create an IAM user
mc -X POST http://localhost:5001/api/v1/iam/users \
  -d '{"username": "devbot"}'

# List IAM groups
mc http://localhost:5001/api/v1/iam/groups

# Create a group
mc -X POST http://localhost:5001/api/v1/iam/groups \
  -d '{"name": "Developers"}'

# Add user to group
mc -X POST http://localhost:5001/api/v1/iam/groups/<group-id>/members \
  -d '{"user_id": "<iam-user-id>"}'

# List policies
mc http://localhost:5001/api/v1/iam/policies

# Create a custom policy
mc -X POST http://localhost:5001/api/v1/iam/policies \
  -d '{
    "name": "EC2StartStopOnly",
    "description": "Allow start/stop only",
    "document": {
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Action": ["ec2:StartInstances", "ec2:StopInstances"],
        "Resource": "*"
      }]
    }
  }'

# Attach policy to user
mc -X POST http://localhost:5001/api/v1/iam/users/<user-id>/policies \
  -d '{"policy_id": "<policy-id>"}'
```

---

## Monitoring

```bash
# Host resource usage (CPU, RAM, network I/O)
mc http://localhost:5001/api/v1/monitoring/host | python3 -m json.tool

# All VM metrics
mc http://localhost:5001/api/v1/monitoring/vms | python3 -m json.tool

# Specific instance metrics
mc http://localhost:5001/api/v1/monitoring/vms/<instance-id> | python3 -m json.tool
```

---

## Quotas

```bash
# Check your quota usage
mc http://localhost:5001/api/v1/quotas | python3 -m json.tool

# Admin: update system-wide defaults
mc -X PUT http://localhost:5001/api/v1/quotas/defaults \
  -d '{"instances": 10, "vcpus": 20, "ram_mb": 20480}'

# Admin: override quota for a specific user
mc -X PUT http://localhost:5001/api/v1/quotas/users/<user-id> \
  -d '{"instances": 20, "vcpus": 40}'
```

---

## System Status

```bash
# Check mini-cloud service health
curl -s http://localhost:5001/api/v1/auth/health

# Check libvirt is running
sudo systemctl is-active libvirtd

# List all running KVM VMs
sudo virsh list --all

# Check LVM volume group
sudo vgdisplay mini-cloud-vg

# Check floating IP interface
ip addr show mc-fip

# Check iptables NAT rules (floating IPs)
sudo iptables -t nat -L -n --line-numbers | grep -E "DNAT|SNAT|mc-fip"

# View mini-cloud service logs
sudo journalctl -u mini-cloud -n 50 --no-pager
```

---

## Useful Diagnostic Commands

```bash
# Verify which user is logged in (token claims)
echo $TOKEN | cut -d. -f2 | base64 -d 2>/dev/null | python3 -m json.tool

# List all libvirt networks (should include 'default')
sudo virsh net-list --all

# Check dnsmasq processes (one per mini-cloud network)
ps aux | grep dnsmasq | grep -v grep

# Watch iptables rules live
sudo watch -n 2 'iptables -t nat -L -n --line-numbers'
```

---

*Project: Mini Cloud System | Flask + libvirt/KVM + LVM + iptables | Ubuntu 24.04 LTS*
