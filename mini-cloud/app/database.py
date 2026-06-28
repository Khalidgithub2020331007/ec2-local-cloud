import os
import sqlite3
from config import DATABASE_PATH, DATABASE_DIR


def get_connection():
    # WAL mode ব্যবহার করা হয়েছে কারণ এটা concurrent reads-এ lock করে না
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # dict-style access: row['username']
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")  # FK constraints enforce করার জন্য
    return conn


def init_db():
    # Database folder না থাকলে তৈরি করো
    os.makedirs(DATABASE_DIR, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    # Users table — প্রতিটি cloud account একটি user row
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            username    TEXT UNIQUE NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL
        )
    ''')

    # API Keys table — AWS Access Key + Secret Key এর মতো programmatic access
    # secret_key একবারই দেখানো হয় (create-এর সময়) — DB তে hash না রেখে plain রাখা হয়েছে
    # কারণ API call verify করার সময় HMAC-এর জন্য original secret দরকার হয়
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            access_key  TEXT UNIQUE NOT NULL,
            secret_key  TEXT NOT NULL,
            name        TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Instances table — প্রতিটি KVM VM এর metadata এখানে থাকে
    # libvirt_name কে UNIQUE রাখা হয়েছে — একই নামে দুটো VM হলে libvirt crash করে
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS instances (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            flavor       TEXT NOT NULL,
            vcpus        INTEGER NOT NULL,
            ram_mb       INTEGER NOT NULL,
            disk_gb      INTEGER NOT NULL,
            libvirt_name TEXT UNIQUE NOT NULL,
            disk_path    TEXT NOT NULL,
            image_path   TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            vnc_port     INTEGER,
            ip_address   TEXT,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Images table — stores metadata for uploaded OS images
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            file_path   TEXT NOT NULL,
            file_size   INTEGER NOT NULL,
            format      TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'available',
            is_public   INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Networks table — Linux bridge-backed private networks (like VPC)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS networks (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            bridge_name TEXT UNIQUE NOT NULL,
            cidr        TEXT NOT NULL,
            gateway     TEXT NOT NULL,
            dhcp_start  TEXT NOT NULL,
            dhcp_end    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Routers table — one iptables MASQUERADE rule per row
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS routers (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            network_id  TEXT NOT NULL,
            ext_iface   TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (network_id) REFERENCES networks(id)
        )
    ''')

    # Floating IPs table — 172.16.0.x pool, mapped via iptables DNAT/SNAT
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS floating_ips (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            ip_address  TEXT UNIQUE NOT NULL,
            instance_id TEXT,
            private_ip  TEXT,
            status      TEXT NOT NULL DEFAULT 'allocated',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # Security Groups — named rule sets that can be attached to VMs (like AWS SGs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_groups (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Security Group Rules — each row is one ACCEPT rule in the iptables chain
    # port_min/port_max are NULL for icmp and all protocols (no port concept)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS security_group_rules (
            id        TEXT PRIMARY KEY,
            group_id  TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
            protocol  TEXT NOT NULL CHECK (protocol IN ('tcp', 'udp', 'icmp', 'all')),
            port_min  INTEGER,
            port_max  INTEGER,
            cidr      TEXT NOT NULL DEFAULT '0.0.0.0/0',
            created_at TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES security_groups(id) ON DELETE CASCADE
        )
    ''')

    # VM ↔ Security Group mapping — one VM can have many groups; one group many VMs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vm_security_groups (
            vm_id    TEXT NOT NULL,
            group_id TEXT NOT NULL,
            PRIMARY KEY (vm_id, group_id),
            FOREIGN KEY (vm_id)    REFERENCES instances(id)        ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES security_groups(id)  ON DELETE CASCADE
        )
    ''')

    # SSH Key Pairs — only public key is stored; private key is shown once at generation and never persisted.
    # Storing the private key server-side would mean a DB breach equals full VM access — unacceptable.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keypairs (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            public_key  TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # keypair_id added in Step 7 — nullable so existing instances are unaffected.
    # ALTER TABLE is safe to re-run; the except swallows the "duplicate column" error.
    try:
        cursor.execute('ALTER TABLE instances ADD COLUMN keypair_id TEXT')
    except Exception:
        pass  # Column already exists from a previous run

    # Volumes — LVM logical volumes, like AWS EBS.
    # source_snapshot_id is set when the volume was cloned from a snapshot (restore).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS volumes (
            id                 TEXT PRIMARY KEY,
            user_id            TEXT NOT NULL,
            name               TEXT NOT NULL,
            size_gb            INTEGER NOT NULL,
            status             TEXT NOT NULL DEFAULT 'available',
            vm_id              TEXT,
            device_name        TEXT,
            source_snapshot_id TEXT,
            created_at         TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Snapshots — COW point-in-time copies of volumes via LVM snapshot.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            name       TEXT NOT NULL,
            volume_id  TEXT NOT NULL,
            size_gb    INTEGER NOT NULL,
            status     TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Quota defaults — one row per resource type, system-wide baseline for all users.
    # These are seeded once; admin can update them via PUT /api/v1/quotas/defaults.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quota_defaults (
            resource_type TEXT PRIMARY KEY,
            limit_value   INTEGER NOT NULL
        )
    ''')

    # Per-user quota overrides — only present when admin grants a user a custom limit.
    # Logic: check this table first; if no row, fall back to quota_defaults.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quota_user_overrides (
            user_id       TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            limit_value   INTEGER NOT NULL,
            PRIMARY KEY (user_id, resource_type),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Load Balancers — each row is one HAProxy frontend+backend pair.
    # port is UNIQUE because two frontends cannot bind the same port on the host.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS load_balancers (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            port        INTEGER NOT NULL UNIQUE,
            algorithm   TEXT NOT NULL DEFAULT 'roundrobin',
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # LB Members — each row maps one VM into a load balancer's HAProxy backend.
    # (lb_id, vm_id) is UNIQUE: a VM can be added to the same LB only once.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lb_members (
            id            TEXT PRIMARY KEY,
            lb_id         TEXT NOT NULL,
            vm_id         TEXT NOT NULL,
            vm_private_ip TEXT NOT NULL,
            member_port   INTEGER NOT NULL,
            status        TEXT NOT NULL DEFAULT 'active',
            created_at    TEXT NOT NULL,
            UNIQUE (lb_id, vm_id),
            FOREIGN KEY (lb_id) REFERENCES load_balancers(id) ON DELETE CASCADE
        )
    ''')

    # source column — 'manual' for user-launched instances, 'autoscaling' for ASG-managed ones
    try:
        cursor.execute("ALTER TABLE instances ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    except Exception:
        pass  # Column already exists

    # Auto Scaling Groups — each row is one scaling policy + VM template
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS autoscaling_groups (
            id                   TEXT PRIMARY KEY,
            user_id              TEXT NOT NULL,
            name                 TEXT NOT NULL,
            image_id             TEXT,
            flavor               TEXT NOT NULL,
            network_id           TEXT,
            keypair_id           TEXT,
            security_group_id    TEXT,
            min_instances        INTEGER NOT NULL DEFAULT 1,
            max_instances        INTEGER NOT NULL DEFAULT 5,
            scale_up_threshold   REAL NOT NULL DEFAULT 70.0,
            scale_down_threshold REAL NOT NULL DEFAULT 30.0,
            cooldown_seconds     INTEGER NOT NULL DEFAULT 120,
            lb_id                TEXT,
            lb_member_port       INTEGER,
            last_action_at       TEXT,
            status               TEXT NOT NULL DEFAULT 'active',
            created_at           TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Instances currently managed by an ASG
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS asg_instances (
            id          TEXT PRIMARY KEY,
            asg_id      TEXT NOT NULL,
            vm_id       TEXT NOT NULL,
            launched_at TEXT NOT NULL,
            FOREIGN KEY (asg_id) REFERENCES autoscaling_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (vm_id)  REFERENCES instances(id) ON DELETE CASCADE
        )
    ''')

    # Audit log of every scale-up / scale-down / ensure_min action
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS asg_events (
            id             TEXT PRIMARY KEY,
            asg_id         TEXT NOT NULL,
            action         TEXT NOT NULL,
            instance_count INTEGER NOT NULL,
            avg_cpu        REAL NOT NULL,
            reason         TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            FOREIGN KEY (asg_id) REFERENCES autoscaling_groups(id) ON DELETE CASCADE
        )
    ''')

    # ─── IAM tables ───────────────────────────────────────────────────────────

    # IAM Users — distinct from login accounts; represent service identities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_users (
            id         TEXT PRIMARY KEY,
            username   TEXT UNIQUE NOT NULL,
            arn        TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # IAM Groups — collections of IAM users that share the same policies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_groups (
            id         TEXT PRIMARY KEY,
            name       TEXT UNIQUE NOT NULL,
            arn        TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')

    # Many-to-many: which IAM users belong to which group
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_group_members (
            group_id TEXT NOT NULL,
            user_id  TEXT NOT NULL,
            PRIMARY KEY (group_id, user_id),
            FOREIGN KEY (group_id) REFERENCES iam_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)  REFERENCES iam_users(id)  ON DELETE CASCADE
        )
    ''')

    # IAM Roles — assumed by trusted services (e.g. EC2 assumes a role to access S3)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_roles (
            id                TEXT PRIMARY KEY,
            name              TEXT UNIQUE NOT NULL,
            arn               TEXT UNIQUE NOT NULL,
            description       TEXT NOT NULL DEFAULT '',
            trusted_service   TEXT NOT NULL,
            trust_policy_json TEXT NOT NULL,
            created_at        TEXT NOT NULL
        )
    ''')

    # IAM Policies — JSON permission documents; type='managed' rows are seeded and protected
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_policies (
            id          TEXT PRIMARY KEY,
            name        TEXT UNIQUE NOT NULL,
            arn         TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            policy_json TEXT NOT NULL,
            type        TEXT NOT NULL CHECK (type IN ('managed', 'customer')),
            created_at  TEXT NOT NULL
        )
    ''')

    # Policy attachments — one row per policy↔entity binding
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS iam_attachments (
            id          TEXT PRIMARY KEY,
            policy_id   TEXT NOT NULL,
            entity_type TEXT NOT NULL CHECK (entity_type IN ('user', 'group', 'role')),
            entity_id   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            UNIQUE (policy_id, entity_type, entity_id),
            FOREIGN KEY (policy_id) REFERENCES iam_policies(id) ON DELETE CASCADE
        )
    ''')

    # Seed the 7 AWS-managed policies once; skip if already present (idempotent)
    existing_policies = cursor.execute(
        "SELECT COUNT(*) FROM iam_policies WHERE type = 'managed'"
    ).fetchone()[0]
    if existing_policies == 0:
        import json as _json
        import uuid as _uuid

        _ACCOUNT = '123456789012'

        def _seed_policy(name, description, statement):
            pid  = str(_uuid.uuid4())
            arn  = f'arn:minicloud:iam::{_ACCOUNT}:policy/{name}'
            doc  = _json.dumps({'Version': '2012-10-17', 'Statement': [statement]})
            cursor.execute(
                '''INSERT INTO iam_policies (id, name, arn, description, policy_json, type, created_at)
                   VALUES (?, ?, ?, ?, ?, 'managed', datetime('now'))''',
                (pid, name, arn, description, doc),
            )

        _seed_policy(
            'AdministratorAccess',
            'Provides full access to all services and resources.',
            {'Effect': 'Allow', 'Action': '*', 'Resource': '*'},
        )
        _seed_policy(
            'PowerUserAccess',
            'Provides full access except IAM operations.',
            {'Effect': 'Allow', 'NotAction': 'iam:*', 'Resource': '*'},
        )
        _seed_policy(
            'ReadOnlyAccess',
            'Provides read-only access to EC2 and IAM describe/list operations.',
            {'Effect': 'Allow', 'Action': ['ec2:Describe*', 'iam:Get*', 'iam:List*'], 'Resource': '*'},
        )
        _seed_policy(
            'AmazonEC2FullAccess',
            'Provides full access to all EC2 operations.',
            {'Effect': 'Allow', 'Action': 'ec2:*', 'Resource': '*'},
        )
        _seed_policy(
            'AmazonEC2ReadOnlyAccess',
            'Provides read-only access to EC2 Describe operations.',
            {'Effect': 'Allow', 'Action': 'ec2:Describe*', 'Resource': '*'},
        )
        _seed_policy(
            'IAMFullAccess',
            'Provides full access to all IAM operations.',
            {'Effect': 'Allow', 'Action': 'iam:*', 'Resource': '*'},
        )
        _seed_policy(
            'IAMReadOnlyAccess',
            'Provides read-only access to IAM Get and List operations.',
            {'Effect': 'Allow', 'Action': ['iam:Get*', 'iam:List*'], 'Resource': '*'},
        )

    # Seed default limits only if the table is empty (idempotent on restart)
    existing = cursor.execute('SELECT COUNT(*) FROM quota_defaults').fetchone()[0]
    if existing == 0:
        defaults = [
            ('instances',            5),
            ('vcpus',                10),
            ('ram_mb',               10240),
            ('volumes',              10),
            ('volume_gb',            500),
            ('floating_ips',         5),
            ('security_groups',      10),
            ('security_group_rules', 50),
            ('key_pairs',            10),
        ]
        cursor.executemany(
            'INSERT INTO quota_defaults (resource_type, limit_value) VALUES (?, ?)',
            defaults,
        )

    conn.commit()
    conn.close()
