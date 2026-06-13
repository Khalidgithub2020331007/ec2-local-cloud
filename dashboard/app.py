import os
import subprocess
import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__)

ADMIN_USER = os.environ.get('OS_USERNAME', 'admin')
ADMIN_PASS = os.environ.get('OS_PASSWORD', 'Admin1234OpenStack')


def detect_host_ip():
    """Detect WiFi IP — DHCP can change it on reconnect, so we check live."""
    env_ip = os.environ.get('HOST_IP')
    if env_ip:
        return env_ip
    try:
        out = subprocess.check_output(
            "ip addr show wlp0s20f3 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1",
            shell=True, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return '10.200.195.97'


def authenticate():
    """Get Keystone token and build service endpoint map from catalog."""
    host_ip = detect_host_ip()
    resp = requests.post(
        f'http://{host_ip}/identity/v3/auth/tokens',
        json={
            "auth": {
                "identity": {
                    "methods": ["password"],
                    "password": {
                        "user": {
                            "name": ADMIN_USER,
                            "password": ADMIN_PASS,
                            "domain": {"name": "Default"}
                        }
                    }
                },
                "scope": {
                    "project": {"name": "admin", "domain": {"name": "Default"}}
                }
            }
        },
        timeout=10
    )
    resp.raise_for_status()
    token = resp.headers['X-Subject-Token']
    endpoints = {}
    for service in resp.json()['token']['catalog']:
        for ep in service.get('endpoints', []):
            if ep.get('interface') == 'public':
                endpoints[service['type']] = ep['url'].rstrip('/')
    return token, endpoints, host_ip


def os_get(url, token, params=None):
    """Authenticated GET to OpenStack API."""
    r = requests.get(url, headers={'X-Auth-Token': token}, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fmt_size(bytes_val):
    """Convert bytes to human-readable string."""
    if not bytes_val:
        return '—'
    if bytes_val < 1024 ** 2:
        return f'{bytes_val / 1024:.0f} KB'
    if bytes_val < 1024 ** 3:
        return f'{bytes_val / 1024 ** 2:.0f} MB'
    return f'{bytes_val / 1024 ** 3:.1f} GB'


def vol_endpoint(eps):
    """Cinder service type varies across DevStack versions."""
    return eps.get('volumev3') or eps.get('block-storage') or eps.get('volume', '')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/overview')
def api_overview():
    try:
        token, eps, host_ip = authenticate()
        servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
        images = os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])
        volumes = os_get(vol_endpoint(eps) + '/volumes/detail', token, {'all_tenants': 1}).get('volumes', [])
        fips = os_get(eps['network'] + '/v2.0/floatingips', token).get('floatingips', [])
        users = os_get(f'http://{host_ip}/identity/v3/users', token).get('users', [])
        projects = os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])
        return jsonify({
            'host_ip': host_ip,
            'instances': {
                'total': len(servers),
                'active': sum(1 for s in servers if s['status'] == 'ACTIVE'),
                'shutoff': sum(1 for s in servers if s['status'] == 'SHUTOFF'),
                'error': sum(1 for s in servers if s['status'] == 'ERROR'),
            },
            'images': {
                'total': len(images),
                'active': sum(1 for i in images if i.get('status') == 'active'),
            },
            'volumes': {
                'total': len(volumes),
                'in_use': sum(1 for v in volumes if v.get('status') == 'in-use'),
                'available': sum(1 for v in volumes if v.get('status') == 'available'),
            },
            'floating_ips': {
                'total': len(fips),
                'attached': sum(1 for f in fips if f.get('fixed_ip_address')),
            },
            'users': len(users),
            'projects': len(projects),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances')
def api_instances():
    try:
        token, eps, host_ip = authenticate()
        servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
        flavors = {f['id']: f for f in os_get(eps['compute'] + '/flavors/detail', token).get('flavors', [])}
        projects = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        images_map = {i['id']: i.get('name', i['id']) for i in os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])}

        result = []
        for s in servers:
            private_ips, floating_ips = [], []
            for addrs in s.get('addresses', {}).values():
                for a in addrs:
                    (floating_ips if a.get('OS-EXT-IPS:type') == 'floating' else private_ips).append(a['addr'])

            fl = flavors.get(s.get('flavor', {}).get('id', ''), {})
            img = s.get('image')
            img_name = images_map.get(img.get('id', '') if isinstance(img, dict) else '', 'Volume Boot')

            result.append({
                'id': s['id'][:8],
                'name': s['name'],
                'status': s['status'],
                'task_state': s.get('OS-EXT-STS:task_state') or '',
                'private_ips': private_ips,
                'floating_ips': floating_ips,
                'flavor': fl.get('name', '?'),
                'vcpus': fl.get('vcpus', '?'),
                'ram_mb': fl.get('ram', 0),
                'image': img_name,
                'project': projects.get(s.get('tenant_id', ''), '?'),
                'created': s.get('created', '')[:10],
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images')
def api_images():
    try:
        token, eps, _ = authenticate()
        images = os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])
        return jsonify([{
            'id': i['id'][:8],
            'name': i.get('name', i['id']),
            'status': i.get('status', 'unknown'),
            'size': fmt_size(i.get('size', 0)),
            'disk_format': i.get('disk_format', ''),
            'visibility': i.get('visibility', 'private'),
            'created_at': i.get('created_at', '')[:10],
            'min_disk_gb': i.get('min_disk', 0),
            'min_ram_mb': i.get('min_ram', 0),
        } for i in images])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes')
