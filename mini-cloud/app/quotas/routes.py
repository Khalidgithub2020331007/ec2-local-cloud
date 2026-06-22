from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth, require_admin
from app.quotas.models import (
    get_all_quotas, get_quota_defaults, set_quota_default,
    set_user_quota_override, delete_user_quota_override,
    get_all_users_with_quotas, RESOURCE_TYPES,
)

quotas_bp = Blueprint('quotas', __name__, url_prefix='/api/v1/quotas')


@quotas_bp.route('', methods=['GET'])
@require_auth
def my_quotas():
    # Returns the calling user's current usage and limits for every resource type
    return jsonify(get_all_quotas(g.current_user['id'])), 200


@quotas_bp.route('/defaults', methods=['GET'])
@require_auth
def list_defaults():
    return jsonify({'defaults': get_quota_defaults()}), 200


@quotas_bp.route('/defaults', methods=['PUT'])
@require_auth
@require_admin
def update_defaults():
    # Admin can update system-wide defaults for one or many resource types at once
    data = request.get_json(silent=True) or {}
    updated = {}
    errors  = []

    for resource_type, limit_value in data.items():
        if resource_type not in RESOURCE_TYPES:
            errors.append(f'Unknown resource type: {resource_type}')
            continue
        try:
            limit_value = int(limit_value)
        except (TypeError, ValueError):
            errors.append(f'{resource_type}: limit_value must be an integer')
            continue
        if limit_value < 0:
            errors.append(f'{resource_type}: limit_value cannot be negative')
            continue
        set_quota_default(resource_type, limit_value)
        updated[resource_type] = limit_value

    if errors:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': '; '.join(errors), 'statusCode': 400}), 400

    return jsonify({'message': 'Defaults updated', 'updated': updated, 'defaults': get_quota_defaults()}), 200


@quotas_bp.route('/users', methods=['GET'])
@require_auth
@require_admin
def list_all_users_quotas():
    # Admin-only: see every user's usage and their custom overrides
    return jsonify({'users': get_all_users_with_quotas()}), 200


@quotas_bp.route('/<user_id>', methods=['GET'])
@require_auth
def user_quotas(user_id):
    # Users can only view their own quota; admin can view anyone's
    if g.current_user['role'] != 'admin' and g.current_user['id'] != user_id:
        return jsonify({'error': 'FORBIDDEN', 'message': 'Admin role required to view other users\' quotas', 'statusCode': 403}), 403

    from app.auth.models import get_user_by_id
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'error': 'NOT_FOUND', 'message': 'User not found', 'statusCode': 404}), 404

    return jsonify(get_all_quotas(user_id)), 200


@quotas_bp.route('/<user_id>', methods=['PUT'])
@require_auth
@require_admin
def update_user_quota(user_id):
    # Admin sets or removes custom limits per user per resource type.
    # Pass limit_value: null to remove the override and revert to the system default.
    from app.auth.models import get_user_by_id
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'error': 'NOT_FOUND', 'message': 'User not found', 'statusCode': 404}), 404

    data    = request.get_json(silent=True) or {}
    updated = {}
    removed = []
    errors  = []

    for resource_type, limit_value in data.items():
        if resource_type not in RESOURCE_TYPES:
            errors.append(f'Unknown resource type: {resource_type}')
            continue

        if limit_value is None:
            # null → remove override, revert to default
            delete_user_quota_override(user_id, resource_type)
            removed.append(resource_type)
            continue

        try:
            limit_value = int(limit_value)
        except (TypeError, ValueError):
            errors.append(f'{resource_type}: limit_value must be an integer or null')
            continue
        if limit_value < 0:
            errors.append(f'{resource_type}: limit_value cannot be negative')
            continue

        set_user_quota_override(user_id, resource_type, limit_value)
        updated[resource_type] = limit_value

    if errors:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': '; '.join(errors), 'statusCode': 400}), 400

    return jsonify({
        'message': 'User quota updated',
        'user_id': user_id,
        'updated': updated,
        'removed': removed,
        'quotas':  get_all_quotas(user_id),
    }), 200
