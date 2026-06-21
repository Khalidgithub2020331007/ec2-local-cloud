import uuid
import hashlib
import base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from app.database import get_connection


def generate_rsa_keypair():
    # 2048-bit RSA is the minimum recommended size still widely supported by SSH clients.
    # TraditionalOpenSSL format (PEM) is what ssh-keygen outputs — most clients expect this.
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')

    public_openssh = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode('utf-8')

    return private_pem, public_openssh


def compute_fingerprint(public_key_str):
    # MD5 of the raw key bytes (base64-decoded middle token) — same format ssh-keygen -l shows.
    # Only the base64 blob matters; the "ssh-rsa" prefix and trailing comment are metadata.
    key_b64 = public_key_str.strip().split()[1]
    key_bytes = base64.b64decode(key_b64)
    md5_hex = hashlib.md5(key_bytes).hexdigest()
    return ':'.join(md5_hex[i:i + 2] for i in range(0, 32, 2))


def create_keypair(user_id, name, public_key, fingerprint):
    keypair_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        'INSERT INTO keypairs (id, user_id, name, public_key, fingerprint, created_at) VALUES (?,?,?,?,?,?)',
        (keypair_id, user_id, name, public_key, fingerprint, created_at),
    )
    conn.commit()
    conn.close()
    return keypair_id


def get_keypair(keypair_id, user_id=None):
    conn = get_connection()
    if user_id:
        row = conn.execute(
            'SELECT id, user_id, name, public_key, fingerprint, created_at FROM keypairs WHERE id=? AND user_id=?',
            (keypair_id, user_id),
        ).fetchone()
    else:
        row = conn.execute(
            'SELECT id, user_id, name, public_key, fingerprint, created_at FROM keypairs WHERE id=?',
            (keypair_id,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_keypairs(user_id):
    conn = get_connection()
    rows = conn.execute(
        'SELECT id, name, fingerprint, created_at FROM keypairs WHERE user_id=? ORDER BY created_at DESC',
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_keypair(keypair_id, user_id):
    conn = get_connection()
    cursor = conn.execute(
        'DELETE FROM keypairs WHERE id=? AND user_id=?',
        (keypair_id, user_id),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
