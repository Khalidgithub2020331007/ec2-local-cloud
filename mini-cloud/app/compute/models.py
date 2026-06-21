import uuid
from datetime import datetime, timezone
from app.database import get_connection


def create_instance(user_id, name, flavor, vcpus, ram_mb, disk_gb,
                    libvirt_name, disk_path, image_path=None):
    instance_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO instances
               (id, user_id, name, flavor, vcpus, ram_mb, disk_gb,
                libvirt_name, disk_path, image_path, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
            (instance_id, user_id, name, flavor, vcpus, ram_mb, disk_gb,
             libvirt_name, disk_path, image_path, created_at),
        )
        conn.commit()
        return instance_id
    finally:
        conn.close()


def update_instance_status(instance_id, status, vnc_port=None, ip_address=None):
    conn = get_connection()
    try:
        if vnc_port is not None and ip_address is not None:
            conn.execute(
                'UPDATE instances SET status=?, vnc_port=?, ip_address=? WHERE id=?',
                (status, vnc_port, ip_address, instance_id),
            )
        elif vnc_port is not None:
            conn.execute(
                'UPDATE instances SET status=?, vnc_port=? WHERE id=?',
                (status, vnc_port, instance_id),
            )
        else:
            conn.execute(
                'UPDATE instances SET status=? WHERE id=?',
                (status, instance_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_instance(instance_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            # user_id check করা হয় — অন্য user এর instance দেখা যাবে না (IDOR prevention)
            row = conn.execute(
                'SELECT * FROM instances WHERE id=? AND user_id=?',
                (instance_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM instances WHERE id=?', (instance_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_instances(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            '''SELECT * FROM instances WHERE user_id=? AND status != 'terminated'
               ORDER BY created_at DESC''',
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_terminated(instance_id):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE instances SET status='terminated' WHERE id=?", (instance_id,)
        )
        conn.commit()
    finally:
        conn.close()
