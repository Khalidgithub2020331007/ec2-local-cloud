import re
import time
import uuid
import logging
import threading
import libvirt

logger = logging.getLogger(__name__)

LIBVIRT_URI      = 'qemu:///system'
POLL_INTERVAL_S  = 30   # seconds between monitor iterations
CPU_SAMPLE_S     = 5    # seconds between the two libvirt CPU readings


# ── CPU measurement ───────────────────────────────────────────────────────────

def _libvirt_connect():
    conn = libvirt.open(LIBVIRT_URI)
    if conn is None:
        raise RuntimeError('Failed to connect to libvirt')
    return conn


def _read_cpu_time(lv_conn, libvirt_name):
    # Returns (cpu_time_ns, vcpus) for a running domain, or (None, None) if not running
    try:
        domain = lv_conn.lookupByName(libvirt_name)
        info   = domain.info()  # [state, maxMem_kb, mem_kb, vcpus, cpu_time_ns]
        if info[0] not in (libvirt.VIR_DOMAIN_RUNNING, libvirt.VIR_DOMAIN_BLOCKED):
            return None, None
        return info[4], info[3]
    except libvirt.libvirtError:
        return None, None


def _sample_avg_cpu(asg_instances):
    # Two libvirt readings CPU_SAMPLE_S apart → average % across all VMs in the group.
    # Returns 0.0 if no VMs are running (group just started, all terminated, etc.).
    if not asg_instances:
        return 0.0

    lv_conn = _libvirt_connect()
    try:
        first = {}
        for vm in asg_instances:
            ns, vcpus = _read_cpu_time(lv_conn, vm['libvirt_name'])
            if ns is not None:
                first[vm['vm_id']] = (ns, vcpus)

        if not first:
            return 0.0

        time.sleep(CPU_SAMPLE_S)

        percentages = []
        interval_ns = CPU_SAMPLE_S * 1_000_000_000
        for vm in asg_instances:
            if vm['vm_id'] not in first:
                continue
            ns2, vcpus2 = _read_cpu_time(lv_conn, vm['libvirt_name'])
            if ns2 is None:
                continue
            ns1, vcpus1 = first[vm['vm_id']]
            vcpus = max(vcpus1, 1)
            pct = ((ns2 - ns1) / (interval_ns * vcpus)) * 100
            percentages.append(max(0.0, min(100.0, pct)))

        return sum(percentages) / len(percentages) if percentages else 0.0
    finally:
        lv_conn.close()


# ── VM lifecycle helpers ──────────────────────────────────────────────────────

def _launch_vm_for_asg(asg, user):
    # Mirrors compute.routes.launch but called from the background thread.
    # Returns the new instance_id on success.
    from app.compute.flavors import get_flavor
    from app.compute.models import create_instance, update_instance_status
    from app.compute.libvirt_manager import (
        create_instance_disk, launch_vm, build_cloud_init_iso, get_vm_vnc_port,
    )
    from app.network.sg_manager import create_vm_sg_chain
    from app.database import get_connection

    flavor = get_flavor(asg['flavor'])
    if not flavor:
        raise RuntimeError(f"Unknown flavor: {asg['flavor']}")

    # Build a unique VM name from the group name + short UUID
    short_id   = str(uuid.uuid4())[:8]
    raw_name   = f"{asg['name'][:18]}-{short_id}"
    # Enforce the same naming rules as the compute route
    name = re.sub(r'[^a-z0-9\-]', '-', raw_name.lower()).strip('-')
    name = re.sub(r'-{2,}', '-', name)

    image_path = None
    if asg['image_id']:
        conn = get_connection()
        try:
            row = conn.execute('SELECT file_path FROM images WHERE id = ?', (asg['image_id'],)).fetchone()
            if row:
                image_path = row['file_path']
        finally:
            conn.close()

    keypair = None
    if asg['keypair_id']:
        from app.keypairs.models import get_keypair
        keypair = get_keypair(asg['keypair_id'], user['id'])

    libvirt_name = f"mc-{user['username']}-{name}"

    instance_id = create_instance(
        user_id      = user['id'],
        name         = name,
        flavor       = asg['flavor'],
        vcpus        = flavor['vcpus'],
        ram_mb       = flavor['ram_mb'],
        disk_gb      = flavor['disk_gb'],
        libvirt_name = libvirt_name,
        disk_path    = '',
        image_path   = image_path,
    )

    disk_path = create_instance_disk(instance_id, flavor['disk_gb'], image_path)

    conn = get_connection()
    try:
        # Mark this instance as autoscaling-managed so the UI can badge it
        conn.execute(
            'UPDATE instances SET disk_path = ?, keypair_id = ?, source = ? WHERE id = ?',
            (disk_path, asg['keypair_id'], 'autoscaling', instance_id),
        )
        conn.commit()
    finally:
        conn.close()

    seed_iso_path = None
    if keypair:
        seed_iso_path = build_cloud_init_iso(instance_id, name, keypair['public_key'])

    launch_vm(libvirt_name, flavor['vcpus'], flavor['ram_mb'], disk_path, instance_id, seed_iso_path)

    vnc_port = get_vm_vnc_port(libvirt_name)
    update_instance_status(instance_id, 'running', vnc_port=vnc_port)

    try:
        create_vm_sg_chain(instance_id)
    except RuntimeError:
        pass  # Non-fatal — security groups can be attached later

    return instance_id


