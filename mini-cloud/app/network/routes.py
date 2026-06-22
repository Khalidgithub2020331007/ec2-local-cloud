import re
from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.network.models import (
    create_network, get_network, list_networks, delete_network, get_next_bridge_name,
    create_router, get_router, list_routers, delete_router,
    create_floating_ip, get_floating_ip, list_floating_ips, delete_floating_ip,
    associate_floating_ip, disassociate_floating_ip, get_next_floating_ip,
)
from app.network.net_manager import (
    create_bridge, start_dnsmasq, delete_bridge,
    get_default_iface, add_nat_rules, remove_nat_rules,
    ensure_fip_interface, allocate_fip_on_host, release_fip_from_host,
    add_fip_nat_rules, remove_fip_nat_rules,
    get_vm_interfaces, parse_cidr,
)

network_bp = Blueprint('network', __name__, url_prefix='/api/v1/network')

_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{0,30}[a-z0-9]$')


# ── Networks ──────────────────────────────────────────────────────────────────

@network_bp.route('/networks', methods=['GET'])
@require_auth
def list_nets():
    return jsonify({'networks': list_networks(g.current_user['id'])}), 200


@network_bp.route('/networks', methods=['POST'])
@require_auth
def create_net():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip().lower()
    cidr = data.get('cidr', '').strip()

    if not name or not _NAME_RE.match(name):
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name must be 2–32 lowercase letters, numbers, or hyphens',
                        'statusCode': 400}), 400
    if not cidr:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'cidr is required (e.g. 192.168.200.0/24)',
                        'statusCode': 400}), 400

    try:
        cidr_normalized, gateway, dhcp_start, dhcp_end, prefix_len = parse_cidr(cidr)
    except ValueError as e:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': str(e), 'statusCode': 400}), 400

    bridge_name = get_next_bridge_name()

    try:
        create_bridge(bridge_name, gateway, prefix_len)
        start_dnsmasq(bridge_name, dhcp_start, dhcp_end)
    except RuntimeError as e:
        # Tear down partial bridge so it doesn't leave a ghost interface
        try:
            delete_bridge(bridge_name)
        except Exception:
            pass
        return jsonify({'error': 'BRIDGE_ERROR', 'message': str(e), 'statusCode': 500}), 500

    network_id = create_network(
        g.current_user['id'], name, bridge_name,
        cidr_normalized, gateway, dhcp_start, dhcp_end,
    )
    network = get_network(network_id)
    return jsonify({'message': 'Network created', 'network': network}), 201


@network_bp.route('/networks/<network_id>', methods=['GET'])
@require_auth
def get_net(network_id):
    net = get_network(network_id, g.current_user['id'])
    if not net:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Network not found', 'statusCode': 404}), 404
    return jsonify({'network': net}), 200


@network_bp.route('/networks/<network_id>', methods=['DELETE'])
@require_auth
def delete_net(network_id):
    net = get_network(network_id, g.current_user['id'])
    if not net:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Network not found', 'statusCode': 404}), 404

    # Block deletion if a router is attached to this network
    from app.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM routers WHERE network_id=?", (network_id,)
        ).fetchone()
        if row[0] > 0:
            return jsonify({'error': 'NETWORK_IN_USE',
                            'message': 'Delete the router attached to this network first',
                            'statusCode': 409}), 409
    finally:
        conn.close()

    try:
        delete_bridge(net['bridge_name'])
    except RuntimeError as e:
        return jsonify({'error': 'BRIDGE_ERROR', 'message': str(e), 'statusCode': 500}), 500

    delete_network(network_id)
    return jsonify({'message': 'Network deleted'}), 200


# ── Routers ───────────────────────────────────────────────────────────────────

@network_bp.route('/routers', methods=['GET'])
@require_auth
def list_rts():
    return jsonify({'routers': list_routers(g.current_user['id'])}), 200


@network_bp.route('/routers', methods=['POST'])
@require_auth
def create_rt():
    data       = request.get_json(silent=True) or {}
    name       = data.get('name', '').strip().lower()
    network_id = data.get('network_id', '').strip()

    if not name or not _NAME_RE.match(name):
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name must be 2–32 lowercase letters, numbers, or hyphens',
                        'statusCode': 400}), 400
    if not network_id:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'network_id is required',
                        'statusCode': 400}), 400

    net = get_network(network_id, g.current_user['id'])
    if not net:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Network not found', 'statusCode': 404}), 404

    ext_iface = get_default_iface()
    if not ext_iface:
        return jsonify({'error': 'NO_ROUTE',
                        'message': 'Cannot detect host default route interface',
                        'statusCode': 500}), 500

    try:
        add_nat_rules(net['cidr'], net['bridge_name'], ext_iface)
    except RuntimeError as e:
        return jsonify({'error': 'IPTABLES_ERROR', 'message': str(e), 'statusCode': 500}), 500

    router_id = create_router(g.current_user['id'], name, network_id, ext_iface)
    router = get_router(router_id)
    return jsonify({'message': 'Router created', 'router': router}), 201


@network_bp.route('/routers/<router_id>', methods=['DELETE'])
@require_auth
def delete_rt(router_id):
    from app.database import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            '''SELECT r.*, n.cidr, n.bridge_name
               FROM routers r JOIN networks n ON r.network_id=n.id
               WHERE r.id=? AND r.user_id=?''',
            (router_id, g.current_user['id']),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Router not found', 'statusCode': 404}), 404

    router = dict(row)
    try:
        remove_nat_rules(router['cidr'], router['bridge_name'], router['ext_iface'])
    except RuntimeError as e:
        return jsonify({'error': 'IPTABLES_ERROR', 'message': str(e), 'statusCode': 500}), 500

    delete_router(router_id)
    return jsonify({'message': 'Router deleted'}), 200


