import uuid
from datetime import datetime, timezone
from app.database import get_connection

MIN_PORT = 1025
MAX_PORT = 65535


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Load Balancer CRUD ────────────────────────────────────────────────────────

def create_lb(user_id, name, port, algorithm='roundrobin'):
    lb_id = str(uuid.uuid4())
    conn  = get_connection()
    try:
        conn.execute(
            '''INSERT INTO load_balancers (id, user_id, name, port, algorithm, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)''',
            (lb_id, user_id, name, port, algorithm, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return lb_id


def get_lb(lb_id):
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM load_balancers WHERE id = ?', (lb_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_lbs(user_id=None):
    conn = get_connection()
    try:
        if user_id:
            rows = conn.execute(
                'SELECT * FROM load_balancers WHERE user_id = ? ORDER BY created_at DESC',
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM load_balancers ORDER BY created_at DESC'
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_lb(lb_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM load_balancers WHERE id = ?', (lb_id,))
        conn.commit()
    finally:
        conn.close()


def port_in_use(port, exclude_lb_id=None):
    # Check if a port is already claimed by another LB — prevents two LBs binding the same port
    conn = get_connection()
    try:
        if exclude_lb_id:
            row = conn.execute(
                'SELECT id FROM load_balancers WHERE port = ? AND id != ?',
                (port, exclude_lb_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT id FROM load_balancers WHERE port = ?', (port,)
            ).fetchone()
        return row is not None
    finally:
        conn.close()


# ── Member CRUD ───────────────────────────────────────────────────────────────

def add_member(lb_id, vm_id, vm_private_ip, member_port):
    member_id = str(uuid.uuid4())
    conn      = get_connection()
    try:
        conn.execute(
            '''INSERT INTO lb_members (id, lb_id, vm_id, vm_private_ip, member_port, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)''',
            (member_id, lb_id, vm_id, vm_private_ip, member_port, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return member_id


def get_members(lb_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT * FROM lb_members WHERE lb_id = ? ORDER BY created_at',
            (lb_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_member_by_vm(lb_id, vm_id):
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT * FROM lb_members WHERE lb_id = ? AND vm_id = ?',
            (lb_id, vm_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def remove_member(lb_id, vm_id):
    conn = get_connection()
    try:
        conn.execute(
            'DELETE FROM lb_members WHERE lb_id = ? AND vm_id = ?',
            (lb_id, vm_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_lbs_with_members():
    # Returns all LBs with their members — used by haproxy_manager to build the full config
    conn = get_connection()
    try:
        lbs = [dict(r) for r in conn.execute(
            'SELECT * FROM load_balancers ORDER BY created_at'
        ).fetchall()]
        for lb in lbs:
            members = conn.execute(
                'SELECT * FROM lb_members WHERE lb_id = ? ORDER BY created_at',
                (lb['id'],),
            ).fetchall()
            lb['members'] = [dict(m) for m in members]
        return lbs
    finally:
        conn.close()
