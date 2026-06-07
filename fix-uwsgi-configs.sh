#!/bin/bash
# Recreates the three uwsgi ini files that DevStack generates during stack.sh
# but doesn't persist after cleanup. Run once with sudo from a terminal.
# 16-core machine → API_WORKERS=4 (max(2, nproc/4))

set -e

# nova-api: unix socket, apache proxies /compute to it
sudo tee /etc/nova/nova-api-uwsgi.ini > /dev/null <<'EOF'
[uwsgi]
module = nova.wsgi.osapi_compute:application
processes = 4
master = true
die-on-term = true
exit-on-reload = false
worker-reload-mercy = 80
enable-threads = true
plugins = http,python3
thunder-lock = true
hook-master-start = unix_signal:15 gracefully_kill_them_all
buffer-size = 65535
add-header = Connection: close
lazy-apps = true
start-time = %t
socket = /var/run/uwsgi/nova-api.socket
chmod-socket = 666
EOF

# nova-metadata: binds directly to HTTP 0.0.0.0:8775 (no apache proxy)
sudo tee /etc/nova/nova-metadata-uwsgi.ini > /dev/null <<'EOF'
[uwsgi]
module = nova.wsgi.metadata:application
processes = 4
master = true
die-on-term = true
exit-on-reload = false
worker-reload-mercy = 80
enable-threads = true
plugins = http,python3
thunder-lock = true
hook-master-start = unix_signal:15 gracefully_kill_them_all
buffer-size = 65535
add-header = Connection: close
lazy-apps = true
start-time = %t
http = 0.0.0.0:8775
EOF

# cinder-api: unix socket, apache proxies /volume to it
sudo tee /etc/cinder/cinder-api-uwsgi.ini > /dev/null <<'EOF'
[uwsgi]
module = cinder.wsgi.api:application
processes = 4
master = true
die-on-term = true
exit-on-reload = false
worker-reload-mercy = 80
enable-threads = true
plugins = http,python3
thunder-lock = true
hook-master-start = unix_signal:15 gracefully_kill_them_all
buffer-size = 65535
add-header = Connection: close
lazy-apps = true
start-time = %t
socket = /var/run/uwsgi/cinder-api.socket
chmod-socket = 666
EOF

sudo systemctl restart devstack@n-api devstack@n-api-meta devstack@c-api
sleep 3
systemctl is-active devstack@n-api devstack@n-api-meta devstack@c-api
echo "Done."
