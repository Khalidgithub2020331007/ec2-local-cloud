from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth, require_admin
from app.iam.models import (
    create_iam_user, list_iam_users, get_iam_user, delete_iam_user,
    create_iam_group, list_iam_groups, delete_iam_group,
    get_group_members, add_group_member, remove_group_member,
    create_iam_role, list_iam_roles, get_iam_role, delete_iam_role,
    create_iam_policy, list_iam_policies, get_iam_policy, delete_iam_policy,
    attach_policy, detach_policy, get_policies_for_entity,
    validate_policy_json,
)

iam_bp = Blueprint('iam', __name__, url_prefix='/api/v1/iam')

_VALID_SERVICES  = {'EC2', 'Lambda', 'S3', 'ECS', 'EKS'}
_VALID_ENT_TYPES = {'user', 'group', 'role'}


# ─── IAM Users ────────────────────────────────────────────────────────────────

@iam_bp.route('/users', methods=['GET'])
@require_auth
def list_users():
    return jsonify({'users': list_iam_users()}), 200


@iam_bp.route('/users', methods=['POST'])
@require_auth
@require_admin
def create_user():
    data     = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'username is required', 'statusCode': 400}), 400
    try:
        user = create_iam_user(username)
    except Exception as exc:
        if 'UNIQUE' in str(exc):
            return jsonify({'error': 'CONFLICT', 'message': 'IAM user with that username already exists', 'statusCode': 409}), 409
        raise
    return jsonify({'user': user}), 201


@iam_bp.route('/users/<user_id>', methods=['DELETE'])
@require_auth
@require_admin
def delete_user(user_id):
    if not get_iam_user(user_id):
        return jsonify({'error': 'NOT_FOUND', 'message': 'IAM user not found', 'statusCode': 404}), 404
    delete_iam_user(user_id)
    return jsonify({'message': 'IAM user deleted'}), 200


# ─── IAM Groups ───────────────────────────────────────────────────────────────

@iam_bp.route('/groups', methods=['GET'])
@require_auth
def list_groups():
    return jsonify({'groups': list_iam_groups()}), 200


@iam_bp.route('/groups', methods=['POST'])
@require_auth
@require_admin
def create_group():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    try:
        group = create_iam_group(name)
    except Exception as exc:
        if 'UNIQUE' in str(exc):
            return jsonify({'error': 'CONFLICT', 'message': 'Group with that name already exists', 'statusCode': 409}), 409
        raise
    return jsonify({'group': group}), 201


@iam_bp.route('/groups/<group_id>', methods=['DELETE'])
@require_auth
@require_admin
def delete_group(group_id):
    delete_iam_group(group_id)
    return jsonify({'message': 'IAM group deleted'}), 200


@iam_bp.route('/groups/<group_id>/members', methods=['GET'])
@require_auth
def list_members(group_id):
    return jsonify({'members': get_group_members(group_id)}), 200


@iam_bp.route('/groups/<group_id>/members', methods=['POST'])
@require_auth
@require_admin
def add_member(group_id):
    data    = request.get_json(silent=True) or {}
    user_id = data.get('user_id', '').strip()
    if not user_id:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'user_id is required', 'statusCode': 400}), 400
    if not get_iam_user(user_id):
        return jsonify({'error': 'NOT_FOUND', 'message': 'IAM user not found', 'statusCode': 404}), 404
    add_group_member(group_id, user_id)
    return jsonify({'message': 'User added to group'}), 200


@iam_bp.route('/groups/<group_id>/members/<user_id>', methods=['DELETE'])
@require_auth
@require_admin
def remove_member(group_id, user_id):
    remove_group_member(group_id, user_id)
    return jsonify({'message': 'User removed from group'}), 200


# ─── IAM Roles ────────────────────────────────────────────────────────────────

@iam_bp.route('/roles', methods=['GET'])
@require_auth
def list_roles():
    return jsonify({'roles': list_iam_roles()}), 200


@iam_bp.route('/roles', methods=['POST'])
@require_auth
@require_admin
def create_role():
    data            = request.get_json(silent=True) or {}
    name            = data.get('name', '').strip()
    description     = data.get('description', '').strip()
    trusted_service = data.get('trusted_service', '').strip()

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if trusted_service not in _VALID_SERVICES:
        return jsonify({
            'error': 'VALIDATION_ERROR',
            'message': f'trusted_service must be one of: {", ".join(sorted(_VALID_SERVICES))}',
            'statusCode': 400,
        }), 400
    try:
        role = create_iam_role(name, description, trusted_service)
    except Exception as exc:
        if 'UNIQUE' in str(exc):
            return jsonify({'error': 'CONFLICT', 'message': 'Role with that name already exists', 'statusCode': 409}), 409
        raise
    return jsonify({'role': role}), 201


