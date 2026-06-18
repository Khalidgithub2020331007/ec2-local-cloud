import os
import subprocess
import requests
from flask import Flask, jsonify, render_template, request

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


def os_post(url, token, body):
    """Authenticated POST to OpenStack API. Returns (status_code, response_dict)."""
    r = requests.post(
        url,
        headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
        json=body,
        timeout=20
    )
    r.raise_for_status()
    return r.status_code, (r.json() if r.content else {})


def os_delete(url, token):
    """Authenticated DELETE to OpenStack API."""
    r = requests.delete(url, headers={'X-Auth-Token': token}, timeout=15)
    r.raise_for_status()
    return r.status_code


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


# ── Read endpoints ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/overview')
def api_overview():
    try:
        token, eps, host_ip = authenticate()
        servers  = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
        images   = os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])
        volumes  = os_get(vol_endpoint(eps) + '/volumes/detail', token, {'all_tenants': 1}).get('volumes', [])
        fips     = os_get(eps['network'] + '/v2.0/floatingips', token).get('floatingips', [])
        users    = os_get(f'http://{host_ip}/identity/v3/users', token).get('users', [])
        projects = os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])
        return jsonify({
            'host_ip': host_ip,
            'instances': {
                'total': len(servers),
                'active': sum(1 for s in servers if s['status'] == 'ACTIVE'),
                'shutoff': sum(1 for s in servers if s['status'] == 'SHUTOFF'),
                'error': sum(1 for s in servers if s['status'] == 'ERROR'),
            },
            'images':   {'total': len(images),  'active': sum(1 for i in images  if i.get('status') == 'active')},
            'volumes':  {'total': len(volumes),  'in_use': sum(1 for v in volumes if v.get('status') == 'in-use'),
                         'available': sum(1 for v in volumes if v.get('status') == 'available')},
            'floating_ips': {'total': len(fips), 'attached': sum(1 for f in fips if f.get('fixed_ip_address'))},
            'users': len(users),
            'projects': len(projects),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances')
def api_instances():
    try:
        token, eps, host_ip = authenticate()
        servers    = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
        flavors    = {f['id']: f for f in os_get(eps['compute'] + '/flavors/detail', token).get('flavors', [])}
        projects   = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        images_map = {i['id']: i.get('name', i['id']) for i in os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])}

        result = []
        for s in servers:
            private_ips, floating_ips = [], []
            for addrs in s.get('addresses', {}).values():
                for a in addrs:
                    (floating_ips if a.get('OS-EXT-IPS:type') == 'floating' else private_ips).append(a['addr'])

            fl  = flavors.get(s.get('flavor', {}).get('id', ''), {})
            img = s.get('image')
            img_name = images_map.get(img.get('id', '') if isinstance(img, dict) else '', 'Volume Boot')

            result.append({
                'id':          s['id'],           # full UUID — needed for actions
                'name':        s['name'],
                'status':      s['status'],
                'task_state':  s.get('OS-EXT-STS:task_state') or '',
                'private_ips': private_ips,
                'floating_ips': floating_ips,
                'flavor':      fl.get('name', '?'),
                'vcpus':       fl.get('vcpus', '?'),
                'ram_mb':      fl.get('ram', 0),
                'image':       img_name,
                'project':     projects.get(s.get('tenant_id', ''), '?'),
                'created':     s.get('created', '')[:10],
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
            'id':           i['id'],              # full UUID — needed for launch form
            'name':         i.get('name', i['id']),
            'status':       i.get('status', 'unknown'),
            'size':         fmt_size(i.get('size', 0)),
            'disk_format':  i.get('disk_format', ''),
            'visibility':   i.get('visibility', 'private'),
            'created_at':   i.get('created_at', '')[:10],
            'min_disk_gb':  i.get('min_disk', 0),
            'min_ram_mb':   i.get('min_ram', 0),
        } for i in images])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/flavors')
def api_flavors():
    try:
        token, eps, _ = authenticate()
        flavors = os_get(eps['compute'] + '/flavors/detail', token).get('flavors', [])
        return jsonify([{
            'id':    f['id'],
            'name':  f['name'],
            'vcpus': f['vcpus'],
            'ram':   f['ram'],
            'disk':  f['disk'],
        } for f in sorted(flavors, key=lambda x: x['vcpus'])])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keypairs')
