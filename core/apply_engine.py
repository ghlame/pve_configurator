"""
Apply engine for PVE Configurator.
Builds an ordered command list from all tab configurations,
executes via SSH with live streaming, and handles network
apply safety (ifreload + reconnect verification).
"""

import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.connection import PVEConnection
from core.models import (
    HostInventory, DesiredConfig,
    StorageRole, NICRole,
    BondConfig, BridgeConfig, VLANConfig, StorageConfig,
    NFSShare, ISCSITarget,
)


# ── Command model ─────────────────────────────────────────────────────────────

class CommandSection(Enum):
    BACKUP      = "Backup"
    REPOS       = "Repositories"
    PACKAGES    = "Package Installation"
    SYSTEM      = "System Settings"
    STORAGE     = "Storage"
    NETWORK     = "Network"
    PVE         = "PVE Settings"
    USERS       = "Users"
    CLUSTER     = "Cluster"

SECTION_COLORS = {
    CommandSection.BACKUP:   "#888888",
    CommandSection.REPOS:    "#5c9bd6",
    CommandSection.PACKAGES: "#5c9bd6",
    CommandSection.SYSTEM:   "#9c27b0",
    CommandSection.STORAGE:  "#ff9800",
    CommandSection.NETWORK:  "#4caf50",
    CommandSection.PVE:      "#5c9bd6",
    CommandSection.USERS:    "#9c27b0",
    CommandSection.CLUSTER:  "#f44336",
}


@dataclass
class ApplyCommand:
    section:     CommandSection
    description: str           # human-readable label shown in UI
    command:     str           # shell command to run
    critical:    bool = True   # if True, stop on non-zero exit
    timeout:     int  = 60     # seconds
    network_apply: bool = False  # True = this is the ifreload step
    check_reconnect: bool = False  # True = verify SSH after this command


@dataclass
class CommandResult:
    command:    ApplyCommand
    stdout:     str = ""
    stderr:     str = ""
    exit_code:  int = -1
    duration_s: float = 0.0
    skipped:    bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 or self.skipped


# ── Command builder ───────────────────────────────────────────────────────────

