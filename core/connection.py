"""
Connection manager for PVE Configurator.
Handles Proxmox API (proxmoxer) and SSH (paramiko) connections.
"""

import re
import traceback
from typing import Optional, Tuple

from core.models import (
    HostCredentials, HostInventory, NICInfo, DiskInfo,
    NICRole, StorageRole, ConnectMethod
)


# ── Optional imports (graceful failure if not installed yet) ──────────────────

try:
    from proxmoxer import ProxmoxAPI
    HAS_PROXMOXER = True
except ImportError:
    HAS_PROXMOXER = False

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


# ── Connection manager ────────────────────────────────────────────────────────

class PVEConnection:
    """
    Wraps both a Proxmox API session and an SSH session for a single host.
    Either may be None if unavailable; callers check before using.
    """

    def __init__(self, creds: HostCredentials):
        self.creds = creds
        self._api: Optional[object] = None   # ProxmoxAPI instance
        self._ssh: Optional[object] = None   # paramiko.SSHClient instance
        self.node_name: str = ""             # resolved from API after connect
        self.errors: list[str] = []

    # ── Connect ──────────────────────────────────────────────────────────────

    def connect(self) -> Tuple[bool, str]:
        """
        Attempt API connection first, then SSH.
        Returns (success, message).
        At least one must succeed for this to return True.
        """
        self.errors = []
        api_ok = self._connect_api()
        ssh_ok = self._connect_ssh()

        if api_ok or ssh_ok:
            methods = []
            if api_ok: methods.append("API")
            if ssh_ok: methods.append("SSH")
            return True, f"Connected via {' + '.join(methods)}"

        return False, "Both API and SSH connections failed:\n" + "\n".join(self.errors)

    def _connect_api(self) -> bool:
        if not HAS_PROXMOXER:
            self.errors.append("API: proxmoxer not installed")
            return False
        try:
            if self.creds.method == ConnectMethod.API_TOKEN:
                self._api = ProxmoxAPI(
                    self.creds.host,
                    port=self.creds.port,
                    token_name=self.creds.api_token_id,
                    token_value=self.creds.api_token_secret,
                    verify_ssl=self.creds.verify_ssl,
                    timeout=10,
                )
            else:
                self._api = ProxmoxAPI(
                    self.creds.host,
                    port=self.creds.port,
                    user=self.creds.username,
                    password=self.creds.password,
                    verify_ssl=self.creds.verify_ssl,
                    timeout=10,
                )
            # Resolve node name
            nodes = self._api.nodes.get()
            if nodes:
                self.node_name = nodes[0]["node"]
            return True
        except Exception as e:
            self.errors.append(f"API: {e}")
            return False

    def _connect_ssh(self) -> bool:
        if not HAS_PARAMIKO:
            self.errors.append("SSH: paramiko not installed")
            return False
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kwargs = dict(
                hostname=self.creds.host,
                port=22,
                username="root",
                timeout=10,
            )
            if self.creds.method == ConnectMethod.SSH_KEY and self.creds.ssh_key_path:
                kwargs["key_filename"] = self.creds.ssh_key_path
            else:
                kwargs["password"] = self.creds.password
            client.connect(**kwargs)
            self._ssh = client
            return True
        except Exception as e:
            self.errors.append(f"SSH: {e}")
            return False

    # ── SSH helpers ───────────────────────────────────────────────────────────

    def ssh_run(self, command: str) -> Tuple[str, str, int]:
        """Run a command over SSH. Returns (stdout, stderr, exit_code)."""
        if not self._ssh:
            return "", "No SSH connection", -1
        try:
            _, stdout, stderr = self._ssh.exec_command(command, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            rc  = stdout.channel.recv_exit_status()
            return out, err, rc
        except Exception as e:
            return "", str(e), -1

    # ── API helpers ───────────────────────────────────────────────────────────

    @property
    def node(self):
        """Shortcut: self._api.nodes(self.node_name)"""
        if self._api and self.node_name:
            return self._api.nodes(self.node_name)
        return None

    def disconnect(self):
        if self._ssh:
            try:
                self._ssh.close()
            except Exception:
                pass
        self._api = None
        self._ssh = None


# ── Hardware discovery ────────────────────────────────────────────────────────

class HardwareDiscovery:
    """
    Reads hardware from a connected PVE host and returns a HostInventory.
    Uses API where possible, SSH as fallback/supplement.
    """

    def __init__(self, conn: PVEConnection):
        self.conn = conn

    def discover(self, progress_callback=None) -> HostInventory:
        inv = HostInventory()
        steps = [
            ("Resolving hostname...",    self._get_hostname),
            ("Reading PVE version...",   self._get_pve_version),
            ("Reading CPU & memory...",  self._get_cpu_memory),
            ("Discovering NICs...",      self._get_nics),
            ("Discovering disks...",     self._get_disks),
            ("Reading network config...",self._get_network_config),
            ("Reading system settings...",self._get_system_settings),
        ]
        for msg, fn in steps:
            if progress_callback:
                progress_callback(msg)
            try:
                fn(inv)
            except Exception:
                traceback.print_exc()
        return inv

    # ── Individual discovery steps ────────────────────────────────────────────

    def _get_hostname(self, inv: HostInventory):
        out, _, _ = self.conn.ssh_run("hostname -f")
        inv.fqdn = out.strip()
        inv.hostname = inv.fqdn.split(".")[0] if inv.fqdn else self.conn.creds.host

        if self.conn.node and not inv.hostname:
            inv.hostname = self.conn.node_name

    def _get_pve_version(self, inv: HostInventory):
        if self.conn.node:
            try:
                ver = self.conn.node.version.get()
                inv.pve_version = f"{ver.get('version','?')}/{ver.get('release','?')}"
                return
            except Exception:
                pass
        out, _, _ = self.conn.ssh_run("pveversion")
        inv.pve_version = out.strip().split("\n")[0] if out else "Unknown"

    def _get_cpu_memory(self, inv: HostInventory):
        if self.conn.node:
            try:
                status = self.conn.node.status.get()
                inv.cpu_cores   = status.get("cpuinfo", {}).get("cores", 0)
                inv.cpu_threads = status.get("cpuinfo", {}).get("cpus",  0)
                inv.cpu_model   = status.get("cpuinfo", {}).get("model", "")
                inv.ram_gb      = round(status.get("memory", {}).get("total", 0) / (1024**3), 1)
                return
            except Exception:
                pass
        # SSH fallback
        out, _, _ = self.conn.ssh_run("lscpu | grep -E 'Model name|CPU\\(s\\):|Core'")
        for line in out.splitlines():
            if "Model name" in line:
                inv.cpu_model = line.split(":", 1)[-1].strip()
            elif "CPU(s):" in line and not inv.cpu_threads:
                try:
                    inv.cpu_threads = int(line.split(":", 1)[-1].strip())
                except ValueError:
                    pass
        mem_out, _, _ = self.conn.ssh_run("free -b | awk '/^Mem/{print $2}'")
        try:
            inv.ram_gb = round(int(mem_out.strip()) / (1024**3), 1)
        except ValueError:
            pass

    def _get_nics(self, inv: HostInventory):
        """
        Primary source: `ip link` + `ethtool` via SSH.
        Supplements with API network list for current config.
        """
        out, _, _ = self.conn.ssh_run("ip -o link show")
        if not out:
            return

        # Parse ethtool speeds in one shot
        ethtool_out, _, _ = self.conn.ssh_run(
            "for i in $(ls /sys/class/net/ | grep -v lo); do "
            "echo \"=== $i ===\"; ethtool $i 2>/dev/null | "
            "grep -E 'Speed|Link detected'; done"
        )
        speeds = _parse_ethtool_block(ethtool_out)

        # Parse current IPv4 addresses per interface
        addr_out, _, _ = self.conn.ssh_run("ip -o -4 addr show")
        addrs = _parse_ip_addr_block(addr_out)

        # Parse default gateway and which interface it's reached through
        route_out, _, _ = self.conn.ssh_run("ip -o -4 route show default")
        gateway, gw_dev = _parse_default_route(route_out)

        virtual_prefixes = ("vmbr", "bond", "veth", "tap", "fwbr", "fwpr", "fwln")
        wifi_drivers = ("wlp", "wlan", "wifi")

        for line in out.splitlines():
            # Format: "N: name: <FLAGS> ..."
            m = re.match(r"^\d+:\s+(\S+?)(?:@\S+)?:\s+<([^>]*)>", line)
            if not m:
                continue
            name  = m.group(1)
            flags = m.group(2)
            if name == "lo":
                continue

            mac_m = re.search(r"link/ether\s+(\S+)", line)
            mac   = mac_m.group(1) if mac_m else ""

            state       = "UP" if "UP" in flags and "LOWER_UP" in flags else "DOWN"
            is_virtual  = name.startswith(virtual_prefixes) or "@" in line
            is_wifi     = any(name.startswith(w) for w in wifi_drivers)
            speed       = speeds.get(name, {}).get("speed")
            link        = speeds.get(name, {}).get("link", False)
            ip_addr, ip_prefix = addrs.get(name, ("", 0))
            iface_gateway = gateway if gw_dev == name else ""

            nic = NICInfo(
                name=name, mac=mac, state=state,
                speed_mbps=speed, link_detected=link,
                is_virtual=is_virtual, is_wifi=is_wifi,
                ip=ip_addr, prefix=ip_prefix, gateway=iface_gateway,
            )
            nic.role = nic.suggested_role
            inv.nics.append(nic)

    def _get_disks(self, inv: HostInventory):
        """Use lsblk for disk enumeration, cross-ref with pvs for OS disk."""
        out, _, _ = self.conn.ssh_run(
            "lsblk -d -o NAME,SIZE,ROTA,TRAN,VENDOR,MODEL,SERIAL --bytes --noheadings 2>/dev/null"
        )
        if not out:
            return

        # Find which devices have partitions (run without -d, look for children)
        part_out, _, _ = self.conn.ssh_run(
            "lsblk -o NAME,TYPE --noheadings 2>/dev/null"
        )
        disks_with_parts: set[str] = set()
        if part_out:
            current_disk = None
            for line in part_out.splitlines():
                stripped = line.strip()
                parts_row = stripped.split()
                if len(parts_row) < 2:
                    continue
                name_raw, type_raw = parts_row[0], parts_row[1]
                # Remove tree characters lsblk adds (├─, └─, etc.)
                clean_name = re.sub(r'^[^a-zA-Z]+', '', name_raw)
                if type_raw == "disk":
                    current_disk = clean_name
                elif type_raw == "part" and current_disk:
                    disks_with_parts.add(current_disk)

        # Find which devices are in the pve VG
        pvs_out, _, _ = self.conn.ssh_run("pvs --noheadings -o pv_name 2>/dev/null")
        pve_pvs = set()
        if pvs_out:
            for line in pvs_out.splitlines():
                pv = line.strip()
                if pv:
                    # Strip partition number to get base device
                    base = re.sub(r'p?\d+$', '', pv.replace("/dev/", ""))
                    pve_pvs.add(base)

        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            name     = parts[0]
            try:
                size_b   = int(parts[1])
            except ValueError:
                continue
            rota     = parts[2] == "1"
            tran     = parts[3].lower() if len(parts) > 3 else ""
            vendor   = parts[4] if len(parts) > 4 else ""
            model    = parts[5] if len(parts) > 5 else ""
            serial   = parts[6] if len(parts) > 6 else ""

            is_usb        = tran == "usb"
            is_pve_os     = name in pve_pvs
            has_partitions = name in disks_with_parts

            disk = DiskInfo(
                name=name,
                path=f"/dev/{name}",
                size_gb=round(size_b / (1024**3), 1),
                is_rotational=rota,
                transport=tran,
                vendor=vendor.strip(),
                model=model.strip(),
                serial=serial.strip(),
                is_usb=is_usb,
                is_pve_os=is_pve_os,
                has_partitions=has_partitions,
            )
            disk.role = disk.suggested_role
            # Default storage name suggestion
            if disk.role == StorageRole.LOCAL_LVM:
                ssd_count = sum(
                    1 for d in inv.disks
                    if d.role == StorageRole.LOCAL_LVM
                )
                disk.storage_name = f"Local-SSD-{ssd_count + 1:02d}"
            elif disk.role == StorageRole.BACKUP_DIR:
                hdd_count = sum(
                    1 for d in inv.disks
                    if d.role == StorageRole.BACKUP_DIR
                )
                disk.storage_name = f"Backup-HDD-{hdd_count + 1:02d}"

            inv.disks.append(disk)

    def _get_network_config(self, inv: HostInventory):
        """Extract current management IP/gateway/VLAN from interfaces file.

        The management interface is identified as the static interface that
        has a `gateway` line — there should only be one default route. We
        don't just take the last `inet static` block found, since hosts with
        multiple static bridges (e.g. a separate storage bridge) would
        otherwise have their management IP overwritten by an unrelated one.
        """
        out, _, _ = self.conn.ssh_run("cat /etc/network/interfaces")
        if not out:
            return

        # Parse into per-interface blocks: {iface_name: {address, prefix, gateway}}
        blocks: dict[str, dict] = {}
        current_iface = None
        for line in out.splitlines():
            line = line.strip()
            m = re.match(r"iface\s+(\S+)\s+inet\s+static", line)
            if m:
                current_iface = m.group(1)
                blocks.setdefault(current_iface, {})
                continue
            if line.startswith("iface ") or line.startswith("auto "):
                # New stanza that isn't a static iface line resets context
                if not re.match(r"iface\s+(\S+)\s+inet\s+static", line):
                    current_iface = None
                continue
            if current_iface is None:
                continue
            if line.startswith("address "):
                addr = line.split()[1]
                if "/" in addr:
                    ip, prefix = addr.split("/")
                    blocks[current_iface]["ip"] = ip
                    blocks[current_iface]["prefix"] = int(prefix)
                else:
                    blocks[current_iface]["ip"] = addr
            elif line.startswith("gateway "):
                blocks[current_iface]["gateway"] = line.split()[1]

        # Prefer the interface that actually has a gateway (the real
        # management/default-route interface). Fall back to the first
        # static interface found if none has a gateway.
        mgmt_iface = next((name for name, b in blocks.items() if b.get("gateway")), None)
        if mgmt_iface is None and blocks:
            mgmt_iface = next(iter(blocks))

        if mgmt_iface:
            b = blocks[mgmt_iface]
            inv.current_ip = b.get("ip", "")
            inv.current_gateway = b.get("gateway", "")
            m = re.search(r"\.(\d+)$", mgmt_iface)
            if m:
                inv.current_vlan = int(m.group(1))

    def _get_system_settings(self, inv: HostInventory):
        """DNS, NTP, timezone, repo status."""
        # DNS
        out, _, _ = self.conn.ssh_run("cat /etc/resolv.conf")
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("nameserver "):
                inv.dns_servers.append(line.split()[1])
            elif line.startswith("search "):
                inv.dns_search = line.split(None, 1)[-1].strip()

        # Timezone
        out, _, _ = self.conn.ssh_run("timedatectl show --property=Timezone --value 2>/dev/null || timedatectl | grep 'Time zone'")
        inv.timezone = out.strip().split()[-1] if out.strip() else ""

        # NTP
        out, _, _ = self.conn.ssh_run("timedatectl | grep 'NTP service'")
        inv.ntp_active = "active" in out.lower()

        # Enterprise repo check
        out, _, _ = self.conn.ssh_run("ls /etc/apt/sources.list.d/")
        inv.has_enterprise_repo = "pve-enterprise" in out

        # Cluster
        out, _, _ = self.conn.ssh_run("pvecm status 2>/dev/null | head -5")
        inv.cluster_status = out.strip()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ethtool_block(text: str) -> dict:
    """Parse multi-NIC ethtool block into {nic_name: {speed, link}} dict."""
    result = {}
    current = None
    for line in text.splitlines():
        m = re.match(r"=== (\S+) ===", line)
        if m:
            current = m.group(1)
            result[current] = {"speed": None, "link": False}
            continue
        if current is None:
            continue
        if "Speed:" in line:
            sm = re.search(r"(\d+)Mb/s", line)
            if sm:
                result[current]["speed"] = int(sm.group(1))
        if "Link detected: yes" in line:
            result[current]["link"] = True
    return result


def _parse_ip_addr_block(text: str) -> dict:
    """
    Parse `ip -o -4 addr show` output into {nic_name: (ip, prefix)}.
    Example line:
    2: nic1    inet 10.0.2.10/21 brd 10.0.7.255 scope global vmbr0\\       valid_lft forever preferred_lft forever
    Only the first IPv4 address per interface is kept.
    """
    result = {}
    if not text:
        return result
    for line in text.splitlines():
        m = re.match(r"^\d+:\s+(\S+?)(?:@\S+)?\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
        if not m:
            continue
        name, ip, prefix = m.group(1), m.group(2), int(m.group(3))
        if name not in result:
            result[name] = (ip, prefix)
    return result


def _parse_default_route(text: str) -> tuple[str, str]:
    """
    Parse `ip -o -4 route show default` output into (gateway, device).
    Example line:
    default via 10.0.0.1 dev vmbr0 proto kernel
    """
    if not text:
        return "", ""
    m = re.search(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)\s+dev\s+(\S+)", text)
    if not m:
        return "", ""
    return m.group(1), m.group(2)
