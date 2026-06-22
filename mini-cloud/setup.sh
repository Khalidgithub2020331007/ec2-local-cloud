#!/usr/bin/env bash
# Mini Cloud System — one-command setup for Ubuntu 24.04
# Run as root or with sudo. Leaves the Flask app running on port 5001.

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="http://localhost:5001"
VG_NAME="mini-cloud-vg"
CIRROS_URL="https://download.cirros-cloud.net/0.6.2/cirros-0.6.2-x86_64-disk.img"
CIRROS_LOCAL="/tmp/cirros-0.6.2.img"
ADMIN_USER="admin"
ADMIN_PASS="Admin1234"
ADMIN_EMAIL="admin@minicloud.local"

# ── Step 1 — Verify OS ────────────────────────────────────────────────────────
info "Step 1/12 — Checking OS..."
if ! grep -q 'Ubuntu 24.04' /etc/os-release 2>/dev/null; then
    error "This script requires Ubuntu 24.04 LTS. Detected: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2)"
fi
info "OS check passed: Ubuntu 24.04 LTS"

# ── Step 2 — Check VMX (KVM hardware virtualisation) ─────────────────────────
info "Step 2/12 — Checking CPU virtualisation support..."
if ! grep -qE '(vmx|svm)' /proc/cpuinfo; then
    error "CPU does not expose VMX/SVM flag. Enable hardware virtualisation in BIOS or use nested virt."
fi
# Also check that /dev/kvm is accessible or can be created
if [[ ! -e /dev/kvm ]]; then
    warn "/dev/kvm not found — KVM module may not be loaded yet. Continuing; kvm_intel/kvm_amd will load after package install."
fi
info "CPU virtualisation flag present"

# ── Step 3 — Install system packages ─────────────────────────────────────────
info "Step 3/12 — Installing system packages (this may take a few minutes)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    libvirt-dev libvirt-daemon-system libvirt-clients \
    qemu-kvm qemu-utils \
    haproxy \
    genisoimage \
    socat websockify \
    lvm2 \
    curl jq \
    bridge-utils iptables

# Load KVM module if not already loaded
modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true

# Enable and start libvirtd
systemctl enable libvirtd --quiet
systemctl start  libvirtd
info "System packages installed"

# ── Step 4 — Create Python virtual environment ────────────────────────────────
info "Step 4/12 — Creating Python virtual environment..."
VENV_DIR="$SCRIPT_DIR/venv"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
info "Virtual environment ready: $VENV_DIR"

# ── Step 5 — Install Python dependencies ─────────────────────────────────────
info "Step 5/12 — Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet flask libvirt-python pyjwt cryptography requests werkzeug
info "Python packages installed"

# ── Step 6 — Create LVM Volume Group ─────────────────────────────────────────
info "Step 6/12 — Setting up LVM volume group '$VG_NAME'..."
if vgs "$VG_NAME" &>/dev/null; then
    info "Volume group '$VG_NAME' already exists — skipping"
else
    # Try to find a spare block device that is not mounted and not the OS disk
    OS_DISK=$(lsblk -ndo PKNAME "$(findmnt -n -o SOURCE /)" 2>/dev/null || \
              lsblk -ndo PKNAME "$(df / | tail -1 | awk '{print $1}')" 2>/dev/null || echo "")
    SPARE_DISK=""
    while IFS= read -r dev; do
        disk="/dev/$dev"
        # Skip if it IS the OS disk or a partition/loop/rom device
        [[ "$dev" == "$OS_DISK" ]] && continue
        [[ "$(lsblk -ndo TYPE "$disk" 2>/dev/null)" != "disk" ]] && continue
        # Skip if it has partitions or is mounted
        MOUNT_COUNT=$(lsblk -no MOUNTPOINT "$disk" 2>/dev/null | grep -c . || true)
        [[ "$MOUNT_COUNT" -gt 0 ]] && continue
        SPARE_DISK="$disk"
        break
    done < <(lsblk -ndo NAME)

    if [[ -n "$SPARE_DISK" ]]; then
        info "Using spare disk $SPARE_DISK for LVM"
        pvcreate "$SPARE_DISK"
        vgcreate "$VG_NAME" "$SPARE_DISK"
    else
        # No spare disk — create a 20 GB loopback-backed VG for the demo
        warn "No spare disk found. Creating a 20 GB loop-device-backed VG for the demo."
        LOOP_FILE="/var/lib/mini-cloud-lvm.img"
        if [[ ! -f "$LOOP_FILE" ]]; then
            dd if=/dev/zero of="$LOOP_FILE" bs=1M count=20480 status=progress
        fi
        LOOP_DEV=$(losetup --find --show "$LOOP_FILE")
        pvcreate "$LOOP_DEV"
        vgcreate "$VG_NAME" "$LOOP_DEV"
        # Persist loop device so it survives reboots
        LOOP_UNIT="/etc/systemd/system/mini-cloud-loop.service"
        cat > "$LOOP_UNIT" <<EOF