# ── Floating IPs ──────────────────────────────────────────────────────────────

@network_bp.route('/floating-ips', methods=['GET'])
@require_auth
def list_fips():
    return jsonify({'floating_ips': list_floating_ips(g.current_user['id'])}), 200


@network_bp.route('/floating-ips', methods=['POST'])
@require_auth
def allocate_fip():
    from app.quotas.models import check_quota
    ok, limit, used = check_quota(g.current_user['id'], 'floating_ips')
    if not ok:
        return jsonify({'error': 'QUOTA_EXCEEDED',
                        'message': f'Floating IP quota exceeded. Limit: {limit}, Current: {used}',
                        'statusCode': 403}), 403

    fip = get_next_floating_ip()
    if not fip:
        return jsonify({'error': 'POOL_EXHAUSTED',
                        'message': 'No floating IPs available in the 192.168.0.224/27 pool (30 IPs max)',
                        'statusCode': 409}), 409

    try:
        ensure_fip_interface()
        allocate_fip_on_host(fip)
    except RuntimeError as e:
        return jsonify({'error': 'FIP_ERROR', 'message': str(e), 'statusCode': 500}), 500

    fip_id = create_floating_ip(g.current_user['id'], fip)
    return jsonify({'message': 'Floating IP allocated',
                    'floating_ip': get_floating_ip(fip_id)}), 201


@network_bp.route('/floating-ips/<fip_id>/associate', methods=['POST'])
@require_auth
def associate_fip(fip_id):
    data        = request.get_json(silent=True) or {}
    instance_id = data.get('instance_id', '').strip()

    if not instance_id:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'instance_id is required',
                        'statusCode': 400}), 400

    fip = get_floating_ip(fip_id, g.current_user['id'])
    if not fip:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Floating IP not found', 'statusCode': 404}), 404
    if fip['status'] == 'associated':
        return jsonify({'error': 'ALREADY_ASSOCIATED',
                        'message': 'Disassociate first before reassigning',
                        'statusCode': 409}), 409

    # Lookup the VM's private IP from libvirt DHCP lease
    from app.compute.models import get_instance
    from app.network.net_manager import get_vm_interfaces
    instance = get_instance(instance_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Instance not found', 'statusCode': 404}), 404

    ifaces = get_vm_interfaces(instance['libvirt_name'])
    private_ip = next((i['ip'] for i in ifaces if i['ip']), None)

    if not private_ip:
        return jsonify({'error': 'NO_IP',
                        'message': 'Instance has no IP yet — is it running?',
                        'statusCode': 409}), 409

    try:
        add_fip_nat_rules(fip['ip_address'], private_ip)
    except RuntimeError as e:
        return jsonify({'error': 'IPTABLES_ERROR', 'message': str(e), 'statusCode': 500}), 500

    associate_floating_ip(fip_id, instance_id, private_ip)
    return jsonify({'message': 'Floating IP associated',
                    'floating_ip': get_floating_ip(fip_id)}), 200


@network_bp.route('/floating-ips/<fip_id>/disassociate', methods=['POST'])
@require_auth
def disassociate_fip(fip_id):
    fip = get_floating_ip(fip_id, g.current_user['id'])
    if not fip:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Floating IP not found', 'statusCode': 404}), 404
    if fip['status'] != 'associated':
        return jsonify({'error': 'NOT_ASSOCIATED',
                        'message': 'Floating IP is not currently associated',
                        'statusCode': 409}), 409

    try:
        remove_fip_nat_rules(fip['ip_address'], fip['private_ip'])
    except RuntimeError as e:
        return jsonify({'error': 'IPTABLES_ERROR', 'message': str(e), 'statusCode': 500}), 500

    disassociate_floating_ip(fip_id)
    return jsonify({'message': 'Floating IP disassociated'}), 200


@network_bp.route('/floating-ips/<fip_id>', methods=['DELETE'])
@require_auth
def release_fip(fip_id):
    fip = get_floating_ip(fip_id, g.current_user['id'])
    if not fip:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Floating IP not found', 'statusCode': 404}), 404
    if fip['status'] == 'associated':
        return jsonify({'error': 'STILL_ASSOCIATED',
                        'message': 'Disassociate the IP before releasing it',
                        'statusCode': 409}), 409

    try:
        release_fip_from_host(fip['ip_address'])
    except RuntimeError as e:
        return jsonify({'error': 'FIP_ERROR', 'message': str(e), 'statusCode': 500}), 500

    delete_floating_ip(fip_id)
    return jsonify({'message': 'Floating IP released'}), 200


# ── Network Interfaces ────────────────────────────────────────────────────────

@network_bp.route('/interfaces', methods=['GET'])
@require_auth
def list_interfaces():
    from app.compute.models import list_instances

    instances = list_instances(g.current_user['id'])
    result = []

    for inst in instances:
        if inst['status'] not in ('running', 'paused'):
            continue
        ifaces = get_vm_interfaces(inst['libvirt_name'])
        for iface in ifaces:
            result.append({
                'instance_id':   inst['id'],
                'instance_name': inst['name'],
                'mac':           iface['mac'],
                'network':       iface['network'],
                'ip':            iface['ip'],
            })

    return jsonify({'interfaces': result, 'count': len(result)}), 200
