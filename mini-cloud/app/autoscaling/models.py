import uuid
from datetime import datetime, timezone
from app.database import get_connection


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── ASG CRUD ──────────────────────────────────────────────────────────────────

def create_asg(user_id, name, image_id, flavor, network_id, keypair_id,
               security_group_id, min_instances, max_instances,
               scale_up_threshold, scale_down_threshold, cooldown_seconds):
    asg_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO autoscaling_groups
               (id, user_id, name, image_id, flavor, network_id, keypair_id,
                security_group_id, min_instances, max_instances,
                scale_up_threshold, scale_down_threshold, cooldown_seconds,
                lb_id, lb_member_port, last_action_at, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, 'active', ?)''',
            (asg_id, user_id, name, image_id, flavor, network_id, keypair_id,
             security_group_id, min_instances, max_instances,
             scale_up_threshold, scale_down_threshold, cooldown_seconds, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return asg_id


def get_asg(asg_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM autoscaling_groups WHERE id = ? AND user_id = ?',
                (asg_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM autoscaling_groups WHERE id = ?', (asg_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_asgs(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM autoscaling_groups WHERE user_id = ? AND status != 'deleting' ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_all_active_asgs():
    # Returns all active ASGs across all users — called by the monitor thread every 30 s
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM autoscaling_groups WHERE status = 'active'"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_asg_status(asg_id, status):
    conn = get_connection()
    try:
        conn.execute('UPDATE autoscaling_groups SET status = ? WHERE id = ?', (status, asg_id))
        conn.commit()
    finally:
        conn.close()


def update_asg_policy(asg_id, scale_up_threshold, scale_down_threshold, cooldown_seconds):
    conn = get_connection()
    try:
        conn.execute(
            '''UPDATE autoscaling_groups
               SET scale_up_threshold = ?, scale_down_threshold = ?, cooldown_seconds = ?
               WHERE id = ?''',
            (scale_up_threshold, scale_down_threshold, cooldown_seconds, asg_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_asg_lb(asg_id, lb_id, lb_member_port):
    conn = get_connection()
    try:
        conn.execute(
            'UPDATE autoscaling_groups SET lb_id = ?, lb_member_port = ? WHERE id = ?',
            (lb_id, lb_member_port, asg_id),
        )
        conn.commit()
    finally:
        conn.close()


def detach_asg_lb(asg_id):
    conn = get_connection()
    try:
        conn.execute(
            'UPDATE autoscaling_groups SET lb_id = NULL, lb_member_port = NULL WHERE id = ?',
            (asg_id,),
        )
        conn.commit()
    finally:
        conn.close()


def record_last_action(asg_id):
    conn = get_connection()
    try:
        conn.execute(
            'UPDATE autoscaling_groups SET last_action_at = ? WHERE id = ?',
            (_now(), asg_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_asg(asg_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM asg_events WHERE asg_id = ?', (asg_id,))
        conn.execute('DELETE FROM asg_instances WHERE asg_id = ?', (asg_id,))
        conn.execute('DELETE FROM autoscaling_groups WHERE id = ?', (asg_id,))
        conn.commit()
    finally:
        conn.close()


# ── ASG Instances ─────────────────────────────────────────────────────────────

def add_asg_instance(asg_id, vm_id):
    record_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            'INSERT INTO asg_instances (id, asg_id, vm_id, launched_at) VALUES (?, ?, ?, ?)',
            (record_id, asg_id, vm_id, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return record_id


def remove_asg_instance(vm_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM asg_instances WHERE vm_id = ?', (vm_id,))
        conn.commit()
    finally:
        conn.close()


def get_asg_instances(asg_id):
    # Joins with the instances table so callers get full VM details in one query
    conn = get_connection()
    try:
        rows = conn.execute(
            '''SELECT ai.launched_at as asg_launched_at,
                      i.id as vm_id, i.name, i.status, i.ip_address, i.flavor,
                      i.vcpus, i.ram_mb, i.libvirt_name, i.created_at
               FROM asg_instances ai
               JOIN instances i ON i.id = ai.vm_id
               WHERE ai.asg_id = ? AND i.status != 'terminated'
               ORDER BY ai.launched_at''',
            (asg_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_asg_instance_count(asg_id):
    conn = get_connection()
    try:
        row = conn.execute(
            '''SELECT COUNT(*) FROM asg_instances ai
               JOIN instances i ON i.id = ai.vm_id
               WHERE ai.asg_id = ? AND i.status != 'terminated' ''',
            (asg_id,),
        ).fetchone()
        return row[0]
    finally:
        conn.close()


def get_newest_asg_instance(asg_id):
    # Returns the most recently launched VM — the one terminated on scale-down
    conn = get_connection()
    try:
        row = conn.execute(
            '''SELECT i.id as vm_id, i.libvirt_name, i.ip_address
               FROM asg_instances ai
               JOIN instances i ON i.id = ai.vm_id
               WHERE ai.asg_id = ? AND i.status != 'terminated'
               ORDER BY ai.launched_at DESC LIMIT 1''',
            (asg_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def is_asg_instance(vm_id):
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT id FROM asg_instances WHERE vm_id = ?', (vm_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ── Scaling Events ────────────────────────────────────────────────────────────

def record_scaling_event(asg_id, action, instance_count, avg_cpu, reason):
    event_id = str(uuid.uuid4())
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO asg_events (id, asg_id, action, instance_count, avg_cpu, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (event_id, asg_id, action, instance_count, avg_cpu, reason, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def get_scaling_history(asg_id, limit=50):
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT * FROM asg_events WHERE asg_id = ? ORDER BY created_at DESC LIMIT ?',
            (asg_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
