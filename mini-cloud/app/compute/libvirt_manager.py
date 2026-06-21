import os
import subprocess
import libvirt
from xml.etree import ElementTree as ET

LIBVIRT_URI = 'qemu:///system'

# VM disk files এখানে রাখা হয় — /var/lib/libvirt/images/ এ sudo দরকার
STORAGE_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', 'storage', 'instances'
)


def _connect():
    # libvirt connection তৈরি করে — qemu:///system = system-wide KVM
    conn = libvirt.open(LIBVIRT_URI)
    if conn is None:
        raise RuntimeError('Failed to connect to libvirt (qemu:///system)')
    return conn


def _build_domain_xml(libvirt_name, vcpus, ram_mb, disk_path):
    # KVM VM এর XML definition — Nova এর বদলে এটাই সরাসরি libvirt কে পাঠানো হয়
    return f"""<domain type='kvm'>
  <name>{libvirt_name}</name>
  <memory unit='MiB'>{ram_mb}</memory>
  <vcpu placement='static'>{vcpus}</vcpu>
  <os>
    <type arch='x86_64'>hvm</type>
    <boot dev='hd'/>
  </os>
  <features>
    <acpi/>
    <apic/>
  </features>
  <cpu mode='host-passthrough'/>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source file='{disk_path}'/>
      <target dev='vda' bus='virtio'/>
    </disk>
    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>
    <serial type='pty'>
      <target port='0'/>
    </serial>
    <console type='pty'>
      <target type='serial' port='0'/>
    </console>
    <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'>
      <listen type='address' address='127.0.0.1'/>
    </graphics>
    <video>
      <model type='vga' vram='16384' heads='1'/>
    </video>
    <memballoon model='virtio'/>
  </devices>
</domain>"""


def _set_qemu_acl(path):
    # libvirt-qemu user কে disk file/dir access দেওয়া হয়
    # QEMU process এই user হিসেবে চলে — সে না পড়লে VM start হয় না
    subprocess.run(['setfacl', '-m', 'u:libvirt-qemu:rwx', path], check=False)


def create_instance_disk(instance_id, disk_gb, base_image_path=None):
    # প্রতিটা instance এর জন্য আলাদা folder এ qcow2 disk তৈরি করা হয়
    instance_dir = os.path.join(STORAGE_BASE, instance_id)
    os.makedirs(instance_dir, exist_ok=True)
    _set_qemu_acl(instance_dir)
    disk_path = os.path.join(instance_dir, 'disk.qcow2')

    if base_image_path and os.path.exists(base_image_path):
        # Base image থেকে overlay disk তৈরি — original image unchanged থাকে
        # -b flag মানে backing file, নতুন writes শুধু overlay তে যায়
        cmd = ['qemu-img', 'create', '-f', 'qcow2',
               '-b', base_image_path, '-F', 'qcow2',
               disk_path, f'{disk_gb}G']
    else:
        # Image না থাকলে blank disk — VM power-on হবে কিন্তু OS boot হবে না
        cmd = ['qemu-img', 'create', '-f', 'qcow2', disk_path, f'{disk_gb}G']

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'qemu-img failed: {result.stderr}')

    _set_qemu_acl(disk_path)
    return disk_path


def launch_vm(libvirt_name, vcpus, ram_mb, disk_path):
    # Domain define করে তারপর start করে — define করলে persistent হয়
    conn = _connect()
    try:
        xml = _build_domain_xml(libvirt_name, vcpus, ram_mb, disk_path)
        domain = conn.defineXML(xml)
        domain.create()  # start the defined domain
        return True
    finally:
        conn.close()


def stop_vm(libvirt_name):
    # ACPI shutdown signal পাঠায় — OS কে gracefully shutdown করতে বলে
    # Guest OS না থাকলে fallback এ destroy() ব্যবহার করা হয়
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        if domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
            try:
                domain.shutdown()
            except libvirt.libvirtError:
                domain.destroy()  # ACPI না থাকলে force-off
        return True
    finally:
        conn.close()


def start_vm(libvirt_name):
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        if domain.state()[0] != libvirt.VIR_DOMAIN_RUNNING:
            domain.create()
        return True
    finally:
        conn.close()


def reboot_vm(libvirt_name):
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        domain.reboot(0)  # 0 = let hypervisor choose reboot method
        return True
    finally:
        conn.close()


def terminate_vm(libvirt_name, instance_id):
    # Domain destroy করে, undefine করে, তারপর disk delete করে
    conn = _connect()
    try:
        try:
            domain = conn.lookupByName(libvirt_name)
            if domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING:
                domain.destroy()
            domain.undefine()
        except libvirt.libvirtError:
            pass  # Already removed — not an error
    finally:
        conn.close()

    # Disk files মুছে দাও
    instance_dir = os.path.join(STORAGE_BASE, instance_id)
    if os.path.exists(instance_dir):
        subprocess.run(['rm', '-rf', instance_dir], check=False)

    return True


def get_vm_status(libvirt_name):
    # libvirt state integer → human-readable string
    STATE_MAP = {
        libvirt.VIR_DOMAIN_RUNNING:     'running',
        libvirt.VIR_DOMAIN_BLOCKED:     'running',
        libvirt.VIR_DOMAIN_PAUSED:      'paused',
        libvirt.VIR_DOMAIN_SHUTDOWN:    'stopped',
        libvirt.VIR_DOMAIN_SHUTOFF:     'stopped',
        libvirt.VIR_DOMAIN_CRASHED:     'error',
        libvirt.VIR_DOMAIN_PMSUSPENDED: 'stopped',
    }
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        state = domain.state()[0]
        return STATE_MAP.get(state, 'unknown')
    except libvirt.libvirtError:
        return 'terminated'
    finally:
        conn.close()


def get_vm_vnc_port(libvirt_name):
    # VNC port autoport দিলে libvirt নিজে assign করে — XML থেকে পড়তে হয়
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        xml_str = domain.XMLDesc(0)
        root = ET.fromstring(xml_str)
        graphics = root.find('.//graphics[@type="vnc"]')
        if graphics is not None:
            return int(graphics.get('port', -1))
        return -1
    except libvirt.libvirtError:
        return -1
    finally:
        conn.close()


def get_vm_stats(libvirt_name):
    # CPU % এবং memory stats — monitoring section এ ব্যবহার হবে (Step 9)
    conn = _connect()
    try:
        domain = conn.lookupByName(libvirt_name)
        if domain.state()[0] != libvirt.VIR_DOMAIN_RUNNING:
            return None
        info = domain.info()
        # info: [state, maxMemory, memory, nVirtCpu, cpuTime]
        return {
            'cpu_time_ns': info[4],
            'ram_used_kb': info[2],
            'ram_max_kb':  info[1],
        }
    except libvirt.libvirtError:
        return None
    finally:
        conn.close()