def _terminate_vm(vm):
    from app.compute.libvirt_manager import terminate_vm
    from app.compute.models import mark_terminated
    from app.network.sg_manager import delete_vm_sg_chain

    try:
        delete_vm_sg_chain(vm['vm_id'])
    except RuntimeError:
        pass

    terminate_vm(vm['libvirt_name'], vm['vm_id'])
    mark_terminated(vm['vm_id'])


def _add_vm_to_lb(asg, vm_id):
    from app.load_balancers.models import add_member, get_member_by_vm
    from app.load_balancers.haproxy_manager import write_and_reload
    from app.database import get_connection

    if not asg.get('lb_id') or not asg.get('lb_member_port'):
        return

    conn = get_connection()
    try:
        row = conn.execute('SELECT ip_address FROM instances WHERE id = ?', (vm_id,)).fetchone()
        ip = row['ip_address'] if row else None
    finally:
        conn.close()

    if not ip:
        return

    if not get_member_by_vm(asg['lb_id'], vm_id):
        add_member(asg['lb_id'], vm_id, ip, asg['lb_member_port'])
        try:
            write_and_reload()
        except RuntimeError as e:
            logger.warning(f'HAProxy reload failed after adding VM {vm_id}: {e}')


def _remove_vm_from_lb(asg, vm_id):
    from app.load_balancers.models import get_member_by_vm, remove_member
    from app.load_balancers.haproxy_manager import write_and_reload

    if not asg.get('lb_id'):
        return

    if get_member_by_vm(asg['lb_id'], vm_id):
        remove_member(asg['lb_id'], vm_id)
        try:
            write_and_reload()
        except RuntimeError as e:
            logger.warning(f'HAProxy reload failed after removing VM {vm_id}: {e}')


# ── Per-ASG check ─────────────────────────────────────────────────────────────

def _check_asg(asg):
    from datetime import datetime, timezone
    from app.auth.models import get_user_by_id
    from app.autoscaling.models import (
        get_asg_instances, add_asg_instance, remove_asg_instance,
        get_newest_asg_instance, record_last_action, record_scaling_event,
    )

    user = get_user_by_id(asg['user_id'])
    if not user:
        return

    instances     = get_asg_instances(asg['id'])
    instance_count = len(instances)

    # Ensure minimum count — no cooldown needed, this is recovery not scaling
    if instance_count < asg['min_instances']:
        shortfall = asg['min_instances'] - instance_count
        for _ in range(shortfall):
            try:
                new_id = _launch_vm_for_asg(asg, user)
                add_asg_instance(asg['id'], new_id)
                _add_vm_to_lb(asg, new_id)
                record_scaling_event(asg['id'], 'ensure_min', instance_count + 1, 0.0,
                                     f'count {instance_count} < min {asg["min_instances"]}')
                instance_count += 1
                logger.info(f'ASG {asg["name"]}: launched minimum instance {new_id}')
            except Exception as e:
                logger.error(f'ASG {asg["name"]}: failed to launch minimum instance: {e}')
        return

    # Check cooldown before threshold-based scaling
    if asg['last_action_at']:
        last = datetime.fromisoformat(asg['last_action_at'])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < asg['cooldown_seconds']:
            return

    avg_cpu = _sample_avg_cpu(instances)

    if avg_cpu > asg['scale_up_threshold'] and instance_count < asg['max_instances']:
        try:
            new_id = _launch_vm_for_asg(asg, user)
            add_asg_instance(asg['id'], new_id)
            _add_vm_to_lb(asg, new_id)
            record_last_action(asg['id'])
            record_scaling_event(asg['id'], 'scale_up', instance_count + 1, round(avg_cpu, 1),
                                 f'avg CPU {avg_cpu:.1f}% > threshold {asg["scale_up_threshold"]}%')
            logger.info(f'ASG {asg["name"]}: scaled up → {instance_count + 1} (CPU {avg_cpu:.1f}%)')
        except Exception as e:
            logger.error(f'ASG {asg["name"]}: scale-up failed: {e}')

    elif avg_cpu < asg['scale_down_threshold'] and instance_count > asg['min_instances']:
        victim = get_newest_asg_instance(asg['id'])
        if not victim:
            return
        try:
            _remove_vm_from_lb(asg, victim['vm_id'])
            _terminate_vm(victim)
            remove_asg_instance(victim['vm_id'])
            record_last_action(asg['id'])
            record_scaling_event(asg['id'], 'scale_down', instance_count - 1, round(avg_cpu, 1),
                                 f'avg CPU {avg_cpu:.1f}% < threshold {asg["scale_down_threshold"]}%')
            logger.info(f'ASG {asg["name"]}: scaled down → {instance_count - 1} (CPU {avg_cpu:.1f}%)')
        except Exception as e:
            logger.error(f'ASG {asg["name"]}: scale-down failed: {e}')


# ── Monitor loop ──────────────────────────────────────────────────────────────

def _monitor_loop():
    # Wait one cycle before first check so Flask finishes its own startup
    time.sleep(POLL_INTERVAL_S)

    while True:
        try:
            from app.autoscaling.models import list_all_active_asgs
            asgs = list_all_active_asgs()
            for asg in asgs:
                try:
                    _check_asg(asg)
                except Exception as e:
                    logger.error(f'ASG monitor error ({asg.get("name", "?")}): {e}')
        except Exception as e:
            logger.error(f'ASG monitor loop error: {e}')

        time.sleep(POLL_INTERVAL_S)


def start_monitor():
    # Daemon thread so it terminates automatically when Flask exits
    t = threading.Thread(target=_monitor_loop, daemon=True, name='asg-monitor')
    t.start()
    logger.info('ASG monitor thread started (30 s interval)')
