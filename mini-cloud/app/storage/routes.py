from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.storage.lvm_manager import (
    create_lv, delete_lv,
    create_lv_snapshot, delete_lv_snapshot,
    restore_lv_from_snapshot,
    attach_volume, detach_volume,
)
from app.storage.models import (
    create_volume, get_volume, list_volumes,
    update_volume_status, delete_volume_record, find_next_device,
    create_snapshot, get_snapshot, list_snapshots,
    delete_snapshot_record, snapshot_has_restored_volumes,
)

storage_bp = Blueprint('storage', __name__, url_prefix='/api/v1')

MAX_VOLUME_SIZE_GB = 1000
MAX_SNAP_NAME_LEN  = 64


def _get_instance_for_user(vm_id, user_id):
    # Imported here to avoid a circular import at module load time.
    from app.compute.models import get_instance
    return get_instance(vm_id, user_id)


# ── Volumes ────────────────────────────────────────────────────────────────────

@storage_bp.route('/volumes', methods=['GET'])
@require_auth
def list_all_volumes():
    volumes = list_volumes(g.current_user['id'])
    return jsonify({'volumes': volumes, 'count': len(volumes)}), 200


@storage_bp.route('/volumes', methods=['POST'])
@require_auth
def create_new_volume():
    data    = request.get_json(silent=True) or {}
    name    = data.get('name', '').strip()
    size_gb = data.get('size_gb')

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name is required', 'statusCode': 400}), 400
    if size_gb is None:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'size_gb is required', 'statusCode': 400}), 400
    try:
        size_gb = int(size_gb)
    except (TypeError, ValueError):
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'size_gb must be an integer', 'statusCode': 400}), 400
    if not (1 <= size_gb <= MAX_VOLUME_SIZE_GB):
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': f'size_gb must be between 1 and {MAX_VOLUME_SIZE_GB}',
                        'statusCode': 400}), 400

    volume_id = create_volume(g.current_user['id'], name, size_gb)
    try:
        create_lv(volume_id, size_gb)
    except RuntimeError as e:
        delete_volume_record(volume_id)
        return jsonify({'error': 'LVM_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    return jsonify({'message': 'Volume created', 'volume': get_volume(volume_id)}), 201


@storage_bp.route('/volumes/<volume_id>', methods=['DELETE'])
@require_auth
def delete_vol(volume_id):
    volume = get_volume(volume_id, g.current_user['id'])
    if not volume:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Volume not found', 'statusCode': 404}), 404
    if volume['status'] == 'in-use':
        return jsonify({'error': 'VOLUME_IN_USE',
                        'message': 'Detach the volume from its instance before deleting',
                        'statusCode': 409}), 409

    try:
        delete_lv(volume_id)
    except RuntimeError as e:
        return jsonify({'error': 'LVM_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    delete_volume_record(volume_id)
    return jsonify({'message': 'Volume deleted'}), 200


@storage_bp.route('/volumes/<volume_id>/attach/<vm_id>', methods=['POST'])
@require_auth
def attach_vol(volume_id, vm_id):
    volume = get_volume(volume_id, g.current_user['id'])
    if not volume:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Volume not found', 'statusCode': 404}), 404
    if volume['status'] == 'in-use':
        return jsonify({'error': 'VOLUME_IN_USE',
                        'message': 'Volume is already attached to an instance',
                        'statusCode': 409}), 409

    instance = _get_instance_for_user(vm_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Instance not found', 'statusCode': 404}), 404

    try:
        device_name = find_next_device(vm_id)
    except RuntimeError as e:
        return jsonify({'error': 'NO_DEVICE_SLOTS',
                        'message': str(e), 'statusCode': 409}), 409

    try:
        attach_volume(instance['libvirt_name'], volume_id, device_name)
    except RuntimeError as e:
        return jsonify({'error': 'LIBVIRT_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    update_volume_status(volume_id, 'in-use', vm_id=vm_id, device_name=device_name)
    return jsonify({
        'message':     'Volume attached',
        'device_name': device_name,
        'volume':      get_volume(volume_id),
    }), 200


@storage_bp.route('/volumes/<volume_id>/detach', methods=['POST'])
@require_auth
def detach_vol(volume_id):
    volume = get_volume(volume_id, g.current_user['id'])
    if not volume:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Volume not found', 'statusCode': 404}), 404
    if volume['status'] != 'in-use':
        return jsonify({'error': 'NOT_ATTACHED',
                        'message': 'Volume is not attached to any instance',
                        'statusCode': 409}), 409

    instance = _get_instance_for_user(volume['vm_id'], g.current_user['id'])
    if not instance:
        # Instance was deleted without detaching — just clear the DB record.
        update_volume_status(volume_id, 'available')
        return jsonify({'message': 'Volume record cleared (instance no longer exists)'}), 200

    try:
        detach_volume(instance['libvirt_name'], volume_id, volume['device_name'])
    except RuntimeError as e:
        return jsonify({'error': 'LIBVIRT_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    update_volume_status(volume_id, 'available')
    return jsonify({'message': 'Volume detached', 'volume': get_volume(volume_id)}), 200


@storage_bp.route('/volumes/<volume_id>/snapshot', methods=['POST'])
@require_auth
def snapshot_vol(volume_id):
    volume = get_volume(volume_id, g.current_user['id'])
    if not volume:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Volume not found', 'statusCode': 404}), 404

    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name is required', 'statusCode': 400}), 400
    if len(name) > MAX_SNAP_NAME_LEN:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': f'name must be under {MAX_SNAP_NAME_LEN} characters',
                        'statusCode': 400}), 400

    # Snapshot COW space = 20% of volume, minimum 1 GB.
    # The snap LV will overflow (and become invalid) if the origin writes more than this.
    snap_size_gb = max(1, volume['size_gb'] // 5)

    snap_id = create_snapshot(g.current_user['id'], name, volume_id, snap_size_gb)
    try:
        create_lv_snapshot(volume_id, snap_id, snap_size_gb)
    except RuntimeError as e:
        delete_snapshot_record(snap_id)
        return jsonify({'error': 'LVM_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    return jsonify({'message': 'Snapshot created', 'snapshot': get_snapshot(snap_id)}), 201


# ── Snapshots ──────────────────────────────────────────────────────────────────

@storage_bp.route('/snapshots', methods=['GET'])
@require_auth
def list_all_snapshots():
    snaps = list_snapshots(g.current_user['id'])
    return jsonify({'snapshots': snaps, 'count': len(snaps)}), 200


@storage_bp.route('/snapshots/<snap_id>/restore', methods=['POST'])
@require_auth
def restore_snap(snap_id):
    snap = get_snapshot(snap_id, g.current_user['id'])
    if not snap:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Snapshot not found', 'statusCode': 404}), 404

    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'name is required for the restored volume', 'statusCode': 400}), 400

    new_volume_id = create_volume(
        g.current_user['id'], name, snap['size_gb'],
        source_snapshot_id=snap_id,
    )
    try:
        restore_lv_from_snapshot(snap_id, new_volume_id, snap['size_gb'])
    except RuntimeError as e:
        delete_volume_record(new_volume_id)
        return jsonify({'error': 'LVM_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    return jsonify({
        'message': 'Volume restored from snapshot',
        'volume':  get_volume(new_volume_id),
    }), 201


@storage_bp.route('/snapshots/<snap_id>', methods=['DELETE'])
@require_auth
def delete_snap(snap_id):
    snap = get_snapshot(snap_id, g.current_user['id'])
    if not snap:
        return jsonify({'error': 'NOT_FOUND',
                        'message': 'Snapshot not found', 'statusCode': 404}), 404

    # Block deletion if volumes were cloned from this snapshot — they depend on its LV data.
    if snapshot_has_restored_volumes(snap_id):
        return jsonify({'error': 'SNAPSHOT_HAS_CHILDREN',
                        'message': 'Delete all volumes restored from this snapshot first',
                        'statusCode': 409}), 409

    try:
        delete_lv_snapshot(snap_id)
    except RuntimeError as e:
        return jsonify({'error': 'LVM_ERROR',
                        'message': str(e), 'statusCode': 500}), 500

    delete_snapshot_record(snap_id)
    return jsonify({'message': 'Snapshot deleted'}), 200
