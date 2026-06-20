import os
import json
import time
import uuid
import subprocess
import requests
from datetime import datetime
from threading import Lock
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

ADMIN_USER    = os.environ.get('OS_USERNAME', 'admin')
ADMIN_PASS    = os.environ.get('OS_PASSWORD', 'Admin1234OpenStack')
ASG_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'asg_groups.json')
IAM_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'iam_data.json')
_asg_lock     = Lock()
_iam_lock     = Lock()

IAM_ACCOUNT_ID = '123456789012'

# Pre-seeded AWS-style managed policies — read-only, cannot be deleted
_MANAGED_POLICIES = [
    {
        'id': 'ANPAAadministratoraccess1',
        'name': 'AdministratorAccess',
        'arn': 'arn:aws:iam::aws:policy/AdministratorAccess',
        'description': 'Provides full access to all AWS services and resources',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'AllowAll', 'Effect': 'Allow', 'Action': '*', 'Resource': '*'}]
        },
    },
    {
        'id': 'ANPAApoweruseraccess00002',
        'name': 'PowerUserAccess',
        'arn': 'arn:aws:iam::aws:policy/PowerUserAccess',
        'description': 'Full access except IAM and Organizations management',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [
                {'Sid': 'AllowNonIAM', 'Effect': 'Allow', 'NotAction': ['iam:*', 'organizations:*'], 'Resource': '*'},
                {'Sid': 'AllowIAMRead', 'Effect': 'Allow', 'Action': ['iam:Get*', 'iam:List*'], 'Resource': '*'},
            ],
        },
    },
    {
        'id': 'ANPAAreadonlyaccess000003',
        'name': 'ReadOnlyAccess',
        'arn': 'arn:aws:iam::aws:policy/ReadOnlyAccess',
        'description': 'Provides read-only access to all AWS services',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'ReadOnly', 'Effect': 'Allow', 'Action': ['ec2:Describe*', 'iam:Get*', 'iam:List*'], 'Resource': '*'}],
        },
    },
    {
        'id': 'ANPAAamazonec2fullaccess4',
        'name': 'AmazonEC2FullAccess',
        'arn': 'arn:aws:iam::aws:policy/AmazonEC2FullAccess',
        'description': 'Provides full access to Amazon EC2 via the AWS Management Console',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'EC2Full', 'Effect': 'Allow', 'Action': 'ec2:*', 'Resource': '*'}],
        },
    },
    {
        'id': 'ANPAAamazonec2readonly005',
        'name': 'AmazonEC2ReadOnlyAccess',
        'arn': 'arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess',
        'description': 'Provides read-only access to Amazon EC2',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'EC2ReadOnly', 'Effect': 'Allow', 'Action': 'ec2:Describe*', 'Resource': '*'}],
        },
    },
    {
        'id': 'ANPAAiamfullaccess000006',
        'name': 'IAMFullAccess',
        'arn': 'arn:aws:iam::aws:policy/IAMFullAccess',
        'description': 'Provides full access to IAM via the AWS Management Console',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'IAMFull', 'Effect': 'Allow', 'Action': 'iam:*', 'Resource': '*'}],
        },
    },
    {
        'id': 'ANPAAiamreadonlyaccess07',
        'name': 'IAMReadOnlyAccess',
        'arn': 'arn:aws:iam::aws:policy/IAMReadOnlyAccess',
        'description': 'Provides read-only access to IAM via the AWS Management Console',
        'is_managed': True,
        'created_at': '2015-02-06T18:39:46Z',
        'document': {
            'Version': '2012-10-17',
            'Statement': [{'Sid': 'IAMReadOnly', 'Effect': 'Allow', 'Action': ['iam:Get*', 'iam:List*'], 'Resource': '*'}],
        },
    },
]


def read_asg_data():
    """Load ASG configs from disk. File is absent on first run."""
    if not os.path.exists(ASG_DATA_FILE):
        return {'groups': []}
    with open(ASG_DATA_FILE) as f:
        return json.load(f)


def write_asg_data(data):
    """Persist ASG configs atomically under a lock to prevent concurrent writes."""
    with _asg_lock:
        with open(ASG_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def read_iam_data():
    """Load IAM entities from disk. Seeds managed policies on first run."""
    if not os.path.exists(IAM_DATA_FILE):
        initial = {'users': [], 'groups': [], 'roles': [], 'policies': _MANAGED_POLICIES}
        write_iam_data(initial)
        return initial
    with open(IAM_DATA_FILE) as f:
        return json.load(f)


def write_iam_data(data):
    """Persist IAM data atomically under a lock to prevent concurrent writes."""
    with _iam_lock:
        with open(IAM_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)


def _new_iam_id(prefix):
    """Generate a random IAM-style entity ID."""
    return prefix + uuid.uuid4().hex[:16].upper()


def _iam_now():
    """Return current UTC time in ISO 8601 format."""
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')


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
                'id':             s['id'],           # full UUID — needed for actions
                'name':           s['name'],
                'status':         s['status'],
                'task_state':     s.get('OS-EXT-STS:task_state') or '',
                'private_ips':    private_ips,
                'floating_ips':   floating_ips,
                'flavor':         fl.get('name', '?'),
                'vcpus':          fl.get('vcpus', '?'),
                'ram_mb':         fl.get('ram', 0),
                'image':          img_name,
                'project':        projects.get(s.get('tenant_id', ''), '?'),
                'created':        s.get('created', '')[:10],
                'security_groups': [sg['name'] for sg in s.get('security_groups', [])],
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
        return jsonify([{
            'name':        kp['keypair']['name'],
            'fingerprint': kp['keypair'].get('fingerprint', ''),
            'public_key':  kp['keypair'].get('public_key', ''),
            'created_at':  kp['keypair'].get('created_at', '')[:10] if kp['keypair'].get('created_at') else '',
        } for kp in keypairs])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keypairs', methods=['POST'])
def create_keypair():
    """Create a new key pair. Body: {name}.
    Nova returns the private key only at creation — the caller must download it immediately."""
    try:
        token, eps, _ = authenticate()
        name = (request.json.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        _, body = os_post(
            eps['compute'] + '/os-keypairs',
            token,
            {"keypair": {"name": name}}
        )
        kp = body.get('keypair', {})
        return jsonify({
            'name':        kp.get('name', ''),
            'fingerprint': kp.get('fingerprint', ''),
            'public_key':  kp.get('public_key', ''),
            'private_key': kp.get('private_key', ''),  # only present on creation, never again
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/keypairs/<name>', methods=['DELETE'])
def delete_keypair(name):
    try:
        token, eps, _ = authenticate()
        os_delete(eps['compute'] + f'/os-keypairs/{name}', token)
        return jsonify({'status': 'deleted'})
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
            # Full server UUID needed by the detach endpoint — short IDs can't be used with Nova API
            'server_id':   v['attachments'][0].get('server_id', '') if v.get('attachments') else '',
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
                'id':      subnets[sid]['id'],
                'name':    subnets[sid].get('name', ''),
                'cidr':    subnets[sid].get('cidr', ''),
                'gateway': subnets[sid].get('gateway_ip', ''),
                'dhcp':    subnets[sid].get('enable_dhcp', False),
            } for sid in n.get('subnets', []) if sid in subnets],
        } for n in networks])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/networks', methods=['POST'])
