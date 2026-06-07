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
# PUBLIC_NETWORK_GATEWAY=10.200.192.1 puts br-ex in a different subnet than
# OVN's public network (10.200.195.128/26). Adding .129 lets OVN route replies back.
sudo ip addr add 10.200.195.129/26 dev br-ex 2>/dev/null || true
sudo ip route del 10.200.195.128/26 dev br-ex 2>/dev/null || true

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

# ── Step 5b: Restart services that may have failed after HOST_IP change ──────
# c-sch/c-vol/n-sch can get stuck connecting to a stale RabbitMQ IP after drift.
# Their configs already have the correct IP; a restart is enough to clear failed state.
for svc in devstack@c-sch devstack@c-vol devstack@n-sch; do
    if ! sudo systemctl is-active --quiet "$svc"; then
        echo "Restarting $svc (was not active)..."
        sudo systemctl restart "$svc"
    fi
done
sleep 3

# ── Step 6: Verify ───────────────────────────────────────────────────────────
sleep 5
echo ""
echo "=== OVN chassis (should show an entry) ==="
ovn-sbctl --db=tcp:${CURRENT_IP}:6642 list chassis | grep -E "hostname|name" || echo "WARNING: no chassis found"

echo ""
echo "=== OVS manager ==="
sudo ovs-vsctl get-manager

echo ""
echo "=== br-ex IPs ==="
ip addr show br-ex | grep inet

echo ""
echo "=== DevStack services ==="
sudo systemctl list-units 'devstack@*' --all --no-pager --no-legend | awk '{print $1, $4}'

echo ""
echo "=== Done. Now run: ==="
echo "   sudo su - stack"
echo "   cd devstack && source /opt/stack/devstack/openrc admin admin"
echo "   openstack server list"
