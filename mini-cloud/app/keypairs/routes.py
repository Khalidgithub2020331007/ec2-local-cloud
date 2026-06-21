from flask import Blueprint, request, jsonify, g
from app.auth.middleware import require_auth
from app.keypairs.models import (
    generate_rsa_keypair, compute_fingerprint,
    create_keypair, get_keypair, list_keypairs, delete_keypair,
)

keypairs_bp = Blueprint('keypairs', __name__, url_prefix='/api/v1/keypairs')

_MAX_PUBLIC_KEY_BYTES = 8192


@keypairs_bp.route('', methods=['GET'])
@require_auth
def list_all():
    pairs = list_keypairs(g.current_user['id'])
    return jsonify({'keypairs': pairs, 'count': len(pairs)}), 200


@keypairs_bp.route('/generate', methods=['POST'])
@require_auth
def generate():
    # Private key is returned here and NEVER stored — caller must save it immediately.
    # The private key is only needed by the SSH client; the server only needs the public half.
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400

    private_pem, public_openssh = generate_rsa_keypair()
    fingerprint = compute_fingerprint(public_openssh)
    keypair_id  = create_keypair(g.current_user['id'], name, public_openssh, fingerprint)

    return jsonify({
        'message':     'Key pair generated. Save the private key now — it will not be shown again.',
        'keypair': {
            'id':          keypair_id,
            'name':        name,
            'fingerprint': fingerprint,
        },
        'private_key': private_pem,
    }), 201


@keypairs_bp.route('/upload', methods=['POST'])
@require_auth
def upload():
    data       = request.get_json(silent=True) or {}
    name       = data.get('name', '').strip()
    public_key = data.get('public_key', '').strip()

    if not name:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'name is required', 'statusCode': 400}), 400
    if not public_key:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'public_key is required', 'statusCode': 400}), 400
    if len(public_key.encode()) > _MAX_PUBLIC_KEY_BYTES:
        return jsonify({'error': 'VALIDATION_ERROR', 'message': 'public_key too large', 'statusCode': 400}), 400

    # Validate it looks like an SSH public key — must have at least two space-separated tokens
    parts = public_key.split()
    if len(parts) < 2 or not parts[0].startswith('ssh-'):
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'public_key must be a valid SSH public key (ssh-rsa, ssh-ed25519, etc.)',
                        'statusCode': 400}), 400

    try:
        fingerprint = compute_fingerprint(public_key)
    except Exception:
        return jsonify({'error': 'VALIDATION_ERROR',
                        'message': 'Could not parse public key — invalid base64 or format',
                        'statusCode': 400}), 400

    keypair_id = create_keypair(g.current_user['id'], name, public_key, fingerprint)
    keypair    = get_keypair(keypair_id)
    return jsonify({'message': 'Key pair imported', 'keypair': keypair}), 201


@keypairs_bp.route('/<keypair_id>', methods=['DELETE'])
@require_auth
def delete(keypair_id):
    deleted = delete_keypair(keypair_id, g.current_user['id'])
    if not deleted:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Key pair not found', 'statusCode': 404}), 404
    # Deleting a keypair does not affect running VMs — the public key is already inside the VM's authorized_keys.
    return jsonify({'message': 'Key pair deleted'}), 200


@keypairs_bp.route('/<keypair_id>/public', methods=['GET'])
@require_auth
def get_public(keypair_id):
    keypair = get_keypair(keypair_id, g.current_user['id'])
    if not keypair:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Key pair not found', 'statusCode': 404}), 404
    return jsonify({'public_key': keypair['public_key']}), 200
