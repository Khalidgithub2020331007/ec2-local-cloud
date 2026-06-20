#!/bin/bash
# Run this after every reboot or power-on before using OpenStack.
# Must be run as khalid (not stack) — it uses sudo for the parts that need root.

set -e

# ── Step 1: HOST_IP drift check ──────────────────────────────────────────────
CURRENT_IP=$(ip addr show wlp0s20f3 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
CONF_IP=$(grep HOST_IP /opt/stack/devstack/local.conf | cut -d= -f2)
echo "Current IP : $CURRENT_IP"
echo "Config IP  : $CONF_IP"

if [ "$CURRENT_IP" != "$CONF_IP" ]; then
    sudo sed -i "s/HOST_IP=$CONF_IP/HOST_IP=$CURRENT_IP/" /opt/stack/devstack/local.conf
    sed -i "s/HOST_IP=$CONF_IP/HOST_IP=$CURRENT_IP/" /home/khalid/ec2-local-cloud/configs/local.conf
    echo "HOST_IP updated to $CURRENT_IP"
else
    echo "IP unchanged — no update needed"
fi

# ── Step 2: Kernel routing fixes ─────────────────────────────────────────────
sudo sysctl -w net.ipv4.conf.all.rp_filter=0
sudo sysctl -w net.ipv4.conf.wlp0s20f3.accept_local=1
sudo sysctl -w net.ipv4.ip_forward=1

# ── Step 3: OVN chassis + OVS manager fix ────────────────────────────────────
# unstack.sh stops OVS; must restart it before any ovs-vsctl commands
sudo systemctl start openvswitch-switch
sudo ovs-vsctl --may-exist add-br br-ex
sudo ovs-vsctl set open . external-ids:ovn-bridge-mappings=public:br-ex
# Without ovn-remote/encap: instances fail to launch ("no OVN chassis for host")
# Without set-manager: os-vif can't plug VIFs into br-int
sudo ovs-vsctl set open . external-ids:ovn-remote=tcp:${CURRENT_IP}:6642
sudo ovs-vsctl set open . external-ids:ovn-encap-type=geneve
sudo ovs-vsctl set open . external-ids:ovn-encap-ip=${CURRENT_IP}
sudo systemctl restart ovn-controller
sudo ovs-vsctl set-manager ptcp:6640

# ── Step 4: Floating IP routing fix ──────────────────────────────────────────
# br-ex starts DOWN after reboot — bring it up and restore the gateway IP.
# Public network is 172.24.4.0/24; br-ex must hold .1 as the gateway.
sudo ip link set br-ex up 2>/dev/null || true
sudo ip addr add 172.24.4.1/24 dev br-ex 2>/dev/null || true

# ── Step 4b: OVN gateway chassis fix for floating IPs ────────────────────────
# OVN forgets gateway_chassis on the router external port after stack.sh re-runs.
# Without it, NAT for floating IPs never completes — DNAT packets are dropped.
# Router external port UUID is stable across reboots (not stack.sh re-runs).
ROUTER_EXT_LRP=lrp-baff0f73-becd-4934-9dd1-3ef810a819a3
CHASSIS_UUID=$(sudo ovn-sbctl --db=tcp:${CURRENT_IP}:6642 list chassis 2>/dev/null | grep "^_uuid" | awk '{print $3}')
if [ -n "$CHASSIS_UUID" ]; then
    sudo ovn-nbctl --db=tcp:${CURRENT_IP}:6641 lrp-set-gateway-chassis "$ROUTER_EXT_LRP" "$CHASSIS_UUID" 1
    echo "gateway_chassis set: $CHASSIS_UUID"
else
    echo "WARNING: could not find chassis UUID — floating IPs will not work"
fi

# ── Step 5: OVN metadata agent ───────────────────────────────────────────────
# DevStack never generated neutron_ovn_metadata_agent.ini — create it and run
# the agent as a systemd service (matching the pattern of devstack@q-meta).
# Privsep (oslo_privsep) requires the agent to run as the stack user; running
# as khalid causes FailedToDropPrivileges and no network namespaces are created.

OVN_META_CONF=/etc/neutron/neutron_ovn_metadata_agent.ini
sudo tee "$OVN_META_CONF" > /dev/null <<EOF
[DEFAULT]
debug = True
nova_metadata_host = ${CURRENT_IP}
metadata_workers = 2
state_path = /opt/stack/data/neutron

[agent]
root_helper = sudo /opt/stack/data/venv/bin/neutron-rootwrap /etc/neutron/rootwrap.conf
root_helper_daemon = sudo /opt/stack/data/venv/bin/neutron-rootwrap-daemon /etc/neutron/rootwrap.conf

[ovs]
ovsdb_connection = tcp:127.0.0.1:6640

[ovn]
ovn_sb_connection = tcp:${CURRENT_IP}:6642
EOF

sudo tee /etc/systemd/system/devstack@q-ovn-metadata-agent.service > /dev/null <<'EOF'
[Unit]
Description = Devstack devstack@q-ovn-metadata-agent.service

[Service]
ExecReload = /usr/bin/kill -HUP $MAINPID
TimeoutStopSec = 300
KillMode = process
ExecStart = /opt/stack/data/venv/bin/neutron-ovn-metadata-agent --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/ml2/ml2_conf.ini --config-file /etc/neutron/neutron_ovn_metadata_agent.ini
User = stack
Environment = "PATH=/bin:/opt/stack/data/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/sbin"

[Install]
WantedBy = multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl restart devstack@q-ovn-metadata-agent.service
sleep 3
sudo systemctl is-active devstack@q-ovn-metadata-agent.service && echo "OVN metadata agent: OK" || echo "OVN metadata agent: FAILED — check: journalctl -u devstack@q-ovn-metadata-agent"

# ── Step 5b: OVN metadata port + DHCP options for private-network ────────────
# ovn_metadata_enabled=False in ml2_conf.ini means Neutron never auto-created
# the ovnmeta port or the classless_static_route DHCP option. These must be set
# manually once per stack.sh run. Idempotent: openstack port create fails silently
# if port already exists; ovn-nbctl set is always safe to re-run.
source /opt/stack/devstack/openrc admin admin 2>/dev/null
PRIVATE_NET=1779a260-3cb2-4648-b797-e68aa998717d
PRIVATE_SUBNET=14a5a4d1-fbc1-411d-a9a0-32c7856f47c4
META_PORT_NAME=ovnmeta-${PRIVATE_NET}
META_DEVICE_ID=ovnmeta-${PRIVATE_NET}

# Create metadata port if it doesn't already exist
if ! openstack port show "$META_PORT_NAME" &>/dev/null; then
    echo "Creating OVN metadata port for private-network..."
    openstack port create \
        --network "$PRIVATE_NET" \
        --device-owner network:distributed \
        --device "$META_DEVICE_ID" \
        --fixed-ip subnet="$PRIVATE_SUBNET",ip-address=192.168.100.10 \
        "$META_PORT_NAME"
else
    # Ensure device_id is set — port create without --device leaves it blank,
    # and the metadata agent only creates the ovnmeta namespace for ports whose
    # device_id matches the expected "ovnmeta-<net-uuid>" pattern.
    openstack port set "$META_PORT_NAME" --device "$META_DEVICE_ID" 2>/dev/null || true
    echo "OVN metadata port already exists — device_id ensured"
fi

# Add classless_static_route DHCP option so instances can reach 169.254.169.254.
# The metadata port is always at 192.168.100.10 (fixed IP above).
# grep on "192.168.100.0/24" cidr is more stable than matching the subnet UUID.
META_IP=$(openstack port show "$META_PORT_NAME" -f value -c fixed_ips 2>/dev/null | grep -oP "'ip_address': '[^']+'" | grep -oP "[0-9.]+")
DHCP_UUID=$(sudo ovn-nbctl --db=tcp:${CURRENT_IP}:6641 list dhcp_options 2>/dev/null | grep -B2 "192.168.100.0/24" | grep "_uuid" | awk '{print $3}')
if [ -n "$DHCP_UUID" ] && [ -n "$META_IP" ]; then
    sudo ovn-nbctl --db=tcp:${CURRENT_IP}:6641 set dhcp_options "$DHCP_UUID" \
        "options:classless_static_route={169.254.169.254/32,${META_IP}, 0.0.0.0/0,192.168.100.1}"
    echo "DHCP classless_static_route set: 169.254.169.254/32 via ${META_IP}"
else
    echo "WARNING: Could not set DHCP classless_static_route (DHCP_UUID=${DHCP_UUID}, META_IP=${META_IP})"
fi

# ── Step 5c: Fix nova-api.conf duplicate ProxyPass lines ──────────────────────
# nova-api.conf can accumulate duplicate ProxyPass lines on repeated stack.sh runs.
# Multiple identical directives cause Apache to silently drop requests to /compute.
NOVA_CONF=/etc/apache2/sites-enabled/nova-api.conf
if [ $(grep -c 'ProxyPass.*compute' "$NOVA_CONF" 2>/dev/null) -gt 1 ]; then
    echo "Fixing nova-api.conf (duplicate ProxyPass lines detected)..."
    sudo tee "$NOVA_CONF" > /dev/null <<'APACHEEOF'
KeepAlive Off
SetEnv proxy-sendchunked 1
ProxyPass "/compute" "unix:/var/run/uwsgi/nova-api.socket|uwsgi://uwsgi-uds-nova-api" retry=0 acquire=1
APACHEEOF
    sudo systemctl reload apache2
fi

# ── Step 5d: Restart services that may have failed after HOST_IP change ──────
# c-sch/c-vol/n-sch can get stuck connecting to a stale RabbitMQ IP after drift.
# n-api workers can get stuck in RabbitMQ retry loops on startup — restart clears them.
# Their configs already have the correct IP; a restart is enough to clear failed state.
for svc in devstack@c-sch devstack@c-vol devstack@n-sch devstack@n-api; do
    sudo systemctl restart "$svc"
    echo "Restarted $svc"
done
sleep 3

# ── Step 6: Verify ──────────────────────────────────────────────────────────
sleep 5
echo ""
echo "=== OVN chassis (should show an entry) ==="
ovn-sbctl --db=tcp:${CURRENT_IP}:6642 list chassis | grep -E "hostname|name" || echo "WARNING: no chassis found"

echo ""
echo "=== OVS manager ==="
sudo ovs-vsctl get-manager

echo ""
echo "=== br-ex IPs ==="
ip addr show br-ex | grep inet || echo "WARNING: br-ex has no inet address"

echo ""
echo "=== DevStack services ==="
sudo systemctl list-units 'devstack@*' --all --no-pager --no-legend | awk '{print $1, $4}'

echo ""
echo "=== Done. Now run: ==="
echo "   sudo su - stack"
echo "   cd devstack && source /opt/stack/devstack/openrc admin admin"
echo "   openstack server list"