class CommandBuilder:
    """
    Builds the full ordered list of ApplyCommands from all tab configurations.
    Does not execute anything — pure data transformation.
    """

    def __init__(
        self,
        inv:            HostInventory,
        system_config:  dict,
        storage_configs: list[StorageConfig],
        nfs_shares:     list[NFSShare],
        iscsi_targets:  list[ISCSITarget],
        bonds:          list[BondConfig],
        bridges:        list[BridgeConfig],
        vlans:          list[VLANConfig],
        interfaces_content: str,
        hostname:       str = "",
    ):
        self.inv                 = inv
        self.sys                 = system_config
        self.storage_configs     = storage_configs
        self.nfs_shares          = nfs_shares
        self.iscsi_targets       = iscsi_targets
        self.bonds               = bonds
        self.bridges             = bridges
        self.vlans               = vlans
        self.interfaces_content  = interfaces_content
        self.hostname            = hostname or inv.hostname

    def build(self) -> list[ApplyCommand]:
        cmds: list[ApplyCommand] = []
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        cmds += self._backup_commands(ts)
        cmds += self._repo_commands()
        cmds += self._package_commands()
        cmds += self._system_commands()
        cmds += self._storage_commands()
        cmds += self._network_commands()
        cmds += self._pve_commands()
        cmds += self._user_commands()
        cmds += self._cluster_commands()

        return cmds

    # ── Backup ────────────────────────────────────────────────────────────────

    def _backup_commands(self, ts: str) -> list[ApplyCommand]:
        cmds = []
        files = [
            "/etc/network/interfaces",
            "/etc/resolv.conf",
        ]
        if self.sys.get("ntp_servers"):
            files.append("/etc/chrony/chrony.conf")

        for f in files:
            cmds.append(ApplyCommand(
                section=CommandSection.BACKUP,
                description=f"Back up {f}",
                command=f"cp {f} {f}.bak.{ts} 2>/dev/null || true",
                critical=False,
                timeout=10,
            ))

        # PVE storage config backup
        cmds.append(ApplyCommand(
            section=CommandSection.BACKUP,
            description="Back up PVE storage config",
            command=f"cp /etc/pve/storage.cfg /etc/pve/storage.cfg.bak.{ts} 2>/dev/null || true",
            critical=False,
            timeout=10,
        ))
        return cmds

    # ── Repos ─────────────────────────────────────────────────────────────────

    def _repo_commands(self) -> list[ApplyCommand]:
        cmds = []
        if self.sys.get("disable_enterprise_repo"):
            cmds.append(ApplyCommand(
                section=CommandSection.REPOS,
                description="Disable enterprise repository",
                command=(
                    "[ -f /etc/apt/sources.list.d/pve-enterprise.sources ] && "
                    "mv /etc/apt/sources.list.d/pve-enterprise.sources "
                    "/etc/apt/sources.list.d/pve-enterprise.sources.disabled || true"
                ),
                critical=False,
                timeout=10,
            ))
            cmds.append(ApplyCommand(
                section=CommandSection.REPOS,
                description="Disable Ceph enterprise repository",
                command=(
                    "[ -f /etc/apt/sources.list.d/ceph.sources ] && "
                    "mv /etc/apt/sources.list.d/ceph.sources "
                    "/etc/apt/sources.list.d/ceph.sources.disabled || true"
                ),
                critical=False,
                timeout=10,
            ))
        if self.sys.get("enable_nosub_repo"):
            cmds.append(ApplyCommand(
                section=CommandSection.REPOS,
                description="Enable no-subscription repository",
                command=(
                    "echo 'deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription' "
                    "> /etc/apt/sources.list.d/pve-no-subscription.list"
                ),
                timeout=10,
            ))
        cmds.append(ApplyCommand(
            section=CommandSection.REPOS,
            description="Update package cache",
            command="apt-get update -qq",
            timeout=120,
        ))
        return cmds

    # ── Packages ──────────────────────────────────────────────────────────────

    def _package_commands(self) -> list[ApplyCommand]:
        cmds = []
        pkgs = []
        if self.sys.get("install_fail2ban"):
            pkgs.append("fail2ban")
        if self.sys.get("install_node_exporter"):
            pkgs.append("prometheus-node-exporter")
        if self.sys.get("enable_unattended_upgrades"):
            pkgs.append("unattended-upgrades")

        if pkgs:
            cmds.append(ApplyCommand(
                section=CommandSection.PACKAGES,
                description=f"Install packages: {', '.join(pkgs)}",
                command=f"DEBIAN_FRONTEND=noninteractive apt-get install -y {' '.join(pkgs)}",
                timeout=300,
            ))

        # fail2ban config
        if self.sys.get("install_fail2ban"):
            cmds.append(ApplyCommand(
                section=CommandSection.PACKAGES,
                description="Configure fail2ban SSH jail",
                command=(
                    "cat > /etc/fail2ban/jail.d/sshd.conf << 'EOF'\n"
                    "[sshd]\nenabled = true\nmaxretry = 5\nbantime = 3600\nfindtime = 600\n"
                    "EOF\n"
                    "systemctl enable --now fail2ban"
                ),
                timeout=30,
            ))

        # unattended-upgrades config
        if self.sys.get("enable_unattended_upgrades"):
            cmds.append(ApplyCommand(
                section=CommandSection.PACKAGES,
                description="Configure unattended-upgrades (exclude PVE/kernel packages)",
                command=(
                    "cat > /etc/apt/apt.conf.d/50unattended-upgrades-pve << 'EOF'\n"
                    'Unattended-Upgrade::Origins-Pattern {\n'
                    '    "origin=Debian,codename=${distro_codename},label=Debian-Security";\n'
                    '};\n'
                    'Unattended-Upgrade::Package-Blacklist {\n'
                    '    "proxmox-ve";\n'
                    '    "pve-*";\n'
                    '    "ceph*";\n'
                    '    "linux-image*";\n'
                    '    "linux-headers*";\n'
                    '};\n'
                    'Unattended-Upgrade::Automatic-Reboot "false";\n'
                    "EOF\n"
                    "systemctl enable --now unattended-upgrades"
                ),
                timeout=30,
            ))

        # node-exporter enable
        if self.sys.get("install_node_exporter"):
            cmds.append(ApplyCommand(
                section=CommandSection.PACKAGES,
                description="Enable prometheus-node-exporter",
                command="systemctl enable --now prometheus-node-exporter",
                timeout=15,
                critical=False,
            ))

        # promtail config
        if self.sys.get("install_promtail"):
            loki = self.sys.get("loki_url") or "http://LOKI-SERVER:3100"
            cmds.append(ApplyCommand(
                section=CommandSection.PACKAGES,
                description="Configure Promtail",
                command=(
                    f"cat > /etc/promtail/config.yml << 'EOF'\n"
                    "server:\n  http_listen_port: 9080\n"
                    "positions:\n  filename: /var/lib/promtail/positions.yaml\n"
                    "clients:\n"
                    f"  - url: {loki}/loki/api/v1/push\n"
                    "scrape_configs:\n"
                    "  - job_name: system\n"
                    "    static_configs:\n"
                    f"      - targets: [localhost]\n"
                    f"        labels:\n"
                    f"          job: system\n"
                    f"          host: {self.hostname}\n"
                    "          __path__: /var/log/*.log\n"
                    "EOF\n"
                    "systemctl enable --now promtail"
                ),
                timeout=15,
                critical=False,
            ))

        return cmds

    # ── System settings ───────────────────────────────────────────────────────

    def _system_commands(self) -> list[ApplyCommand]:
        cmds = []

        # Timezone
        tz = self.sys.get("timezone")
        if tz:
            cmds.append(ApplyCommand(
                section=CommandSection.SYSTEM,
                description=f"Set timezone to {tz}",
                command=f"timedatectl set-timezone {tz}",
                timeout=15,
            ))

        # NTP
        ntp_servers = self.sys.get("ntp_servers", [])
        if ntp_servers:
            server_lines = "\n".join(f"server {s} iburst" for s in ntp_servers)
            cmds.append(ApplyCommand(
                section=CommandSection.SYSTEM,
                description="Configure Chrony NTP",
                command=(
                    f"cat > /etc/chrony/chrony.conf << 'EOF'\n"
                    f"{server_lines}\n"
                    "driftfile /var/lib/chrony/drift\n"
                    "makestep 1.0 3\n"
                    "rtcsync\n"
                    "EOF\n"
                    "systemctl restart chrony"
                ),
                timeout=20,
            ))

        # DNS
        dns_servers = self.sys.get("dns_servers", [])
        dns_search  = self.sys.get("dns_search", "")
        if dns_servers:
            lines = []
            if dns_search:
                lines.append(f"search {dns_search}")
            for s in dns_servers:
                lines.append(f"nameserver {s}")
            content = "\n".join(lines)
            cmds.append(ApplyCommand(
                section=CommandSection.SYSTEM,
                description="Configure DNS (/etc/resolv.conf)",
                command=f"cat > /etc/resolv.conf << 'EOF'\n{content}\nEOF",
                timeout=10,
            ))

        # SSH hardening
        if self.sys.get("ssh_prohibit_password"):
            cmds.append(ApplyCommand(
                section=CommandSection.SYSTEM,
                description="Set SSH PermitRootLogin prohibit-password",
                command=(
                    "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "
                    "/etc/ssh/sshd_config && systemctl restart sshd"
                ),
                timeout=15,
            ))

        # Log rotation check
        cmds.append(ApplyCommand(
            section=CommandSection.SYSTEM,
            description="Verify log rotation",
            command="logrotate --debug /etc/logrotate.conf 2>&1 | head -5",
            critical=False,
            timeout=15,
        ))

        return cmds

    # ── Storage ───────────────────────────────────────────────────────────────

    def _storage_commands(self) -> list[ApplyCommand]:
        cmds = []
        from core.models import StorageRole

        for cfg in self.storage_configs:
            if cfg.role == StorageRole.LOCAL_LVM:
                if cfg.wipe_disk:
                    cmds.append(ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Wipe {cfg.disk_path}",
                        command=f"wipefs -a {cfg.disk_path}",
                        timeout=30,
                    ))
                vg = cfg.vg_name or f"pve-{cfg.name.lower()}"
                pool = cfg.thin_pool_name or "data"
                pct  = cfg.thin_pool_size_pct
                content = ",".join(cfg.content_types)
                cmds += [
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Create PV on {cfg.disk_path}",
                        command=f"pvcreate {cfg.disk_path}",
                        timeout=30,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Create VG {vg}",
                        command=f"vgcreate {vg} {cfg.disk_path}",
                        timeout=30,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Create thin pool {vg}/{pool}",
                        command=f"lvcreate -l {pct}%FREE -T {vg}/{pool}",
                        timeout=60,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Add PVE storage {cfg.name}",
                        command=(
                            f"pvesm add lvmthin {cfg.name} "
                            f"--vgname {vg} --thinpool {pool} --content {content}"
                        ),
                        timeout=30,
                    ),
                ]

            elif cfg.role == StorageRole.BACKUP_DIR:
                mount = cfg.dir_path or f"/mnt/pve/{cfg.name.lower()}"
                content = ",".join(cfg.content_types)
                if cfg.wipe_disk:
                    cmds.append(ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Wipe {cfg.disk_path}",
                        command=f"wipefs -a {cfg.disk_path}",
                        timeout=30,
                    ))
                cmds += [
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Partition {cfg.disk_path}",
                        command=(
                            f"parted -s {cfg.disk_path} mklabel gpt && "
                            f"parted -s {cfg.disk_path} mkpart primary 0% 100%"
                        ),
                        timeout=30,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Format {cfg.disk_path}1 as ext4",
                        command=f"mkfs.ext4 -F {cfg.disk_path}1",
                        timeout=120,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Create mount point {mount}",
                        command=f"mkdir -p {mount}",
                        timeout=10,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Add fstab entry for {mount}",
                        command=(
                            f"echo '{cfg.disk_path}1  {mount}  ext4  defaults  0  2' "
                            f">> /etc/fstab && mount {mount}"
                        ),
                        timeout=30,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Add PVE storage {cfg.name}",
                        command=(
                            f"pvesm add dir {cfg.name} "
                            f"--path {mount} --content {content}"
                        ),
                        timeout=30,
                    ),
                ]

            elif cfg.role == StorageRole.ZFS_POOL:
                pool = cfg.zfs_pool_name or cfg.name.lower()
                level = cfg.zfs_level.value if cfg.zfs_level else "single"
                raid  = "" if level == "single" else level
                content = ",".join(cfg.content_types)
                if cfg.wipe_disk:
                    cmds.append(ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Wipe {cfg.disk_path}",
                        command=f"wipefs -a {cfg.disk_path}",
                        timeout=30,
                    ))
                cmds += [
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Create ZFS pool {pool}",
                        command=f"zpool create {pool} {raid} {cfg.disk_path}",
                        timeout=60,
                    ),
                    ApplyCommand(
                        section=CommandSection.STORAGE,
                        description=f"Add PVE ZFS storage {cfg.name}",
                        command=(
                            f"pvesm add zfspool {cfg.name} "
                            f"--pool {pool} --content {content}"
                        ),
                        timeout=30,
                    ),
                ]

        # NFS shares
        for share in self.nfs_shares:
            content = ",".join(share.content_types)
            cmds.append(ApplyCommand(
                section=CommandSection.STORAGE,
                description=f"Add NFS storage {share.storage_id}",
                command=(
                    f"pvesm status --storage {share.storage_id} > /dev/null 2>&1 && "
                    f"echo 'Storage {share.storage_id} already exists, skipping' || "
                    f"pvesm add nfs {share.storage_id} "
                    f"--server {share.server} --export {share.export} "
                    f"--content {content}"
                ),
                timeout=30,
                critical=False,
            ))

        # iSCSI targets
        for target in self.iscsi_targets:
            cmds.append(ApplyCommand(
                section=CommandSection.STORAGE,
                description=f"Add iSCSI storage {target.storage_id}",
                command=(
                    f"pvesm status --storage {target.storage_id} > /dev/null 2>&1 && "
                    f"echo 'Storage {target.storage_id} already exists, skipping' || "
                    f"pvesm add iscsi {target.storage_id} "
                    f"--portal {target.portal} --target {target.target} "
                    f"--content none"
                ),
                timeout=30,
                critical=False,
            ))

        return cmds

    # ── Network ───────────────────────────────────────────────────────────────

    def _network_commands(self) -> list[ApplyCommand]:
        if not self.interfaces_content:
            return []
        # Escape the interfaces content for safe embedding in a heredoc
        content = self.interfaces_content
        cmds = [
            ApplyCommand(
                section=CommandSection.NETWORK,
                description="Write /etc/network/interfaces",
                command=(
                    f"cat > /tmp/interfaces_desired << 'INTERFACES_EOF'\n"
                    f"{content}\n"
                    "INTERFACES_EOF"
                ),
                timeout=15,
            ),
            ApplyCommand(
                section=CommandSection.NETWORK,
                description="Validate new network config",
                command=(
                    "if diff -q /tmp/interfaces_desired /etc/network/interfaces > /dev/null 2>&1; then "
                    "echo 'Network config unchanged — skipping validation'; "
                    "else "
                    "ifup --no-act -a -i /tmp/interfaces_desired 2>&1; "
                    "fi"
                ),
                critical=False,
                timeout=30,
            ),
            ApplyCommand(
                section=CommandSection.NETWORK,
                description="Apply network changes (ifreload)",
                command=(
                    "if diff -q /tmp/interfaces_desired /etc/network/interfaces > /dev/null 2>&1; then "
                    "echo 'Network config unchanged — skipping ifreload'; "
                    "else "
                    "cp /tmp/interfaces_desired /etc/network/interfaces && ifreload -a; "
                    "fi"
                ),
                timeout=45,
                network_apply=True,
                check_reconnect=True,
            ),
        ]
        return cmds

    # ── PVE settings ──────────────────────────────────────────────────────────

    def _pve_commands(self) -> list[ApplyCommand]:
        cmds = []

        # Subscription nag removal
        if self.sys.get("remove_nag"):
            cmds.append(ApplyCommand(
                section=CommandSection.PVE,
                description="Remove subscription nag",
                command=(
                    "sed -i.bak 's/NotFound/Active/g' "
                    "/usr/share/perl5/PVE/API2/Subscription.pm && "
                    "systemctl restart pveproxy"
                ),
                critical=False,
                timeout=30,
            ))

        # Firewall
        if self.sys.get("enable_firewall"):
            cidr = self.sys.get("firewall_mgmt_cidr", "10.0.0.0/8")
            fw_content = (
                "[OPTIONS]\nenable: 1\nlog_ratelimit: burst=10,rate=5/second\n\n"
                "[RULES]\n"
                f"IN ACCEPT -source {cidr} -dport 22 -p tcp -log nolog\n"
                f"IN ACCEPT -source {cidr} -dport 8006 -p tcp -log nolog\n"
                f"IN ACCEPT -source {cidr} -dport 3128 -p tcp -log nolog\n"
                f"IN ACCEPT -source {cidr} -dport 5900:5999 -p tcp -log nolog\n"
                "IN ACCEPT -dport 5405 -p udp -log nolog\n"
                "IN DROP -log warning\n"
            )
            cmds += [
                ApplyCommand(
                    section=CommandSection.PVE,
                    description="Write PVE datacenter firewall rules",
                    command=(
                        f"cat > /etc/pve/firewall/cluster.fw << 'EOF'\n"
                        f"{fw_content}EOF"
                    ),
                    timeout=15,
                ),
            ]

        # PVE Prometheus exporter (separate package from node-exporter;
        # exposes PVE cluster/VM metrics, not OS-level metrics)
        if self.sys.get("enable_pve_metrics"):
            cmds.append(ApplyCommand(
                section=CommandSection.PVE,
                description="Install prometheus-pve-exporter",
                command=(
                    "apt-get install -y prometheus-pve-exporter && "
                    "systemctl enable --now prometheus-pve-exporter"
                ),
                critical=False,
                timeout=60,
            ))

        return cmds

    # ── Users ─────────────────────────────────────────────────────────────────

    def _user_commands(self) -> list[ApplyCommand]:
        cmds = []
        username = self.sys.get("create_username", "")
        if not username:
            return cmds

        cmds += [
            ApplyCommand(
                section=CommandSection.USERS,
                description=f"Create user {username}",
                command=(
                    f"id {username} &>/dev/null || "
                    f"useradd -m -s /bin/bash {username}"
                ),
                timeout=15,
            ),
            ApplyCommand(
                section=CommandSection.USERS,
                description=f"Add {username} to sudo group",
                command=f"usermod -aG sudo {username}",
                timeout=10,
            ),
        ]

        if self.sys.get("user_sudo_nopasswd"):
            cmds.append(ApplyCommand(
                section=CommandSection.USERS,
                description=f"Grant {username} passwordless sudo",
                command=(
                    f"echo '{username} ALL=(ALL) NOPASSWD:ALL' "
                    f"> /etc/sudoers.d/{username} && "
                    f"chmod 440 /etc/sudoers.d/{username}"
                ),
                timeout=10,
            ))

        pub_key = self.sys.get("user_ssh_pubkey", "")
        if pub_key:
            cmds += [
                ApplyCommand(
                    section=CommandSection.USERS,
                    description=f"Install SSH key for {username}",
                    command=(
                        f"mkdir -p /home/{username}/.ssh && "
                        f"echo '{pub_key}' >> /home/{username}/.ssh/authorized_keys && "
                        f"chmod 700 /home/{username}/.ssh && "
                        f"chmod 600 /home/{username}/.ssh/authorized_keys && "
                        f"chown -R {username}:{username} /home/{username}/.ssh"
                    ),
                    timeout=10,
                ),
            ]
        return cmds

    # ── Cluster ───────────────────────────────────────────────────────────────

    def _cluster_commands(self) -> list[ApplyCommand]:
        cmds = []
        mode = self.sys.get("cluster_mode", "skip")

        if mode == "create":
            name  = self.sys.get("cluster_name", "")
            ring0 = self.sys.get("cluster_ring0", "")
            if name:
                cmd = f"pvecm create {name}"
                if ring0:
                    cmd += f" --link0 {ring0}"
                cmds.append(ApplyCommand(
                    section=CommandSection.CLUSTER,
                    description=f"Create cluster '{name}'",
                    command=cmd,
                    timeout=60,
                ))

        elif mode == "join":
            host = self.sys.get("cluster_join_host", "")
            pw   = self.sys.get("cluster_join_password", "")
            if host and pw:
                cmds.append(ApplyCommand(
                    section=CommandSection.CLUSTER,
                    description=f"Join cluster via {host}",
                    command=(
                        f"pvecm add {host} "
                        f"--use_ssh 1"
                    ),
                    timeout=120,
                    critical=True,
                ))

        return cmds


