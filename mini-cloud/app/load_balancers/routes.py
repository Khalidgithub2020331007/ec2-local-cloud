from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.load_balancers.models import (
    create_lb, get_lb, get_all_lbs, delete_lb,
    port_in_use, add_member, get_members,
    get_member_by_vm, remove_member,
    MIN_PORT, MAX_PORT,
)
from app.load_balancers.haproxy_manager import write_and_reload, get_member_health

lb_bp = Blueprint('load_balancers', __name__, url_prefix='/api/v1/load-balancers')


def _lb_with_member_count(lb):
    members = get_members(lb['id'])
    return {**lb, 'member_count': len(members)}


# ── Load Balancer CRUD ────────────────────────────────────────────────────────

@lb_bp.route('', methods=['POST'])
@require_auth
def create_load_balancer():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    port = data.get('port')

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400

    try:
        port = int(port)
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'port must be an integer', 'statusCode': 400}), 400

    if port < MIN_PORT or port > MAX_PORT:
        return jsonify({
            'error':      'VALIDATION_ERROR',
            'message':    f'port must be between {MIN_PORT} and {MAX_PORT} (ports 1–1024 are reserved)',
            'statusCode': 400,
        }), 400

    if port_in_use(port):
        return jsonify({
            'error':      'PORT_CONFLICT',
            'message':    f'Port {port} is already used by another load balancer',
            'statusCode': 409,
        }), 409

    lb_id = create_lb(g.current_user['id'], name, port)

    try:
        write_and_reload()
    except RuntimeError as e:
        # LB is saved to DB but HAProxy could not reload — surface the reason
        return jsonify({
            'error':      'HAPROXY_ERROR',
            'message':    str(e),
            'statusCode': 500,
        }), 500

    lb = get_lb(lb_id)
    return jsonify({'load_balancer': _lb_with_member_count(lb)}), 201


@lb_bp.route('', methods=['GET'])
@require_auth
def list_load_balancers():
    lbs = get_all_lbs(g.current_user['id'])
    return jsonify({'load_balancers': [_lb_with_member_count(lb) for lb in lbs]}), 200


@lb_bp.route('/<lb_id>', methods=['DELETE'])
@require_auth
def delete_load_balancer(lb_id):
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404

    if lb['user_id'] != g.current_user['id'] and g.current_user['role'] != 'admin':
        return jsonify({'error': 'FORBIDDEN', 'message': 'Not your load balancer', 'statusCode': 403}), 403

    delete_lb(lb_id)

    try:
        write_and_reload()
    except RuntimeError as e:
        return jsonify({'error': 'HAPROXY_ERROR', 'message': str(e), 'statusCode': 500}), 500

    return jsonify({'message': 'Load balancer deleted'}), 200


# ── Members ───────────────────────────────────────────────────────────────────

@lb_bp.route('/<lb_id>/members', methods=['POST'])
@require_auth
def add_lb_member(lb_id):
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404

    if lb['user_id'] != g.current_user['id'] and g.current_user['role'] != 'admin':
        return jsonify({'error': 'FORBIDDEN', 'message': 'Not your load balancer', 'statusCode': 403}), 403

    data          = request.get_json(silent=True) or {}
    vm_id         = (data.get('vm_id') or '').strip()
    vm_private_ip = (data.get('vm_private_ip') or '').strip()
    member_port   = data.get('member_port')

    if not vm_id or not vm_private_ip:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'vm_id and vm_private_ip are required', 'statusCode': 400}), 400

    try:
        member_port = int(member_port)
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'member_port must be an integer', 'statusCode': 400}), 400

    if get_member_by_vm(lb_id, vm_id):
        return jsonify({'error': 'CONFLICT', 'message': 'VM is already a member of this load balancer', 'statusCode': 409}), 409

    member_id = add_member(lb_id, vm_id, vm_private_ip, member_port)

    try:
        write_and_reload()
    except RuntimeError as e:
        return jsonify({'error': 'HAPROXY_ERROR', 'message': str(e), 'statusCode': 500}), 500

    return jsonify({'member_id': member_id, 'message': 'Member added'}), 201


@lb_bp.route('/<lb_id>/members', methods=['GET'])
@require_auth
def list_lb_members(lb_id):
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404

    return jsonify({'members': get_members(lb_id)}), 200


@lb_bp.route('/<lb_id>/members/<vm_id>', methods=['DELETE'])
@require_auth
def remove_lb_member(lb_id, vm_id):
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404

    if lb['user_id'] != g.current_user['id'] and g.current_user['role'] != 'admin':
        return jsonify({'error': 'FORBIDDEN', 'message': 'Not your load balancer', 'statusCode': 403}), 403

    if not get_member_by_vm(lb_id, vm_id):
        return jsonify({'error': 'NOT_FOUND', 'message': 'VM is not a member of this load balancer', 'statusCode': 404}), 404

    remove_member(lb_id, vm_id)

    try:
        write_and_reload()
    except RuntimeError as e:
        return jsonify({'error': 'HAPROXY_ERROR', 'message': str(e), 'statusCode': 500}), 500

    return jsonify({'message': 'Member removed'}), 200


# ── Status (live HAProxy health) ──────────────────────────────────────────────

@lb_bp.route('/<lb_id>/status', methods=['GET'])
@require_auth
def lb_status(lb_id):
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404

    members = get_members(lb_id)
    health  = get_member_health(lb_id)  # dict: vm_id → health info from HAProxy socket

    member_statuses = []
    for m in members:
        vm_id = m['vm_id']
        h = health.get(vm_id, {})
        member_statuses.append({
            'vm_id':           vm_id,
            'ip':              m['vm_private_ip'],
            'member_port':     m['member_port'],
            'status':          h.get('status', 'unknown'),
            'haproxy_status':  h.get('haproxy_status', 'no check'),
            'requests_served': h.get('requests_served', 0),
        })

    return jsonify({
        'lb_id':   lb_id,
        'name':    lb['name'],
        'port':    lb['port'],
        'members': member_statuses,
    }), 200
