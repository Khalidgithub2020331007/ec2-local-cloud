import jwt
from functools import wraps
from flask import request, jsonify, g
from config import JWT_SECRET
from app.auth.models import get_user_by_id


def require_auth(f):
    # Bearer token validate করে এবং g.current_user set করে দেয়
    # Route handler-কে আলাদা করে DB query করতে হয় না
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'error': 'UNAUTHORIZED',
                'message': 'Authorization: Bearer <token> header required',
                'statusCode': 401,
            }), 401

        token = auth_header[7:]  # "Bearer " prefix বাদ দেওয়া হচ্ছে
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({
                'error': 'TOKEN_EXPIRED',
                'message': 'Token expired, please login again',
                'statusCode': 401,
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                'error': 'INVALID_TOKEN',
                'message': 'Token is invalid or tampered',
                'statusCode': 401,
            }), 401

        user = get_user_by_id(payload.get('user_id'))
        if not user or not user['is_active']:
            return jsonify({
                'error': 'USER_NOT_FOUND',
                'message': 'Account no longer exists or has been disabled',
                'statusCode': 401,
            }), 401

        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def require_admin(f):
    # require_auth এর পরে ব্যবহার করতে হবে — g.current_user আগে set থাকতে হবে
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(g, 'current_user') or g.current_user.get('role') != 'admin':
            return jsonify({
                'error': 'FORBIDDEN',
                'message': 'Admin role required',
                'statusCode': 403,
            }), 403
        return f(*args, **kwargs)

    return decorated
