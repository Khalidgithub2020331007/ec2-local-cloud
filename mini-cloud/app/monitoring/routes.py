from flask import Blueprint, jsonify, g
from app.auth.middleware import require_auth
from app.compute.models import list_instances, get_instance
from app.monitoring.metrics import get_all_host_metrics, get_vm_metrics

monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/api/v1')


@monitoring_bp.route('/monitoring/host', methods=['GET'])
@require_auth
def host_metrics():
    metrics = get_all_host_metrics()
    return jsonify(metrics), 200


@monitoring_bp.route('/monitoring/vms', methods=['GET'])
@require_auth
def all_vm_metrics():
    instances = list_instances(g.current_user['id'])
    result = []
    for inst in instances:
        vm_metrics = get_vm_metrics(inst['libvirt_name'], inst['id'])
        result.append({
            'vm_id': inst['id'],
            'name':  inst['name'],
            **vm_metrics,
        })
    return jsonify({'vms': result, 'count': len(result)}), 200


@monitoring_bp.route('/monitoring/vms/<vm_id>', methods=['GET'])
@require_auth
def single_vm_metrics(vm_id):
    inst = get_instance(vm_id, g.current_user['id'])
    if not inst:
        return jsonify({
            'error': 'NOT_FOUND',
            'message': 'Instance not found',
            'statusCode': 404,
        }), 404

    vm_metrics = get_vm_metrics(inst['libvirt_name'], inst['id'])
    return jsonify({
        'vm_id': inst['id'],
        'name':  inst['name'],
        **vm_metrics,
    }), 200


@monitoring_bp.route('/monitoring/summary', methods=['GET'])
@require_auth
def monitoring_summary():
    # Single call that returns host metrics + VM counts — used by the dashboard overview.
    host      = get_all_host_metrics()
    instances = list_instances(g.current_user['id'])
    running   = sum(1 for i in instances if i['status'] == 'running')
    return jsonify({
        **host,
        'vm_total':   len(instances),
        'vm_running': running,
    }), 200
