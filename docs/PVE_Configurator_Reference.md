# PVE Configurator
## Technical Reference & Operations Guide

ProbablyMonsters Infrastructure Team  
Version 5 — Stage 5 Build

---

## Table of Contents

1. [Overview](#1-overview)
2. [Tab 1 — Connect](#2-tab-1--connect)
3. [Tab 2 — Discover](#3-tab-2--discover)
4. [Tab 3 — Network](#4-tab-3--network)
5. [Tab 4 — Storage](#5-tab-4--storage)
6. [Tab 5 — System](#6-tab-5--system)
7. [Tab 6 — Review & Apply](#7-tab-6--review--apply)
8. [Site Profiles](#8-site-profiles)
9. [Host Profiles](#9-host-profiles)
10. [Recommended Workflow](#10-recommended-workflow)
11. [Dependencies & Installation](#11-dependencies--installation)
11. [Appendix A — Fort Worth Lab Environment Reference](#appendix-a--fort-worth-lab-environment-reference)
12. [Appendix B — SSH Command Reference](#appendix-b--ssh-command-reference)

---

## 1. Overview

PVE Configurator is a PyQt6 desktop application built to automate and standardize the provisioning of Proxmox VE (PVE) hosts across ProbablyMonsters infrastructure. It replaces manual, error-prone per-host configuration with a guided, auditable workflow that reads hardware directly from the target host and presents the operator with structured configuration choices.

The tool is designed to work across two phases of infrastructure lifecycle:

- **Initial provisioning** — configuring a fresh PVE node from scratch: network topology, storage pools, system settings, and optionally joining a cluster.
- **Ongoing management** — re-running against existing hosts to audit configuration, apply changes, or onboard a host that was not provisioned through the standard pipeline.

### 1.1 Architecture

The application is structured as a Python package with a clear separation between data models, connectivity, and UI:

| Component | Purpose |
|-----------|---------|
| `core/models.py` | All data classes: NICInfo, DiskInfo, HostInventory, StorageConfig, BondConfig, BridgeConfig, VLANConfig, SiteProfile, HostProfile, NFSShare, ISCSITarget, DesiredConfig. |
| `core/connection.py` | PVEConnection class managing both the Proxmox API (proxmoxer) and SSH (paramiko) sessions. HardwareDiscovery class that interrogates the live host. |
| `core/sites.py` | SiteProfileManager and HostProfileManager — load, save, and manage named configuration profiles stored in `~/.config/pve-configurator/`. |
| `tabs/connect_tab.py` | Tab 1 — host address and credential entry, connection test. |
| `tabs/discovery_tab.py` | Tab 2 — hardware discovery runner and results display. |
| `tabs/network_tab.py` | Tab 3 — NIC role assignment, bond/bridge/VLAN builder, live interfaces preview. |
| `tabs/storage_tab.py` | Tab 4 — local disk assignment, NFS/iSCSI shared storage scanner, command preview. |
| `tabs/system_tab.py` | Tab 5 — repos, time/NTP, DNS, monitoring, security, firewall, users, cluster. |
| `tabs/profile_manager.py` | Profile Manager dialog — create, edit, duplicate, and delete site and host profiles. |
| `main.py` | Main window, tab shell, site/host profile toolbar, entry point. |

### 1.2 Connectivity Model

The tool uses two independent connection channels to the target host:

| Channel | Used For |
|---------|----------|
| Proxmox API (HTTPS port 8006) | Reading node status, CPU/memory info, storage config, network config, PVE version. Applying network and storage changes via PVE's own API. |
| SSH (port 22) | Raw hardware discovery (lsblk, ip link, ethtool, showmount, iscsiadm). Writing config files. Running commands that have no API equivalent. Cluster join operations. |

Both channels are attempted on connect. The tool operates correctly with either one alone — API-only or SSH-only — but full functionality requires both. SSH is the primary channel for hardware discovery; the API is used where it provides richer or more structured data.

---

## 2. Tab 1 — Connect

The Connect tab is the starting point for every session. It establishes connectivity to a target PVE host before any other tab becomes active.

### 2.1 Fields

| Field | Description |
|-------|-------------|
| Host | IP address or hostname of the target PVE node. Example: 10.80.8.11 |
| API Port | Proxmox API port. Default 8006. Only change if PVE has been reconfigured to use a non-standard port. |
| Verify SSL | Whether to validate the PVE API's TLS certificate. Disabled by default because PVE uses a self-signed certificate out of the box. |
| Method | Authentication method: Root Password, API Token (GPG), or SSH Key. Each method controls which credential fields are shown. |

### 2.2 Authentication Methods

#### Root Password

Provides a username (default `root@pam`) and password. The password is used for both the Proxmox API connection and the SSH connection. This is the simplest method and the recommended starting point for fresh hosts that have not yet had SSH keys deployed.

#### API Token (GPG)

Provides a Proxmox API token ID (format: `user@realm!tokenname`) and token secret. The API token is used for the Proxmox API connection only. SSH falls back to password if no key is configured. API tokens are per-user and cluster-wide — create one token on any cluster node and it works across all nodes. Best suited for post-cluster-formation ongoing use.

> **NOTE:** API tokens require `ALLOW_OAUTH2_FOR_EXTERNAL_USERS` to be enabled on the PVE host if the user is an AD/LDAP user. For root@pam this is not required.

#### SSH Key

Provides both a root password (used for the Proxmox API connection, which does not support SSH key auth) and an SSH private key file path (used for all SSH commands). This is the most secure operational mode — the root password is only sent once for the API handshake, and all subsequent shell operations use key-based authentication.

The Browse button opens a file dialog that shows hidden files and directories and defaults to `~/.ssh/`, allowing direct selection of `id_ed25519` or any other private key file.

> **NOTE:** Always select the **private key** (`id_ed25519`), not the public key (`id_ed25519.pub`). Paramiko authenticates using the private key; the public key lives on the server in `~/.ssh/authorized_keys`.

### 2.3 Connection Process

Clicking Connect launches a background thread (ConnectWorker) that attempts both connections concurrently:

1. Proxmox API connection via proxmoxer. On success, resolves the node name by calling `GET /nodes`.
2. SSH connection via paramiko. On success, a persistent SSHClient session is held open for the duration of the session.
3. At least one must succeed for the connection to be considered successful. If both fail, individual error messages for each are displayed in the status log.
4. On success, the Connected Host summary panel appears showing host IP, PVE version (populated after discovery), and the authentication method used.
5. The Discover tab is unlocked and the application automatically advances to it.

### 2.4 SSH Key Setup

For SSH key authentication, the public key must be present in `/root/.ssh/authorized_keys` on the target PVE host before the tool can connect using that method. For fresh hosts, push the key first using password authentication:

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@10.80.8.11
```

This prompts for the root password once and installs the public key. Subsequent connections from the tool can then use SSH Key method.

---

## 3. Tab 2 — Discover

The Discovery tab reads the hardware and current configuration state of the connected host. It is the foundation for all subsequent configuration tabs — no configuration work should begin until discovery has completed successfully.

### 3.1 What Gets Discovered

| Category | Data Collected |
|----------|---------------|
| Hostname | Short hostname (`hostname -s`) and FQDN (`hostname -f`). |
| PVE Version | pve-manager version string and running kernel version via `GET /nodes/{node}/version` or `pveversion` via SSH. |
| CPU & Memory | CPU model, core count, thread count, RAM total via `GET /nodes/{node}/status` or `lscpu`/`free` via SSH. |
| Network Interfaces | All interfaces from `ip -o link show`: name, MAC address, flags, state (UP/DOWN). Virtual interfaces (vmbr*, bond*, veth*) are detected and categorized separately from physical NICs. |
| NIC Speeds | Per-interface ethtool output: Speed (Mb/s), duplex, link detected. Run as a single SSH command across all interfaces for efficiency. |
| Block Devices | `lsblk -d` output: device name, size in bytes (converted to GB/TB), rotational flag, transport (sata/nvme/usb), vendor, model, serial. |
| Partition Detection | Second `lsblk` pass without `-d` flag to identify which whole disks have existing partitions. Disks with partitions receive an orange warning in the Storage tab. |
| PVE VG Detection | `pvs` output cross-referenced against disk names to identify which disk contains the pve volume group (OS disk). That disk is marked protected and excluded from configuration. |
| Current Network Config | `/etc/network/interfaces` parsed to extract the current management IP, prefix length, gateway, and management VLAN ID. |
| PVE Storage Config | `/etc/pve/storage.cfg` read to show existing storage pools. |
| LVM Layout | `vgs`, `pvs`, `lvs` output showing existing volume groups, physical volumes, and logical volumes. |
| ZFS Pools | `zpool list` and `zfs list` output. |
| DNS | `/etc/resolv.conf` parsed for `nameserver` and `search` entries. |
| Timezone | `timedatectl show --property=Timezone` output. |
| NTP Status | `timedatectl` output checked for `NTP service: active`. |
| APT Repositories | `ls /etc/apt/sources.list.d/` checked for `pve-enterprise.sources` presence (flagged in red if found). |
| Cluster Status | `pvecm status` output. Empty = not in a cluster. |

### 3.2 Discovery Process

Clicking **Run Discovery** launches a background thread (DiscoveryWorker) that calls `HardwareDiscovery.discover()` with a progress callback. Each step emits a progress message to the log strip at the bottom of the tab. The steps run sequentially:

1. Resolving hostname
2. Reading PVE version
3. Reading CPU & memory
4. Discovering NICs
5. Discovering disks
6. Reading network config
7. Reading system settings

On completion, the `HostInventory` object is emitted to all subsequent tabs. The status bar updates with the hostname, NIC count, and disk count. All remaining tabs are unlocked.

### 3.3 Results Display

| Area | Contents |
|------|----------|
| Left panel — Host card | Hostname, FQDN, PVE version, CPU model and thread count, RAM. |
| Left panel — Current Network card | Management IP, gateway, and VLAN ID extracted from the running `/etc/network/interfaces`. |
| Left panel — System card | DNS servers, search domain, timezone, NTP status (green = active), repo status (red = enterprise repo detected), cluster status. |
| Right panel — Network Interfaces tree | Physical NICs, WiFi/Excluded, and Virtual (bridges/VLANs) in separate collapsible sections. Each NIC shows name, MAC, speed, state, and suggested role color-coded by role type. |
| Right panel — Block Devices tree | Configurable disks, OS Disk (protected), and USB/Excluded in separate sections. Each disk shows device path, size, type, transport, model, and suggested role. |

### 3.4 Auto-classification

The tool applies heuristic rules to suggest roles for NICs and disks:

| Condition | Suggested Role |
|-----------|---------------|
| NIC speed >= 10GbE | VM Traffic |
| NIC speed <= 1GbE | Management |
| WiFi NIC (wlp*, wlan*) | Exclude / Ignore |
| Virtual interface (vmbr*, bond*, veth*) | Exclude / Ignore |
| Disk on nvme transport in pve VG | OS Disk (protected) |
| Disk on usb transport | Exclude / Ignore |
| Rotational disk (HDD) | Backup Storage (directory) |
| Non-rotational, non-OS disk | VM Images (LVM-thin) |

These suggestions are starting points only. The operator reviews and overrides them in the Network and Storage tabs.

---

## 4. Tab 3 — Network

The Network tab is where the operator defines the complete network topology for the PVE host. It has three resizable sections separated by draggable dividers, and generates a live preview of `/etc/network/interfaces` that updates in real time.

### 4.1 NIC Role Assignment

The top section shows one row per physical NIC (virtual interfaces and WiFi are excluded). Each row displays interface name, speed, state, MAC address, a role dropdown, and an auto-updating description.

Available NIC roles:

| Role | Purpose |
|------|---------|
| Unassigned | Not yet given a role. Will not appear in the interfaces file. |
| Management | Host management traffic. Used for SSH, PVE web UI, AD authentication. Typically 1GbE in simple setups. |
| VM Traffic | Guest VM network traffic. Becomes a member of vmbr0 (VLAN-aware bridge). Typically 10GbE. |
| iSCSI A | iSCSI storage path A. Configured with static IP, no bridge, MTU 9000 (jumbo frames). |
| iSCSI B | iSCSI storage path B. Second path for multipath iSCSI. |
| Corosync | Proxmox cluster heartbeat traffic. Dedicated NIC or VLAN. |
| Migration | VM live migration traffic. High bandwidth, low latency. |
| Exclude / Ignore | NIC will not appear in the generated interfaces file. |

### 4.2 Network Objects

#### Bonds

A bond combines multiple physical NICs into a single logical interface for redundancy or throughput.

| Field | Description |
|-------|-------------|
| Bond name | Linux bond interface name, e.g. bond0, bond1. |
| Mode | `active-backup`: one active NIC, other on standby. `802.3ad` (LACP): both NICs active, requires switch support. `balance-alb`: adaptive load balancing, no switch config needed. |
| MTU | Maximum Transmission Unit. 1500 for standard Ethernet. 9000 for jumbo frames (iSCSI). |
| Member NICs | Checkboxes for each physical NIC. Only NICs assigned the appropriate role should be selected. |

#### Bridges

A bridge connects a NIC or bond to the virtual network layer, allowing VMs to access the network.

| Field | Description |
|-------|-------------|
| Bridge name | PVE bridge name, e.g. vmbr0, vmbr1. |
| Port (NIC or bond) | The physical interface or bond that feeds this bridge. Example: `nic3` or `bond0`. |
| VLAN aware | When enabled, the bridge passes 802.1Q VLAN tags through to VMs. Corresponds to `bridge-vlan-aware yes` in interfaces file. |
| VLAN IDs | Range of VLAN IDs to pass through, e.g. `2-4094`. Only relevant when VLAN aware is enabled. |
| MTU | Bridge MTU. Should match the port MTU. |

#### VLANs / IP Interfaces

A VLAN interface is a sub-interface of a bridge that carries traffic for a specific VLAN and optionally has an IP address assigned to it. This is how the PVE host itself participates in each VLAN.

| Field | Description |
|-------|-------------|
| Interface name | Auto-generated as `parent.vlanid`, e.g. `vmbr0.2008`. Can be overridden. |
| Parent bridge | The bridge this VLAN interface rides on, e.g. `vmbr0`. |
| VLAN ID | The 802.1Q VLAN tag. Changing this auto-updates the interface name. |
| IP address | Static IP for this VLAN on this host. Leave blank for pure VM traffic VLANs. |
| Prefix length | Subnet prefix, e.g. 24 for /24 (255.255.255.0). |
| Gateway | Default gateway. **Only set on the management VLAN.** All other VLANs should have this blank. |
| Role hint | Auto-populated description for known VLANs (2008=Management, 2009=VM Network, 2010=Storage, 2011=Migration, 2012=Corosync). |

### 4.3 Auto-suggest

The **Auto-suggest from roles** button reads the current NIC role assignments and automatically builds a suggested network object structure:

- Two or more VM Traffic NICs → bond0 (802.3ad LACP) → vmbr0 (VLAN-aware, 2-4094)
- One VM Traffic NIC → vmbr0 directly, no bond
- Two or more Management NICs → bond1 (active-backup)
- VLAN interfaces for all five lab VLANs (2008–2012) pre-populated with IPs derived from the discovered management IP host octet

Auto-suggest replaces all existing objects and is intended as a starting point, not an incremental update.

### 4.4 Pre-population from Discovery

When the inventory arrives from Tab 2, the network tab pre-populates with the currently running configuration: existing bridges are added with their current port NIC, and existing VLAN sub-interfaces are added with their current IP, prefix, and gateway.

### 4.5 Lab VLAN Reference

| VLAN | Purpose | Subnet |
|------|---------|--------|
| 2008 | Management — host access, SSH, PVE web UI | 10.80.8.0/24 |
| 2009 | VM Network — guest traffic | 10.80.9.0/24 |
| 2010 | Storage — iSCSI / NFS traffic | 10.80.10.0/24 |
| 2011 | Migration — live VM migration | 10.80.11.0/24 |
| 2012 | Corosync — cluster heartbeat | 10.80.12.0/24 |

### 4.6 Live Interfaces Preview

The bottom section shows `/etc/network/interfaces` exactly as it will be written to the host. It updates in real time. Generated file structure:

1. Loopback stanza (`auto lo` / `iface lo inet loopback`)
2. Manual stanzas for each physical NIC (`iface nicX inet manual`)
3. Bond stanzas with `bond-slaves`, `bond-mode`, `bond-miimon`, optional MTU
4. Bridge stanzas with `bridge-ports`, `bridge-stp off`, `bridge-fd 0`, optional VLAN settings
5. VLAN interface stanzas with static IP, gateway, `vlan-raw-device`
6. `source /etc/network/interfaces.d/*` at the end

---

## 5. Tab 4 — Storage

The Storage tab handles both local disk configuration and shared storage (NFS and iSCSI). It has three resizable sections and a live command preview.

### 5.1 Local Disk Assignment

The top section shows all discovered block devices. Existing data indicators:

| Indicator | Meaning |
|-----------|---------|
| OS disk — protected (blue) | Contains the pve VG. Locked, no commands generated. |
| Has existing partitions (orange) | lsblk detected partitions. Wipe checkbox defaults to OFF. |
| Clean (grey) | No partitions detected. |
| USB / excluded (orange) | USB transport. Defaulted to Exclude and locked. |

### 5.2 Storage Roles

| Role | Description |
|------|-------------|
| OS Disk (protected) | Contains the PVE operating system. No changes made. |
| VM Images (LVM-thin) | Creates an LVM thin-provisioned pool for VM disk images and container filesystems. |
| Backup Storage (directory) | Partitions, formats, and mounts the disk as a directory for vzdump backups, ISOs, and CT templates. |
| ZFS Pool | Creates a ZFS pool using PVE's built-in ZFS support. Supports single, mirror, raidz, raidz2, raidz3. |
| Exclude / Ignore | Disk will not appear in any generated commands. |
| Unassigned | No role chosen yet. |

### 5.3 LVM-thin Configuration

| Field | Description |
|-------|-------------|
| Storage ID | PVE storage pool name. Auto-named `Local-SSD-01`, `Local-SSD-02`, etc. Difficult to rename after VMs reference it — choose carefully. |
| Volume Group | LVM VG name. Auto-named `pve-{storage-id-lowercase}`. Must be unique. |
| Thin pool name | LVM thin pool LV name within the VG. Default: `data`. |
| Pool size | Percentage of VG to allocate to thin pool. Default 95% — leaves ~5% for LVM metadata. |
| Wipe disk | Runs `wipefs -a` before `pvcreate`. Required if disk has been used before. OFF by default. |
| Content types | `images` (VM disk images) and/or `rootdir` (CT filesystems). |

Generated commands:
```bash
wipefs -a /dev/sdX                          # if wipe enabled
pvcreate /dev/sdX
vgcreate pve-local-ssd-01 /dev/sdX
lvcreate -l 95%FREE -T pve-local-ssd-01/data
pvesm add lvmthin Local-SSD-01 --vgname pve-local-ssd-01 --thinpool data --content images,rootdir
```

### 5.4 Backup Directory Configuration

| Field | Description |
|-------|-------------|
| Storage ID | PVE storage name. Auto-named `Backup-HDD-01`, etc. |
| Mount point | Where the disk will be mounted. Auto-named `/mnt/pve/{storage-id-lowercase}`. |
| Filesystem | `ext4` (default) or `xfs`. |
| Wipe disk | Runs `wipefs -a` before partitioning. OFF by default. |
| Content types | Typically: `backup`, `iso`, `vztmpl`. |

Generated commands:
```bash
wipefs -a /dev/sdX                          # if wipe enabled
parted -s /dev/sdX mklabel gpt
parted -s /dev/sdX mkpart primary 0% 100%
mkfs.ext4 /dev/sdX1
mkdir -p /mnt/pve/backup-hdd-01
echo '/dev/sdX1  /mnt/pve/backup-hdd-01  ext4  defaults  0  2' >> /etc/fstab
mount /mnt/pve/backup-hdd-01
pvesm add dir Backup-HDD-01 --path /mnt/pve/backup-hdd-01 --content backup,iso,vztmpl
```

### 5.5 ZFS Pool Configuration

| Field | Description |
|-------|-------------|
| Storage ID | PVE storage name. Auto-named `ZFS-Pool-01`, etc. |
| ZFS pool name | The ZFS pool name, e.g. `tank`. |
| RAID level | `single` (no redundancy), `mirror` (RAID-1), `raidz` (RAID-5), `raidz2` (RAID-6), `raidz3` (triple parity). |
| Wipe disk | Runs `wipefs -a` before `zpool create`. OFF by default. |

### 5.6 Shared Storage — NFS

Process:
1. Enter the NAS IP address and click **Scan for exports**.
2. The tool runs `showmount -e {ip} --no-headers` via SSH on the PVE host. Connectivity is tested from the PVE node, not the operator's workstation.
3. Discovered exports appear with **+ Add** buttons.
4. Click **+ Add** to create a configured NFS share entry.
5. Click a configured share to set Storage ID, mount point, and content types.

Generated command:
```bash
pvesm add nfs NAS-Backup --server 10.80.10.50 --export /volume1/backups --content backup,iso,vztmpl
```

### 5.7 Shared Storage — iSCSI

Process:
1. Enter the target portal IP and click **Discover targets**.
2. The tool runs `iscsiadm -m discovery -t sendtargets -p {ip}` via SSH on the PVE host.
3. Discovered IQNs appear with **+ Add** buttons.
4. Each added target can optionally have an LVM-thin layer created on top of it — the standard PVE pattern for iSCSI VM image storage.

Generated commands (with LVM on top):
```bash
pvesm add iscsi iSCSI-SAN-01 --portal 10.80.10.50 --target iqn.2024-01.com.example:storage --content none
# After iSCSI device appears:
pvesm add lvmthin iSCSI-LVM-01 --vgname pve-iscsi-lvm-01 --thinpool data --content images,rootdir
```

### 5.8 Content Type Reference

| Content Type | Description |
|-------------|-------------|
| `images` | VM disk images (.qcow2, .raw, .vmdk). Required for VM storage pools. |
| `rootdir` | Container (LXC) filesystem storage. Required for CT storage pools. |
| `backup` | vzdump backup archives (.vma, .tar.zst). Backup storage only. |
| `iso` | ISO disc images for VM OS installation. |
| `vztmpl` | LXC container templates. |
| `snippets` | Hook scripts and cloud-init configuration snippets. |

---

## 6. Tab 5 — System

The System tab configures host-level settings: repositories, time and NTP, DNS, monitoring, security hardening, firewall, local users, and cluster membership. A live command preview at the bottom shows all commands that will be executed.

### 6.1 Repository Management

| Option | Action |
|--------|--------|
| Disable enterprise repository | Renames `/etc/apt/sources.list.d/pve-enterprise.sources` to `.disabled`. |
| Enable no-subscription repository | Creates `/etc/apt/sources.list.d/pve-no-subscription.list`. |
| Enable Ceph no-subscription repository | Adds the Ceph no-subscription repo. Only needed for hyper-converged setups. |
| Remove subscription nag | Patches `/usr/share/perl5/PVE/API2/Subscription.pm` to return Active status. Restarts pveproxy. |
| Run apt-get update | Refreshes the package cache after repo changes. |

> **⚠ WARNING:** The subscription nag removal patches a Perl file that may be overwritten after a PVE update. Re-running the tool re-applies it.

### 6.2 Time & NTP

| Field | Description |
|-------|-------------|
| Timezone | Sets system timezone via `timedatectl set-timezone`. Pre-populated from active site profile. |
| NTP servers | Comma-separated list written to `/etc/chrony/chrony.conf`. AD DCs recommended as primary sources. Kerberos (AD auth) fails if clock skew exceeds ~5 minutes. |

Fort Worth site NTP servers: `10.80.0.5` (primary DC), `10.80.0.6` (secondary DC), `pool.ntp.org` (fallback).

Generated Chrony configuration:
```
server 10.80.0.5 iburst
server 10.80.0.6 iburst
server pool.ntp.org iburst
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
```

### 6.3 DNS

Writes `/etc/resolv.conf` with the specified nameservers and search domain. Both fields are pre-populated from the active site profile.

Fort Worth: DNS `10.80.0.5`, `10.80.0.6`. Search domain: `probablymonsters.com`.

### 6.4 Remote Logging & Monitoring

#### prometheus-node-exporter

Installs and enables the Prometheus node exporter, exposing OS-level metrics (CPU, memory, disk I/O, network) on port 9100 at `/metrics`. Configuration is on the Prometheus server side — no server URL needed on the PVE host.

#### PVE Metrics Endpoint

Enables PVE's built-in Prometheus metrics endpoint on port 8006 at `/metrics`. Exposes PVE-specific metrics: VM status, storage usage, cluster state, backup status. Requires authentication.

#### Promtail

Installs and configures Promtail to ship `/var/log/*.log` to Loki.

If the Loki URL field is left blank, Promtail is installed with a placeholder URL (`http://LOKI-SERVER:3100`). When the Loki server is ready, update `/etc/promtail/config.yml` and restart — no re-provisioning needed.

> **NOTE:** A ready-to-use `prometheus.yml` scrape config snippet is generated in the command preview. Save this for use when the monitoring stack is stood up.

### 6.5 Security Hardening

#### fail2ban

Installs fail2ban with SSH jail configuration:
- `maxretry = 5` — ban after 5 failed attempts
- `bantime = 3600` — 1 hour ban duration
- `findtime = 600` — 10 minute counting window

Monitors `/var/log/auth.log` and bans offending IPs via iptables.

#### SSH PermitRootLogin prohibit-password

Sets `PermitRootLogin prohibit-password` in `/etc/ssh/sshd_config`. Allows root SSH via key authentication, blocks password-based root login. Full root SSH disable would break PVE cluster operations.

#### Unattended Security Updates

Configures `unattended-upgrades` for Debian security patches only. Explicitly excluded packages:
- `proxmox-ve`
- `pve-*`
- `ceph*`
- `linux-image*`
- `linux-headers*`

Automatic reboots are disabled. PVE and kernel updates must be applied manually after review.

#### Log Rotation Verification

Runs `logrotate --debug /etc/logrotate.conf` to verify log rotation is operational. Output shown in command preview. Catches cases where `/var/log` could fill the OS disk.

### 6.6 PVE Datacenter Firewall

Enables PVE's built-in firewall at the datacenter level, applying to all cluster nodes. Configuration written to `/etc/pve/firewall/cluster.fw`.

Default ruleset (operator specifies trusted management CIDR):

| Rule | Description |
|------|-------------|
| IN ACCEPT TCP 22 from mgmt CIDR | SSH from trusted management subnet only. |
| IN ACCEPT TCP 8006 from mgmt CIDR | PVE web UI from trusted management subnet only. |
| IN ACCEPT TCP 3128 from mgmt CIDR | SPICE proxy for VM console. |
| IN ACCEPT TCP 5900-5999 from mgmt CIDR | VNC console range. |
| IN ACCEPT UDP 5405 | Corosync cluster heartbeat — all sources. |
| IN DROP (logged) | All other inbound traffic dropped and logged. |

Fort Worth management CIDR: `10.80.8.0/24`.

> **⚠ WARNING:** The PVE firewall and fail2ban are complementary. The firewall restricts which IPs reach which ports. fail2ban bans IPs making too many failed authentication attempts on allowed ports.

### 6.7 Local User Account

| Field | Description |
|-------|-------------|
| Username | Created with `useradd -m -s /bin/bash`. |
| SSH public key | Written to `~/.ssh/authorized_keys` for the new user. |
| Grant passwordless sudo | Creates `/etc/sudoers.d/{username}` with `NOPASSWD:ALL`. |

### 6.8 Cluster Configuration

#### Skip
No cluster configuration. Host remains standalone.

#### Create New Cluster

| Field | Description |
|-------|-------------|
| Cluster name | Cluster identifier, e.g. `lab-cluster-01`. Cannot be changed after creation. |
| Ring 0 IP | Corosync IP for this node. Should be the Corosync VLAN IP (10.80.12.x). |

```bash
pvecm create lab-cluster-01 --link0 10.80.12.11
```

#### Join Existing Cluster

| Field | Description |
|-------|-------------|
| Existing node IP | IP of any node already in the cluster. |
| Root password | Root password of the existing cluster node, required by `pvecm add`. |

**Run pre-checks** verifies before join:
- NTP sync (`chronyc tracking`) — cluster join fails if clock skew > ~5 seconds
- Network interface check — confirms IPs assigned
- Corosync reachability — pings the target node
- Cluster status — confirms this node is not already in a cluster

> **⚠ WARNING:** Never attempt a cluster join without running pre-checks first. A failed or partial join can leave the cluster in a degraded state.

---

## 7. Tab 6 — Review & Apply

The Review & Apply tab is where all configuration from the previous tabs is assembled into an ordered execution plan and applied to the host. It is the only tab that makes changes to the target system.

### 7.1 Auto-sync

Switching to the Review & Apply tab automatically pulls the current state from all other tabs — network config, storage config, and system settings — and rebuilds the command list. The list is always current; there is no manual refresh needed unless you switch back to another tab and make additional changes, in which case the Refresh button re-syncs.

### 7.2 Summary Cards

Eight color-coded cards at the top show how many commands will run in each section:

| Section | Color | Contents |
|---------|-------|----------|
| Repositories | Blue | Repo enable/disable, apt-get update |
| Packages | Blue | apt-get install, service enables, config files |
| System | Purple | Timezone, NTP, DNS, SSH hardening |
| Storage | Orange | wipefs, pvcreate, mkfs, mount, pvesm add |
| Network | Green | Write interfaces file, validate, ifreload |
| PVE Settings | Blue | Firewall, metrics endpoint, nag removal |
| Users | Purple | useradd, sudo, SSH key installation |
| Cluster | Red | pvecm create or pvecm add |

### 7.3 Command Tree

The full ordered command list is displayed as a tree showing sequence number, section, human-readable description, and a truncated version of the shell command. After apply completes, each row receives a ✓ (green) or ✗ (red) indicator.

### 7.4 Confirmation Checkboxes

The Apply button remains disabled until all three boxes are checked:

- **I have reviewed all commands** — operator confirms they have read the command list.
- **I understand network changes may interrupt connectivity** — acknowledges that `ifreload` may briefly drop SSH, and the tool will reconnect automatically.
- **Configuration files will be backed up** — acknowledges that backups are created before changes.

### 7.5 Apply Order

Commands execute in this fixed order regardless of which tabs have changes:

1. **Backups** — copies of `/etc/network/interfaces`, `/etc/resolv.conf`, `/etc/chrony/chrony.conf`, and `/etc/pve/storage.cfg` with timestamps
2. **Repositories** — disable enterprise, enable no-subscription, apt-get update
3. **Packages** — all apt-get installs, service enables, config file writes
4. **System Settings** — timezone, NTP, DNS, SSH hardening, log rotation check
5. **Storage** — wipefs, pvcreate/vgcreate/lvcreate, mkfs, fstab, mount, pvesm add, NFS/iSCSI
6. **Network** — write interfaces file, validate with `ifup --no-act`, apply with `ifreload -a`
7. **PVE Settings** — firewall rules, metrics endpoint, subscription nag removal
8. **Users** — useradd, sudo config, SSH key installation
9. **Cluster** — pvecm create or pvecm add (always last)

Network is applied second-to-last so that all packages and services are in place before the network changes. Cluster is always absolute last because a partial cluster join is difficult to recover from.

### 7.6 Network Apply Safety

Network changes are the most dangerous part of any PVE provisioning operation because a misconfigured interfaces file can make the host unreachable. The tool handles this as follows:

1. The new interfaces content is written to `/etc/network/interfaces`.
2. `ifup --no-act -a` validates the config without applying it. A non-zero exit is logged but does not stop apply (some warnings are harmless).
3. `ifreload -a` applies the config atomically. PVE's `ifreload` rolls back if the new config fails to come up.
4. After `ifreload`, the apply engine waits up to 30 seconds and attempts to reconnect SSH (6 attempts, 5 seconds apart).
5. If SSH reconnects successfully, apply continues normally.
6. If SSH cannot reconnect within 30 seconds, apply halts with a clear error. The host may be in a degraded state and requires manual investigation.

> **⚠ WARNING:** If the management IP or VLAN changes as part of the network apply, SSH will reconnect to the new IP. Ensure the new IP is reachable from the operator workstation before applying.

### 7.7 Critical vs Non-critical Commands

Each command is flagged as critical or non-critical:

- **Critical** (default) — a non-zero exit code stops the entire apply immediately. The operator sees the error, exit code, and stderr output. No further commands run.
- **Non-critical** — failures are logged in orange and execution continues. Used for commands where failure is expected or recoverable (e.g., backup copies, log rotation check, PVE metrics endpoint).

### 7.8 Progress Log

The progress log streams live output from every command:

- Section headers in section color
- `$` prefix lines show the command being run (truncated to 120 characters)
- stdout in white
- stderr in orange (non-critical failure) or red (critical failure)
- ✓ OK or ✗ FAILED with elapsed time after each command

### 7.9 Post-apply Actions

After apply completes, two buttons appear:

- **Re-discover host** — switches to Tab 2 and re-runs discovery against the host. This confirms the final state matches intent — NICs are up, storage pools exist, cluster membership is correct.
- **Save log** — saves the complete apply log to a timestamped file (`pve_apply_{hostname}_{datetime}.log`). Recommended for audit trail, especially for production provisioning.

---

## 8. Site Profiles

Site profiles capture location-specific configuration common to all hosts at a given site. Selecting a site profile in the toolbar auto-populates the System tab.

### 8.1 Site Profile Fields

| Field | Description |
|-------|-------------|
| Profile name | Display name in the toolbar dropdown. |
| Timezone | IANA timezone string, e.g. `America/Chicago`. |
| NTP servers | Ordered list. AD DCs first, public pool as fallback. |
| DNS servers | Ordered list of DNS server IPs. AD DCs recommended. |
| DNS search domain | Domain appended to unqualified hostnames. |
| AD domain | Active Directory domain for reference. |
| VLANs | Management, VM, Storage, Migration, Corosync VLAN IDs. 0 = not configured. |
| Management subnet | CIDR of management subnet, e.g. `10.80.8.0/24`. |
| Firewall CIDR | Trusted CIDR for firewall rules. Usually same as management subnet. |
| Loki URL | Loki endpoint. Leave blank until monitoring stack is ready. |
| Prometheus URL | Prometheus server URL. Leave blank until ready. |
| Notes | Free-text notes. |

### 8.2 Built-in Site Profiles

| Profile | Pre-configured Values |
|---------|----------------------|
| Fort Worth | Timezone: America/Chicago. NTP: 10.80.0.5, 10.80.0.6, pool.ntp.org. DNS: 10.80.0.5, 10.80.0.6. Search: probablymonsters.com. VLANs: 2008/2009/2010/2011/2012. Mgmt: 10.80.8.0/24. |
| Seattle | Timezone: America/Los_Angeles. NTP: pool.ntp.org. DNS/VLANs: TBD. |
| Default (blank template) | Timezone: UTC. NTP: pool.ntp.org. All other fields blank. |

### 8.3 Saving a Site Profile

Click **💾 Save as site profile…** in the System tab title row. Prompts for a profile name. Built-in profiles cannot be overwritten — saved copies with conflicting names get a `(custom)` suffix.

Profiles are stored in `~/.config/pve-configurator/sites.json`. This file is not tracked by version control and should be backed up separately.

---

## 9. Host Profiles

Host profiles capture hardware-topology and system-option patterns common across a class of servers. They complement site profiles — a site profile says *where*, a host profile says *what kind*.

### 9.1 Host Profile Fields

| Field | Description |
|-------|-------------|
| Profile name | Display name in the toolbar dropdown. |
| Description | Brief description of this host type. |
| VM traffic bond mode | `802.3ad` (LACP, requires switch config) or `active-backup`. |
| Management bond mode | `active-backup` recommended. |
| VLAN-aware bridge | Whether vmbr0 should be VLAN-aware. Almost always yes. |
| System options | Checkboxes for fail2ban, SSH prohibit-password, unattended upgrades, firewall, node-exporter, Promtail, repo management. |
| Default cluster mode | `skip`, `create`, or `join`. |
| Notes | Free-text notes. |

### 9.2 Built-in Host Profiles

| Profile | Intended Use |
|---------|-------------|
| Standard Compute Node | Single 10GbE NIC trunk to vmbr0. All VLANs on top. NVMe as OS disk, SATA HDD as backup storage. Typical lab/edge node. |
| Bonded Compute Node | Two 10GbE NICs bonded (LACP) for VM traffic, two 1GbE bonded (active-backup) for management. Production compute node pattern. |
| Storage Node | Bonded 10GbE for VM traffic, dedicated management bond, multiple SSD pools and HDD backup storage. |
| Blank Template | No pre-configured roles. All system options enabled. Starting point for custom types. |

### 9.3 Profile Manager

Opened via the **Manage Profiles…** toolbar button. Two tabs: Site Profiles and Host Profiles.

- Built-in profiles shown in blue — read-only, cannot be deleted.
- **Duplicate** creates an editable copy with `(copy)` appended.
- **+ New** creates a blank profile.
- User-defined profiles can be edited and saved.
- User-defined profiles can be deleted (confirmation required).

---

## 10. Recommended Workflow

### 10.1 Pre-provisioning Checklist

1. PVE 9.x installed on the host from the official ISO.
2. Host reachable on the management network.
3. Root password known.
4. SSH key pushed to `root@{host-ip}` if using SSH Key authentication (optional but recommended).
5. Correct **site profile** selected in the toolbar.
6. Correct **host profile** selected in the toolbar.

### 10.2 Step-by-Step

1. **Tab 1 — Connect:** Enter host IP, select auth method, click Connect. Verify Connected Host summary shows correct hostname.
2. **Tab 2 — Discover:** Click Run Discovery. Review NIC, disk, and system findings. Verify OS disk is correctly identified. Verify NIC speeds are correct.
3. **Tab 3 — Network:** Review auto-assigned NIC roles. Adjust if needed. Add/modify bonds and bridges per host profile. Add VLAN interfaces for all required VLANs. Verify the live interfaces preview matches intent.
4. **Tab 4 — Storage:** Review disk assignments. Configure each configurable disk with role, Storage ID, and content types. Add NFS or iSCSI shared storage if applicable. Verify command preview.
5. **Tab 5 — System:** Verify site profile is active. Check timezone, NTP, DNS. Review security options. Set firewall management CIDR. Configure cluster action. If joining, run pre-checks first.
6. **Tab 6 — Review & Apply**: Click Refresh to sync all tab configurations. Review summary cards and full command list. Check all three confirmation boxes. Click Apply Now. Monitor the progress log. On completion, click Re-discover host to verify final state.

### 10.3 Lab Cluster Build Sequence

For building the three-node Fort Worth lab cluster (210pve001, 210pve002, 210pve003):

1. Provision **210pve001** with cluster mode = **Create**. Cluster name: `lab-cluster-01`. Ring 0 IP: `10.80.12.11`.
2. Provision **210pve002** with cluster mode = **Join**. Existing node IP: `10.80.8.11`. Run pre-checks. Apply.
3. Provision **210pve003** with cluster mode = **Join**. Existing node IP: `10.80.8.11` (or any cluster member). Run pre-checks. Apply.
4. Verify from any node: `pvecm status` should show 3 nodes, quorum met.

---

## 11. Dependencies & Installation

### 11.1 Python Dependencies

| Package | Purpose |
|---------|---------|
| `PyQt6 >= 6.5` | Desktop GUI framework. All UI components. |
| `proxmoxer >= 2.0` | Proxmox VE API client. |
| `paramiko >= 3.0` | SSH client library. |
| `requests >= 2.31` | HTTP library. Used by proxmoxer. |
| `urllib3 >= 2.0` | HTTP connection pooling. |

### 11.2 Installation

```bash
cd pve_configurator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The tool uses `.venv` (not `venv`) consistently across all projects.

### 11.3 Target Host Requirements

| Requirement | Notes |
|-------------|-------|
| Proxmox VE 9.x | Tested on 9.2.2. |
| SSH access as root | Port 22 must be reachable from the operator workstation. |
| `showmount` (nfs-common) | For NFS scanning. Install: `apt-get install nfs-common` |
| `iscsiadm` (open-iscsi) | For iSCSI discovery. Install: `apt-get install open-iscsi` |
| `ethtool` | NIC speed detection. Usually pre-installed. |
| `chrony` | NTP. Pre-installed on PVE. |

### 11.4 Version Control

Excluded from version control (`.gitignore`):
- `.venv/` — Python virtual environment
- `__pycache__/` — compiled bytecode
- `~/.config/pve-configurator/` — site and host profiles
- `*.gpg`, `*.asc` — encrypted credential files

---

## Appendix A — Fort Worth Lab Environment Reference

| Item | Value |
|------|-------|
| Management VLAN | 2008 |
| VM Network VLAN | 2009 |
| Storage VLAN | 2010 |
| Migration VLAN | 2011 |
| Corosync VLAN | 2012 |
| Management subnet | 10.80.8.0/24 |
| DC / DNS / NTP primary | 10.80.0.5 |
| DC / DNS / NTP secondary | 10.80.0.6 |
| AD domain | probablymonsters.com |
| Timezone | America/Chicago (CDT/CST) |
| Lab node 1 | 210pve001 — 10.80.8.11 |
| Lab node 2 | 210pve002 — TBD |
| Lab node 3 | 210pve003 — TBD |
| Cluster name | lab-cluster-01 (planned) |
| Firewall trusted CIDR | 10.80.8.0/24 |

---

## Appendix B — SSH Command Reference

Key SSH commands used by the tool during discovery:

| Command | Purpose |
|---------|---------|
| `hostname -f` | Resolve FQDN. |
| `pveversion` | PVE version string. |
| `lscpu` | CPU model and core count. |
| `free -b` | Memory total in bytes. |
| `ip -o link show` | All network interfaces and flags. |
| `ethtool {iface}` | NIC speed, duplex, link state. |
| `lsblk -d --bytes` | Whole disk inventory with sizes. |
| `lsblk -o NAME,TYPE` | Disk/partition type tree for has_partitions detection. |
| `pvs --noheadings -o pv_name` | Physical volumes — identifies OS disk. |
| `cat /etc/network/interfaces` | Current network configuration. |
| `cat /etc/resolv.conf` | DNS configuration. |
| `timedatectl show` | Timezone and NTP status. |
| `ls /etc/apt/sources.list.d/` | Repo file list — enterprise repo detection. |
| `pvecm status` | Cluster membership status. |
| `showmount -e {ip}` | NFS export enumeration. |
| `iscsiadm -m discovery -t sendtargets -p {ip}` | iSCSI target discovery. |
| `chronyc tracking` | NTP sync status for cluster pre-check. |
| `ping -c 2 {ip}` | Cluster node reachability check. |