[Unit]
Description=Mini Cloud LVM loop device
DefaultDependencies=no
Before=lvm2.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/losetup --find --show $LOOP_FILE
ExecStop=/sbin/losetup -d $LOOP_DEV

[Install]
WantedBy=sysinit.target
EOF
        systemctl daemon-reload
        systemctl enable mini-cloud-loop --quiet
    fi
    info "LVM volume group '$VG_NAME' created"
fi

# ── Step 7 — Start Flask (initialises DB and seeds IAM + quotas) ──────────────
info "Step 7/12 — Starting Flask application..."
LOG_FILE="/tmp/mini-cloud.log"
PID_FILE="/tmp/mini-cloud.pid"

# Kill any existing instance on port 5001
pkill -f "run.py" 2>/dev/null || true
sleep 1

cd "$SCRIPT_DIR"
nohup "$VENV_DIR/bin/python" run.py > "$LOG_FILE" 2>&1 &
FLASK_PID=$!
echo "$FLASK_PID" > "$PID_FILE"

# Wait for the server to accept connections (up to 30 s)
READY=false
for i in $(seq 1 30); do
    if curl -sf "$BASE_URL" -o /dev/null 2>/dev/null; then
        READY=true
        break
    fi
    sleep 1
done

if [[ "$READY" != "true" ]]; then
    error "Flask did not start within 30 seconds. Check $LOG_FILE for errors."
fi
info "Flask started (PID $FLASK_PID), DB initialised"

# ── Step 8 — DB and IAM seed ──────────────────────────────────────────────────
# init_db() in database.py seeds the 7 AWS managed IAM policies and quota
# defaults automatically on first startup — nothing extra to do here.
info "Step 8/12 — Database schema and IAM policies already seeded by Flask startup"

# ── Step 9 — Create default admin user ───────────────────────────────────────
info "Step 9/12 — Creating admin user..."
REGISTER_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USER\",\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASS\"}" \
    2>/dev/null || echo '{}')

if echo "$REGISTER_RESP" | grep -q '"CONFLICT"'; then
    info "Admin user already exists — skipping"
else
    # Promote to admin role via direct DB update (the API has no role endpoint)
    "$VENV_DIR/bin/python" - <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import get_connection
conn = get_connection()
conn.execute("UPDATE users SET role='admin' WHERE username='admin'")
conn.commit()
conn.close()
print("Admin role granted")
PYEOF
    info "Admin user created: username='$ADMIN_USER' password='$ADMIN_PASS'"
fi

# ── Step 10 — Download CirrOS test image ──────────────────────────────────────
info "Step 10/12 — Downloading CirrOS test image..."
if [[ ! -f "$CIRROS_LOCAL" ]]; then
    curl -L --progress-bar -o "$CIRROS_LOCAL" "$CIRROS_URL"
else
    info "CirrOS already downloaded at $CIRROS_LOCAL"
fi

# Upload the image to the Mini Cloud image store via API
# First, get a JWT token for admin
TOKEN=$(curl -sf -X POST "$BASE_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" \
    2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token',''))" || echo "")

if [[ -z "$TOKEN" ]]; then
    warn "Could not get JWT token — image upload skipped. Run manually after starting the app."
else
    # Check if image is already uploaded
    IMAGE_EXISTS=$(curl -sf "$BASE_URL/api/v1/images" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if any(i['name']=='CirrOS 0.6.2' for i in d.get('images',[])) else 'no')" 2>/dev/null || echo "no")

    if [[ "$IMAGE_EXISTS" == "yes" ]]; then
        info "CirrOS image already in image store — skipping upload"
    else
        info "Uploading CirrOS to image store..."
        UPLOAD_RESP=$(curl -sf -X POST "$BASE_URL/api/v1/images" \
            -H "Authorization: Bearer $TOKEN" \
            -F "name=CirrOS 0.6.2" \
            -F "description=CirrOS test image for demo" \
            -F "file=@$CIRROS_LOCAL" \
            2>/dev/null || echo '{}')
        if echo "$UPLOAD_RESP" | grep -q '"id"'; then
            IMAGE_ID=$(echo "$UPLOAD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('image',{}).get('id',''))" 2>/dev/null)
            info "CirrOS uploaded (image_id: $IMAGE_ID)"
        else
            warn "Image upload returned unexpected response — check manually."
        fi
    fi
fi

# ── Step 11 — Flask is already running (started in step 7) ────────────────────
info "Step 11/12 — Flask is running (PID $(cat $PID_FILE 2>/dev/null || echo unknown))"
info "            Logs: $LOG_FILE"
info "            PID file: $PID_FILE"

# ── Step 12 — Done ────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Mini Cloud ready at http://localhost:5001${NC}"
echo -e "${GREEN}  Dashboard: http://localhost:5001${NC}"
echo -e "${GREEN}  Login: admin / Admin1234${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
info "Step 12/12 — Setup complete"
