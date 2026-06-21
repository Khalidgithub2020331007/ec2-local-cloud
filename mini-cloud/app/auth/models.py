import uuid
import secrets
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.database import get_connection
from config import ACCESS_KEY_PREFIX


def create_user(username, email, password, role='user'):
    # bcrypt-style hash — werkzeug internally uses pbkdf2:sha256
    password_hash = generate_password_hash(password)
    user_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            'INSERT INTO users (id, username, email, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)',
            (user_id, username, email, password_hash, role, created_at),
        )
        conn.commit()
        return {'id': user_id, 'username': username, 'email': email, 'role': role}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM users WHERE username = ? AND is_active = 1', (username,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id):
    # password_hash কে SELECT এ বাদ দেওয়া হয়েছে — token payload এ কখনো পাঠানো যাবে না
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id, username, email, role, is_active, created_at FROM users WHERE id = ?',
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def verify_password(user, plain_password):
    return check_password_hash(user['password_hash'], plain_password)


def create_api_key(user_id, name):
    # Access key: MCLD + 16 hex chars uppercase (like AWS: AKIAIOSFODNN7EXAMPLE)
    access_key = ACCESS_KEY_PREFIX + secrets.token_hex(8).upper()
    # Secret key: 40-char URL-safe random string (like AWS secret access key)
    secret_key = secrets.token_urlsafe(30)
    key_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            'INSERT INTO api_keys (id, user_id, access_key, secret_key, name, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)',
            (key_id, user_id, access_key, secret_key, name, created_at),
        )
        conn.commit()
        # secret_key এখানে একবারই return হয় — DB তে store হওয়ার পরে আর retrieve করা যাবে না
        return {
            'id': key_id,
            'access_key': access_key,
            'secret_key': secret_key,
            'name': name,
            'created_at': created_at,
        }
    finally:
        conn.close()


def list_api_keys(user_id):
    # secret_key list-এ দেখানো হয় না — শুধু create-এর সময় একবার দেখানো হয়
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT id, access_key, name, is_active, created_at FROM api_keys WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_api_key(key_id, user_id):
    conn = get_connection()
    try:
        result = conn.execute(
            'DELETE FROM api_keys WHERE id = ? AND user_id = ?', (key_id, user_id)
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def get_user_by_access_key(access_key):
    # API key authentication-এর জন্য — access_key দিয়ে user খোঁজে
    conn = get_connection()
    try:
        row = conn.execute(
            '''SELECT u.id, u.username, u.email, u.role, ak.secret_key
               FROM api_keys ak
               JOIN users u ON ak.user_id = u.id
               WHERE ak.access_key = ? AND ak.is_active = 1 AND u.is_active = 1''',
            (access_key,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
