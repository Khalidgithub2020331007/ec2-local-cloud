import json
import uuid
from datetime import datetime, timezone
from app.database import get_connection

_ACCOUNT_ID = '123456789012'


def _make_arn(entity_type, name):
    return f'arn:minicloud:iam::{_ACCOUNT_ID}:{entity_type}/{name}'


def _now():
    return datetime.now(timezone.utc).isoformat()


def _make_trust_policy(trusted_service):
    # sts:AssumeRole trust policy — the service listed here can call AssumeRole on this role
    doc = {
        'Version': '2012-10-17',
        'Statement': [{
            'Effect': 'Allow',
            'Principal': {'Service': trusted_service},
            'Action': 'sts:AssumeRole',
        }],
    }
    return json.dumps(doc, indent=2)


def validate_policy_json(policy_str):
    # Customer policies must be valid JSON with Version + Statement array
    try:
        doc = json.loads(policy_str)
    except ValueError:
        return False, 'Invalid JSON — could not parse the policy document'
    if 'Version' not in doc:
        return False, "Policy must include a 'Version' field (e.g. \"2012-10-17\")"
    if 'Statement' not in doc or not isinstance(doc['Statement'], list):
        return False, "Policy must include a 'Statement' array"
    return True, None


# ─── IAM Users ────────────────────────────────────────────────────────────────

def create_iam_user(username):
    conn = get_connection()
    uid  = str(uuid.uuid4())
    arn  = _make_arn('user', username)
    conn.execute(
        'INSERT INTO iam_users (id, username, arn, created_at) VALUES (?, ?, ?, ?)',
        (uid, username, arn, _now()),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM iam_users WHERE id = ?', (uid,)).fetchone()
    conn.close()
    return dict(row)


def list_iam_users():
    conn  = get_connection()
    rows  = conn.execute('SELECT * FROM iam_users ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_iam_user(user_id):
    conn = get_connection()
    row  = conn.execute('SELECT * FROM iam_users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_iam_user(user_id):
    # Cascades to iam_group_members and iam_attachments via FK ON DELETE CASCADE
    conn = get_connection()
    conn.execute('DELETE FROM iam_users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


# ─── IAM Groups ───────────────────────────────────────────────────────────────

def create_iam_group(name):
    conn = get_connection()
    gid  = str(uuid.uuid4())
    arn  = _make_arn('group', name)
    conn.execute(
        'INSERT INTO iam_groups (id, name, arn, created_at) VALUES (?, ?, ?, ?)',
        (gid, name, arn, _now()),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM iam_groups WHERE id = ?', (gid,)).fetchone()
    conn.close()
    return dict(row)


def list_iam_groups():
    conn   = get_connection()
    groups = conn.execute('SELECT * FROM iam_groups ORDER BY created_at DESC').fetchall()
    result = []
    for g in groups:
        g = dict(g)
        g['member_count'] = conn.execute(
            'SELECT COUNT(*) FROM iam_group_members WHERE group_id = ?', (g['id'],)
        ).fetchone()[0]
        result.append(g)
    conn.close()
    return result


def delete_iam_group(group_id):
    conn = get_connection()
    conn.execute('DELETE FROM iam_groups WHERE id = ?', (group_id,))
    conn.commit()
    conn.close()


def get_group_members(group_id):
    conn = get_connection()
    rows = conn.execute('''
        SELECT u.* FROM iam_users u
        JOIN iam_group_members m ON m.user_id = u.id
        WHERE m.group_id = ?
        ORDER BY u.username
    ''', (group_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_group_member(group_id, user_id):
    conn = get_connection()
    conn.execute(
        'INSERT OR IGNORE INTO iam_group_members (group_id, user_id) VALUES (?, ?)',
        (group_id, user_id),
    )
    conn.commit()
    conn.close()


def remove_group_member(group_id, user_id):
    conn = get_connection()
    conn.execute(
        'DELETE FROM iam_group_members WHERE group_id = ? AND user_id = ?',
        (group_id, user_id),
    )
    conn.commit()
    conn.close()


# ─── IAM Roles ────────────────────────────────────────────────────────────────

def create_iam_role(name, description, trusted_service):
    conn         = get_connection()
    rid          = str(uuid.uuid4())
    arn          = _make_arn('role', name)
    trust_policy = _make_trust_policy(trusted_service)
    conn.execute(
        '''INSERT INTO iam_roles
             (id, name, arn, description, trusted_service, trust_policy_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (rid, name, arn, description, trusted_service, trust_policy, _now()),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM iam_roles WHERE id = ?', (rid,)).fetchone()
    conn.close()
    return dict(row)


def list_iam_roles():
    conn = get_connection()
    rows = conn.execute('SELECT * FROM iam_roles ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_iam_role(role_id):
    conn = get_connection()
    row  = conn.execute('SELECT * FROM iam_roles WHERE id = ?', (role_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_iam_role(role_id):
    conn = get_connection()
    conn.execute('DELETE FROM iam_roles WHERE id = ?', (role_id,))
    conn.commit()
    conn.close()


# ─── IAM Policies ─────────────────────────────────────────────────────────────

def create_iam_policy(name, description, policy_json_str, policy_type='customer'):
    conn = get_connection()
    pid  = str(uuid.uuid4())
    arn  = _make_arn('policy', name)
    conn.execute(
        '''INSERT INTO iam_policies
             (id, name, arn, description, policy_json, type, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (pid, name, arn, description, policy_json_str, policy_type, _now()),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM iam_policies WHERE id = ?', (pid,)).fetchone()
    conn.close()
    return dict(row)


def list_iam_policies():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM iam_policies ORDER BY type DESC, name ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_iam_policy(policy_id):
    conn = get_connection()
    row  = conn.execute('SELECT * FROM iam_policies WHERE id = ?', (policy_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_iam_policy(policy_id):
    # Caller must verify type == 'customer' before calling; managed policies must not be deleted
    conn = get_connection()
    conn.execute(
        "DELETE FROM iam_policies WHERE id = ? AND type = 'customer'", (policy_id,)
    )
    conn.commit()
    conn.close()


# ─── Policy Attachments ───────────────────────────────────────────────────────

def attach_policy(policy_id, entity_type, entity_id):
    conn = get_connection()
    aid  = str(uuid.uuid4())
    conn.execute(
        '''INSERT OR IGNORE INTO iam_attachments
             (id, policy_id, entity_type, entity_id, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        (aid, policy_id, entity_type, entity_id, _now()),
    )
    conn.commit()
    conn.close()


def detach_policy(policy_id, entity_type, entity_id):
    conn = get_connection()
    conn.execute(
        '''DELETE FROM iam_attachments
           WHERE policy_id = ? AND entity_type = ? AND entity_id = ?''',
        (policy_id, entity_type, entity_id),
    )
    conn.commit()
    conn.close()


def get_policies_for_entity(entity_type, entity_id):
    # Returns all policies currently attached to a given user, group, or role
    conn = get_connection()
    rows = conn.execute(
        '''SELECT p.* FROM iam_policies p
           JOIN iam_attachments a ON a.policy_id = p.id
           WHERE a.entity_type = ? AND a.entity_id = ?
           ORDER BY p.type DESC, p.name ASC''',
        (entity_type, entity_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
