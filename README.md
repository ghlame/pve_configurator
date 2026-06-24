# PVE Configurator

A PyQt6 desktop application for guided, auditable provisioning of Proxmox VE hosts. Reads hardware directly from the target host and walks the operator through network topology, storage configuration, system settings, and cluster membership — generating exact commands and applying them with live progress reporting.

Built for the ProbablyMonsters infrastructure team to standardize PVE node provisioning across multiple sites and server classes.

---

## Features

- **Hardware discovery** — connects to a live PVE host via API and SSH, reads NICs, disks, current network config, DNS, NTP, repo status, and cluster membership
- **Network configuration** — NIC role assignment, bond/bridge/VLAN builder with live `/etc/network/interfaces` preview
- **Storage configuration** — LVM-thin pools, backup directories, ZFS pools, NFS and iSCSI shared storage scanner
- **System configuration** — repository management, NTP/DNS, Promtail/node-exporter monitoring, fail2ban, PVE firewall, unattended security updates, local user creation, cluster create/join with pre-checks
- **Site profiles** — named per-location configurations (timezone, DNS, NTP, VLANs, firewall CIDR) that auto-populate all tabs
- **Host profiles** — named per-server-class configurations (NIC/disk role patterns, system options) for consistent provisioning across identical hardware
- **Command preview** — every tab shows the exact commands that will run before anything is applied
- **Review & Apply** — full ordered command list with confirmation checkboxes, live execution with streaming output, network reconnect verification, and post-apply re-discovery

---

## Requirements

**Operator workstation (where the tool runs):**
- Linux (developed and tested on Linux Mint 22.3)
- Python 3.12+
- PyQt6

**Target PVE hosts:**
- Proxmox VE 9.x (tested on 9.2.2)
- SSH access as root (port 22)
- `ethtool` (usually pre-installed)
- `nfs-common` for NFS scanning: `apt-get install nfs-common`
- `open-iscsi` for iSCSI discovery: `apt-get install open-iscsi`

---

## Installation

```bash
git clone git@github.com:jaysellers/pve-configurator.git
cd pve-configurator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Usage

### 1. Connect
Enter the host IP, select an authentication method (Root Password, API Token, or SSH Key), and click **Connect**. The tool attempts both the Proxmox API (port 8006) and SSH simultaneously.

For SSH Key authentication, push your public key to the host first:
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@10.80.8.11
```

### 2. Discover
Click **Run Discovery** to read the host's hardware and current configuration. Review the results — NICs, disks, current network config, and system state — before proceeding.

### 3. Network
Assign roles to each physical NIC (VM Traffic, Management, iSCSI, Corosync, etc.), then build bonds, bridges, and VLAN interfaces. The `/etc/network/interfaces` preview updates live as you make changes. Use **Auto-suggest from roles** to generate a starting configuration automatically.

### 4. Storage
Assign roles to configurable disks (LVM-thin, Backup Directory, ZFS Pool) and configure each one. Use the **NFS** and **iSCSI** tabs to scan for and add shared storage from a NAS or SAN.

### 5. System
Configure repositories, NTP, DNS, monitoring (Promtail + node-exporter), security hardening (fail2ban, SSH hardening, unattended upgrades), the PVE datacenter firewall, and cluster membership. Use **Run pre-checks** before any cluster join operation.

### 6. Review & Apply
Review all planned changes organized by section (Repos, Packages, System, Storage, Network, PVE, Users, Cluster). Check all three confirmation boxes, then click **Apply Now**. The tool executes commands in the correct order via SSH with live streaming output. After network changes, SSH reconnection is verified automatically. On completion, click **Re-discover host** to confirm the final state.

---

## Site & Host Profiles

The toolbar at the top of the window has two dropdowns and a **Manage Profiles…** button.

**Site profiles** capture location-specific settings shared across all hosts at a site: timezone, DNS servers, NTP servers, VLAN IDs, management subnet, and monitoring endpoints.

**Host profiles** capture hardware-pattern settings for a class of servers: NIC role defaults, bond modes, storage role defaults, and which system options to enable.

Built-in profiles:

| Type | Profile | Description |
|------|---------|-------------|
| Site | Fort Worth | America/Chicago, DCs at 10.80.0.5/10.80.0.6, VLANs 2008–2012 |
| Site | Seattle | America/Los_Angeles, VLANs/IPs TBD |
| Site | Default | Blank template |
| Host | Standard Compute Node | Single 10GbE trunk, all VLANs on vmbr0 |
| Host | Bonded Compute Node | LACP bond for VM traffic, active-backup for management |
| Host | Storage Node | Multiple SSD pools, HDD backup storage |
| Host | Blank Template | No pre-configured roles |

User-defined profiles are saved to `~/.config/pve-configurator/sites.json` and `hosts.json`. These files are not tracked by version control.

---

## Apply Engine

The apply engine builds a fully ordered command list from all tab configurations and executes it safely:

- **Apply order** — Backups → Repos → Packages → System Settings → Storage → Network → PVE Settings → Users → Cluster
- **Pre-apply backups** — `/etc/network/interfaces`, `/etc/resolv.conf`, `/etc/chrony/chrony.conf`, and `/etc/pve/storage.cfg` are backed up with timestamps before any changes
- **Network safety** — network changes use `ifreload -a` for atomic apply; the engine verifies SSH reconnection within 30 seconds and halts if connectivity is lost
- **Critical commands** — any command flagged critical that returns a non-zero exit code stops the apply immediately with a clear error message
- **Apply log** — the full timestamped log can be saved after apply completes

---

## Project Structure

```
pve_configurator/
├── main.py                   # Entry point, main window, toolbar
├── requirements.txt
├── README.md
├── core/
│   ├── models.py             # Data classes (NICInfo, DiskInfo, StorageConfig, etc.)
│   ├── connection.py         # PVEConnection (API + SSH) and HardwareDiscovery
│   ├── sites.py              # Site and host profile managers
│   └── apply_engine.py       # CommandBuilder and ApplyWorker
└── tabs/
    ├── connect_tab.py        # Tab 1: Connect
    ├── discovery_tab.py      # Tab 2: Discover
    ├── network_tab.py        # Tab 3: Network
    ├── storage_tab.py        # Tab 4: Storage
    ├── system_tab.py         # Tab 5: System
    ├── review_apply_tab.py   # Tab 6: Review & Apply
    └── profile_manager.py    # Profile Manager dialog
```

---

## Configuration Files

| File | Location | Contents |
|------|----------|----------|
| Site profiles | `~/.config/pve-configurator/sites.json` | User-defined site profiles |
| Host profiles | `~/.config/pve-configurator/hosts.json` | User-defined host profiles |

These files contain infrastructure-specific information (IP addresses, domain names, VLAN IDs) and are intentionally excluded from version control.

---

## Documentation

Full technical reference covering every tab, field, and generated command:

- `docs/PVE_Configurator_Reference.md` — Markdown version
- `docs/PVE_Configurator_Reference.docx` — Word version

---

## Build Stages

| Stage | Contents | Status |
|-------|----------|--------|
| 1 | Connect + Discover tabs | ✅ Complete |
| 2 | Network tab | ✅ Complete |
| 3 | Storage tab (local + NFS/iSCSI) | ✅ Complete |
| 4 | System tab + site profiles | ✅ Complete |
| 5 | Host profiles + Profile Manager | ✅ Complete |
| 6 | Review & Apply tab + apply engine | ✅ Complete |

---

## Lab Environment Reference



---

## License

Internal tooling — LameServers use only.
