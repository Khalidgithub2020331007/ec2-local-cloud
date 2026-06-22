import subprocess
import logging

logger = logging.getLogger(__name__)

# { instance_id: subprocess.Popen } — one websockify process per active console session
_proxies: dict[str, subprocess.Popen] = {}

# websocket_port = vnc_port + 1000 so they never collide with VNC ports
_WS_PORT_OFFSET = 1000

# noVNC static files are served by Flask — websockify does NOT serve them
NOVNC_STATIC_PATH = None  # not used; Flask handles static serving


def get_vnc_port(instance_id: str, libvirt_name: str) -> int:
    """Read the VNC port libvirt auto-assigned when the VM started.

    libvirt allocates VNC ports dynamically (port='-1' autoport='yes' in XML).
    The actual assigned port is only visible after the domain starts, so we
    must read the live XML — not the definition XML.
    """
    from app.compute.libvirt_manager import get_vm_vnc_port
    port = get_vm_vnc_port(libvirt_name)
    if port <= 0:
        raise RuntimeError(f'VM {libvirt_name} has no VNC port — is it running?')
    return port


def start_console_proxy(instance_id: str, vnc_port: int) -> int:
    """Start a websockify process for this VM if one is not already running.

    Returns the WebSocket port the browser should connect to.
    Reuses an existing process if one is alive for the same instance_id.
    """
    ws_port = vnc_port + _WS_PORT_OFFSET

    existing = _proxies.get(instance_id)
    if existing is not None and existing.poll() is None:
        # Process is still alive — reuse it
        return ws_port

    # websockify --wrap-mode=ignore keeps the process alive even after disconnect
    # so the user can reconnect without requesting a new proxy.
    cmd = [
        'websockify',
        '--wrap-mode=ignore',
        f'0.0.0.0:{ws_port}',
        f'localhost:{vnc_port}',
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(
            'websockify not found. Install it with: pip3 install websockify'
        )

    _proxies[instance_id] = proc
    logger.info('Started websockify for instance %s: ws-port=%d vnc-port=%d pid=%d',
                instance_id, ws_port, vnc_port, proc.pid)
    return ws_port


def stop_console_proxy(instance_id: str) -> None:
    """Kill the websockify process for this VM, if one is running.

    Called when the VM is terminated so we don't leak processes.
    """
    proc = _proxies.pop(instance_id, None)
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    logger.info('Stopped websockify proxy for instance %s', instance_id)