def api_volumes():
    try:
        token, eps, host_ip = authenticate()
        volumes = os_get(vol_endpoint(eps) + '/volumes/detail', token, {'all_tenants': 1}).get('volumes', [])
        projects = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        return jsonify([{
            'id': v['id'][:8],
            'name': v.get('name') or v['id'][:8],
            'status': v.get('status', 'unknown'),
            'size_gb': v.get('size', 0),
            'volume_type': v.get('volume_type', ''),
            'bootable': v.get('bootable') == 'true',
            'attached_to': [a.get('server_id', '')[:8] for a in v.get('attachments', [])],
            'project': projects.get(v.get('os-vol-tenant-attr:tenant_id', ''), '?'),
            'created_at': v.get('created_at', '')[:10],
        } for v in volumes])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/networks')
def api_networks():
    try:
        token, eps, _ = authenticate()
        networks = os_get(eps['network'] + '/v2.0/networks', token).get('networks', [])
        subnets = {s['id']: s for s in os_get(eps['network'] + '/v2.0/subnets', token).get('subnets', [])}
        return jsonify([{
            'id': n['id'][:8],
            'name': n.get('name', n['id'][:8]),
            'status': n.get('status', 'unknown'),
            'shared': n.get('shared', False),
            'external': n.get('router:external', False),
            'subnets': [{
                'name': subnets[sid].get('name', ''),
                'cidr': subnets[sid].get('cidr', ''),
                'gateway': subnets[sid].get('gateway_ip', ''),
                'dhcp': subnets[sid].get('enable_dhcp', False),
            } for sid in n.get('subnets', []) if sid in subnets],
        } for n in networks])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/floating-ips')
def api_floating_ips():
    try:
        token, eps, _ = authenticate()
        fips = os_get(eps['network'] + '/v2.0/floatingips', token).get('floatingips', [])
        return jsonify([{
            'id': f['id'][:8],
            'floating_ip': f.get('floating_ip_address', ''),
            'fixed_ip': f.get('fixed_ip_address') or '—',
            'status': f.get('status', 'DOWN'),
        } for f in fips])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/security-groups')
def api_security_groups():
    try:
        token, eps, _ = authenticate()
        sgs = os_get(eps['network'] + '/v2.0/security-groups', token).get('security_groups', [])
        result = []
        for sg in sgs:
            rules = sg.get('security_group_rules', [])
            ingress = [r for r in rules if r.get('direction') == 'ingress' and r.get('protocol')]
            result.append({
                'id': sg['id'][:8],
                'name': sg.get('name', ''),
                'description': sg.get('description', ''),
                'rule_count': len(rules),
                'ingress_rules': [{
                    'protocol': (r.get('protocol') or 'any').upper(),
                    'port_min': r.get('port_range_min', ''),
                    'port_max': r.get('port_range_max', ''),
                    'remote_ip': r.get('remote_ip_prefix') or '0.0.0.0/0',
                } for r in ingress],
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/users')
def api_users():
    try:
        token, _, host_ip = authenticate()
        users = os_get(f'http://{host_ip}/identity/v3/users', token).get('users', [])
        projects = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        result = []
        for u in users:
            assignments = os_get(f'http://{host_ip}/identity/v3/role_assignments', token, {'user.id': u['id']}).get('role_assignments', [])
            user_projects = sorted({
                projects[ra['scope']['project']['id']]
                for ra in assignments
                if 'project' in ra.get('scope', {}) and ra['scope']['project']['id'] in projects
            })
            result.append({
                'id': u['id'][:8],
                'name': u.get('name', ''),
                'enabled': u.get('enabled', True),
                'projects': user_projects,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    host_ip = detect_host_ip()
    print(f'\n  Dashboard  →  http://localhost:8080')
    print(f'  Network    →  http://{host_ip}:8080')
    print(f'  OpenStack  →  http://{host_ip}/identity\n')
    app.run(host='0.0.0.0', port=8080, debug=False)
