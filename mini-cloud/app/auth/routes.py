import jwt
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from app.auth.models import (
    create_user,
    get_user_by_username,
    verify_password,
    create_api_key,
    list_api_keys,
    delete_api_key,
)
from app.auth.middleware import require_auth
from config import JWT_SECRET, JWT_EXPIRY_HOURS

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not username or not email or not password:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'username, email, and password are required', 'statusCode': 400}), 400

    if len(username) < 3 or len(username) > 32:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'Username must be 3–32 characters', 'statusCode': 400}), 400

    if len(password) < 8:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'Password must be at least 8 characters', 'statusCode': 400}), 400

    if '@' not in email:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'Invalid email address', 'statusCode': 400}), 400

    try:
        user = create_user(username, email, password)
        return jsonify({
            'message': 'Account created successfully',
            'user': {'id': user['id'], 'username': user['username'], 'email': user['email']},
        }), 201
    except Exception as e:
        if 'UNIQUE constraint failed' in str(e):
            return jsonify({'error': 'CONFLICT', 'message': 'Username or email already exists', 'statusCode': 409}), 409
        return jsonify({'error': 'SERVER_ERROR', 'message': 'Failed to create account', 'statusCode': 500}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'username and password are required', 'statusCode': 400}), 400

    user = get_user_by_username(username)
    # Timing-safe: wrong username এবং wrong password-এ একই error দেওয়া হয়
    # আলাদা error দিলে attacker username enumerate করতে পারে
    if not user or not verify_password(user, password):
        return jsonify({'error': 'INVALID_CREDENTIALS', 'message': 'Invalid username or password', 'statusCode': 401}), 401

    expiry = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    token = jwt.encode(
        {'user_id': user['id'], 'username': user['username'], 'role': user['role'], 'exp': expiry},
        JWT_SECRET,
        algorithm='HS256',
    )

    return jsonify({
        'message': 'Login successful',
        'token': token,
        'expires_at': expiry.isoformat(),
        'user': {'id': user['id'], 'username': user['username'], 'email': user['email'], 'role': user['role']},
    }), 200


@auth_bp.route('/me', methods=['GET'])
@require_auth
def me():
    # Token valid হলে current user এর info দেয় — dashboard এ user info দেখানোর জন্য
    return jsonify({'user': g.current_user}), 200


@auth_bp.route('/keys', methods=['GET'])
@require_auth
def list_keys():
    keys = list_api_keys(g.current_user['id'])
    return jsonify({'api_keys': keys, 'count': len(keys)}), 200


@auth_bp.route('/keys', methods=['POST'])
@require_auth
def create_key():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400

    key = create_api_key(g.current_user['id'], name)
    return jsonify({
        'message': 'API key created. Save the secret_key now — it will NOT be shown again.',
        'api_key': key,
    }), 201


@auth_bp.route('/keys/<key_id>', methods=['DELETE'])
@require_auth
def delete_key(key_id):
    deleted = delete_api_key(key_id, g.current_user['id'])
    if not deleted:
        return jsonify({'error': 'NOT_FOUND', 'message': 'API key not found', 'statusCode': 404}), 404
    return jsonify({'message': 'API key deleted successfully'}), 200
