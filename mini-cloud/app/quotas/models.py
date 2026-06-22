from app.database import get_connection

# All quota resource types tracked in this system
RESOURCE_TYPES = [
    'instances', 'vcpus', 'ram_mb',
    'volumes', 'volume_gb',
    'floating_ips', 'security_groups', 'security_group_rules', 'key_pairs',
]


def get_user_quota(user_id, resource_type):
    # Returns the effective limit: user override if one exists, else system default.
    # This two-table lookup is why we don't use a single "user quotas" table.
    conn = get_connection()
    try:
        row = conn.execute(
            'SELECT limit_value FROM quota_user_overrides WHERE user_id=? AND resource_type=?',
            (user_id, resource_type),
        ).fetchone()
        if row:
            return row['limit_value']

        row = conn.execute(
            'SELECT limit_value FROM quota_defaults WHERE resource_type=?',
            (resource_type,),
        ).fetchone()
        return row['limit_value'] if row else 0
    finally:
        conn.close()


def get_current_usage(user_id, resource_type):
    # Counts live resource usage directly from the source tables — no cached counter.
    # A cached counter would go stale on crashes or manual DB edits; counting is safer.
    conn = get_connection()
    try:
        if resource_type == 'instances':
            row = conn.execute(
                "SELECT COUNT(*) FROM instances WHERE user_id=? AND status != 'terminated'",
                (user_id,),
            ).fetchone()

        elif resource_type == 'vcpus':
            # Only count vCPUs for instances that are actively running — stopped
            # instances release their virtual CPU slots back to the pool.
            row = conn.execute(
                "SELECT COALESCE(SUM(vcpus), 0) FROM instances "
                "WHERE user_id=? AND status NOT IN ('terminated', 'stopped', 'error')",
                (user_id,),
            ).fetchone()

        elif resource_type == 'ram_mb':
            row = conn.execute(
                "SELECT COALESCE(SUM(ram_mb), 0) FROM instances "
                "WHERE user_id=? AND status NOT IN ('terminated', 'stopped', 'error')",
                (user_id,),
            ).fetchone()

        elif resource_type == 'volumes':
            row = conn.execute(
                'SELECT COUNT(*) FROM volumes WHERE user_id=?',
                (user_id,),
            ).fetchone()

        elif resource_type == 'volume_gb':
            row = conn.execute(
                'SELECT COALESCE(SUM(size_gb), 0) FROM volumes WHERE user_id=?',
                (user_id,),
            ).fetchone()

        elif resource_type == 'floating_ips':
            row = conn.execute(
                'SELECT COUNT(*) FROM floating_ips WHERE user_id=?',
                (user_id,),
            ).fetchone()

        elif resource_type == 'security_groups':
            row = conn.execute(
                'SELECT COUNT(*) FROM security_groups WHERE user_id=?',
                (user_id,),
            ).fetchone()

        elif resource_type == 'security_group_rules':
            # Count all rules across every group owned by this user
            row = conn.execute(
                '''SELECT COUNT(*) FROM security_group_rules
                   WHERE group_id IN (SELECT id FROM security_groups WHERE user_id=?)''',
                (user_id,),
            ).fetchone()

        elif resource_type == 'key_pairs':
            row = conn.execute(
                'SELECT COUNT(*) FROM keypairs WHERE user_id=?',
                (user_id,),
            ).fetchone()

        else:
            return 0

        return row[0]
    finally:
        conn.close()


def check_quota(user_id, resource_type, requested_amount=1):
    # Returns (allowed: bool, limit: int, used: int).
    # Caller uses limit/used in the 403 error message so users know exactly where they stand.
    limit = get_user_quota(user_id, resource_type)
    used  = get_current_usage(user_id, resource_type)
    return (used + requested_amount) <= limit, limit, used


def get_all_quotas(user_id):
    # Build the full quota summary in one call — used by GET /api/v1/quotas
    result = {}
    for resource_type in RESOURCE_TYPES:
        limit = get_user_quota(user_id, resource_type)
        used  = get_current_usage(user_id, resource_type)
        result[resource_type] = {
            'limit':     limit,
            'used':      used,
            'available': max(0, limit - used),
        }
    return result


def set_user_quota_override(user_id, resource_type, limit_value):
    # UPSERT: insert or replace so admin can call PUT repeatedly without errors
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO quota_user_overrides (user_id, resource_type, limit_value)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, resource_type) DO UPDATE SET limit_value=excluded.limit_value''',
            (user_id, resource_type, limit_value),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user_quota_override(user_id, resource_type):
    conn = get_connection()
    try:
        conn.execute(
            'DELETE FROM quota_user_overrides WHERE user_id=? AND resource_type=?',
            (user_id, resource_type),
        )
        conn.commit()
    finally:
        conn.close()


def get_quota_defaults():
    conn = get_connection()
    try:
        rows = conn.execute('SELECT resource_type, limit_value FROM quota_defaults').fetchall()
        return {r['resource_type']: r['limit_value'] for r in rows}
    finally:
        conn.close()


def set_quota_default(resource_type, limit_value):
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO quota_defaults (resource_type, limit_value) VALUES (?, ?)
               ON CONFLICT(resource_type) DO UPDATE SET limit_value=excluded.limit_value''',
            (resource_type, limit_value),
        )
        conn.commit()
    finally:
        conn.close()


def get_all_users_with_quotas():
    # Admin view: list every user with their current usage and effective limits
    conn = get_connection()
    try:
        users = conn.execute(
            'SELECT id, username, email, role FROM users WHERE is_active=1 ORDER BY username',
        ).fetchall()
    finally:
        conn.close()

    result = []
    for user in users:
        quotas = get_all_quotas(user['id'])
        overrides = _get_user_overrides(user['id'])
        result.append({
            'id':        user['id'],
            'username':  user['username'],
            'email':     user['email'],
            'role':      user['role'],
            'quotas':    quotas,
            'overrides': overrides,
        })
    return result


def _get_user_overrides(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            'SELECT resource_type, limit_value FROM quota_user_overrides WHERE user_id=?',
            (user_id,),
        ).fetchall()
        return {r['resource_type']: r['limit_value'] for r in rows}
    finally:
        conn.close()
