# PVE Configurator

A PyQt6 desktop application for guided, auditable provisioning of Proxmox VE hosts. Reads hardware directly from the target host and walks the operator through network topology, storage configuration, system settings, and cluster membership — generating exact commands and applying them with live progress reporting.

---

## Features

- **Hardware discovery** — connects to a live PVE host via API and SSH, reads NICs, disks, current network config, DNS, NTP, repo status, and cluster membership
- **Network configuration** — NIC role assignment, bond/bridge/VLAN builder with live `/etc/network/interfaces` preview
- **Storage configuration** — LVM-thin pools, backup directories, ZFS pools, NFS and iSCSI shared storage scanner
- **System configuration** — repository management, NTP/DNS, monitoring, fail2ban, PVE firewall, unattended security updates, local user creation, cluster create/join with pre-checks
- **Site profiles** — named per-location configurations (timezone, DNS, NTP, VLANs, firewall CIDR, NAS IP) that auto-populate all tabs
- **Host profiles** — named per-server-class configurations (NIC/disk role patterns, system options) for consistent provisioning across identical hardware
- **Command preview** — every tab shows the exact commands that will run before anything is applied
- **Review & Apply** — full ordered command list with confirmation checkboxes, live execution with streaming output, network reconnect verification, re-apply without restart, and post-apply re-discovery

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
git clone <repo-url>
cd pve_configurator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

---

## Usage

### 1. Connect
Enter the host IP or hostname, select an authentication method (Root Password, API Token, or SSH Key), and click **Connect**. The tool attempts both the Proxmox API (port 8006) and SSH simultaneously.

For SSH Key authentication, push your public key to the host first:
```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@<host-ip>
```

### 2. Discover
Click **Run Discovery** to read the host's hardware and current configuration. NIC roles are automatically assigned from the active host profile, and network bridges are auto-suggested. Review before proceeding.

### 3. Network
NIC roles are pre-assigned from the host profile. Bonds, bridges, and VLAN interfaces are auto-generated. The `/etc/network/interfaces` preview updates live. Adjust as needed before applying.

### 4. Storage
Assign roles to configurable disks and configure each one. The NAS IP is pre-populated from the site profile. Use the **NFS** and **iSCSI** tabs to scan for and add shared storage.

### 5. System
Configure repositories, NTP, DNS, monitoring, security hardening, the PVE datacenter firewall, and cluster membership. All fields pre-populate from the active site profile.

### 6. Review & Apply
Review all planned changes organized by section. Check the confirmation boxes, then click **Apply Now**. The tool executes commands in order via SSH with live streaming output. After network changes, SSH reconnection is verified automatically. Use **Re-apply** if needed without restarting the app.

---

## Site & Host Profiles

The toolbar at the top of the window has two dropdowns and a **Manage Profiles…** button.

**Site profiles** capture location-specific settings shared across all hosts at a site: timezone, DNS servers, NTP servers, VLAN IDs, management subnet, NAS IP, and monitoring endpoints.

**Host profiles** capture hardware-pattern settings for a class of servers: NIC role defaults by name or speed, disk role defaults, and which system options to enable.

User-defined profiles are saved to `~/.config/pve-configurator/sites.json` and `hosts.json`. These files are not tracked by version control.

---

## Apply Engine

The apply engine builds a fully ordered command list from all tab configurations and executes it safely:

- **Apply order** — Backups → Repos → Packages → System Settings → Storage → Network → PVE Settings → Users → Cluster
- **Pre-apply backups** — key config files are backed up with timestamps before any changes
- **Network safety** — network changes use `ifreload -a` with diff-based idempotency; skips apply if config is unchanged
- **Critical commands** — any command flagged critical that returns a non-zero exit code stops the apply immediately
- **Re-apply** — failed or partial applies can be retried without restarting the app
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

These files contain infrastructure-specific information and are intentionally excluded from version control.