# ── Apply worker ──────────────────────────────────────────────────────────────

class ApplyWorker(QThread):
    """
    Executes the apply command list via SSH.
    Emits progress signals for each command.
    """

    # (section_name, description, status, stdout, stderr)
    command_started  = pyqtSignal(str, str)
    command_finished = pyqtSignal(str, str, bool, str, str, float)
    log_line         = pyqtSignal(str, str)   # (text, color)
    finished_all     = pyqtSignal(bool, str)   # (success, summary)

    def __init__(self, conn: PVEConnection, commands: list[ApplyCommand]):
        super().__init__()
        self.conn     = conn
        self.commands = commands
        self._stop    = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        except Exception as e:
            traceback.print_exc()
            self.finished_all.emit(False, f"Unexpected error: {e}")

    def _run(self):
        total   = len(self.commands)
        passed  = 0
        failed  = 0

        for i, cmd in enumerate(self.commands):
            if self._stop:
                self.finished_all.emit(False, "Apply cancelled by operator.")
                return

            self.command_started.emit(cmd.section.value, cmd.description)
            self.log_line.emit(
                f"\n[{i+1}/{total}] {cmd.section.value} — {cmd.description}",
                SECTION_COLORS.get(cmd.section, "#888")
            )
            self.log_line.emit(f"$ {cmd.command[:120]}{'...' if len(cmd.command) > 120 else ''}", "#666")

            t0 = time.time()
            stdout, stderr, rc = self.conn.ssh_run(cmd.command)
            elapsed = round(time.time() - t0, 1)

            ok = rc == 0
            if stdout.strip():
                self.log_line.emit(stdout.strip(), "#d4d4d4")
            if stderr.strip():
                color = "#ff9800" if ok else "#f44336"
                self.log_line.emit(stderr.strip(), color)

            status_color = "#4caf50" if ok else "#f44336"
            status_text  = f"✓ OK ({elapsed}s)" if ok else f"✗ FAILED (exit {rc}, {elapsed}s)"
            self.log_line.emit(status_text, status_color)

            self.command_finished.emit(
                cmd.section.value, cmd.description,
                ok, stdout, stderr, elapsed
            )

            if ok:
                passed += 1
            else:
                failed += 1
                if cmd.critical:
                    msg = (
                        f"Critical command failed: {cmd.description}\n"
                        f"Exit code: {rc}\n"
                        f"stderr: {stderr.strip()[:300]}"
                    )
                    self.finished_all.emit(False, msg)
                    return

            # Network reconnect verification
            if cmd.check_reconnect:
                self.log_line.emit("Verifying SSH connectivity after network change…", "#888")
                reconnected = self._verify_reconnect()
                if not reconnected:
                    self.finished_all.emit(
                        False,
                        "SSH connection lost after network apply and could not reconnect.\n"
                        "The host may be unreachable. Check the network configuration manually."
                    )
                    return
                self.log_line.emit("✓ SSH reconnected successfully.", "#4caf50")

        summary = f"Apply complete — {passed} succeeded, {failed} failed."
        self.finished_all.emit(failed == 0, summary)

    def _verify_reconnect(self, attempts: int = 6, delay: float = 5.0) -> bool:
        """Try to reconnect SSH up to `attempts` times after network apply."""
        for attempt in range(attempts):
            time.sleep(delay)
            self.log_line.emit(
                f"  Reconnect attempt {attempt + 1}/{attempts}…", "#888"
            )
            try:
                ok, _ = self.conn.connect()
                if ok:
                    return True
            except Exception:
                pass
        return False
