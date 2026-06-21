import re
from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.compute.flavors import get_flavor, list_flavors
from app.compute.models import (
    create_instance, update_instance_status,
    get_instance, list_instances, mark_terminated,
)
from app.compute.libvirt_manager import (
    create_instance_disk, launch_vm, stop_vm, start_vm,
    reboot_vm, terminate_vm, get_vm_status, get_vm_vnc_port,
)

compute_bp = Blueprint('compute', __name__, url_prefix='/api/v1/compute')

# Instance name: lowercase letters, numbers, hyphens only (like AWS)
_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{1,30}[a-z0-9]$')


@compute_bp.route('/flavors', methods=['GET'])
@require_auth
def flavors():
    return jsonify({'flavors': list_flavors()}), 200


@compute_bp.route('/instances', methods=['GET'])
@require_auth
def list_all():
    instances = list_instances(g.current_user['id'])
    # Live status libvirt থেকে sync করা হয় — DB-র cached status না পড়ে
    for inst in instances:
        live = get_vm_status(inst['libvirt_name'])
        if live not in (inst['status'], 'terminated'):
            update_instance_status(inst['id'], live)
            inst['status'] = live
    return jsonify({'instances': instances, 'count': len(instances)}), 200


@compute_bp.route('/instances', methods=['POST'])
@require_auth
def launch():
    data = request.get_json(silent=True) or {}
    name        = data.get('name', '').strip().lower()
    flavor_name = data.get('flavor', '').strip()
    image_id    = data.get('image_id', '').strip() or None
    image_path  = data.get('image_path', '').strip() or None

    # image_id takes precedence — look up its file path from the images table
    if image_id:
        from app.images.models import get_image
        img = get_image(image_id, g.current_user['id'])
        if not img:
            return jsonify({'error': 'NOT_FOUND', 'message': 'Image not found', 'statusCode': 404}), 404
        image_path = img['file_path']

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if not _NAME_RE.match(name):
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name must be 3–32 lowercase letters, numbers, or hyphens', 'statusCode': 400}), 400

    flavor = get_flavor(flavor_name)
    if not flavor:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': f'Unknown flavor. Valid: {[f["name"] for f in list_flavors()]}', 'statusCode': 400}), 400

    # libvirt domain name: mc-<user>-<instance-name> — globally unique in KVM
    libvirt_name = f"mc-{g.current_user['username']}-{name}"

    try:
        # Step 1: DB record তৈরি করো (status=pending)
        instance_id = create_instance(
            user_id      = g.current_user['id'],
            name         = name,
            flavor       = flavor_name,
            vcpus        = flavor['vcpus'],
            ram_mb       = flavor['ram_mb'],
            disk_gb      = flavor['disk_gb'],
            libvirt_name = libvirt_name,
            disk_path    = '',  # Step 2-এ update হবে
            image_path   = image_path,
        )

        # Step 2: Disk তৈরি করো
        disk_path = create_instance_disk(instance_id, flavor['disk_gb'], image_path)
        update_instance_status(instance_id, 'pending')

        # Update disk_path in DB
        from app.database import get_connection
        conn = get_connection()
        conn.execute('UPDATE instances SET disk_path=? WHERE id=?', (disk_path, instance_id))
        conn.commit()
        conn.close()

        # Step 3: libvirt এ VM launch করো
        launch_vm(libvirt_name, flavor['vcpus'], flavor['ram_mb'], disk_path)

        # Step 4: VNC port পড়ো এবং status update করো
        vnc_port = get_vm_vnc_port(libvirt_name)
        update_instance_status(instance_id, 'running', vnc_port=vnc_port)

        instance = get_instance(instance_id)
        return jsonify({'message': 'Instance launched', 'instance': instance}), 201

    except Exception as e:
        if 'instance_id' in locals():
            update_instance_status(instance_id, 'error')
        return jsonify({'error': 'LAUNCH_FAILED', 'message': str(e), 'statusCode': 500}), 500


@compute_bp.route('/instances/<instance_id>', methods=['GET'])
@require_auth
def get_one(instance_id):
    instance = get_instance(instance_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Instance not found', 'statusCode': 404}), 404

    # Always return live status
    live = get_vm_status(instance['libvirt_name'])
    if live != instance['status']:
        update_instance_status(instance_id, live)
        instance['status'] = live

    return jsonify({'instance': instance}), 200


@compute_bp.route('/instances/<instance_id>/action', methods=['POST'])
@require_auth
def action(instance_id):
    data   = request.get_json(silent=True) or {}
    act    = data.get('action', '').strip()
    valid  = {'stop', 'start', 'reboot', 'terminate'}

    if act not in valid:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': f'action must be one of {sorted(valid)}', 'statusCode': 400}), 400

    instance = get_instance(instance_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Instance not found', 'statusCode': 404}), 404

    lname = instance['libvirt_name']

    try:
        if act == 'stop':
            stop_vm(lname)
            update_instance_status(instance_id, 'stopped')
            return jsonify({'message': 'Instance stopped'}), 200

        elif act == 'start':
            start_vm(lname)
            vnc_port = get_vm_vnc_port(lname)
            update_instance_status(instance_id, 'running', vnc_port=vnc_port)
            return jsonify({'message': 'Instance started'}), 200

        elif act == 'reboot':
            reboot_vm(lname)
            update_instance_status(instance_id, 'running')
            return jsonify({'message': 'Instance rebooting'}), 200

        elif act == 'terminate':
            terminate_vm(lname, instance_id)
            mark_terminated(instance_id)
            return jsonify({'message': 'Instance terminated'}), 200

    except Exception as e:
        return jsonify({'error': 'ACTION_FAILED', 'message': str(e), 'statusCode': 500}), 500
