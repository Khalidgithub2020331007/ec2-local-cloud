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

    # Images table — stores metadata for uploaded OS images (like AWS AMI / Glance)
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

    conn.commit()
    conn.close()
