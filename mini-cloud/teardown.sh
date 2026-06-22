#!/usr/bin/env bash
# Mini Cloud System — teardown script
# Stops Flask, destroys all VMs, removes LVM VG, drops the database.

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VG_NAME="mini-cloud-vg"
PID_FILE="/tmp/mini-cloud.pid"

echo ""
echo -e "${RED}════════════════════════════════════════════════════════${NC}"
echo -e "${RED}  WARNING: This will destroy ALL Mini Cloud data.${NC}"
echo -e "${RED}  VMs, volumes, images, database — everything.${NC}"
echo -e "${RED}════════════════════════════════════════════════════════${NC}"
echo ""
read -r -p "Type 'yes' to continue: " CONFIRM
[[ "$CONFIRM" != "yes" ]] && { info "Teardown cancelled."; exit 0; }

# ── Step 1 — Stop Flask ───────────────────────────────────────────────────────
info "Step 1/5 — Stopping Flask application..."
if [[ -f "$PID_FILE" ]]; then
    FLASK_PID=$(cat "$PID_FILE")
    if kill -0 "$FLASK_PID" 2>/dev/null; then
        kill "$FLASK_PID"
        info "Flask stopped (PID $FLASK_PID)"
    else
        warn "PID $FLASK_PID not running"
    fi
    rm -f "$PID_FILE"
fi
# Belt-and-suspenders: kill by matching the run.py command
pkill -f "run\.py" 2>/dev/null && info "Remaining Flask processes killed" || true

# ── Step 2 — Terminate all running VMs ───────────────────────────────────────
info "Step 2/5 — Terminating all running VMs..."
if command -v virsh &>/dev/null; then
    # List all running domains and destroy them
    RUNNING=$(virsh list --name 2>/dev/null | grep -v '^$' || true)
    if [[ -n "$RUNNING" ]]; then
        while IFS= read -r dom; do
            [[ -z "$dom" ]] && continue
            virsh destroy "$dom" 2>/dev/null || true
            info "  Destroyed VM: $dom"
        done <<< "$RUNNING"
    else
        info "  No running VMs found"
    fi

    # Also undefine (remove) all defined domains created by Mini Cloud (prefix: mc-)
    ALL=$(virsh list --all --name 2>/dev/null | grep '^mc-' || true)
    if [[ -n "$ALL" ]]; then
        while IFS= read -r dom; do
            [[ -z "$dom" ]] && continue
            virsh undefine "$dom" --remove-all-storage 2>/dev/null || \
                virsh undefine "$dom" 2>/dev/null || true
            info "  Undefined VM: $dom"
        done <<< "$ALL"
    fi

    # Kill any stray websockify proxy processes started for VNC consoles
    pkill -f "websockify" 2>/dev/null && info "  websockify processes killed" || true
else
    warn "virsh not found — VMs not terminated"
fi

# ── Step 3 — Remove LVM Volume Group ─────────────────────────────────────────
info "Step 3/5 — Removing LVM volume group '$VG_NAME'..."
if vgs "$VG_NAME" &>/dev/null; then
    # Remove all logical volumes first
    LVS=$(lvs --noheadings -o lv_name "$VG_NAME" 2>/dev/null | awk '{print $1}' || true)
    if [[ -n "$LVS" ]]; then
        while IFS= read -r lv; do
            [[ -z "$lv" ]] && continue
            lvremove -f "/dev/$VG_NAME/$lv" 2>/dev/null || true
            info "  Removed LV: $lv"
        done <<< "$LVS"
    fi
    vgremove -f "$VG_NAME" 2>/dev/null && info "Volume group '$VG_NAME' removed" || warn "Could not remove VG"

    # Clean up physical volume
    PVS=$(pvdisplay 2>/dev/null | grep 'PV Name' | awk '{print $3}' || true)
    if [[ -n "$PVS" ]]; then
        while IFS= read -r pv; do
            [[ -z "$pv" ]] && continue
            pvremove -f "$pv" 2>/dev/null || true
        done <<< "$PVS"
    fi

    # If loop device was used, detach it
    LOOP_FILE="/var/lib/mini-cloud-lvm.img"
    if [[ -f "$LOOP_FILE" ]]; then
        LOOP_DEV=$(losetup -j "$LOOP_FILE" 2>/dev/null | cut -d: -f1 || true)
        [[ -n "$LOOP_DEV" ]] && losetup -d "$LOOP_DEV" && info "  Loop device detached: $LOOP_DEV"
        rm -f "$LOOP_FILE"
        systemctl disable mini-cloud-loop --quiet 2>/dev/null || true
        rm -f /etc/systemd/system/mini-cloud-loop.service
        systemctl daemon-reload
        info "  Loop backing file removed"
    fi
else
    info "Volume group '$VG_NAME' not found — skipping"
fi

# ── Step 4 — Drop SQLite database ────────────────────────────────────────────
info "Step 4/5 — Removing database..."
DB_DIR="$SCRIPT_DIR/database"
if [[ -d "$DB_DIR" ]]; then
    rm -rf "$DB_DIR"
    info "Database directory removed: $DB_DIR"
else
    info "No database directory found — skipping"
fi

# Also remove uploaded images from storage
STORAGE_DIR="$SCRIPT_DIR/storage"
if [[ -d "$STORAGE_DIR" ]]; then
    rm -rf "$STORAGE_DIR"
    info "Storage directory removed: $STORAGE_DIR"
fi

# Remove cloud-init seed ISOs for VMs
CLOUD_INIT_DIR="/tmp/mini-cloud-*"
rm -rf $CLOUD_INIT_DIR 2>/dev/null || true

# ── Step 5 — Flush iptables rules added by Mini Cloud ─────────────────────────
info "Step 5/5 — Flushing Mini Cloud iptables rules..."
# Floating IP rules use the MINICLOUD-FIP chain
iptables -t nat -F MINICLOUD-FIP 2>/dev/null && \
    iptables -t nat -X MINICLOUD-FIP 2>/dev/null || true

# Remove per-VM security group chains (named MC-SG-<vm_id>)
iptables-save 2>/dev/null | grep '^:MC-SG-' | awk -F: '{print $2}' | awk '{print $1}' | \
    while read -r chain; do
        iptables -F "$chain" 2>/dev/null || true
        iptables -X "$chain" 2>/dev/null || true
    done

# Remove MASQUERADE rules added for routers
iptables -t nat -S POSTROUTING 2>/dev/null | grep 'MASQUERADE' | grep -v DOCKER | \
    while read -r rule; do
        iptables -t nat -D ${rule#-A } 2>/dev/null || true
    done

info "iptables rules flushed"

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Mini Cloud removed cleanly${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
