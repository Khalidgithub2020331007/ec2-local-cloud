import subprocess
import libvirt

LIBVIRT_URI  = 'qemu:///system'
VOLUME_GROUP = 'mini-cloud-vg'


def _run_lvm(cmd):
    # All LVM ops need root — Flask must run with sudo or have proper udev rules.
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'{cmd[0]} failed: {result.stderr.strip()}')
    return result.stdout


def lv_path(volume_id):
    return f'/dev/{VOLUME_GROUP}/vol-{volume_id}'


def snap_path(snapshot_id):
    return f'/dev/{VOLUME_GROUP}/snap-{snapshot_id}'


# ── LVM operations ──────────────────────────────────────────────────────────────

def create_lv(volume_id, size_gb):
    # Carves a new thick LV out of the VG — immediately occupies {size_gb}G of physical space.
    _run_lvm(['lvcreate', '-n', f'vol-{volume_id}', '-L', f'{size_gb}G', VOLUME_GROUP])


def delete_lv(volume_id):
    # -f skips the "do you really want to remove" prompt — safe because caller checks status.
    _run_lvm(['lvremove', '-f', f'{VOLUME_GROUP}/vol-{volume_id}'])


def create_lv_snapshot(volume_id, snapshot_id, snap_size_gb):
    # COW snapshot: only writes to the origin after this point consume snap space.
    # snap_size_gb must be large enough to hold all writes before the snap is deleted.
    _run_lvm([
        'lvcreate', '-n', f'snap-{snapshot_id}',
        '-L', f'{snap_size_gb}G',
        '-s', f'{VOLUME_GROUP}/vol-{volume_id}',
    ])


def delete_lv_snapshot(snapshot_id):
    _run_lvm(['lvremove', '-f', f'{VOLUME_GROUP}/snap-{snapshot_id}'])


def restore_lv_from_snapshot(snapshot_id, new_volume_id, size_gb):
    # Creates a new COW snapshot of the snapshot — effectively a read-write clone of that point in time.
    # Requires LVM2 with snapshot-of-snapshot support (kernel ≥ 3.5) or thin-provisioned VG.
    _run_lvm([
        'lvcreate', '-n', f'vol-{new_volume_id}',
        '-L', f'{size_gb}G',
        '--snapshot', f'{VOLUME_GROUP}/snap-{snapshot_id}',
    ])


# ── libvirt hotplug / hotunplug ─────────────────────────────────────────────────

def _disk_xml(volume_id, device_name):
    # io='native' avoids double-buffering since the host already does buffered I/O on the LV.
    return f"""<disk type='block' device='disk'>
  <driver name='qemu' type='raw' cache='none' io='native'/>
  <source dev='{lv_path(volume_id)}'/>
  <target dev='{device_name}' bus='virtio'/>
</disk>"""


def attach_volume(libvirt_name, volume_id, device_name):
    # AFFECT_LIVE hotplugs to the running guest; AFFECT_CONFIG persists in XML so it survives reboot.
    # For stopped VMs only CONFIG is applied — the volume appears on next boot.
    conn = libvirt.open(LIBVIRT_URI)
    try:
        domain = conn.lookupByName(libvirt_name)
        xml    = _disk_xml(volume_id, device_name)
        is_running = domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING
        if is_running:
            flags = libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG
        else:
            flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
        domain.attachDeviceFlags(xml, flags)
    except libvirt.libvirtError as e:
        raise RuntimeError(f'libvirt attach failed: {e}')
    finally:
        conn.close()


def detach_volume(libvirt_name, volume_id, device_name):
    # Mirror of attach — remove from live guest AND strip from persistent XML.
    conn = libvirt.open(LIBVIRT_URI)
    try:
        domain = conn.lookupByName(libvirt_name)
        xml    = _disk_xml(volume_id, device_name)
        is_running = domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING
        if is_running:
            flags = libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG
        else:
            flags = libvirt.VIR_DOMAIN_AFFECT_CONFIG
        domain.detachDeviceFlags(xml, flags)
    except libvirt.libvirtError as e:
        raise RuntimeError(f'libvirt detach failed: {e}')
    finally:
        conn.close()
