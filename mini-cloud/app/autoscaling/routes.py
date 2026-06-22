from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.autoscaling.models import (
    create_asg, get_asg, list_asgs, set_asg_status, delete_asg,
    update_asg_policy, update_asg_lb, detach_asg_lb,
    get_asg_instances, get_asg_instance_count, get_scaling_history,
    get_newest_asg_instance, add_asg_instance, remove_asg_instance,
    record_scaling_event,
)

asg_bp = Blueprint('autoscaling', __name__, url_prefix='/api/v1/autoscaling')


def _asg_with_count(asg):
    return {**asg, 'instance_count': get_asg_instance_count(asg['id'])}


# ── Create / List / Get ───────────────────────────────────────────────────────

@asg_bp.route('', methods=['POST'])
@require_auth
def create():
    data = request.get_json(silent=True) or {}
    name              = (data.get('name') or '').strip()
    image_id          = (data.get('image_id') or '').strip() or None
    flavor            = (data.get('flavor') or '').strip()
    network_id        = (data.get('network_id') or '').strip() or None
    keypair_id        = (data.get('keypair_id') or '').strip() or None
    security_group_id = (data.get('security_group_id') or '').strip() or None

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if not flavor:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'flavor is required', 'statusCode': 400}), 400

    from app.compute.flavors import get_flavor
    if not get_flavor(flavor):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': f'Unknown flavor: {flavor}', 'statusCode': 400}), 400

    try:
        min_instances        = int(data.get('min_instances', 1))
        max_instances        = int(data.get('max_instances', 5))
        scale_up_threshold   = float(data.get('scale_up_threshold', 70))
        scale_down_threshold = float(data.get('scale_down_threshold', 30))
        cooldown_seconds     = int(data.get('cooldown_seconds', 120))
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'Invalid numeric value in request', 'statusCode': 400}), 400

    if min_instances < 1 or max_instances < min_instances:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'min_instances >= 1 and max_instances >= min_instances required',
                        'statusCode': 400}), 400
    if scale_down_threshold >= scale_up_threshold:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'scale_down_threshold must be less than scale_up_threshold',
                        'statusCode': 400}), 400

    asg_id = create_asg(
        user_id              = g.current_user['id'],
        name                 = name,
        image_id             = image_id,
        flavor               = flavor,
        network_id           = network_id,
        keypair_id           = keypair_id,
        security_group_id    = security_group_id,
        min_instances        = min_instances,
        max_instances        = max_instances,
        scale_up_threshold   = scale_up_threshold,
        scale_down_threshold = scale_down_threshold,
        cooldown_seconds     = cooldown_seconds,
    )

    asg = get_asg(asg_id)
    return jsonify({'autoscaling_group': _asg_with_count(asg)}), 201


@asg_bp.route('', methods=['GET'])
@require_auth
def list_all():
    asgs = list_asgs(g.current_user['id'])
    return jsonify({'autoscaling_groups': [_asg_with_count(a) for a in asgs], 'count': len(asgs)}), 200


@asg_bp.route('/<asg_id>', methods=['GET'])
@require_auth
def get_one(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404
    return jsonify({'autoscaling_group': _asg_with_count(asg)}), 200


# ── Delete ────────────────────────────────────────────────────────────────────

@asg_bp.route('/<asg_id>', methods=['DELETE'])
@require_auth
def delete_one(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    # Mark deleting first so the monitor skips it during cleanup
    set_asg_status(asg_id, 'deleting')

    from app.compute.libvirt_manager import terminate_vm
    from app.compute.models import mark_terminated
    from app.network.sg_manager import delete_vm_sg_chain
    from app.load_balancers.models import get_member_by_vm, remove_member
    from app.load_balancers.haproxy_manager import write_and_reload

    instances = get_asg_instances(asg_id)
    lb_changed = False

    for vm in instances:
        if asg['lb_id']:
            try:
                if get_member_by_vm(asg['lb_id'], vm['vm_id']):
                    remove_member(asg['lb_id'], vm['vm_id'])
                    lb_changed = True
            except Exception:
                pass

        try:
            delete_vm_sg_chain(vm['vm_id'])
        except RuntimeError:
            pass

        try:
            terminate_vm(vm['libvirt_name'], vm['vm_id'])
            mark_terminated(vm['vm_id'])
        except Exception:
            pass

        remove_asg_instance(vm['vm_id'])

    if lb_changed:
        try:
            write_and_reload()
        except RuntimeError:
            pass

    delete_asg(asg_id)
    return jsonify({'message': 'Auto scaling group and all its instances deleted'}), 200


# ── Policy ────────────────────────────────────────────────────────────────────

@asg_bp.route('/<asg_id>/policy', methods=['PUT'])
@require_auth
def update_policy(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    data = request.get_json(silent=True) or {}
    try:
        up   = float(data.get('scale_up_threshold',   asg['scale_up_threshold']))
        down = float(data.get('scale_down_threshold', asg['scale_down_threshold']))
        cd   = int(data.get('cooldown_seconds',       asg['cooldown_seconds']))
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'Invalid numeric values', 'statusCode': 400}), 400

    if down >= up:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'scale_down_threshold must be less than scale_up_threshold',
                        'statusCode': 400}), 400

    update_asg_policy(asg_id, up, down, cd)
    return jsonify({'message': 'Scaling policy updated'}), 200


# ── Instances / History ───────────────────────────────────────────────────────

@asg_bp.route('/<asg_id>/instances', methods=['GET'])
@require_auth
def list_instances(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    instances = get_asg_instances(asg_id)
    return jsonify({'instances': instances, 'count': len(instances)}), 200


@asg_bp.route('/<asg_id>/history', methods=['GET'])
@require_auth
def scaling_history(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    history = get_scaling_history(asg_id)
    return jsonify({'history': history}), 200


# ── Load Balancer attachment ──────────────────────────────────────────────────

@asg_bp.route('/<asg_id>/attach-lb/<lb_id>', methods=['POST'])
@require_auth
def attach_lb(asg_id, lb_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    from app.load_balancers.models import get_lb
    lb = get_lb(lb_id)
    if not lb:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Load balancer not found', 'statusCode': 404}), 404
    if lb['user_id'] != g.current_user['id'] and g.current_user['role'] != 'admin':
        return jsonify({'error': 'FORBIDDEN', 'message': 'Not your load balancer', 'statusCode': 403}), 403

    data = request.get_json(silent=True) or {}
    try:
        member_port = int(data.get('member_port'))
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'member_port (integer) is required', 'statusCode': 400}), 400

    update_asg_lb(asg_id, lb_id, member_port)
    return jsonify({'message': 'Load balancer attached', 'lb_id': lb_id, 'member_port': member_port}), 200


@asg_bp.route('/<asg_id>/detach-lb', methods=['POST'])
@require_auth
def detach_lb(asg_id):
    asg = get_asg(asg_id, g.current_user['id'])
    if not asg:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Auto scaling group not found', 'statusCode': 404}), 404

    detach_asg_lb(asg_id)
    return jsonify({'message': 'Load balancer detached'}), 200
