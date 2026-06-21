import uuid
from datetime import datetime, timezone
from app.database import get_connection


# ── Networks ──────────────────────────────────────────────────────────────────

def create_network(user_id, name, bridge_name, cidr, gateway,
                   dhcp_start, dhcp_end):
    network_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO networks
               (id, user_id, name, bridge_name, cidr, gateway,
                dhcp_start, dhcp_end, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)''',
            (network_id, user_id, name, bridge_name, cidr, gateway,
             dhcp_start, dhcp_end, created_at),
        )
        conn.commit()
        return network_id
    finally:
        conn.close()


def get_network(network_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM networks WHERE id=? AND user_id=?',
                (network_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM networks WHERE id=?', (network_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_networks(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM networks WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_network(network_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM networks WHERE id=?', (network_id,))
        conn.commit()
    finally:
        conn.close()


def get_next_bridge_name():
    # Find the lowest unused mcbrN index across all networks
    conn = get_connection()
    try:
        rows = conn.execute('SELECT bridge_name FROM networks').fetchall()
        used = set()
        for r in rows:
            name = r['bridge_name']
            if name.startswith('mcbr'):
                try:
                    used.add(int(name[4:]))
                except ValueError:
                    pass
        i = 0
        while i in used:
            i += 1
        return f'mcbr{i}'
    finally:
        conn.close()


# ── Routers ───────────────────────────────────────────────────────────────────

def create_router(user_id, name, network_id, ext_iface):
    router_id  = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO routers
               (id, user_id, name, network_id, ext_iface, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)''',
            (router_id, user_id, name, network_id, ext_iface, created_at),
        )
        conn.commit()
        return router_id
    finally:
        conn.close()


def get_router(router_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM routers WHERE id=? AND user_id=?',
                (router_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM routers WHERE id=?', (router_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_routers(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            '''SELECT r.*, n.name AS network_name, n.cidr AS network_cidr,
                      n.bridge_name AS bridge_name
               FROM routers r
               JOIN networks n ON r.network_id = n.id
               WHERE r.user_id=? ORDER BY r.created_at DESC''',
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_router(router_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM routers WHERE id=?', (router_id,))
        conn.commit()
    finally:
        conn.close()


# ── Floating IPs ──────────────────────────────────────────────────────────────

def create_floating_ip(user_id, ip_address):
    fip_id     = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            '''INSERT INTO floating_ips
               (id, user_id, ip_address, instance_id, private_ip, status, created_at)
               VALUES (?, ?, ?, NULL, NULL, 'allocated', ?)''',
            (fip_id, user_id, ip_address, created_at),
        )
        conn.commit()
        return fip_id
    finally:
        conn.close()


def get_floating_ip(fip_id, user_id=None):
    conn = get_connection()
    try:
        if user_id:
            row = conn.execute(
                'SELECT * FROM floating_ips WHERE id=? AND user_id=?',
                (fip_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM floating_ips WHERE id=?', (fip_id,)
            ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_floating_ips(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            '''SELECT f.*, i.name AS instance_name
               FROM floating_ips f
               LEFT JOIN instances i ON f.instance_id = i.id
               WHERE f.user_id=? ORDER BY f.created_at DESC''',
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def associate_floating_ip(fip_id, instance_id, private_ip):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE floating_ips SET instance_id=?, private_ip=?, status='associated' WHERE id=?",
            (instance_id, private_ip, fip_id),
        )
        conn.commit()
    finally:
        conn.close()


def disassociate_floating_ip(fip_id):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE floating_ips SET instance_id=NULL, private_ip=NULL, status='allocated' WHERE id=?",
            (fip_id,),
        )
        conn.commit()
    finally:
        conn.close()


def delete_floating_ip(fip_id):
    conn = get_connection()
    try:
        conn.execute('DELETE FROM floating_ips WHERE id=?', (fip_id,))
        conn.commit()
    finally:
        conn.close()


def get_next_floating_ip():
    # Pool: 192.168.0.224/27 → usable IPs are .225–.254 (30 addresses)
    # .224 is the network address and .255 is broadcast — both are excluded
    conn = get_connection()
    try:
        rows = conn.execute('SELECT ip_address FROM floating_ips').fetchall()
        used = {r['ip_address'] for r in rows}
        for i in range(225, 255):
            candidate = f'192.168.0.{i}'
            if candidate not in used:
                return candidate
        return None  # Pool exhausted (30-IP max)
    finally:
        conn.close()
