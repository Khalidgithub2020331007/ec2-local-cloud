from flask import Blueprint, jsonify, render_template, request, g
from app.auth.middleware import require_auth
from app.compute.models import get_instance
from app.console.proxy import get_vnc_port, start_console_proxy

console_bp = Blueprint('console', __name__)


@console_bp.route('/api/v1/instances/<instance_id>/console', methods=['GET'])
@require_auth
def get_console(instance_id):
    """Return the WebSocket URL for this VM's VNC console.

    The browser cannot connect directly to the VNC TCP port — browsers only
    support WebSockets. This endpoint starts a websockify bridge process that
    translates WebSocket traffic to raw TCP and forwards it to the VNC port.
    """
    instance = get_instance(instance_id, g.current_user['id'])
    if not instance:
        return jsonify({'error': 'NOT_FOUND', 'message': 'Instance not found', 'statusCode': 404}), 404

    if instance['status'] != 'running':
        return jsonify({
            'error': 'INSTANCE_NOT_RUNNING',
            'message': 'Instance must be running to open a console',
            'statusCode': 409,
        }), 409

    try:
        vnc_port = get_vnc_port(instance_id, instance['libvirt_name'])
        ws_port = start_console_proxy(instance_id, vnc_port)
    except RuntimeError as e:
        return jsonify({'error': 'CONSOLE_ERROR', 'message': str(e), 'statusCode': 500}), 500

    # Use the Host header so the URL works regardless of which IP the user accesses
    host = request.host.split(':')[0]  # strip port if present
    websocket_url = f'ws://{host}:{ws_port}'

    return jsonify({
        'websocket_url': websocket_url,
        'vnc_port': vnc_port,
        'ws_port': ws_port,
        'instance_id': instance_id,
        'instance_name': instance['name'],
    }), 200


@console_bp.route('/console/<instance_id>', methods=['GET'])
def console_page(instance_id):
    """Serve the noVNC console page for a running VM.

    No auth check here because the page itself has no secrets — the JWT is
    checked by the /api/v1/instances/{id}/console endpoint that the page calls
    first to obtain the WebSocket URL.
    """
    return render_template('console.html', instance_id=instance_id)
