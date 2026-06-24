"""
Data models for PVE Configurator.
All hardware discovery results and configuration state live here.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────────────

class NICRole(Enum):
    UNASSIGNED   = "Unassigned"
    MANAGEMENT   = "Management"
    VM_TRAFFIC   = "VM Traffic"
    STORAGE      = "Storage"
    ISCSI_A      = "iSCSI A"
    ISCSI_B      = "iSCSI B"
    COROSYNC     = "Corosync"
    MIGRATION    = "Migration"
    EXCLUDE      = "Exclude / Ignore"

class BondMode(Enum):
    ACTIVE_BACKUP = "active-backup"
    LACP_802_3AD  = "802.3ad"
    BALANCE_ALB   = "balance-alb"

class StorageRole(Enum):
    UNASSIGNED    = "Unassigned"
    OS_DISK       = "OS Disk (protected)"
    LOCAL_LVM     = "VM Images (LVM-thin)"
    BACKUP_DIR    = "Backup Storage (directory)"
    ZFS_POOL      = "ZFS Pool"
    EXCLUDE       = "Exclude / Ignore"

class ZFSLevel(Enum):
    SINGLE  = "single"
    MIRROR  = "mirror"
    RAIDZ   = "raidz"
    RAIDZ2  = "raidz2"
    RAIDZ3  = "raidz3"

class ConnectMethod(Enum):
    PASSWORD  = "Root Password"
    API_TOKEN = "API Token (GPG)"
    SSH_KEY   = "SSH Key"


# ── NIC ──────────────────────────────────────────────────────────────────────

@dataclass
class NICInfo:
    name: str
    mac: str
    state: str                        # UP / DOWN / UNKNOWN
    speed_mbps: Optional[int] = None  # None = unknown/unplugged
    link_detected: bool = False
    driver: str = ""
    vendor: str = ""
    model: str = ""
    is_wifi: bool = False
    is_virtual: bool = False          # bridges, VLANs, bonds
    ip: str = ""                      # current IPv4 address, e.g. 10.0.2.10
    prefix: int = 0                   # current CIDR prefix, e.g. 21 (0 = none)
    gateway: str = ""                 # default gateway via this interface, if any

    # Assigned by operator
    role: NICRole = NICRole.UNASSIGNED

    @property
    def speed_label(self) -> str:
        if self.speed_mbps is None:
            return "Unknown"
        if self.speed_mbps >= 10000:
            return f"{self.speed_mbps // 1000}GbE"
        return f"{self.speed_mbps}Mb/s"

    @property
    def state_label(self) -> str:
        if self.is_virtual:
            return "Virtual"
        return "UP ✓" if self.state == "UP" else "DOWN"

    @property
    def suggested_role(self) -> NICRole:
        """Heuristic role suggestion based on name and speed."""
        if self.is_wifi or self.is_virtual:
            return NICRole.EXCLUDE
        # Name-based defaults for known home lab NIC naming
        if self.name == "nic0":
            return NICRole.STORAGE
        if self.name == "nic1":
            return NICRole.MANAGEMENT
        if self.speed_mbps is not None and self.speed_mbps >= 10000:
            return NICRole.VM_TRAFFIC
        if self.speed_mbps is not None and self.speed_mbps <= 1000:
            return NICRole.MANAGEMENT
        return NICRole.UNASSIGNED


# ── Disk ─────────────────────────────────────────────────────────────────────

@dataclass
class DiskInfo:
    name: str          # sda, nvme0n1, etc.
    path: str          # /dev/sda
    size_gb: float
    is_rotational: bool
    transport: str     # sata, nvme, usb, etc.
    vendor: str = ""
    model: str = ""
    serial: str = ""
    has_partitions: bool = False
    is_pve_os: bool = False    # contains pve VG — protect this
    is_usb: bool = False

    # Assigned by operator
    role: StorageRole = StorageRole.UNASSIGNED
    storage_name: str = ""     # e.g. "Local-SSD-01", "Backup-HDD-01"

    @property
    def size_label(self) -> str:
        if self.size_gb >= 1000:
            return f"{self.size_gb / 1000:.1f} TB"
        return f"{self.size_gb:.0f} GB"

    @property
    def type_label(self) -> str:
        if self.transport == "nvme":
            return "NVMe SSD"
        if self.transport == "usb":
            return "USB"
        if self.is_rotational:
            return "HDD"
        return "SSD"

    @property
    def suggested_role(self) -> StorageRole:
        if self.is_pve_os:
            return StorageRole.OS_DISK
        if self.is_usb:
            return StorageRole.EXCLUDE
        if self.has_partitions:
            return StorageRole.EXCLUDE
        if self.is_rotational:
            return StorageRole.BACKUP_DIR
        return StorageRole.LOCAL_LVM


# ── Host credentials ─────────────────────────────────────────────────────────

@dataclass
class HostCredentials:
    host: str
    port: int = 8006
    method: ConnectMethod = ConnectMethod.PASSWORD
    username: str = "root@pam"
    password: str = ""           # for PASSWORD method
    api_token_id: str = ""       # for API_TOKEN method
    api_token_secret: str = ""   # for API_TOKEN method
    ssh_key_path: str = ""       # for SSH_KEY method
    verify_ssl: bool = False


# ── Full inventory ────────────────────────────────────────────────────────────

@dataclass
class HostInventory:
    hostname: str = ""
    fqdn: str = ""
    pve_version: str = ""
    cpu_model: str = ""
    cpu_cores: int = 0
    cpu_threads: int = 0
    ram_gb: float = 0.0
    nics: list[NICInfo] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    current_ip: str = ""
    current_gateway: str = ""
    current_vlan: Optional[int] = None
    timezone: str = ""
    dns_servers: list[str] = field(default_factory=list)
    dns_search: str = ""
    ntp_active: bool = False
    has_enterprise_repo: bool = False
    cluster_status: str = ""   # empty = not in cluster

    @property
    def physical_nics(self) -> list[NICInfo]:
        return [n for n in self.nics if not n.is_virtual and not n.is_wifi]

    @property
    def configurable_disks(self) -> list[DiskInfo]:
        return [d for d in self.disks if not d.is_usb]


# ── Desired configuration (what operator builds up) ──────────────────────────

@dataclass
class BondConfig:
    name: str              # bond0, bond1, etc.
    members: list[str]     # NIC names
    mode: BondMode = BondMode.ACTIVE_BACKUP
    mtu: int = 1500

@dataclass
class BridgeConfig:
    name: str              # vmbr0, vmbr1, etc.
    bond_or_nic: str       # what it bridges
    vlan_aware: bool = False
    vlan_ids: str = ""
    mtu: int = 1500
    ip: str = ""           # e.g. 10.0.2.10 (blank = inet manual)
    prefix: int = 24
    gateway: str = ""

@dataclass
class VLANConfig:
    name: str              # vmbr0.2008
    parent: str            # vmbr0
    vlan_id: int
    ip: str = ""
    prefix: int = 24
    gateway: str = ""

# ── Content type constants ────────────────────────────────────────────────────

CONTENT_IMAGES   = "images"
CONTENT_ROOTDIR  = "rootdir"
CONTENT_BACKUP   = "backup"
CONTENT_ISO      = "iso"
CONTENT_VZTMPL   = "vztmpl"
CONTENT_SNIPPETS = "snippets"

CONTENT_BY_ROLE = {
    StorageRole.LOCAL_LVM:  [CONTENT_IMAGES, CONTENT_ROOTDIR],
    StorageRole.BACKUP_DIR: [CONTENT_BACKUP, CONTENT_ISO, CONTENT_VZTMPL],
    StorageRole.ZFS_POOL:   [CONTENT_IMAGES, CONTENT_ROOTDIR],
}

ALL_CONTENT_TYPES = [
    CONTENT_IMAGES, CONTENT_ROOTDIR, CONTENT_BACKUP,
    CONTENT_ISO, CONTENT_VZTMPL, CONTENT_SNIPPETS,
]


@dataclass
class StorageConfig:
    """Local disk storage configuration."""
    name: str                          # PVE storage ID, e.g. Local-SSD-01
    disk_path: str                     # /dev/sda
    role: StorageRole = StorageRole.LOCAL_LVM
    wipe_disk: bool = False            # run wipefs before setup
    # LVM-thin options
    vg_name: str = ""
    thin_pool_name: str = "data"
    thin_pool_size_pct: int = 95       # % of VG to allocate to thin pool
    # Dir options
    dir_path: str = "/mnt/pve"        # mount point base
    # ZFS options
    zfs_level: "ZFSLevel" = None
    content_types: list[str] = field(default_factory=list)

    def __post_init__(self):
        if self.zfs_level is None:
            from core.models import ZFSLevel
            self.zfs_level = ZFSLevel.SINGLE
        if not self.content_types:
            self.content_types = list(CONTENT_BY_ROLE.get(self.role, []))


@dataclass
class NFSShare:
    """A single NFS share to add as PVE storage."""
    storage_id: str          # PVE storage name
    server: str              # NAS IP
    export: str              # /volume1/backups
    mount_point: str = ""    # auto-generated if blank
    content_types: list[str] = field(default_factory=list)
    options: str = ""        # extra mount options

    def __post_init__(self):
        if not self.content_types:
            self.content_types = [CONTENT_BACKUP, CONTENT_ISO, CONTENT_VZTMPL]
        if not self.mount_point:
            safe = self.export.replace("/", "-").strip("-")
            self.mount_point = f"/mnt/pve/{safe}"


@dataclass
class ISCSITarget:
    """An iSCSI target to add as PVE storage."""
    storage_id: str          # PVE storage name (raw iscsi)
    portal: str              # target IP
    target: str              # IQN string
    # Optional LVM on top of iSCSI
    add_lvm: bool = False
    lvm_storage_id: str = ""
    content_types: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.content_types:
            self.content_types = [CONTENT_IMAGES, CONTENT_ROOTDIR]

@dataclass
class DesiredConfig:
    """Complete desired state the operator has configured."""
    # Management
    mgmt_ip: str = ""
    mgmt_prefix: int = 24
    mgmt_gateway: str = ""
    mgmt_vlan: int = 0

    # Network objects
    bonds: list[BondConfig] = field(default_factory=list)
    bridges: list[BridgeConfig] = field(default_factory=list)
    vlans: list[VLANConfig] = field(default_factory=list)

    # Storage
    storage_configs: list[StorageConfig] = field(default_factory=list)

    # System
    ntp_server: str = ""
    dns_servers: list[str] = field(default_factory=list)
    dns_search: str = ""
    timezone: str = ""
    disable_enterprise_repo: bool = True
    enable_no_subscription_repo: bool = True

    # Cluster
    join_cluster: bool = False
    cluster_host: str = ""
    cluster_password: str = ""

    # Profile metadata
    profile_name: str = ""
    profile_description: str = ""
