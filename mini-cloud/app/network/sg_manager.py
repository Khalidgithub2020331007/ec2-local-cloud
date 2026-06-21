import subprocess


def _run(cmd):
    # Prepend sudo -n — iptables needs root; user has passwordless sudo configured
    result = subprocess.run(['sudo', '-n'] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return result.stdout.strip()


def _run_soft(cmd):
    # Like _run but never raises — used for cleanup where partial state is acceptable
    subprocess.run(['sudo', '-n'] + cmd, capture_output=True, text=True)


def _tap_name(instance_id):
    # Linux interface names are limited to 15 chars (IFNAMSIZ-1).
    # UUIDs are 36 chars, so we use the first 8 hex chars — unique enough for a mini-cloud.
    return f'tap-{instance_id[:8]}'


def _chain_name(instance_id):
    # iptables chain names have a 29-char max; this stays well under that.
    return f'sg-{instance_id[:8]}'


# ── Chain lifecycle ────────────────────────────────────────────────────────────

def create_vm_sg_chain(instance_id):
    """
    Create the iptables chain for a VM and wire it into FORWARD with default-deny.

    Chain layout after this call:
        FORWARD rule:  -o tap-{id} → jump to sg-{id}
        sg-{id} rule 1: ESTABLISHED,RELATED → ACCEPT  (allow return traffic)
        sg-{id} rule 2: DROP                           (deny all new inbound)
    """
    chain = _chain_name(instance_id)
    tap   = _tap_name(instance_id)

    # iptables -N sg-{id}
    #   -N  Create a New custom chain.
    #   Custom chains are subroutines: FORWARD can jump into them.
    #   The chain starts empty; we add rules immediately after.
    _run(['iptables', '-N', chain])

    # iptables -I FORWARD 1 -o tap-{id} -j sg-{id}
    #   -I FORWARD 1   Insert at position 1 (evaluated before any existing FORWARD rules).
    #   -o tap-{id}    Match packets leaving through the VM's tap device.
    #                  "Leaving through tap" = packet is travelling FROM the bridge TO the VM.
    #                  This is "inbound" traffic from the VM's point of view.
    #   -j sg-{id}     Jump: hand the packet to our chain for further evaluation.
    _run(['iptables', '-I', 'FORWARD', '1', '-o', tap, '-j', chain])

    # iptables -A sg-{id} -m state --state ESTABLISHED,RELATED -j ACCEPT
    #   -A sg-{id}     Append to our chain (position 1 — first rule evaluated).
    #   -m state       Load the "state" connection-tracking extension.
    #   --state ESTABLISHED,RELATED
    #     ESTABLISHED  This packet belongs to a connection already seen in both directions.
    #                  Example: the TCP reply to an outbound SSH connection.
    #     RELATED      This packet is associated with an existing connection but is a new flow.
    #                  Example: an ICMP "port unreachable" error, or FTP data channel.
    #   -j ACCEPT      Allow the packet through.
    #   WHY: Without this rule, any reply to a connection the VM initiates would be
    #        blocked by the DROP rule below. Stateful tracking is essential for usability.
    _run(['iptables', '-A', chain,
          '-m', 'state', '--state', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'])

    # iptables -A sg-{id} -j DROP
    #   -j DROP   Silently discard — sender receives no error or RST.
    #   This is the default-deny policy: all new inbound connections are blocked
    #   unless a user ACCEPT rule (inserted at position 2) matches first.
    _run(['iptables', '-A', chain, '-j', 'DROP'])


def delete_vm_sg_chain(instance_id):
    """
    Remove the FORWARD jump rule, flush the chain, then delete it.
    Must be called when a VM is terminated. Order is critical:
      1. Remove FORWARD jump first — packets stop entering the chain.
      2. Flush the chain — clear its rules (iptables requires empty chain to delete).
      3. Delete the chain — iptables refuses to delete non-empty or referenced chains.
    """
    chain = _chain_name(instance_id)
    tap   = _tap_name(instance_id)

    # -D FORWARD: delete the jump rule by exact match — same flags as the -I rule.
    _run_soft(['iptables', '-D', 'FORWARD', '-o', tap, '-j', chain])

    # -F sg-{id}: Flush all rules from the chain (chain still exists after this).
    _run_soft(['iptables', '-F', chain])

    # -X sg-{id}: eXpunge (delete) the now-empty chain.
    #   Requires: chain is empty (-F done) AND no other rule references it (-D done).
    _run_soft(['iptables', '-X', chain])


def rebuild_vm_sg_chain(instance_id, inbound_rules):
    """
    Destroy and recreate a VM's chain from a list of rule dicts.
    Called after attach/detach and on app startup to restore state.
    Each dict needs: protocol, port_min, port_max, cidr.
    """
    chain = _chain_name(instance_id)
    tap   = _tap_name(instance_id)

    # Full teardown first — guarantees a clean slate even if chain is partially built
    delete_vm_sg_chain(instance_id)

    # Recreate with _run_soft so a missing tap device (VM stopped) is not fatal.
    # The chain will still be created in iptables; rules will match when tap comes up.
    _run_soft(['iptables', '-N', chain])
    _run_soft(['iptables', '-I', 'FORWARD', '1', '-o', tap, '-j', chain])
    _run_soft(['iptables', '-A', chain,
               '-m', 'state', '--state', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'])

    for rule in inbound_rules:
        _run_soft(['iptables', '-A', chain] +
                  _build_rule_args(rule['protocol'], rule['port_min'],
                                   rule['port_max'], rule['cidr']))

    _run_soft(['iptables', '-A', chain, '-j', 'DROP'])


# ── Rule add / remove ──────────────────────────────────────────────────────────

def _build_rule_args(protocol, port_min, port_max, cidr):
    """
    Build the iptables match arguments shared by add, remove, and rebuild.
    Keeping this in one place ensures add and delete always use identical flags —
    iptables delete matches by exact argument comparison.
    """
    # -s cidr  Source IP or CIDR range to match (who is allowed to send this traffic)
    args = ['-s', cidr]

    if protocol in ('tcp', 'udp'):
        # -p protocol  Match by IP protocol number (TCP=6, UDP=17).
        # --dport min:max  Destination port range.
        #   22:22  → single port (SSH)
        #   8000:9000 → port range
        args += ['-p', protocol, '--dport', f'{port_min}:{port_max}']
    elif protocol == 'icmp':
        # ICMP uses message types (echo, unreachable, etc.), not ports.
        # Matching -p icmp without a type allows all ICMP from this source.
        args += ['-p', 'icmp']
    # protocol == 'all': no extra args — matches any IP protocol from the source CIDR

    # -j ACCEPT  Allow the packet through — user rules are always ACCEPT
    args += ['-j', 'ACCEPT']
    return args


def add_sg_rule_to_chain(instance_id, protocol, port_min, port_max, cidr):
    """
    Insert one ACCEPT rule at position 2 in the VM's chain.
    Position 1 is always ESTABLISHED,RELATED; DROP is always last.
    Inserting at 2 keeps the DROP at the end where it belongs.
    """
    chain = _chain_name(instance_id)

    # -I chain 2  Insert at position 2.
    #   Position 1 = ESTABLISHED,RELATED (stays there).
    #   Position 2 = the new ACCEPT rule.
    #   DROP shifts to position 3 (or further as more rules are added).
    #   iptables evaluates top-to-bottom; first match wins.
    _run(['iptables', '-I', chain, '2'] +
         _build_rule_args(protocol, port_min, port_max, cidr))


def remove_sg_rule_from_chain(instance_id, protocol, port_min, port_max, cidr):
    """
    Delete one ACCEPT rule by exact parameter match.
    Uses _run_soft — a rule already missing from the chain is not an error.
    """
    chain = _chain_name(instance_id)

    # -D chain  Delete the first rule whose every flag matches exactly.
    #   iptables compares: source, protocol, port, target — all must match.
    #   If no match is found, iptables exits with code 1 — _run_soft ignores it.
    _run_soft(['iptables', '-D', chain] +
              _build_rule_args(protocol, port_min, port_max, cidr))