def api_keypairs():
    try:
        token, eps, _ = authenticate()
        keypairs = os_get(eps['compute'] + '/os-keypairs', token).get('keypairs', [])
        return jsonify([kp['keypair']['name'] for kp in keypairs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes')
def api_volumes():
    try:
        token, eps, host_ip = authenticate()
        volumes  = os_get(vol_endpoint(eps) + '/volumes/detail', token, {'all_tenants': 1}).get('volumes', [])
        projects = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        return jsonify([{
            'id':          v['id'],               # full UUID — needed for delete
            'name':        v.get('name') or v['id'][:8],
            'status':      v.get('status', 'unknown'),
            'size_gb':     v.get('size', 0),
            'volume_type': v.get('volume_type', ''),
            'bootable':    v.get('bootable') == 'true',
            'attached_to': [a.get('server_id', '')[:8] for a in v.get('attachments', [])],
            'project':     projects.get(v.get('os-vol-tenant-attr:tenant_id', ''), '?'),
            'created_at':  v.get('created_at', '')[:10],
        } for v in volumes])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/networks')
def api_networks():
    try:
        token, eps, _ = authenticate()
        networks = os_get(eps['network'] + '/v2.0/networks', token).get('networks', [])
        subnets  = {s['id']: s for s in os_get(eps['network'] + '/v2.0/subnets', token).get('subnets', [])}
        return jsonify([{
            'id':       n['id'][:8],
            'uuid':     n['id'],         # full UUID needed for Nova network attachment
            'name':     n.get('name', n['id'][:8]),
            'status':   n.get('status', 'unknown'),
            'shared':   n.get('shared', False),
            'external': n.get('router:external', False),
            'subnets': [{
                'name':    subnets[sid].get('name', ''),
                'cidr':    subnets[sid].get('cidr', ''),
                'gateway': subnets[sid].get('gateway_ip', ''),
                'dhcp':    subnets[sid].get('enable_dhcp', False),
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
            'id':          f['id'],               # full UUID — needed for delete
            'floating_ip': f.get('floating_ip_address', ''),
            'fixed_ip':    f.get('fixed_ip_address') or '—',
            'status':      f.get('status', 'DOWN'),
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
            rules   = sg.get('security_group_rules', [])
            ingress = [r for r in rules if r.get('direction') == 'ingress' and r.get('protocol')]
            result.append({
                'id':          sg['id'][:8],
                'name':        sg.get('name', ''),
                'description': sg.get('description', ''),
                'rule_count':  len(rules),
                'ingress_rules': [{
                    'protocol':  (r.get('protocol') or 'any').upper(),
                    'port_min':  r.get('port_range_min', ''),
                    'port_max':  r.get('port_range_max', ''),
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
        users    = os_get(f'http://{host_ip}/identity/v3/users', token).get('users', [])
        projects = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        result   = []
        for u in users:
            assignments = os_get(f'http://{host_ip}/identity/v3/role_assignments', token, {'user.id': u['id']}).get('role_assignments', [])
            user_projects = sorted({
                projects[ra['scope']['project']['id']]
                for ra in assignments
                if 'project' in ra.get('scope', {}) and ra['scope']['project']['id'] in projects
            })
            result.append({
                'id':       u['id'][:8],
                'name':     u.get('name', ''),
                'enabled':  u.get('enabled', True),
                'projects': user_projects,
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Instances ───────────────────────────────────────────────

@app.route('/api/instances', methods=['POST'])
def create_instance():
    """Launch new instance(s). Body: {name, image_id, flavor_id, network_id, security_groups, key_name, count, user_data}."""
    import base64
    try:
        token, eps, _ = authenticate()
        data = request.json

        name             = (data.get('name') or '').strip()
        image_id         = data.get('image_id', '')
        flavor_id        = data.get('flavor_id', '')
        network_id       = data.get('network_id', '')
        security_groups  = data.get('security_groups') or ['ssh-only']
        key_name         = data.get('key_name', '')
        count            = min(max(int(data.get('count', 1)), 1), 5)
        user_data_raw    = (data.get('user_data') or '').strip()

        if not name or not image_id or not flavor_id or not network_id:
            return jsonify({'error': 'name, image_id, flavor_id, and network_id are required'}), 400

        payload = {
            "server": {
                "name":            name,
                "imageRef":        image_id,
                "flavorRef":       flavor_id,
                "networks":        [{"uuid": network_id}],
                "security_groups": [{"name": sg} for sg in security_groups],
                "min_count":       count,
                "max_count":       count,
            }
        }
        if key_name:
            payload['server']['key_name'] = key_name
        if user_data_raw:
            # Nova requires user_data as base64-encoded string
            payload['server']['user_data'] = base64.b64encode(user_data_raw.encode()).decode()

        _, body = os_post(eps['compute'] + '/servers', token, payload)
        return jsonify({'id': body.get('server', {}).get('id', ''), 'status': 'BUILD'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/stop', methods=['POST'])
def stop_instance(server_id):
    try:
        token, eps, _ = authenticate()
        os_post(eps['compute'] + f'/servers/{server_id}/action', token, {"os-stop": None})
        return jsonify({'status': 'stopping'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/start', methods=['POST'])
def start_instance(server_id):
    try:
        token, eps, _ = authenticate()
        os_post(eps['compute'] + f'/servers/{server_id}/action', token, {"os-start": None})
        return jsonify({'status': 'starting'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/reboot', methods=['POST'])
def reboot_instance(server_id):
    try:
        token, eps, _ = authenticate()
        # SOFT asks the OS to restart gracefully; Nova falls back to HARD if unresponsive
        os_post(eps['compute'] + f'/servers/{server_id}/action', token, {"reboot": {"type": "SOFT"}})
        return jsonify({'status': 'rebooting'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/resize', methods=['POST'])
def resize_instance(server_id):
    """Resize to a different flavor. Instance must be SHUTOFF first. Body: {flavor_id}."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        flavor_id = (data.get('flavor_id') or '').strip()
        if not flavor_id:
            return jsonify({'error': 'flavor_id is required'}), 400
        os_post(eps['compute'] + f'/servers/{server_id}/action', token, {"resize": {"flavorRef": flavor_id}})
        return jsonify({'status': 'resizing'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/confirm-resize', methods=['POST'])
def confirm_resize(server_id):
    """Confirm a completed resize. Instance must be in VERIFY_RESIZE state."""
    try:
        token, eps, _ = authenticate()
        os_post(eps['compute'] + f'/servers/{server_id}/action', token, {"confirmResize": None})
        return jsonify({'status': 'confirmed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>', methods=['DELETE'])
def delete_instance(server_id):
    try:
        token, eps, _ = authenticate()
        os_delete(eps['compute'] + f'/servers/{server_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/image', methods=['POST'])
def create_image_from_instance(server_id):
    """Create an AMI snapshot from a running instance. Body: {name}.
    Uses Nova microversion 2.45 so image_id is returned in the body, not the Location header."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        r = requests.post(
            eps['compute'] + f'/servers/{server_id}/action',
            headers={
                'X-Auth-Token': token,
                'Content-Type': 'application/json',
                'X-OpenStack-Nova-API-Version': '2.45',
            },
            json={"createImage": {"name": name, "metadata": {}}},
            timeout=20
        )
        r.raise_for_status()
        body = r.json() if r.content else {}
        return jsonify({'id': body.get('image_id', ''), 'name': name, 'status': 'saving'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Volumes ─────────────────────────────────────────────────

@app.route('/api/volumes', methods=['POST'])
def create_volume():
    """Create a new volume. Body: {name, size}."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        _, body = os_post(
            vol_endpoint(eps) + '/volumes',
            token,
            {"volume": {"name": data['name'], "size": int(data['size'])}}
        )
        return jsonify({'id': body.get('volume', {}).get('id', ''), 'status': 'creating'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes/<volume_id>', methods=['DELETE'])
def delete_volume(volume_id):
    try:
        token, eps, _ = authenticate()
        os_delete(vol_endpoint(eps) + f'/volumes/{volume_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Images (AMI) ───────────────────────────────────────────

@app.route('/api/images/<image_id>', methods=['DELETE'])
def delete_image(image_id):
    try:
        token, eps, _ = authenticate()
        os_delete(eps['image'] + f'/v2/images/{image_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images/<image_id>/copy', methods=['POST'])
def copy_image(image_id):
    """Duplicate an image with a new name. Body: {name}.
    Streams image data through to avoid holding it in memory — slow for large images."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        src = os_get(eps['image'] + f'/v2/images/{image_id}', token)

        # Create target image record with the same format/size metadata
        create_r = requests.post(
            eps['image'] + '/v2/images',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={
                'name':             name,
                'disk_format':      src.get('disk_format', 'qcow2'),
                'container_format': src.get('container_format', 'bare'),
                'visibility':       'private',
                'min_disk':         src.get('min_disk', 0),
                'min_ram':          src.get('min_ram', 0),
            },
            timeout=20
        )
        create_r.raise_for_status()
        new_image_id = create_r.json()['id']

        # Stream image data directly from source to new image record
        src_stream = requests.get(
            eps['image'] + f'/v2/images/{image_id}/file',
            headers={'X-Auth-Token': token},
            stream=True,
            timeout=300
        )
        src_stream.raise_for_status()

        upload_r = requests.put(
            eps['image'] + f'/v2/images/{new_image_id}/file',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/octet-stream'},
            data=src_stream.iter_content(chunk_size=1024 * 1024),
            timeout=600
        )
        upload_r.raise_for_status()

        return jsonify({'id': new_image_id, 'name': name, 'status': 'active'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Floating IPs ────────────────────────────────────────────

@app.route('/api/floating-ips', methods=['POST'])
def allocate_floating_ip():
    """Allocate a new floating IP from the public pool."""
    try:
        token, eps, _ = authenticate()
        networks   = os_get(eps['network'] + '/v2.0/networks', token).get('networks', [])
        public_net = next((n for n in networks if n.get('router:external')), None)
        if not public_net:
            return jsonify({'error': 'No external network found'}), 400

        _, body = os_post(
            eps['network'] + '/v2.0/floatingips',
            token,
            {"floatingip": {"floating_network_id": public_net['id']}}
        )
        fip = body.get('floatingip', {})
        return jsonify({'id': fip.get('id', ''), 'floating_ip': fip.get('floating_ip_address', '')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/floating-ips/<fip_id>', methods=['DELETE'])
def release_floating_ip(fip_id):
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/floatingips/{fip_id}', token)
        return jsonify({'status': 'released'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    host_ip = detect_host_ip()
    print(f'\n  Dashboard  →  http://localhost:8080')
    print(f'  Network    →  http://{host_ip}:8080')
    print(f'  OpenStack  →  http://{host_ip}/identity\n')
    app.run(host='0.0.0.0', port=8080, debug=False)
