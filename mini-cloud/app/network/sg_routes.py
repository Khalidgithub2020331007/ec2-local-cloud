import ipaddress
from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.database import get_connection
from app.network.models import (
    create_security_group, get_security_group, list_security_groups, delete_security_group,
    add_sg_rule_db, get_sg_rule, list_sg_rules, delete_sg_rule,
    attach_vm_to_sg, detach_vm_from_sg, get_vm_security_groups, get_all_vm_sg_rules,
)
from app.network.sg_manager import (
    add_sg_rule_to_chain, remove_sg_rule_from_chain, rebuild_vm_sg_chain,
)

sg_bp = Blueprint('security_groups', __name__, url_prefix='/api/v1')

VALID_PROTOCOLS  = {'tcp', 'udp', 'icmp', 'all'}
VALID_DIRECTIONS = {'inbound', 'outbound'}


def _rebuild_vm_inbound_chain(vm_id):
    # Filter to inbound-only — outbound is not enforced via the tap chain
    inbound_rules = [r for r in get_all_vm_sg_rules(vm_id) if r['direction'] == 'inbound']
    try:
        rebuild_vm_sg_chain(vm_id, inbound_rules)
    except RuntimeError:
        pass  # VM not running yet — chain will be built when VM starts


# ── Security Groups ────────────────────────────────────────────────────────────

@sg_bp.route('/security-groups', methods=['GET'])
@require_auth
def list_sgs():
    groups = list_security_groups(g.current_user['id'])
    for group in groups:
        group['rules'] = list_sg_rules(group['id'])
    return jsonify({'security_groups': groups}), 200


@sg_bp.route('/security-groups', methods=['POST'])
@require_auth
def create_sg():
    data        = request.get_json(silent=True) or {}
    name        = data.get('name', '').strip()
    description = data.get('description', '').strip()

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name is required',
                        'statusCode': 400}), 400

    from app.quotas.models import check_quota
    ok, limit, used = check_quota(g.current_user['id'], 'security_groups')
    if not ok:
        return jsonify({'error': 'QUOTA_EXCEEDED',
                        'message': f'Security group quota exceeded. Limit: {limit}, Current: {used}',
                        'statusCode': 403}), 403

    group_id      = create_security_group(g.current_user['id'], name, description)
    group         = get_security_group(group_id)
    group['rules'] = []
    return jsonify({'message': 'Security group created', 'security_group': group}), 201


@sg_bp.route('/security-groups/<group_id>', methods=['DELETE'])
@require_auth
def delete_sg(group_id):
    group = get_security_group(group_id, g.current_user['id'])
    if not group:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Security group not found',
                        'statusCode': 404}), 404

    # Block deletion if still attached to any VMs — would leave iptables rules orphaned
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT COUNT(*) FROM vm_security_groups WHERE group_id=?', (group_id,)
        ).fetchone()
        if row[0] > 0:
            return jsonify({'error': 'GROUP_IN_USE',
                            'message': 'Detach from all VMs before deleting',
                            'statusCode': 409}), 409
    finally:
        conn.close()

    delete_security_group(group_id)  # ON DELETE CASCADE removes all rules
    return jsonify({'message': 'Security group deleted'}), 200


# ── Rules ──────────────────────────────────────────────────────────────────────