@iam_bp.route('/roles/<role_id>', methods=['DELETE'])
@require_auth
@require_admin
def delete_role(role_id):
    delete_iam_role(role_id)
    return jsonify({'message': 'IAM role deleted'}), 200


# ─── IAM Policies ─────────────────────────────────────────────────────────────

@iam_bp.route('/policies', methods=['GET'])
@require_auth
def list_policies():
    return jsonify({'policies': list_iam_policies()}), 200


@iam_bp.route('/policies', methods=['POST'])
@require_auth
@require_admin
def create_policy():
    data        = request.get_json(silent=True) or {}
    name        = data.get('name', '').strip()
    description = data.get('description', '').strip()
    policy_json = data.get('policy_json', '').strip()

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if not policy_json:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'policy_json is required', 'statusCode': 400}), 400

    valid, err = validate_policy_json(policy_json)
    if not valid:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': err, 'statusCode': 400}), 400

    try:
        policy = create_iam_policy(name, description, policy_json)
    except Exception as exc:
        if 'UNIQUE' in str(exc):
            return jsonify({'error': 'CONFLICT', 'message': 'Policy with that name already exists', 'statusCode': 409}), 409
        raise
    return jsonify({'policy': policy}), 201


@iam_bp.route('/policies/<policy_id>', methods=['DELETE'])
@require_auth
@require_admin
def delete_policy(policy_id):
    policy = get_iam_policy(policy_id)
    if not policy:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Policy not found', 'statusCode': 404}), 404
    # AWS-managed policies are permanent and cannot be removed
    if policy['type'] == 'managed':
        return jsonify({'error': 'FORBIDDEN', 'message': 'AWS Managed policies cannot be deleted', 'statusCode': 403}), 403
    delete_iam_policy(policy_id)
    return jsonify({'message': 'Policy deleted'}), 200


@iam_bp.route('/policies/<policy_id>/json', methods=['GET'])
@require_auth
def get_policy_json(policy_id):
    policy = get_iam_policy(policy_id)
    if not policy:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Policy not found', 'statusCode': 404}), 404
    return jsonify({'policy_json': policy['policy_json']}), 200


@iam_bp.route('/policies/<policy_id>/attach', methods=['POST'])
@require_auth
@require_admin
def attach(policy_id):
    data        = request.get_json(silent=True) or {}
    entity_type = data.get('entity_type', '').strip()
    entity_id   = data.get('entity_id', '').strip()

    if entity_type not in _VALID_ENT_TYPES:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'entity_type must be user, group, or role', 'statusCode': 400}), 400
    if not entity_id:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'entity_id is required', 'statusCode': 400}), 400
    if not get_iam_policy(policy_id):
        return jsonify({'error': 'NOT_FOUND', 'message': 'Policy not found', 'statusCode': 404}), 404

    attach_policy(policy_id, entity_type, entity_id)
    return jsonify({'message': 'Policy attached'}), 200


@iam_bp.route('/policies/<policy_id>/detach', methods=['POST'])
@require_auth
@require_admin
def detach(policy_id):
    data        = request.get_json(silent=True) or {}
    entity_type = data.get('entity_type', '').strip()
    entity_id   = data.get('entity_id', '').strip()

    if entity_type not in _VALID_ENT_TYPES:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'entity_type must be user, group, or role', 'statusCode': 400}), 400
    if not entity_id:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'entity_id is required', 'statusCode': 400}), 400

    detach_policy(policy_id, entity_type, entity_id)
    return jsonify({'message': 'Policy detached'}), 200


@iam_bp.route('/entities/<entity_type>/<entity_id>/policies', methods=['GET'])
@require_auth
def entity_policies(entity_type, entity_id):
    # Returns all policies currently attached to a given user, group, or role
    if entity_type not in _VALID_ENT_TYPES:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'entity_type must be user, group, or role', 'statusCode': 400}), 400
    return jsonify({'policies': get_policies_for_entity(entity_type, entity_id)}), 200
