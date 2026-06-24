"""
Site and host profile management for PVE Configurator.
Profiles stored in ~/.config/pve-configurator/
  sites.json  — site profiles (location-specific settings)
  hosts.json  — host profiles (hardware/role patterns)
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


CONFIG_DIR  = Path.home() / ".config" / "pve-configurator"
SITES_FILE  = CONFIG_DIR / "sites.json"
HOSTS_FILE  = CONFIG_DIR / "hosts.json"


# ─────────────────────────────────────────────────────────────────────────────
# Site Profile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SiteProfile:
    name: str
    timezone: str = "UTC"
    ntp_servers: list[str] = field(default_factory=list)
    dns_servers: list[str] = field(default_factory=list)
    dns_search: str = ""
    # VLANs (0 = not configured)
    vlan_management: int = 0
    vlan_vm: int = 0
    vlan_storage: int = 0
    vlan_migration: int = 0
    vlan_corosync: int = 0
    # Networking
    mgmt_subnet: str = ""
    firewall_mgmt_cidr: str = ""
    # Monitoring
    loki_url: str = ""
    prometheus_url: str = ""
    # AD
    ad_domain: str = ""
    # Meta
    notes: str = ""
    builtin: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SiteProfile":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})

    def summary(self) -> str:
        parts = []
        if self.timezone:
            parts.append(self.timezone)
        if self.dns_servers:
            parts.append(f"DNS: {', '.join(self.dns_servers[:2])}")
        if self.vlan_management:
            parts.append(f"Mgmt VLAN: {self.vlan_management}")
        return "  |  ".join(parts) if parts else "No details configured"


# ─────────────────────────────────────────────────────────────────────────────
# Host Profile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NICRoleAssignment:
    """Maps a NIC name pattern to a role."""
    pattern: str        # e.g. "nic0", "nic1", or speed-based "1GbE", "10GbE"
    role: str           # NICRole value string
    match_by: str = "name"   # "name" or "speed"

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, d): return cls(**d)


@dataclass
class DiskRoleAssignment:
    """Maps a disk type/transport to a role."""
    transport: str      # "nvme", "sata", "usb"
    is_rotational: bool = False
    role: str = "Unassigned"
    storage_name_prefix: str = ""

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, d): return cls(**d)


@dataclass
class HostProfile:
    name: str
    description: str = ""
    # Network
    nic_roles: list[NICRoleAssignment] = field(default_factory=list)
    # Bond defaults
    vm_bond_mode: str = "802.3ad"         # for VM traffic NICs
    mgmt_bond_mode: str = "active-backup" # for management NICs
    # Bridge defaults
    vlan_aware_bridge: bool = True
    bridge_vlan_ids: str = "2-4094"
    # Storage
    disk_roles: list[DiskRoleAssignment] = field(default_factory=list)
    # System options
    install_fail2ban: bool = True
    ssh_prohibit_password: bool = True
    enable_unattended_upgrades: bool = True
    enable_firewall: bool = True
    install_node_exporter: bool = True
    install_promtail: bool = True
    disable_enterprise_repo: bool = True
    enable_nosub_repo: bool = True
    remove_nag: bool = True
    # Cluster
    cluster_mode: str = "skip"   # skip / create / join
    # Meta
    notes: str = ""
    builtin: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "HostProfile":
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in d.items() if k in known}
        # Re-inflate nested dataclasses
        if "nic_roles" in filtered:
            filtered["nic_roles"] = [
                NICRoleAssignment.from_dict(r) for r in filtered["nic_roles"]
            ]
        if "disk_roles" in filtered:
            filtered["disk_roles"] = [
                DiskRoleAssignment.from_dict(r) for r in filtered["disk_roles"]
            ]
        return cls(**filtered)

    def summary(self) -> str:
        parts = []
        if self.nic_roles:
            parts.append(f"{len(self.nic_roles)} NIC rules")
        if self.disk_roles:
            parts.append(f"{len(self.disk_roles)} disk rules")
        parts.append(f"Cluster: {self.cluster_mode}")
        return "  |  ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in profiles
# ─────────────────────────────────────────────────────────────────────────────

BUILTIN_SITE_PROFILES = [
    SiteProfile(
        name="HomeLab",
        timezone="America/Chicago",
        ntp_servers=["0.pool.ntp.org", "1.pool.ntp.org", "2.pool.ntp.org"],
        dns_servers=["10.0.0.10", "10.0.0.11"],
        dns_search="lab.lameservers.net",
        vlan_management=0,
        vlan_vm=0,
        vlan_storage=0,
        vlan_migration=0,
        vlan_corosync=0,
        mgmt_subnet="10.0.0.0/21",
        firewall_mgmt_cidr="10.0.0.0/21",
        notes="Home lab — flat network, Pi-hole DNS at 10.0.0.10 and 10.0.0.11",
        builtin=True,
    ),
    SiteProfile(
        name="Default (blank template)",
        timezone="UTC",
        ntp_servers=["pool.ntp.org"],
        notes="Blank template — fill in all fields for a new site.",
        builtin=True,
    ),
]

BUILTIN_HOST_PROFILES = [
    HostProfile(
        name="HomeLab Node",
        description="Mac Pro 2014 — dual 1GbE, NFS storage on 10.0.10.0/24",
        nic_roles=[
            NICRoleAssignment(pattern="nic1", role="VM Traffic",  match_by="name"),
            NICRoleAssignment(pattern="nic0", role="Storage",     match_by="name"),
        ],
        disk_roles=[
            DiskRoleAssignment(transport="nvme", is_rotational=False,
                               role="OS Disk (protected)"),
            DiskRoleAssignment(transport="usb",  role="Exclude / Ignore"),
        ],
        vm_bond_mode="active-backup",
        cluster_mode="skip",
        notes="Flat network — no VLANs. nic1 -> vmbr0 (VM/mgmt), nic0 -> vmbr_nfs (storage). All storage via Synology NFS at 10.0.10.7.",
        builtin=True,
    ),
    HostProfile(
        name="Blank Template",
        description="No pre-configured roles — fill in manually",
        builtin=True,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Profile managers
# ─────────────────────────────────────────────────────────────────────────────

class SiteProfileManager:
    def __init__(self):
        self._user: list[SiteProfile] = []
        self._load()

    def _load(self):
        if not SITES_FILE.exists():
            return
        try:
            data = json.loads(SITES_FILE.read_text())
            self._user = [SiteProfile.from_dict(p) for p in data.get("profiles", [])]
        except Exception as e:
            print(f"[SiteProfileManager] load error: {e}")

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"profiles": [p.to_dict() for p in self._user]}
        SITES_FILE.write_text(json.dumps(data, indent=2))

    @property
    def all_profiles(self) -> list[SiteProfile]:
        return BUILTIN_SITE_PROFILES + self._user

    @property
    def profile_names(self) -> list[str]:
        return [p.name for p in self.all_profiles]

    def get(self, name: str) -> Optional[SiteProfile]:
        return next((p for p in self.all_profiles if p.name == name), None)

    def add_or_update(self, profile: SiteProfile):
        builtin_names = {p.name for p in BUILTIN_SITE_PROFILES}
        if profile.name in builtin_names:
            profile.name = f"{profile.name} (custom)"
        profile.builtin = False
        idx = next((i for i, p in enumerate(self._user)
                    if p.name == profile.name), None)
        if idx is not None:
            self._user[idx] = profile
        else:
            self._user.append(profile)
        self.save()

    def delete(self, name: str) -> bool:
        if any(p.name == name for p in BUILTIN_SITE_PROFILES):
            return False
        self._user = [p for p in self._user if p.name != name]
        self.save()
        return True


class HostProfileManager:
    def __init__(self):
        self._user: list[HostProfile] = []
        self._load()

    def _load(self):
        if not HOSTS_FILE.exists():
            return
        try:
            data = json.loads(HOSTS_FILE.read_text())
            self._user = [HostProfile.from_dict(p) for p in data.get("profiles", [])]
        except Exception as e:
            print(f"[HostProfileManager] load error: {e}")

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {"profiles": [p.to_dict() for p in self._user]}
        HOSTS_FILE.write_text(json.dumps(data, indent=2))

    @property
    def all_profiles(self) -> list[HostProfile]:
        return BUILTIN_HOST_PROFILES + self._user

    @property
    def profile_names(self) -> list[str]:
        return [p.name for p in self.all_profiles]

    def get(self, name: str) -> Optional[HostProfile]:
        return next((p for p in self.all_profiles if p.name == name), None)

    def add_or_update(self, profile: HostProfile):
        builtin_names = {p.name for p in BUILTIN_HOST_PROFILES}
        if profile.name in builtin_names:
            profile.name = f"{profile.name} (custom)"
        profile.builtin = False
        idx = next((i for i, p in enumerate(self._user)
                    if p.name == profile.name), None)
        if idx is not None:
            self._user[idx] = profile
        else:
            self._user.append(profile)
        self.save()

    def delete(self, name: str) -> bool:
        if any(p.name == name for p in BUILTIN_HOST_PROFILES):
            return False
        self._user = [p for p in self._user if p.name != name]
        self.save()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Singletons
# ─────────────────────────────────────────────────────────────────────────────

_site_mgr: Optional[SiteProfileManager] = None
_host_mgr: Optional[HostProfileManager] = None

def get_profile_manager() -> SiteProfileManager:
    global _site_mgr
    if _site_mgr is None:
        _site_mgr = SiteProfileManager()
    return _site_mgr

def get_host_profile_manager() -> HostProfileManager:
    global _host_mgr
    if _host_mgr is None:
        _host_mgr = HostProfileManager()
    return _host_mgr
