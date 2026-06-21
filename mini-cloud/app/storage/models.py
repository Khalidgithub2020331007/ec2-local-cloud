import uuid
from datetime import datetime
from app.database import get_connection


def _new_id():
    return str(uuid.uuid4())


def _now():
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


# ── Volumes ────────────────────────────────────────────────────────────────────

def create_volume(user_id, name, size_gb, source_snapshot_id=None):
    volume_id = _new_id()
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO volumes
               (id, user_id, name, size_gb, status, source_snapshot_id, created_at)
               VALUES (?, ?, ?, ?, 'available', ?, ?)''',
            (volume_id, user_id, name, size_gb, source_snapshot_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return volume_id


def get_volume(volume_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM volumes WHERE id=? AND user_id=?', (volume_id, user_id)
            ).fetchone()
        else:
            row = conn.execute('SELECT * FROM volumes WHERE id=?', (volume_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_volumes(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT * FROM volumes WHERE user_id=? ORDER BY created_at DESC', (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_volume_status(volume_id, status, vm_id=None, device_name=None):
    conn = get_connection()
    try:
        conn.execute(
            'UPDATE volumes SET status=?, vm_id=?, device_name=? WHERE id=?',
            (status, vm_id, device_name, volume_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_volume_record(volume_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM volumes WHERE id=?', (volume_id,))
        conn.commit()
    finally:
        conn.close()


def find_next_device(vm_id):
    # vda is always the boot disk — start scanning from vdb.
    # Letters b–z give 25 possible data disks, which is more than enough.
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT device_name FROM volumes WHERE vm_id=? AND status='in-use'", (vm_id,)
        ).fetchall()
    finally:
        conn.close()

    used = {r['device_name'] for r in rows if r['device_name']}
    for letter in 'bcdefghijklmnopqrstuvwxyz':
        candidate = f'vd{letter}'
        if candidate not in used:
            return candidate

    raise RuntimeError('No free virtio device slots — all vdb–vdz are occupied')


# ── Snapshots ──────────────────────────────────────────────────────────────────

def create_snapshot(user_id, name, volume_id, size_gb):
    snap_id = _new_id()
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO snapshots
               (id, user_id, name, volume_id, size_gb, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'available', ?)''',
            (snap_id, user_id, name, volume_id, size_gb, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return snap_id


def get_snapshot(snapshot_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM snapshots WHERE id=? AND user_id=?', (snapshot_id, user_id)
            ).fetchone()
        else:
            row = conn.execute('SELECT * FROM snapshots WHERE id=?', (snapshot_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_snapshots(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT * FROM snapshots WHERE user_id=? ORDER BY created_at DESC', (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_snapshot_record(snapshot_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM snapshots WHERE id=?', (snapshot_id,))
        conn.commit()
    finally:
        conn.close()


def snapshot_has_restored_volumes(snapshot_id):
    # If any volume was cloned from this snapshot, deleting it would orphan that volume's backing data.
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT COUNT(*) FROM volumes WHERE source_snapshot_id=?', (snapshot_id,)
        ).fetchone()
        return row[0] > 0
    finally:
        conn.close()