def create_network():
    """Create a new Neutron network. Body: {name, shared, admin_state_up}."""
    try:
        token, eps, _ = authenticate()
        data = request.get_json() or {}
        name   = data.get('name', '').strip()
        shared = bool(data.get('shared', False))
        if not name:
            return jsonify({'error': 'name is required'}), 400
        _, body = os_post(
            eps['network'] + '/v2.0/networks', token,
            {"network": {"name": name, "shared": shared, "admin_state_up": True}}
        )
        n = body.get('network', {})
        return jsonify({'id': n['id'], 'name': n.get('name', name)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/networks/<network_id>', methods=['DELETE'])
def delete_network(network_id):
    """Delete a Neutron network. Will fail if subnets are still attached."""
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/networks/{network_id}', token)
        return jsonify({'status': 'deleted'})
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
            egress  = [r for r in rules if r.get('direction') == 'egress'  and r.get('protocol')]

            def fmt_rule(r):
                return {
                    'uuid':      r['id'],
                    'protocol':  (r.get('protocol') or 'any').upper(),
                    'port_min':  r.get('port_range_min', ''),
                    'port_max':  r.get('port_range_max', ''),
                    'remote_ip': r.get('remote_ip_prefix') or '0.0.0.0/0',
                }

            result.append({
                'id':            sg['id'][:8],
                'uuid':          sg['id'],
                'name':          sg.get('name', ''),
                'description':   sg.get('description', ''),
                'rule_count':    len(rules),
                'ingress_rules': [fmt_rule(r) for r in ingress],
                'egress_rules':  [fmt_rule(r) for r in egress],
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


@app.route('/api/volumes/<volume_id>/attach', methods=['POST'])
def attach_volume(volume_id):
    """Attach a volume to an instance via Nova. Body: {server_id, device (optional)}."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        server_id = (data.get('server_id') or '').strip()
        if not server_id:
            return jsonify({'error': 'server_id is required'}), 400

        body = {'volumeAttachment': {'volumeId': volume_id}}
        if data.get('device'):
            body['volumeAttachment']['device'] = data['device']

        # Nova handles volume attachment; Cinder just tracks state
        _, resp = os_post(
            eps['compute'] + f'/servers/{server_id}/os-volume_attachments',
            token,
            body
        )
        attachment = resp.get('volumeAttachment', {})
        return jsonify({'attachment_id': attachment.get('id', ''), 'status': 'attaching'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes/<volume_id>/detach', methods=['POST'])
def detach_volume(volume_id):
    """Detach a volume from its instance. Body: {server_id}."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        server_id = (data.get('server_id') or '').strip()
        if not server_id:
            return jsonify({'error': 'server_id is required'}), 400

        # Attachment ID in Nova equals the volume ID for single-attachment volumes
        os_delete(
            eps['compute'] + f'/servers/{server_id}/os-volume_attachments/{volume_id}',
            token
        )
        return jsonify({'status': 'detaching'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes/<volume_id>/resize', methods=['POST'])
def resize_volume(volume_id):
    """Extend a volume to a new size (GiB). Body: {new_size}. Size can only increase."""
    try:
        token, eps, _ = authenticate()
        data = request.json
        new_size = data.get('new_size')
        if not new_size:
            return jsonify({'error': 'new_size is required'}), 400

        os_post(
            vol_endpoint(eps) + f'/volumes/{volume_id}/action',
            token,
            {'os-extend': {'new_size': int(new_size)}}
        )
        return jsonify({'status': 'extending'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Images (AMI) ───────────────────────────────────────────

@app.route('/api/images', methods=['POST'])
def upload_image():
    """Register a new image by streaming data from a public URL into Glance.
    Body: {name, url, disk_format, container_format, visibility, min_disk, min_ram}."""
    try:
        token, eps, _ = authenticate()
        data             = request.json
        name             = (data.get('name') or '').strip()
        url              = (data.get('url') or '').strip()
        disk_format      = (data.get('disk_format') or 'qcow2').strip()
        container_format = (data.get('container_format') or 'bare').strip()
        visibility       = (data.get('visibility') or 'private').strip()
        min_disk         = int(data.get('min_disk') or 0)
        min_ram          = int(data.get('min_ram') or 0)

        if not name:
            return jsonify({'error': 'name is required'}), 400
        if not url:
            return jsonify({'error': 'url is required'}), 400

        # Create the image record — status will be "queued" until data is uploaded
        create_r = requests.post(
            eps['image'] + '/v2/images',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={
                'name':             name,
                'disk_format':      disk_format,
                'container_format': container_format,
                'visibility':       visibility,
                'min_disk':         min_disk,
                'min_ram':          min_ram,
            },
            timeout=20
        )
        create_r.raise_for_status()
        new_image_id = create_r.json()['id']

        # Stream image data from the external URL directly into the Glance image record
        src_stream = requests.get(url, stream=True, timeout=30)
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


@app.route('/api/floating-ips/<fip_id>/associate', methods=['PUT'])
def associate_floating_ip(fip_id):
    """Attach a floating IP to an instance by finding its first fixed-IP port.
    Body: {server_id}. Neutron requires the port_id, not the server_id directly."""
    try:
        token, eps, _ = authenticate()
        server_id = (request.get_json() or {}).get('server_id', '').strip()
        if not server_id:
            return jsonify({'error': 'server_id is required'}), 400

        # Resolve server → port: find the first network port owned by this server
        ports = os_get(eps['network'] + '/v2.0/ports', token, {'device_id': server_id}).get('ports', [])
        if not ports:
            return jsonify({'error': 'No network port found for this instance'}), 404
        port_id = ports[0]['id']

        r = requests.put(
            eps['network'] + f'/v2.0/floatingips/{fip_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"floatingip": {"port_id": port_id}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'associated', 'port_id': port_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/floating-ips/<fip_id>/disassociate', methods=['PUT'])
def disassociate_floating_ip(fip_id):
    """Detach a floating IP from its instance without releasing it back to the pool."""
    try:
        token, eps, _ = authenticate()
        r = requests.put(
            eps['network'] + f'/v2.0/floatingips/{fip_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"floatingip": {"port_id": None}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'disassociated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Write endpoints — Security Groups ────────────────────────────────────────

@app.route('/api/security-groups', methods=['POST'])
def create_security_group():
    """Create a new security group. Body: {name, description}."""
    try:
        token, eps, _ = authenticate()
        data        = request.json
        name        = (data.get('name') or '').strip()
        description = (data.get('description') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        _, body = os_post(
            eps['network'] + '/v2.0/security-groups',
            token,
            {"security_group": {"name": name, "description": description}}
        )
        sg = body.get('security_group', {})
        return jsonify({'id': sg.get('id', ''), 'name': sg.get('name', '')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/security-groups/<sg_id>', methods=['DELETE'])
def delete_security_group(sg_id):
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/security-groups/{sg_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/security-groups/<sg_id>/rules', methods=['POST'])
def add_security_group_rule(sg_id):
    """Add an ingress or egress rule. Body: {direction, protocol, port_min, port_max, remote_ip}.
    direction defaults to 'ingress'; omit protocol/ports to allow all traffic."""
    try:
        token, eps, _ = authenticate()
        data      = request.json
        direction = data.get('direction', 'ingress')
        protocol  = (data.get('protocol') or '').lower() or None
        port_min  = data.get('port_min')
        port_max  = data.get('port_max')
        remote_ip = (data.get('remote_ip') or '0.0.0.0/0').strip() or None

        rule = {
            "security_group_id": sg_id,
            "direction":         direction,
            "ethertype":         "IPv4",
        }
        if protocol:
            rule["protocol"] = protocol
        if port_min is not None:
            rule["port_range_min"] = int(port_min)
        if port_max is not None:
            rule["port_range_max"] = int(port_max)
        if remote_ip:
            rule["remote_ip_prefix"] = remote_ip

        _, body = os_post(
            eps['network'] + '/v2.0/security-group-rules',
            token,
            {"security_group_rule": rule}
        )
        r = body.get('security_group_rule', {})
        return jsonify({'id': r.get('id', '')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/security-groups/<sg_id>/rules/<rule_id>', methods=['DELETE'])
def delete_security_group_rule(sg_id, rule_id):
    # Neutron rules are immutable — to modify a rule: delete it here, then POST a new one.
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/security-group-rules/{rule_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/security-groups', methods=['POST'])
def attach_security_group(server_id):
    """Attach a security group to a running instance. Body: {name}."""
    try:
        token, eps, _ = authenticate()
        name = (request.json.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400

        # Nova action API identifies SGs by name, not UUID
        os_post(
            eps['compute'] + f'/servers/{server_id}/action',
            token,
            {"addSecurityGroup": {"name": name}}
        )
        return jsonify({'status': 'attached'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/security-groups/<sg_name>', methods=['DELETE'])
def detach_security_group(server_id, sg_name):
    """Detach a security group from a running instance. Uses Nova removeSecurityGroup action."""
    try:
        token, eps, _ = authenticate()
        os_post(
            eps['compute'] + f'/servers/{server_id}/action',
            token,
            {"removeSecurityGroup": {"name": sg_name}}
        )
        return jsonify({'status': 'detached'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Auto Scaling Groups ───────────────────────────────────────────────────────

def _apply_capacity_change(token, eps, group, old_desired, new_desired):
    """Launch or terminate member instances to match a desired count change.
    Shared by scale, update, and execute-policy routes to avoid duplicated logic."""
    name    = group['name']
    prefix  = name + '-'
    servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
    members = [s for s in servers if s['name'].startswith(prefix)]

    if new_desired > old_desired:
        existing_indices = {
            int(s['name'][len(prefix):])
            for s in members if s['name'][len(prefix):].isdigit()
        }
        next_idx = (max(existing_indices) + 1) if existing_indices else 1
        for _ in range(new_desired - old_desired):
            while next_idx in existing_indices:
                next_idx += 1
            payload = {
                "server": {
                    "name":            f"{name}-{next_idx}",
                    "imageRef":        group['image_id'],
                    "flavorRef":       group['flavor_id'],
                    "networks":        [{"uuid": group['network_id']}],
                    "security_groups": [{"name": sg} for sg in group['security_groups']],
                    "min_count": 1, "max_count": 1,
                }
            }
            if group.get('key_name'):
                payload['server']['key_name'] = group['key_name']
            os_post(eps['compute'] + '/servers', token, payload)
            existing_indices.add(next_idx)
            next_idx += 1

    elif new_desired < old_desired:
        def _suffix_index(s):
            suffix = s['name'][len(prefix):]
            return int(suffix) if suffix.isdigit() else 0

        to_delete = sorted(members, key=_suffix_index, reverse=True)[:old_desired - new_desired]
        for s in to_delete:
            try:
                os_delete(eps['compute'] + f'/servers/{s["id"]}', token)
            except Exception:
                pass  # best-effort — desired count is updated regardless


@app.route('/api/auto-scaling-groups')
def api_auto_scaling_groups():
    """List all ASGs with live running-instance counts derived from Nova."""
    try:
        data    = read_asg_data()
        token, eps, _ = authenticate()
        servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])

        result = []
        for group in data['groups']:
            prefix  = group['name'] + '-'
            members = [s for s in servers if s['name'].startswith(prefix)]
            result.append({
                'name':             group['name'],
                'image_name':       group.get('image_name', ''),
                'flavor_name':      group.get('flavor_name', ''),
                'min_size':         group['min_size'],
                'max_size':         group['max_size'],
                'desired_capacity': group['desired_capacity'],
                'running':          sum(1 for s in members if s['status'] == 'ACTIVE'),
                'total_instances':  len(members),
                'policy_count':     len(group.get('policies', [])),
                'created_at':       group.get('created_at', ''),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups', methods=['POST'])
def create_auto_scaling_group():
    """Create an ASG and launch desired_capacity instances named {name}-1, {name}-2, …
    Body: {name, image_id, flavor_id, network_id, security_groups, key_name, min_size, max_size, desired_capacity}."""
    try:
        token, eps, _ = authenticate()
        d = request.json

        name             = (d.get('name') or '').strip()
        image_id         = d.get('image_id', '')
        flavor_id        = d.get('flavor_id', '')
        network_id       = d.get('network_id', '')
        security_groups  = d.get('security_groups') or ['default']
        key_name         = d.get('key_name', '')
        min_size         = max(1, int(d.get('min_size', 1)))
        max_size         = max(min_size, int(d.get('max_size', 3)))
        desired_capacity = min(max(min_size, int(d.get('desired_capacity', min_size))), max_size)

        if not all([name, image_id, flavor_id, network_id]):
            return jsonify({'error': 'name, image_id, flavor_id, and network_id are required'}), 400

        data = read_asg_data()
        if any(g['name'] == name for g in data['groups']):
            return jsonify({'error': f'Auto Scaling Group "{name}" already exists'}), 409

        images  = os_get(eps['image'] + '/v2/images', token, {'limit': 1000}).get('images', [])
        flavors = os_get(eps['compute'] + '/flavors/detail', token).get('flavors', [])
        image_name  = next((i.get('name', image_id) for i in images  if i['id'] == image_id), image_id[:8])
        flavor_name = next((f['name']               for f in flavors if f['id'] == flavor_id), flavor_id[:8])

        # Launch desired_capacity instances; each is independently scheduled by Nova
        launched = 0
        for idx in range(1, desired_capacity + 1):
            payload = {
                "server": {
                    "name":            f"{name}-{idx}",
                    "imageRef":        image_id,
                    "flavorRef":       flavor_id,
                    "networks":        [{"uuid": network_id}],
                    "security_groups": [{"name": sg} for sg in security_groups],
                    "min_count": 1, "max_count": 1,
                }
            }
            if key_name:
                payload['server']['key_name'] = key_name
            os_post(eps['compute'] + '/servers', token, payload)
            launched += 1

        data['groups'].append({
            'name':             name,
            'image_id':         image_id,
            'image_name':       image_name,
            'flavor_id':        flavor_id,
            'flavor_name':      flavor_name,
            'network_id':       network_id,
            'security_groups':  security_groups,
            'key_name':         key_name,
            'min_size':         min_size,
            'max_size':         max_size,
            'desired_capacity': desired_capacity,
            'created_at':       d.get('created_at', ''),
            'policies':         [],
        })
        write_asg_data(data)
        return jsonify({'name': name, 'desired_capacity': desired_capacity, 'launched': launched}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>', methods=['PUT'])
def update_auto_scaling_group(name):
    """Update min_size, max_size, desired_capacity of an existing ASG.
    Body: {min_size, max_size, desired_capacity}. Scales instances if desired changed."""
    try:
        token, eps, _ = authenticate()
        d = request.json

        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        new_min     = max(1, int(d.get('min_size', group['min_size'])))
        new_max     = max(new_min, int(d.get('max_size', group['max_size'])))
        new_desired = min(max(new_min, int(d.get('desired_capacity', group['desired_capacity']))), new_max)
        old_desired = group['desired_capacity']

        if new_desired != old_desired:
            _apply_capacity_change(token, eps, group, old_desired, new_desired)

        group['min_size']         = new_min
        group['max_size']         = new_max
        group['desired_capacity'] = new_desired
        write_asg_data(data)
        return jsonify({'name': name, 'min_size': new_min, 'max_size': new_max, 'desired_capacity': new_desired})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>/scale', methods=['POST'])
def scale_auto_scaling_group(name):
    """Manually set desired capacity. Body: {desired}. Clamped to [min_size, max_size]."""
    try:
        token, eps, _ = authenticate()
        new_desired = int(request.json.get('desired', 0))

        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        new_desired      = min(max(group['min_size'], new_desired), group['max_size'])
        previous_desired = group['desired_capacity']

        _apply_capacity_change(token, eps, group, previous_desired, new_desired)

        group['desired_capacity'] = new_desired
        write_asg_data(data)
        return jsonify({'name': name, 'previous_desired': previous_desired, 'desired_capacity': new_desired})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>', methods=['DELETE'])
def delete_auto_scaling_group(name):
    """Delete an ASG and terminate all member instances."""
    try:
        token, eps, _ = authenticate()
        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])
        prefix  = name + '-'
        members = [s for s in servers if s['name'].startswith(prefix)]

        for s in members:
            try:
                os_delete(eps['compute'] + f'/servers/{s["id"]}', token)
            except Exception:
                pass  # best-effort — remove group config regardless

        data['groups'] = [g for g in data['groups'] if g['name'] != name]
        write_asg_data(data)
        return jsonify({'status': 'deleted', 'instances_terminated': len(members)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Scaling Policies ──────────────────────────────────────────────────────────

@app.route('/api/auto-scaling-groups/<name>/policies')
def list_scaling_policies(name):
    """Return all scaling policies defined for an ASG."""
    try:
        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404
        return jsonify(group.get('policies', []))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>/policies', methods=['POST'])
def create_scaling_policy(name):
    """Add a scaling policy to an ASG.
    Body: {policy_name, adjustment_type, scaling_adjustment, cooldown}.
    adjustment_type: 'ChangeInCapacity' (+/- N) or 'ExactCapacity' (set to N)."""
    try:
        d = request.json
        policy_name       = (d.get('policy_name') or '').strip()
        adjustment_type   = d.get('adjustment_type', 'ChangeInCapacity')
        scaling_adjustment = int(d.get('scaling_adjustment', 1))
        cooldown          = max(0, int(d.get('cooldown', 0)))

        if not policy_name:
            return jsonify({'error': 'policy_name is required'}), 400
        if adjustment_type not in ('ChangeInCapacity', 'ExactCapacity'):
            return jsonify({'error': 'adjustment_type must be ChangeInCapacity or ExactCapacity'}), 400

        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        if 'policies' not in group:
            group['policies'] = []

        if any(p['policy_name'] == policy_name for p in group['policies']):
            return jsonify({'error': f'Policy "{policy_name}" already exists on this group'}), 409

        policy = {
            'policy_name':        policy_name,
            'adjustment_type':    adjustment_type,
            'scaling_adjustment': scaling_adjustment,
            'cooldown':           cooldown,
            'created_at':         d.get('created_at', ''),
        }
        group['policies'].append(policy)
        write_asg_data(data)
        return jsonify(policy), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>/policies/<policy_name>/execute', methods=['POST'])
def execute_scaling_policy(name, policy_name):
    """Execute a named policy against the group's current desired capacity."""
    try:
        token, eps, _ = authenticate()
        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        policy = next((p for p in group.get('policies', []) if p['policy_name'] == policy_name), None)
        if not policy:
            return jsonify({'error': 'Policy not found'}), 404

        current  = group['desired_capacity']
        adj_type = policy['adjustment_type']
        adj      = policy['scaling_adjustment']

        if adj_type == 'ChangeInCapacity':
            new_desired = current + adj
        else:  # ExactCapacity
            new_desired = adj

        new_desired = min(max(group['min_size'], new_desired), group['max_size'])

        _apply_capacity_change(token, eps, group, current, new_desired)

        group['desired_capacity'] = new_desired
        write_asg_data(data)
        return jsonify({
            'policy_name':       policy_name,
            'previous_desired':  current,
            'desired_capacity':  new_desired,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auto-scaling-groups/<name>/policies/<policy_name>', methods=['DELETE'])
def delete_scaling_policy(name, policy_name):
    """Remove a scaling policy from an ASG."""
    try:
        data  = read_asg_data()
        group = next((g for g in data['groups'] if g['name'] == name), None)
        if not group:
            return jsonify({'error': 'Auto Scaling Group not found'}), 404

        before = len(group.get('policies', []))
        group['policies'] = [p for p in group.get('policies', []) if p['policy_name'] != policy_name]
        if len(group['policies']) == before:
            return jsonify({'error': 'Policy not found'}), 404

        write_asg_data(data)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── DevStack Monitor ─────────────────────────────────────────────────────────

STACK_LOG_PATH = '/opt/stack/logs/stack.sh.log.2026-06-18-220331'
STACK_LOG_FALLBACK = '/tmp/stack-octavia.log'

def _stack_log_path():
    """Return the most recent full stack.sh log (excludes .summary files)."""
    import glob
    logs = sorted(
        f for f in glob.glob('/opt/stack/logs/stack.sh.log.*')
        if 'summary' not in f
    )
    if logs:
        return logs[-1]
    return STACK_LOG_FALLBACK


@app.route('/api/devstack/status')
def devstack_status():
    """Return stack.sh running state, PID, last 80 log lines, and phase summary."""
    import signal
    result = subprocess.run(
        "pgrep -f 'bash.*stack.sh' | head -1",
        shell=True, capture_output=True, text=True
    )
    pid = result.stdout.strip()
    is_running = bool(pid)

    log_path = _stack_log_path()
    lines = []
    try:
        with open(log_path, 'r', errors='replace') as f:
            raw = f.readlines()
        # Strip verbose xtrace noise (lines containing only tput or +function:)
        cleaned = [
            l.rstrip() for l in raw
            if not l.startswith('tput:') and not (l.startswith('+') and ':' in l and l.count(':') >= 2)
        ]
        lines = cleaned[-80:]
    except FileNotFoundError:
        lines = ['Log file not found yet — stack.sh starting up…']

    # Detect completion or error from log tail
    tail_text = '\n'.join(lines[-20:])
    if 'ERROR' in tail_text and is_running is False:
        phase = 'error'
    elif 'This is your host' in tail_text or 'Horizon is now available' in tail_text or 'stack.sh completed' in tail_text.lower():
        phase = 'completed'
    elif is_running:
        # Detect current phase from last meaningful line
        recent = '\n'.join(lines[-10:]).lower()
        if 'octavia' in recent:
            phase = 'installing-octavia'
        elif 'pip install' in recent or 'pip3 install' in recent:
            phase = 'pip-install'
        elif 'git clone' in recent or 'git_clone' in recent:
            phase = 'git-clone'
        elif 'creating' in recent or 'start' in recent:
            phase = 'starting-services'
        else:
            phase = 'running'
    else:
        phase = 'stopped'

    return jsonify({
        'running':   is_running,
        'pid':       pid or None,
        'phase':     phase,
        'log_lines': lines,
        'log_path':  log_path,
    })


@app.route('/api/devstack/log')
def devstack_log():
    """Return last N lines of the stack.sh log (cleaned of xtrace noise).
    Query param: lines (default 100)."""
    n = min(500, max(10, int(request.args.get('lines', 100))))
    log_path = _stack_log_path()
    try:
        with open(log_path, 'r', errors='replace') as f:
            raw = f.readlines()
        cleaned = [
            l.rstrip() for l in raw
            if not l.startswith('tput:') and not (l.startswith('+') and ':' in l and l.count(':') >= 2)
        ]
        return jsonify({'lines': cleaned[-n:], 'total': len(cleaned)})
    except FileNotFoundError:
        return jsonify({'lines': ['Log file not found yet.'], 'total': 0})


@app.route('/api/devstack/stop', methods=['POST'])
def devstack_stop():
    """Kill the running stack.sh process (SIGTERM)."""
    result = subprocess.run(
        "pgrep -f 'bash.*stack.sh'",
        shell=True, capture_output=True, text=True
    )
    pids = result.stdout.strip().split()
    if not pids:
        return jsonify({'error': 'No stack.sh process found'}), 404
    for pid in pids:
        try:
            subprocess.run(f'sudo kill {pid}', shell=True, check=True)
        except subprocess.CalledProcessError:
            pass
    return jsonify({'status': 'stopped', 'pids': pids})


# ── Subnets ───────────────────────────────────────────────────────────────────

@app.route('/api/subnets')
def api_subnets():
    """Return all subnets for form dropdowns (LB creation, member attachment)."""
    try:
        token, eps, _ = authenticate()
        subnets = os_get(eps['network'] + '/v2.0/subnets', token).get('subnets', [])
        return jsonify([{
            'id':         s['id'],
            'name':       s.get('name') or s['cidr'],
            'cidr':       s['cidr'],
            'network_id': s['network_id'],
        } for s in subnets])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/subnets', methods=['POST'])
def create_subnet():
    """Create a subnet on an existing network. Body: {name, network_id, cidr, gateway_ip, enable_dhcp, ip_version}."""
    try:
        token, eps, _ = authenticate()
        data       = request.get_json() or {}
        name       = data.get('name', '').strip()
        network_id = data.get('network_id', '').strip()
        cidr       = data.get('cidr', '').strip()
        if not network_id or not cidr:
            return jsonify({'error': 'network_id and cidr are required'}), 400
        body = {
            "subnet": {
                "name":         name,
                "network_id":   network_id,
                "cidr":         cidr,
                "ip_version":   int(data.get('ip_version', 4)),
                "enable_dhcp":  bool(data.get('enable_dhcp', True)),
            }
        }
        gateway = data.get('gateway_ip', '').strip()
        if gateway:
            body['subnet']['gateway_ip'] = gateway
        _, resp = os_post(eps['network'] + '/v2.0/subnets', token, body)
        s = resp.get('subnet', {})
        return jsonify({'id': s['id'], 'name': s.get('name', cidr), 'cidr': s.get('cidr', cidr)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/subnets/<subnet_id>', methods=['DELETE'])
def delete_subnet(subnet_id):
    """Delete a subnet. Will fail if ports are still attached."""
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/subnets/{subnet_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Routers ───────────────────────────────────────────────────────────────────

@app.route('/api/routers')
def list_routers():
    """List all routers with their attached subnet interfaces."""
    try:
        token, eps, _ = authenticate()
        routers  = os_get(eps['network'] + '/v2.0/routers', token).get('routers', [])
        ports    = os_get(eps['network'] + '/v2.0/ports', token, {'device_owner': 'network:router_interface'}).get('ports', [])
        subnets  = {s['id']: s for s in os_get(eps['network'] + '/v2.0/subnets', token).get('subnets', [])}

        # Map router_id → list of attached subnet info
        router_subnets = {}
        for p in ports:
            rid = p.get('device_id')
            if not rid:
                continue
            router_subnets.setdefault(rid, [])
            for fip in p.get('fixed_ips', []):
                sid = fip.get('subnet_id')
                if sid and sid in subnets:
                    router_subnets[rid].append({
                        'id':   sid,
                        'name': subnets[sid].get('name') or subnets[sid].get('cidr', ''),
                        'cidr': subnets[sid].get('cidr', ''),
                    })

        result = []
        for r in routers:
            gw    = r.get('external_gateway_info') or {}
            gw_id = gw.get('network_id', '')
            result.append({
                'id':              r['id'],
                'name':            r.get('name', r['id'][:8]),
                'status':          r.get('status', 'unknown'),
                'admin_state_up':  r.get('admin_state_up', True),
                'gateway_network': gw_id,
                'has_gateway':     bool(gw_id),
                'subnets':         router_subnets.get(r['id'], []),
                'route_count':     len(r.get('routes', [])),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers', methods=['POST'])
def create_router():
    """Create a router. Body: {name, gateway_network_id (optional)}."""
    try:
        token, eps, _ = authenticate()
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'name is required'}), 400
        body = {"router": {"name": name, "admin_state_up": True}}
        gw_net = data.get('gateway_network_id', '').strip()
        if gw_net:
            body['router']['external_gateway_info'] = {"network_id": gw_net}
        _, resp = os_post(eps['network'] + '/v2.0/routers', token, body)
        r = resp.get('router', {})
        return jsonify({'id': r['id'], 'name': r.get('name', name)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>', methods=['DELETE'])
def delete_router(router_id):
    """Delete a router. Caller must detach all interfaces and clear gateway first."""
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/routers/{router_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/gateway', methods=['PUT'])
def set_router_gateway(router_id):
    """Attach or update external gateway. Body: {network_id}."""
    try:
        token, eps, _ = authenticate()
        data   = request.get_json() or {}
        net_id = data.get('network_id', '').strip()
        if not net_id:
            return jsonify({'error': 'network_id is required'}), 400
        r = requests.put(
            eps['network'] + f'/v2.0/routers/{router_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"router": {"external_gateway_info": {"network_id": net_id}}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/gateway', methods=['DELETE'])
def clear_router_gateway(router_id):
    """Detach the external gateway from a router."""
    try:
        token, eps, _ = authenticate()
        r = requests.put(
            eps['network'] + f'/v2.0/routers/{router_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"router": {"external_gateway_info": {}}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'cleared'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/subnets', methods=['POST'])
def attach_subnet_to_router(router_id):
    """Add a subnet interface to a router. Body: {subnet_id}."""
    try:
        token, eps, _ = authenticate()
        data      = request.get_json() or {}
        subnet_id = data.get('subnet_id', '').strip()
        if not subnet_id:
            return jsonify({'error': 'subnet_id is required'}), 400
        _, resp = os_post(
            eps['network'] + f'/v2.0/routers/{router_id}/add_router_interface', token,
            {"subnet_id": subnet_id}
        )
        return jsonify({'status': 'attached', 'port_id': resp.get('port_id', '')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/subnets/<subnet_id>', methods=['DELETE'])
def detach_subnet_from_router(router_id, subnet_id):
    """Remove a subnet interface from a router."""
    try:
        token, eps, _ = authenticate()
        _, resp = os_post(
            eps['network'] + f'/v2.0/routers/{router_id}/remove_router_interface', token,
            {"subnet_id": subnet_id}
        )
        return jsonify({'status': 'detached'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/routes')
def list_router_routes(router_id):
    """Return the extra static routes configured on a router."""
    try:
        token, eps, _ = authenticate()
        router = os_get(eps['network'] + f'/v2.0/routers/{router_id}', token).get('router', {})
        routes = router.get('routes', [])
        return jsonify({'routes': routes, 'router_name': router.get('name', router_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/routes', methods=['POST'])
def add_router_route(router_id):
    """Add a static route to a router. Body: {destination, nexthop}.
    Neutron replaces the full routes list on PUT — so we fetch existing routes first."""
    try:
        token, eps, _ = authenticate()
        data        = request.get_json() or {}
        destination = data.get('destination', '').strip()
        nexthop     = data.get('nexthop', '').strip()
        if not destination or not nexthop:
            return jsonify({'error': 'destination and nexthop are required'}), 400

        router = os_get(eps['network'] + f'/v2.0/routers/{router_id}', token).get('router', {})
        routes = router.get('routes', [])

        # Avoid duplicate routes
        if any(r['destination'] == destination and r['nexthop'] == nexthop for r in routes):
            return jsonify({'error': 'Route already exists'}), 409

        routes.append({'destination': destination, 'nexthop': nexthop})
        r = requests.put(
            eps['network'] + f'/v2.0/routers/{router_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"router": {"routes": routes}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'added', 'routes': routes}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/routers/<router_id>/routes', methods=['DELETE'])
def delete_router_route(router_id):
    """Remove a specific static route. Body: {destination, nexthop}."""
    try:
        token, eps, _ = authenticate()
        data        = request.get_json() or {}
        destination = data.get('destination', '').strip()
        nexthop     = data.get('nexthop', '').strip()

        router = os_get(eps['network'] + f'/v2.0/routers/{router_id}', token).get('router', {})
        routes = [
            rt for rt in router.get('routes', [])
            if not (rt['destination'] == destination and rt['nexthop'] == nexthop)
        ]
        r = requests.put(
            eps['network'] + f'/v2.0/routers/{router_id}',
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"router": {"routes": routes}},
            timeout=20
        )
        r.raise_for_status()
        return jsonify({'status': 'deleted', 'routes': routes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Load Balancers ────────────────────────────────────────────────────────────

def _lb_wait_active(lb_ep, token, lb_id, max_wait=30):
    """Poll until LB provisioning_status is ACTIVE or ERROR. OVN is near-instant."""
    for _ in range(max_wait):
        resp = os_get(lb_ep + f'/v2/lbaas/loadbalancers/{lb_id}', token)
        status = resp.get('loadbalancer', {}).get('provisioning_status', '')
        if status in ('ACTIVE', 'ERROR'):
            return status
        time.sleep(1)
    return 'TIMEOUT'


def _get_default_pool_id(lb_ep, token, lb_id):
    """Return the first pool ID associated with this LB, or None."""
    pools = os_get(lb_ep + '/v2/lbaas/pools', token, {'loadbalancer_id': lb_id}).get('pools', [])
    return pools[0]['id'] if pools else None


@app.route('/api/load-balancers')
def list_load_balancers():
    """List LBs with listener and member counts derived from Octavia."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available — run stack.sh first'}), 503

        lbs       = os_get(lb_ep + '/v2/lbaas/loadbalancers', token).get('loadbalancers', [])
        listeners = os_get(lb_ep + '/v2/lbaas/listeners', token).get('listeners', [])

        # Build per-LB listener count from the listeners list
        listener_count = {}
        for l in listeners:
            for lb_ref in l.get('loadbalancers', []):
                lid = lb_ref['id']
                listener_count[lid] = listener_count.get(lid, 0) + 1

        result = []
        for lb in lbs:
            pools        = os_get(lb_ep + '/v2/lbaas/pools', token, {'loadbalancer_id': lb['id']}).get('pools', [])
            member_count = sum(len(p.get('members', [])) for p in pools)
            pool_id      = pools[0]['id'] if pools else None

            result.append({
                'id':                  lb['id'],
                'name':                lb['name'],
                'description':         lb.get('description', ''),
                'vip_address':         lb.get('vip_address', ''),
                'vip_subnet_id':       lb.get('vip_subnet_id', ''),
                'provisioning_status': lb.get('provisioning_status', ''),
                'operating_status':    lb.get('operating_status', ''),
                'provider':            lb.get('provider', ''),
                'listener_count':      listener_count.get(lb['id'], 0),
                'member_count':        member_count,
                'default_pool_id':     pool_id,
                'created_at':          lb.get('created_at', ''),
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers', methods=['POST'])
def create_load_balancer():
    """Create LB + default HTTP/ROUND_ROBIN pool in one call.
    Body: {name, subnet_id, description}."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available'}), 503

        data        = request.json
        name        = (data.get('name') or '').strip()
        subnet_id   = (data.get('subnet_id') or '').strip()
        description = (data.get('description') or '').strip()

        if not name or not subnet_id:
            return jsonify({'error': 'name and subnet_id are required'}), 400

        _, lb_body = os_post(lb_ep + '/v2/lbaas/loadbalancers', token, {
            'loadbalancer': {
                'name':          name,
                'description':   description,
                'vip_subnet_id': subnet_id,
                'provider':      'ovn',
            }
        })
        lb    = lb_body.get('loadbalancer', {})
        lb_id = lb.get('id', '')

        # OVN provision is near-instant; wait for ACTIVE before creating pool
        status = _lb_wait_active(lb_ep, token, lb_id)
        if status == 'ERROR':
            return jsonify({'error': 'Load balancer entered ERROR state during provisioning'}), 500

        _, pool_body = os_post(lb_ep + '/v2/lbaas/pools', token, {
            'pool': {
                'name':             f'{name}-pool',
                'loadbalancer_id':  lb_id,
                'protocol':         'HTTP',
                'lb_algorithm':     'ROUND_ROBIN',
            }
        })
        return jsonify({
            'id':      lb_id,
            'name':    name,
            'pool_id': pool_body.get('pool', {}).get('id', ''),
        }), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>', methods=['DELETE'])
def delete_load_balancer(lb_id):
    """Cascade-delete a load balancer with all listeners, pools, members, and monitors."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available'}), 503

        # cascade=true removes all child resources atomically
        os_delete(lb_ep + f'/v2/lbaas/loadbalancers/{lb_id}?cascade=true', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/listeners')
def list_lb_listeners(lb_id):
    """List all listeners (routing rules) for a load balancer."""
    try:
        token, eps, _ = authenticate()
        lb_ep     = eps.get('load-balancer', '')
        listeners = os_get(lb_ep + '/v2/lbaas/listeners', token, {'loadbalancer_id': lb_id}).get('listeners', [])
        return jsonify([{
            'id':                  l['id'],
            'name':                l['name'],
            'protocol':            l['protocol'],
            'protocol_port':       l['protocol_port'],
            'provisioning_status': l.get('provisioning_status', ''),
            'operating_status':    l.get('operating_status', ''),
            'default_pool_id':     l.get('default_pool_id', ''),
        } for l in listeners])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/listeners', methods=['POST'])
def create_lb_listener(lb_id):
    """Create a routing rule (listener). Body: {name, protocol, protocol_port}."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available'}), 503

        data          = request.json
        name          = (data.get('name') or '').strip()
        protocol      = (data.get('protocol') or 'HTTP').upper()
        protocol_port = int(data.get('protocol_port', 80))

        if not name:
            return jsonify({'error': 'name is required'}), 400

        _lb_wait_active(lb_ep, token, lb_id)
        pool_id = _get_default_pool_id(lb_ep, token, lb_id)

        listener_payload = {
            'listener': {
                'name':            name,
                'loadbalancer_id': lb_id,
                'protocol':        protocol,
                'protocol_port':   protocol_port,
            }
        }
        # Attach default pool if one exists so traffic is forwarded immediately
        if pool_id:
            listener_payload['listener']['default_pool_id'] = pool_id

        _, body = os_post(lb_ep + '/v2/lbaas/listeners', token, listener_payload)
        l = body.get('listener', {})
        return jsonify({'id': l.get('id', ''), 'name': l.get('name', '')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/listeners/<listener_id>', methods=['DELETE'])
def delete_lb_listener(lb_id, listener_id):
    """Delete a routing rule (listener)."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        _lb_wait_active(lb_ep, token, lb_id)
        os_delete(lb_ep + f'/v2/lbaas/listeners/{listener_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/members')
def list_lb_members(lb_id):
    """List all members in the LB's default pool."""
    try:
        token, eps, _ = authenticate()
        lb_ep   = eps.get('load-balancer', '')
        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify([])

        members = os_get(lb_ep + f'/v2/lbaas/pools/{pool_id}/members', token).get('members', [])
        return jsonify([{
            'id':                  m['id'],
            'name':                m.get('name', ''),
            'address':             m['address'],
            'protocol_port':       m['protocol_port'],
            'provisioning_status': m.get('provisioning_status', ''),
            'operating_status':    m.get('operating_status', ''),
        } for m in members])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/members', methods=['POST'])
def add_lb_member(lb_id):
    """Attach an instance to the LB pool. Resolves instance fixed IP from Nova.
    Body: {instance_id, protocol_port, subnet_id}."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available'}), 503

        data          = request.json
        instance_id   = (data.get('instance_id') or '').strip()
        protocol_port = int(data.get('protocol_port', 80))
        subnet_id     = (data.get('subnet_id') or '').strip()

        if not instance_id:
            return jsonify({'error': 'instance_id is required'}), 400

        # Resolve fixed IP from Nova — floating IPs cannot be pool members
        server    = os_get(eps['compute'] + f'/servers/{instance_id}', token).get('server', {})
        fixed_ip  = None
        for net_addrs in server.get('addresses', {}).values():
            for addr in net_addrs:
                if addr.get('OS-EXT-IPS:type') == 'fixed':
                    fixed_ip = addr['addr']
                    break
            if fixed_ip:
                break

        if not fixed_ip:
            return jsonify({'error': 'Could not resolve a fixed IP for this instance'}), 400

        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify({'error': 'No pool found for this load balancer'}), 404

        _lb_wait_active(lb_ep, token, lb_id)

        member_payload = {
            'member': {
                'name':          server.get('name', instance_id[:8]),
                'address':       fixed_ip,
                'protocol_port': protocol_port,
            }
        }
        if subnet_id:
            member_payload['member']['subnet_id'] = subnet_id

        _, body = os_post(lb_ep + f'/v2/lbaas/pools/{pool_id}/members', token, member_payload)
        m = body.get('member', {})
        return jsonify({'id': m.get('id', ''), 'address': fixed_ip}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/members/<member_id>', methods=['DELETE'])
def remove_lb_member(lb_id, member_id):
    """Remove a member from the LB's default pool."""
    try:
        token, eps, _ = authenticate()
        lb_ep   = eps.get('load-balancer', '')
        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify({'error': 'No pool found'}), 404

        _lb_wait_active(lb_ep, token, lb_id)
        os_delete(lb_ep + f'/v2/lbaas/pools/{pool_id}/members/{member_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/health-monitor')
def get_lb_health_monitor(lb_id):
    """Get health monitor for the LB's pool, or empty dict if none configured."""
    try:
        token, eps, _ = authenticate()
        lb_ep   = eps.get('load-balancer', '')
        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify({})

        pool  = os_get(lb_ep + f'/v2/lbaas/pools/{pool_id}', token).get('pool', {})
        hm_id = pool.get('healthmonitor_id')
        if not hm_id:
            return jsonify({})

        hm = os_get(lb_ep + f'/v2/lbaas/healthmonitors/{hm_id}', token).get('healthmonitor', {})
        return jsonify({
            'id':                  hm['id'],
            'type':                hm['type'],
            'delay':               hm['delay'],
            'timeout':             hm['timeout'],
            'max_retries':         hm['max_retries'],
            'provisioning_status': hm.get('provisioning_status', ''),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/health-monitor', methods=['POST'])
def create_lb_health_monitor(lb_id):
    """Create a health monitor on the LB's default pool.
    Body: {type, delay, timeout, max_retries}."""
    try:
        token, eps, _ = authenticate()
        lb_ep = eps.get('load-balancer', '')
        if not lb_ep:
            return jsonify({'error': 'Octavia load-balancer service not available'}), 503

        data        = request.json
        hm_type     = (data.get('type') or 'HTTP').upper()
        delay       = max(1, int(data.get('delay', 5)))
        timeout     = max(1, int(data.get('timeout', 3)))
        max_retries = max(1, int(data.get('max_retries', 3)))

        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify({'error': 'No pool found for this load balancer'}), 404

        _lb_wait_active(lb_ep, token, lb_id)

        _, body = os_post(lb_ep + '/v2/lbaas/healthmonitors', token, {
            'healthmonitor': {
                'pool_id':     pool_id,
                'type':        hm_type,
                'delay':       delay,
                'timeout':     timeout,
                'max_retries': max_retries,
            }
        })
        hm = body.get('healthmonitor', {})
        return jsonify({'id': hm.get('id', ''), 'type': hm_type}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/load-balancers/<lb_id>/health-monitor', methods=['DELETE'])
def delete_lb_health_monitor(lb_id):
    """Delete the health monitor from the LB's default pool."""
    try:
        token, eps, _ = authenticate()
        lb_ep   = eps.get('load-balancer', '')
        pool_id = _get_default_pool_id(lb_ep, token, lb_id)
        if not pool_id:
            return jsonify({'error': 'No pool found'}), 404

        pool  = os_get(lb_ep + f'/v2/lbaas/pools/{pool_id}', token).get('pool', {})
        hm_id = pool.get('healthmonitor_id')
        if not hm_id:
            return jsonify({'error': 'No health monitor configured on this load balancer'}), 404

        _lb_wait_active(lb_ep, token, lb_id)
        os_delete(lb_ep + f'/v2/lbaas/healthmonitors/{hm_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Snapshots (EBS Snapshot equivalent) ──────────────────────────────────────

@app.route('/api/snapshots')
def api_snapshots():
    """List all volume snapshots across all projects."""
    try:
        token, eps, host_ip = authenticate()
        snapshots = os_get(vol_endpoint(eps) + '/snapshots/detail', token, {'all_tenants': 1}).get('snapshots', [])
        projects  = {p['id']: p['name'] for p in os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])}
        return jsonify([{
            'id':          s['id'],
            'name':        s.get('name') or s['id'][:8],
            'description': s.get('description', ''),
            'status':      s.get('status', 'unknown'),
            'size_gb':     s.get('size', 0),
            'volume_id':   s.get('volume_id', ''),
            'project':     projects.get(s.get('os-extended-snapshot-attributes:project_id', ''), '?'),
            'created_at':  s.get('created_at', '')[:10],
        } for s in snapshots])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshots', methods=['POST'])
def create_snapshot():
    """Create a snapshot from a volume. Body: {volume_id, name, description}.
    force=True allows snapshotting in-use volumes — data consistency is OS-level."""
    try:
        token, eps, _ = authenticate()
        data        = request.json
        volume_id   = (data.get('volume_id') or '').strip()
        name        = (data.get('name') or '').strip()
        description = (data.get('description') or '').strip()
        if not volume_id or not name:
            return jsonify({'error': 'volume_id and name are required'}), 400

        _, body = os_post(
            vol_endpoint(eps) + '/snapshots',
            token,
            {"snapshot": {"volume_id": volume_id, "name": name, "description": description, "force": True}}
        )
        s = body.get('snapshot', {})
        return jsonify({'id': s.get('id', ''), 'name': name, 'status': s.get('status', 'creating')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshots/<snapshot_id>', methods=['DELETE'])
def delete_snapshot(snapshot_id):
    try:
        token, eps, _ = authenticate()
        os_delete(vol_endpoint(eps) + f'/snapshots/{snapshot_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/volumes/from-snapshot', methods=['POST'])
def create_volume_from_snapshot():
    """Restore a new volume from a snapshot. Body: {snapshot_id, name, size}.
    Size must be >= the original snapshot size."""
    try:
        token, eps, _ = authenticate()
        data        = request.json
        snapshot_id = (data.get('snapshot_id') or '').strip()
        name        = (data.get('name') or '').strip()
        size        = int(data.get('size', 0))
        if not snapshot_id or not name or size < 1:
            return jsonify({'error': 'snapshot_id, name, and size (>=1) are required'}), 400

        _, body = os_post(
            vol_endpoint(eps) + '/volumes',
            token,
            {"volume": {"name": name, "snapshot_id": snapshot_id, "size": size}}
        )
        return jsonify({'id': body.get('volume', {}).get('id', ''), 'status': 'creating'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Instance Console ──────────────────────────────────────────────────────────

@app.route('/api/instances/<server_id>/console', methods=['POST'])
def get_instance_console(server_id):
    """Get a browser VNC console URL. Body: {type} — novnc (default) or xvpvnc."""
    try:
        token, eps, _ = authenticate()
        console_type = (request.json or {}).get('type', 'novnc')
        _, body = os_post(
            eps['compute'] + f'/servers/{server_id}/action',
            token,
            {"os-getVNCConsole": {"type": console_type}}
        )
        console = body.get('console', {})
        return jsonify({'url': console.get('url', ''), 'type': console.get('type', '')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/console-output')
def get_console_output(server_id):
    """Return recent serial console output (boot logs, crash output).
    Query param: lines (default 50, max 500)."""
    try:
        token, eps, _ = authenticate()
        length = min(500, max(10, int(request.args.get('lines', 50))))
        _, body = os_post(
            eps['compute'] + f'/servers/{server_id}/action',
            token,
            {"os-getConsoleOutput": {"length": length}}
        )
        return jsonify({'output': body.get('output', '')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── CloudWatch equivalent: metrics via Nova diagnostics ───────────────────────

@app.route('/api/instances/<server_id>/metrics')
def get_instance_metrics(server_id):
    # Nova diagnostics are only available for ACTIVE instances on a live hypervisor.
    # Returns cumulative counters, not rates — call twice and diff for throughput.
    try:
        token, eps, _ = authenticate()
        diag = os_get(eps['compute'] + f'/servers/{server_id}/diagnostics', token)

        # Sum across all CPUs, disks, and NICs — keys follow vda_read, vnet0_rx patterns.
        cpu_time_ns = sum(v for k, v in diag.items()
                          if k.startswith('cpu') and k.endswith('_time') and isinstance(v, (int, float)))
        disk_read   = sum(v for k, v in diag.items()
                          if k.endswith('_read') and isinstance(v, (int, float)))
        disk_write  = sum(v for k, v in diag.items()
                          if k.endswith('_write') and isinstance(v, (int, float)))
        net_rx      = sum(v for k, v in diag.items()
                          if k.startswith('vnet') and k.endswith('_rx') and isinstance(v, (int, float)))
        net_tx      = sum(v for k, v in diag.items()
                          if k.startswith('vnet') and k.endswith('_tx') and isinstance(v, (int, float)))

        return jsonify({
            'cpu_time_ns':      cpu_time_ns,
            'memory_kb':        diag.get('memory', 0),
            'disk_read_bytes':  disk_read,
            'disk_write_bytes': disk_write,
            'net_rx_bytes':     net_rx,
            'net_tx_bytes':     net_tx,
            'raw':              diag,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/summary')
def api_metrics_summary():
    # Uses /os-hypervisors/statistics — the /detail endpoint returns empty on this DevStack build
    # even though nova-compute is up and running (known Nova 2025.1 behavior).
    try:
        token, eps, _ = authenticate()
        h       = os_get(eps['compute'] + '/os-hypervisors/statistics', token).get('hypervisor_statistics', {})
        servers = os_get(eps['compute'] + '/servers/detail', token, {'all_tenants': 1}).get('servers', [])

        status_counts = {}
        for s in servers:
            status = s['status']
            status_counts[status] = status_counts.get(status, 0) + 1

        return jsonify({
            'vcpus_total':            h.get('vcpus', 0),
            'vcpus_used':             h.get('vcpus_used', 0),
            'ram_total_mb':           h.get('memory_mb', 0),
            'ram_used_mb':            h.get('memory_mb_used', 0),
            'disk_total_gb':          h.get('local_gb', 0),
            'disk_used_gb':           h.get('local_gb_used', 0),
            'running_vms':            h.get('running_vms', 0),
            'instance_status_counts': status_counts,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Network Interfaces / Ports (ENI equivalent) ───────────────────────────────

@app.route('/api/ports')
def api_ports():
    """List all Neutron ports with subnet and device info."""
    try:
        token, eps, _ = authenticate()
        ports   = os_get(eps['network'] + '/v2.0/ports', token).get('ports', [])
        subnets = {s['id']: s for s in os_get(eps['network'] + '/v2.0/subnets', token).get('subnets', [])}
        return jsonify([{
            'id':           p['id'],
            'name':         p.get('name') or p['id'][:8],
            'status':       p.get('status', 'unknown'),
            'mac_address':  p.get('mac_address', ''),
            'device_id':    p.get('device_id', ''),
            'device_owner': p.get('device_owner', ''),
            'network_id':   p.get('network_id', ''),
            'fixed_ips': [{
                'ip':     fip['ip_address'],
                'subnet': subnets.get(fip['subnet_id'], {}).get('name') or subnets.get(fip['subnet_id'], {}).get('cidr', ''),
            } for fip in p.get('fixed_ips', [])],
        } for p in ports])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ports', methods=['POST'])
def create_port():
    """Create a standalone port on a network. Body: {network_id, name}.
    Useful for pre-allocating a fixed IP before attaching it to an instance."""
    try:
        token, eps, _ = authenticate()
        data       = request.json
        network_id = (data.get('network_id') or '').strip()
        name       = (data.get('name') or '').strip()
        if not network_id:
            return jsonify({'error': 'network_id is required'}), 400

        _, body = os_post(
            eps['network'] + '/v2.0/ports',
            token,
            {"port": {"network_id": network_id, "name": name, "admin_state_up": True}}
        )
        p = body.get('port', {})
        return jsonify({'id': p['id'], 'name': p.get('name', name), 'mac_address': p.get('mac_address', '')}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ports/<port_id>', methods=['DELETE'])
def delete_port(port_id):
    """Delete a port. Will fail if still attached to a running instance."""
    try:
        token, eps, _ = authenticate()
        os_delete(eps['network'] + f'/v2.0/ports/{port_id}', token)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/interfaces', methods=['POST'])
def attach_interface(server_id):
    """Attach a port or a new interface to a running instance.
    Body: {port_id} to attach an existing port, or {network_id} to create one on-the-fly."""
    try:
        token, eps, _ = authenticate()
        data       = request.json
        port_id    = (data.get('port_id') or '').strip()
        network_id = (data.get('network_id') or '').strip()
        if not port_id and not network_id:
            return jsonify({'error': 'port_id or network_id is required'}), 400

        payload = {'interfaceAttachment': {}}
        if port_id:
            payload['interfaceAttachment']['port_id'] = port_id
        else:
            payload['interfaceAttachment']['net_id'] = network_id

        _, resp = os_post(eps['compute'] + f'/servers/{server_id}/os-interface', token, payload)
        iface = resp.get('interfaceAttachment', {})
        return jsonify({'port_id': iface.get('port_id', ''), 'status': 'attached'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/interfaces/<port_id>', methods=['DELETE'])
def detach_interface(server_id, port_id):
    """Detach a network interface from an instance without deleting the port."""
    try:
        token, eps, _ = authenticate()
        os_delete(eps['compute'] + f'/servers/{server_id}/os-interface/{port_id}', token)
        return jsonify({'status': 'detached'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances/<server_id>/interfaces')
def list_interfaces(server_id):
    """List all network interfaces currently attached to an instance."""
    try:
        token, eps, _ = authenticate()
        ifaces = os_get(eps['compute'] + f'/servers/{server_id}/os-interface', token).get('interfaceAttachments', [])
        return jsonify([{
            'port_id':    i['port_id'],
            'mac_address':i.get('mac_addr', ''),
            'network_id': i.get('net_id', ''),
            'status':     i.get('port_state', ''),
            'fixed_ips':  [{'ip': fip['ip_address'], 'subnet_id': fip.get('subnet_id', '')} for fip in i.get('fixed_ips', [])],
        } for i in ifaces])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Resource Quotas ───────────────────────────────────────────────────────────

@app.route('/api/quotas')
def api_quotas():
    """Return compute, volume, and network quotas with usage for all projects."""
    try:
        token, eps, host_ip = authenticate()
        projects = os_get(f'http://{host_ip}/identity/v3/projects', token).get('projects', [])

        result = []
        for p in projects:
            pid = p['id']
            # detail=1 returns {in_use, limit, reserved} per field
            compute_q = os_get(eps['compute'] + f'/os-quota-sets/{pid}', token, {'usage': 'True'}).get('quota_set', {})
            volume_q  = os_get(vol_endpoint(eps) + f'/os-quota-sets/{pid}', token, {'usage': 'True'}).get('quota_set', {})
            network_q = os_get(eps['network'] + f'/v2.0/quotas/{pid}/details.json', token).get('quota', {})

            result.append({
                'project_id':   pid,
                'project_name': p['name'],
                'compute': {
                    'instances': compute_q.get('instances', {}),
                    'vcpus':     compute_q.get('cores', {}),
                    'ram_mb':    compute_q.get('ram', {}),
                    'key_pairs': compute_q.get('key_pairs', {}),
                },
                'storage': {
                    'volumes':   volume_q.get('volumes', {}),
                    'snapshots': volume_q.get('snapshots', {}),
                    'gigabytes': volume_q.get('gigabytes', {}),
                },
                'network': {
                    'networks':        network_q.get('network', {}),
                    'subnets':         network_q.get('subnet', {}),
                    'routers':         network_q.get('router', {}),
                    'floating_ips':    network_q.get('floatingip', {}),
                    'security_groups': network_q.get('security_group', {}),
                    'ports':           network_q.get('port', {}),
                },
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/quotas/<project_id>', methods=['PUT'])
def update_quota(project_id):
    """Update a compute or volume quota limit for a project.
    Body: {type, key, value}. type: 'compute' | 'volume'. value -1 = unlimited."""
    try:
        token, eps, _ = authenticate()
        data  = request.json
        qtype = data.get('type', 'compute')
        key   = (data.get('key') or '').strip()
        value = int(data.get('value', -1))
        if not key:
            return jsonify({'error': 'key is required'}), 400

        if qtype == 'compute':
            url = eps['compute'] + f'/os-quota-sets/{project_id}'
        elif qtype == 'volume':
            url = vol_endpoint(eps) + f'/os-quota-sets/{project_id}'
        else:
            return jsonify({'error': 'type must be compute or volume'}), 400

        r = requests.put(
            url,
            headers={'X-Auth-Token': token, 'Content-Type': 'application/json'},
            json={"quota_set": {key: value}},
            timeout=15
        )
        r.raise_for_status()
        return jsonify({'status': 'updated', 'key': key, 'value': value})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── IAM — Users ──────────────────────────────────────────────────────────────

@app.route('/api/iam/users')
def list_iam_users():
    """List all IAM users with their attached policies and group memberships."""
    data       = read_iam_data()
    policy_map = {p['arn']: p['name'] for p in data['policies']}
    group_map  = {g['id']: g['name'] for g in data['groups']}
    return jsonify([{
        'id':                u['id'],
        'username':          u['username'],
        'arn':               u['arn'],
        'created_at':        u.get('created_at', ''),
        'attached_policies': [{'arn': a, 'name': policy_map.get(a, a)} for a in u.get('attached_policies', [])],
        'groups':            [{'id': g, 'name': group_map.get(g, g)} for g in u.get('groups', [])],
    } for u in data['users']])


@app.route('/api/iam/users', methods=['POST'])
def create_iam_user():
    """Create an IAM user. Body: {username}."""
    data     = read_iam_data()
    username = (request.json.get('username') or '').strip()
    if not username:
        return jsonify({'error': 'username is required'}), 400
    if any(u['username'] == username for u in data['users']):
        return jsonify({'error': f'User "{username}" already exists'}), 409

    user = {
        'id':                _new_iam_id('AIDA'),
        'username':          username,
        'arn':               f'arn:aws:iam::{IAM_ACCOUNT_ID}:user/{username}',
        'created_at':        _iam_now(),
        'attached_policies': [],
        'groups':            [],
    }
    data['users'].append(user)
    write_iam_data(data)
    return jsonify(user), 201


@app.route('/api/iam/users/<user_id>', methods=['DELETE'])
def delete_iam_user(user_id):
    """Delete an IAM user and remove them from all groups."""
    data = read_iam_data()
    user = next((u for u in data['users'] if u['id'] == user_id), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Remove this user from all groups before deleting
    for g in data['groups']:
        g['members'] = [m for m in g.get('members', []) if m != user_id]

    data['users'] = [u for u in data['users'] if u['id'] != user_id]
    write_iam_data(data)
    return jsonify({'status': 'deleted'})


@app.route('/api/iam/users/<user_id>/attach-policy', methods=['POST'])
def attach_policy_to_user(user_id):
    """Attach a policy to a user. Body: {policy_arn}."""
    data       = read_iam_data()
    user       = next((u for u in data['users'] if u['id'] == user_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not user:
        return jsonify({'error': 'User not found'}), 404
    if not policy_arn:
        return jsonify({'error': 'policy_arn is required'}), 400
    if not any(p['arn'] == policy_arn for p in data['policies']):
        return jsonify({'error': 'Policy not found'}), 404
    if policy_arn in user.get('attached_policies', []):
        return jsonify({'error': 'Policy already attached'}), 409

    user.setdefault('attached_policies', []).append(policy_arn)
    write_iam_data(data)
    return jsonify({'status': 'attached'})


@app.route('/api/iam/users/<user_id>/detach-policy', methods=['POST'])
def detach_policy_from_user(user_id):
    """Detach a policy from a user. Body: {policy_arn}."""
    data       = read_iam_data()
    user       = next((u for u in data['users'] if u['id'] == user_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not user:
        return jsonify({'error': 'User not found'}), 404
    user['attached_policies'] = [a for a in user.get('attached_policies', []) if a != policy_arn]
    write_iam_data(data)
    return jsonify({'status': 'detached'})


# ── IAM — Groups ─────────────────────────────────────────────────────────────

@app.route('/api/iam/groups')
def list_iam_groups():
    """List all IAM groups with attached policies and member usernames."""
    data       = read_iam_data()
    policy_map = {p['arn']: p['name'] for p in data['policies']}
    user_map   = {u['id']: u['username'] for u in data['users']}
    return jsonify([{
        'id':                g['id'],
        'name':              g['name'],
        'arn':               g['arn'],
        'created_at':        g.get('created_at', ''),
        'attached_policies': [{'arn': a, 'name': policy_map.get(a, a)} for a in g.get('attached_policies', [])],
        'members':           [{'id': m, 'username': user_map.get(m, m)} for m in g.get('members', [])],
    } for g in data['groups']])


@app.route('/api/iam/groups', methods=['POST'])
def create_iam_group():
    """Create an IAM group. Body: {name}."""
    data = read_iam_data()
    name = (request.json.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if any(g['name'] == name for g in data['groups']):
        return jsonify({'error': f'Group "{name}" already exists'}), 409

    group = {
        'id':                _new_iam_id('AGPA'),
        'name':              name,
        'arn':               f'arn:aws:iam::{IAM_ACCOUNT_ID}:group/{name}',
        'created_at':        _iam_now(),
        'attached_policies': [],
        'members':           [],
    }
    data['groups'].append(group)
    write_iam_data(data)
    return jsonify(group), 201


@app.route('/api/iam/groups/<group_id>', methods=['DELETE'])
def delete_iam_group(group_id):
    """Delete a group and remove group membership from all users."""
    data  = read_iam_data()
    group = next((g for g in data['groups'] if g['id'] == group_id), None)
    if not group:
        return jsonify({'error': 'Group not found'}), 404

    # Remove this group from all user records before deleting
    for u in data['users']:
        u['groups'] = [g for g in u.get('groups', []) if g != group_id]

    data['groups'] = [g for g in data['groups'] if g['id'] != group_id]
    write_iam_data(data)
    return jsonify({'status': 'deleted'})


@app.route('/api/iam/groups/<group_id>/attach-policy', methods=['POST'])
def attach_policy_to_group(group_id):
    """Attach a policy to a group. Body: {policy_arn}."""
    data       = read_iam_data()
    group      = next((g for g in data['groups'] if g['id'] == group_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not group:
        return jsonify({'error': 'Group not found'}), 404
    if not policy_arn:
        return jsonify({'error': 'policy_arn is required'}), 400
    if not any(p['arn'] == policy_arn for p in data['policies']):
        return jsonify({'error': 'Policy not found'}), 404
    if policy_arn in group.get('attached_policies', []):
        return jsonify({'error': 'Policy already attached'}), 409

    group.setdefault('attached_policies', []).append(policy_arn)
    write_iam_data(data)
    return jsonify({'status': 'attached'})


@app.route('/api/iam/groups/<group_id>/detach-policy', methods=['POST'])
def detach_policy_from_group(group_id):
    """Detach a policy from a group. Body: {policy_arn}."""
    data       = read_iam_data()
    group      = next((g for g in data['groups'] if g['id'] == group_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not group:
        return jsonify({'error': 'Group not found'}), 404
    group['attached_policies'] = [a for a in group.get('attached_policies', []) if a != policy_arn]
    write_iam_data(data)
    return jsonify({'status': 'detached'})


@app.route('/api/iam/groups/<group_id>/add-user', methods=['POST'])
def add_user_to_group(group_id):
    """Add a user to a group. Body: {user_id}."""
    data    = read_iam_data()
    group   = next((g for g in data['groups'] if g['id'] == group_id), None)
    user_id = (request.json.get('user_id') or '').strip()
    user    = next((u for u in data['users'] if u['id'] == user_id), None)

    if not group:
        return jsonify({'error': 'Group not found'}), 404
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user_id in group.get('members', []):
        return jsonify({'error': 'User already in group'}), 409

    group.setdefault('members', []).append(user_id)
    user.setdefault('groups', []).append(group_id)
    write_iam_data(data)
    return jsonify({'status': 'added'})


@app.route('/api/iam/groups/<group_id>/remove-user', methods=['POST'])
def remove_user_from_group(group_id):
    """Remove a user from a group. Body: {user_id}."""
    data    = read_iam_data()
    group   = next((g for g in data['groups'] if g['id'] == group_id), None)
    user_id = (request.json.get('user_id') or '').strip()
    user    = next((u for u in data['users'] if u['id'] == user_id), None)

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    group['members'] = [m for m in group.get('members', []) if m != user_id]
    if user:
        user['groups'] = [g for g in user.get('groups', []) if g != group_id]

    write_iam_data(data)
    return jsonify({'status': 'removed'})


# ── IAM — Roles ──────────────────────────────────────────────────────────────

@app.route('/api/iam/roles')
def list_iam_roles():
    """List all IAM roles with their attached policies."""
    data       = read_iam_data()
    policy_map = {p['arn']: p['name'] for p in data['policies']}
    return jsonify([{
        'id':                r['id'],
        'name':              r['name'],
        'arn':               r['arn'],
        'description':       r.get('description', ''),
        'trusted_service':   r.get('trusted_service', ''),
        'created_at':        r.get('created_at', ''),
        'attached_policies': [{'arn': a, 'name': policy_map.get(a, a)} for a in r.get('attached_policies', [])],
    } for r in data['roles']])


@app.route('/api/iam/roles', methods=['POST'])
def create_iam_role():
    """Create an IAM role. Body: {name, description, trusted_service}."""
    data            = read_iam_data()
    d               = request.json
    name            = (d.get('name') or '').strip()
    description     = (d.get('description') or '').strip()
    # trusted_service is the AWS service principal allowed to assume this role
    trusted_service = (d.get('trusted_service') or 'ec2.amazonaws.com').strip()

    if not name:
        return jsonify({'error': 'name is required'}), 400
    if any(r['name'] == name for r in data['roles']):
        return jsonify({'error': f'Role "{name}" already exists'}), 409

    role = {
        'id':              _new_iam_id('AROA'),
        'name':            name,
        'arn':             f'arn:aws:iam::{IAM_ACCOUNT_ID}:role/{name}',
        'description':     description,
        'trusted_service': trusted_service,
        'created_at':      _iam_now(),
        'trust_policy': {
            'Version': '2012-10-17',
            'Statement': [{
                'Effect': 'Allow',
                'Principal': {'Service': trusted_service},
                'Action': 'sts:AssumeRole',
            }],
        },
        'attached_policies': [],
    }
    data['roles'].append(role)
    write_iam_data(data)
    return jsonify(role), 201


@app.route('/api/iam/roles/<role_id>', methods=['DELETE'])
def delete_iam_role(role_id):
    """Delete an IAM role."""
    data = read_iam_data()
    role = next((r for r in data['roles'] if r['id'] == role_id), None)
    if not role:
        return jsonify({'error': 'Role not found'}), 404
    data['roles'] = [r for r in data['roles'] if r['id'] != role_id]
    write_iam_data(data)
    return jsonify({'status': 'deleted'})


@app.route('/api/iam/roles/<role_id>/attach-policy', methods=['POST'])
def attach_policy_to_role(role_id):
    """Attach a policy to a role. Body: {policy_arn}."""
    data       = read_iam_data()
    role       = next((r for r in data['roles'] if r['id'] == role_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not role:
        return jsonify({'error': 'Role not found'}), 404
    if not policy_arn:
        return jsonify({'error': 'policy_arn is required'}), 400
    if not any(p['arn'] == policy_arn for p in data['policies']):
        return jsonify({'error': 'Policy not found'}), 404
    if policy_arn in role.get('attached_policies', []):
        return jsonify({'error': 'Policy already attached'}), 409

    role.setdefault('attached_policies', []).append(policy_arn)
    write_iam_data(data)
    return jsonify({'status': 'attached'})


@app.route('/api/iam/roles/<role_id>/detach-policy', methods=['POST'])
def detach_policy_from_role(role_id):
    """Detach a policy from a role. Body: {policy_arn}."""
    data       = read_iam_data()
    role       = next((r for r in data['roles'] if r['id'] == role_id), None)
    policy_arn = (request.json.get('policy_arn') or '').strip()

    if not role:
        return jsonify({'error': 'Role not found'}), 404
    role['attached_policies'] = [a for a in role.get('attached_policies', []) if a != policy_arn]
    write_iam_data(data)
    return jsonify({'status': 'detached'})


# ── IAM — Policies ────────────────────────────────────────────────────────────

@app.route('/api/iam/policies')
def list_iam_policies():
    """List all IAM policies (AWS managed + customer-managed)."""
    data = read_iam_data()
    return jsonify([{
        'id':          p['id'],
        'name':        p['name'],
        'arn':         p['arn'],
        'description': p.get('description', ''),
        'is_managed':  p.get('is_managed', False),
        'created_at':  p.get('created_at', ''),
    } for p in data['policies']])


@app.route('/api/iam/policies/<policy_id>')
def get_iam_policy(policy_id):
    """Get full policy detail including the JSON document."""
    data   = read_iam_data()
    policy = next((p for p in data['policies'] if p['id'] == policy_id), None)
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    return jsonify(policy)


@app.route('/api/iam/policies', methods=['POST'])
def create_iam_policy():
    """Create a customer-managed policy. Body: {name, description, document}."""
    data        = read_iam_data()
    d           = request.json
    name        = (d.get('name') or '').strip()
    description = (d.get('description') or '').strip()
    document    = d.get('document')

    if not name:
        return jsonify({'error': 'name is required'}), 400
    if document is None:
        return jsonify({'error': 'document is required'}), 400
    if not isinstance(document, dict) or 'Statement' not in document:
        return jsonify({'error': 'document must be a JSON object with a Statement array'}), 400
    if any(p['name'] == name for p in data['policies']):
        return jsonify({'error': f'Policy "{name}" already exists'}), 409

    policy = {
        'id':          _new_iam_id('ANPA'),
        'name':        name,
        'arn':         f'arn:aws:iam::{IAM_ACCOUNT_ID}:policy/{name}',
        'description': description,
        'is_managed':  False,
        'created_at':  _iam_now(),
        'document':    document,
    }
    data['policies'].append(policy)
    write_iam_data(data)
    return jsonify(policy), 201


@app.route('/api/iam/policies/<policy_id>', methods=['DELETE'])
def delete_iam_policy(policy_id):
    """Delete a customer-managed policy; auto-detaches it from all entities first."""
    data   = read_iam_data()
    policy = next((p for p in data['policies'] if p['id'] == policy_id), None)
    if not policy:
        return jsonify({'error': 'Policy not found'}), 404
    if policy.get('is_managed'):
        return jsonify({'error': 'AWS managed policies cannot be deleted'}), 403

    arn = policy['arn']
    # Auto-detach from all entities so no dangling references remain
    for u in data['users']:
        u['attached_policies'] = [a for a in u.get('attached_policies', []) if a != arn]
    for g in data['groups']:
        g['attached_policies'] = [a for a in g.get('attached_policies', []) if a != arn]
    for r in data['roles']:
        r['attached_policies'] = [a for a in r.get('attached_policies', []) if a != arn]

    data['policies'] = [p for p in data['policies'] if p['id'] != policy_id]
    write_iam_data(data)
    return jsonify({'status': 'deleted'})


if __name__ == '__main__':
    host_ip = detect_host_ip()
    print(f'\n  Dashboard  →  http://localhost:8080')
    print(f'  Network    →  http://{host_ip}:8080')
    print(f'  OpenStack  →  http://{host_ip}/identity\n')
    app.run(host='0.0.0.0', port=8080, debug=False)