@sg_bp.route('/security-groups/<group_id>/rules', methods=['POST'])
@require_auth
def add_rule(group_id):
    group = get_security_group(group_id, g.current_user['id'])
    if not group:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Security group not found',
                        'statusCode': 404}), 404

    data      = request.get_json(silent=True) or {}
    direction = data.get('direction', 'inbound').strip().lower()
    protocol  = data.get('protocol', '').strip().lower()
    port_min  = data.get('port_min')
    port_max  = data.get('port_max')
    cidr      = data.get('cidr', '0.0.0.0/0').strip()

    if direction not in VALID_DIRECTIONS:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'direction must be inbound or outbound',
                        'statusCode': 400}), 400
    if protocol not in VALID_PROTOCOLS:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'protocol must be tcp, udp, icmp, or all',
                        'statusCode': 400}), 400

    if protocol in ('tcp', 'udp'):
        if port_min is None or port_max is None:
            return jsonify({'error': 'VALIDATION_ERROR',
                            'message': 'port_min and port_max are required for tcp/udp',
                            'statusCode': 400}), 400
        try:
            port_min, port_max = int(port_min), int(port_max)
        except (ValueError, TypeError):
            return jsonify({'error': 'VALIDATION_ERROR',
                            'message': 'port_min and port_max must be integers',
                            'statusCode': 400}), 400
        if not (1 <= port_min <= 65535 and 1 <= port_max <= 65535):
            return jsonify({'error': 'VALIDATION_ERROR',
                            'message': 'ports must be between 1 and 65535',
                            'statusCode': 400}), 400
        if port_min > port_max:
            return jsonify({'error': 'VALIDATION_ERROR',
                            'message': 'port_min must be <= port_max',
                            'statusCode': 400}), 400
    else:
        port_min = port_max = None

    try:
        ipaddress.IPv4Network(cidr, strict=False)
    except ValueError:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': f'Invalid CIDR: {cidr}',
                        'statusCode': 400}), 400

    from app.quotas.models import check_quota
    ok, limit, used = check_quota(g.current_user['id'], 'security_group_rules')
    if not ok:
        return jsonify({'error': 'QUOTA_EXCEEDED',
                        'message': f'Security group rules quota exceeded. Limit: {limit}, Current: {used}',
                        'statusCode': 403}), 403

    rule_id = add_sg_rule_db(group_id, direction, protocol, port_min, port_max, cidr)

    # Immediately apply to every running VM that has this group attached.
    # Only inbound rules map to iptables — outbound is stored in DB for display only.
    if direction == 'inbound':
        conn = get_connection()
        try:
            vm_rows = conn.execute(
                'SELECT vm_id FROM vm_security_groups WHERE group_id=?', (group_id,)
            ).fetchall()
        finally:
            conn.close()

        for vm_row in vm_rows:
            try:
                add_sg_rule_to_chain(vm_row['vm_id'], protocol, port_min, port_max, cidr)
            except RuntimeError:
                pass  # VM not running — rule is in DB and will be applied on next start

    return jsonify({'message': 'Rule added', 'rule': get_sg_rule(rule_id)}), 201


@sg_bp.route('/security-groups/<group_id>/rules/<rule_id>', methods=['DELETE'])
@require_auth
def remove_rule(group_id, rule_id):
    group = get_security_group(group_id, g.current_user['id'])
    if not group:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Security group not found',
                        'statusCode': 404}), 404

    rule = get_sg_rule(rule_id)
    if not rule or rule['group_id'] != group_id:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Rule not found in this security group',
                        'statusCode': 404}), 404

    # Remove from iptables first while we still have the rule parameters in memory
    if rule['direction'] == 'inbound':
        conn = get_connection()
        try:
            vm_rows = conn.execute(
                'SELECT vm_id FROM vm_security_groups WHERE group_id=?', (group_id,)
            ).fetchall()
        finally:
            conn.close()

        for vm_row in vm_rows:
            remove_sg_rule_from_chain(
                vm_row['vm_id'], rule['protocol'],
                rule['port_min'], rule['port_max'], rule['cidr'],
            )

    delete_sg_rule(rule_id)
    return jsonify({'message': 'Rule removed'}), 200


# ── Attach / Detach ────────────────────────────────────────────────────────────

@sg_bp.route('/security-groups/<group_id>/attach/<vm_id>', methods=['POST'])
@require_auth
def attach_sg(group_id, vm_id):
    group = get_security_group(group_id, g.current_user['id'])
    if not group:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Security group not found',
                        'statusCode': 404}), 404

    from app.compute.models import get_instance
    instance = get_instance(vm_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Instance not found',
                        'statusCode': 404}), 404

    attach_vm_to_sg(vm_id, group_id)

    # Rebuild chain from scratch so the new group's rules take effect immediately.
    # Rebuild (not incremental add) guarantees no duplicate rules on repeated attach.
    _rebuild_vm_inbound_chain(vm_id)

    return jsonify({
        'message':  'Security group attached',
        'vm_id':    vm_id,
        'group_id': group_id,
        'security_groups': get_vm_security_groups(vm_id),
    }), 200


@sg_bp.route('/security-groups/<group_id>/detach/<vm_id>', methods=['POST'])
@require_auth
def detach_sg(group_id, vm_id):
    group = get_security_group(group_id, g.current_user['id'])
    if not group:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Security group not found',
                        'statusCode': 404}), 404

    from app.compute.models import get_instance
    instance = get_instance(vm_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Instance not found',
                        'statusCode': 404}), 404

    detach_vm_from_sg(vm_id, group_id)

    # Rebuild without the detached group's rules.
    # A full rebuild is simpler than trying to surgically remove one group's rules.
    _rebuild_vm_inbound_chain(vm_id)

    return jsonify({
        'message':  'Security group detached',
        'vm_id':    vm_id,
        'group_id': group_id,
        'security_groups': get_vm_security_groups(vm_id),
    }), 200
