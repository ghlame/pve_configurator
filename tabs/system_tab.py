"""
Tab 5: System Configuration
Repos, time/NTP, DNS, remote logging, monitoring, security hardening,
firewall, local users, and cluster join/create.
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QLineEdit, QInputDialog,
    QCheckBox, QTextEdit, QSpinBox, QScrollArea, QFrame,
    QRadioButton, QButtonGroup, QSizePolicy, QSplitter,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from core.models import HostInventory
from core.connection import PVEConnection
from core.sites import SiteProfile, HostProfile, get_profile_manager
from tabs.profile_manager import SaveProfileDialog


# ── Timezone list (common zones — full list would be 500+ entries) ────────────

TIMEZONES = [
    "UTC",
    "America/Chicago",
    "America/Los_Angeles",
    "America/New_York",
    "America/Denver",
    "America/Phoenix",
    "America/Anchorage",
    "America/Adak",
    "America/Honolulu",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Amsterdam",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Australia/Sydney",
    "Pacific/Auckland",
]


# ── Cluster pre-check worker ──────────────────────────────────────────────────

class ClusterPreCheckWorker(QThread):
    result = pyqtSignal(dict)   # {check_name: (ok, message)}

    def __init__(self, conn: PVEConnection, cluster_host: str = ""):
        super().__init__()
        self.conn         = conn
        self.cluster_host = cluster_host

    def run(self):
        results = {}
        try:
            # Time sync check
            out, _, rc = self.conn.ssh_run(
                "chronyc tracking 2>/dev/null | grep 'System time'"
            )
            if rc == 0 and out:
                results["NTP sync"] = (True, out.strip())
            else:
                results["NTP sync"] = (False, "chrony not responding or not synced")

            # Corosync reachability (ping the corosync IP if we can determine it)
            out2, _, _ = self.conn.ssh_run(
                "ip addr show | grep 'inet ' | grep -v '127.0.0.1'"
            )
            results["Network interfaces"] = (True, f"{len(out2.splitlines())} interfaces with IPs")

            # Cluster join check — ping the target node
            if self.cluster_host:
                out3, _, rc3 = self.conn.ssh_run(
                    f"ping -c 2 -W 2 {self.cluster_host} 2>&1 | tail -2"
                )
                ok = rc3 == 0
                results[f"Reach {self.cluster_host}"] = (ok, out3.strip())

            # Check pvecm status
            out4, _, _ = self.conn.ssh_run("pvecm status 2>&1 | head -3")
            in_cluster = "Quorum information" in out4
            results["Cluster status"] = (
                not in_cluster,
                "Already in a cluster" if in_cluster else "Not in cluster (good)"
            )

        except Exception as e:
            traceback.print_exc()
            results["Error"] = (False, str(e))

        self.result.emit(results)


# ── Small helpers ─────────────────────────────────────────────────────────────

class SectionHeader(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Sans", 11, QFont.Weight.Bold))
        self.setStyleSheet(
            "color: #5c9bd6; padding: 6px 0px 2px 0px; border-bottom: 1px solid #555;"
        )

class HLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #333;")


def _ip_list_edit(placeholder: str) -> QLineEdit:
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    return edit


# ── System Tab ────────────────────────────────────────────────────────────────

class SystemTab(QWidget):
    config_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inventory: HostInventory | None = None
        self._conn: PVEConnection | None = None
        self._precheck_worker: ClusterPreCheckWorker | None = None
        self._build_ui()

    def set_inventory(self, inv: HostInventory):
        self._inventory = inv
        self._populate_from_inventory(inv)

    def set_connection(self, conn: PVEConnection):
        self._conn = conn

    def apply_site_profile(self, profile: SiteProfile):
        """Populate all fields from a site profile."""
        # Timezone
        idx = self._tz_combo.findText(profile.timezone)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        else:
            # Add it if not in our list
            self._tz_combo.addItem(profile.timezone)
            self._tz_combo.setCurrentText(profile.timezone)

        # NTP
        self._ntp_edit.setText(", ".join(profile.ntp_servers))

        # DNS
        self._dns_edit.setText(", ".join(profile.dns_servers))
        self._dns_search_edit.setText(profile.dns_search)

        # Monitoring
        if profile.loki_url:
            self._loki_edit.setText(profile.loki_url)
        if profile.prometheus_url:
            self._prom_edit.setText(profile.prometheus_url)

        # Firewall
        if profile.firewall_mgmt_cidr:
            self._fw_mgmt_cidr_edit.setText(profile.firewall_mgmt_cidr)

        self._refresh_preview()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(6)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Vertical splitter: form (top) | preview (bottom) ──────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setStyleSheet("QSplitter::handle { background: #444; height: 4px; }")

        # ── Scrollable form ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(12)
        form_layout.setContentsMargins(16, 16, 16, 16)

        # Title row with Save button
        title_row = QHBoxLayout()
        title = QLabel("System Configuration")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self._save_profile_btn = QPushButton("💾  Save as site profile…")
        self._save_profile_btn.setFixedHeight(28)
        self._save_profile_btn.clicked.connect(self._save_as_site_profile)
        title_row.addWidget(self._save_profile_btn)
        form_layout.addLayout(title_row)
        hint = QLabel(
            "Configure system settings for this PVE host. "
            "Fields are pre-populated from discovery and the active site profile."
        )
        hint.setStyleSheet("color: #b0b0b0;")
        hint.setWordWrap(True)
        form_layout.addWidget(hint)

        # 1. Repository Management
        form_layout.addWidget(SectionHeader("Repository Management"))
        repo_group = QGroupBox()
        repo_group.setStyleSheet("QGroupBox { border: none; }")
        repo_layout = QVBoxLayout(repo_group)
        repo_layout.setSpacing(6)
        self._repo_disable_enterprise = QCheckBox(
            "Disable enterprise repository  (pve-enterprise.sources)"
        )
        self._repo_disable_enterprise.setChecked(True)
        self._repo_enable_nosub = QCheckBox(
            "Enable no-subscription repository"
        )
        self._repo_enable_nosub.setChecked(True)
        self._repo_enable_ceph = QCheckBox(
            "Enable Ceph no-subscription repository  (for hyper-converged setups)"
        )
        self._repo_remove_nag = QCheckBox(
            "Remove 'No valid subscription' login nag"
        )
        self._repo_remove_nag.setChecked(True)
        self._repo_run_update = QCheckBox(
            "Run apt-get update after repo changes"
        )
        self._repo_run_update.setChecked(True)
        for cb in [self._repo_disable_enterprise, self._repo_enable_nosub,
                   self._repo_enable_ceph, self._repo_remove_nag,
                   self._repo_run_update]:
            cb.stateChanged.connect(self._refresh_preview)
            repo_layout.addWidget(cb)
        form_layout.addWidget(repo_group)

        # 2. Time & NTP
        form_layout.addWidget(SectionHeader("Time & NTP"))
        time_form = QFormLayout()
        time_form.setSpacing(8)
        self._tz_combo = QComboBox()
        self._tz_combo.setEditable(True)
        for tz in TIMEZONES:
            self._tz_combo.addItem(tz)
        self._tz_combo.currentTextChanged.connect(self._refresh_preview)
        time_form.addRow("Timezone:", self._tz_combo)

        self._ntp_edit = QLineEdit()
        self._ntp_edit.setPlaceholderText(
            "e.g. 10.80.0.5, 10.80.0.6, pool.ntp.org  (comma-separated)"
        )
        self._ntp_edit.textChanged.connect(self._refresh_preview)
        time_form.addRow("NTP servers:", self._ntp_edit)

        ntp_note = QLabel(
            "AD domain controllers are recommended as primary NTP sources.\n"
            "PVE uses Chrony — servers will be written to /etc/chrony/chrony.conf."
        )
        ntp_note.setStyleSheet("color: #999; font-size: 8pt;")
        time_form.addRow("", ntp_note)
        form_layout.addLayout(time_form)

        # 3. DNS
        form_layout.addWidget(SectionHeader("DNS"))
        dns_form = QFormLayout()
        dns_form.setSpacing(8)
        self._dns_edit = QLineEdit()
        self._dns_edit.setPlaceholderText(
            "e.g. 10.80.0.5, 10.80.0.6  (comma-separated)"
        )
        self._dns_edit.textChanged.connect(self._refresh_preview)
        dns_form.addRow("DNS servers:", self._dns_edit)

        self._dns_search_edit = QLineEdit()
        self._dns_search_edit.setPlaceholderText("e.g. probablymonsters.com")
        self._dns_search_edit.textChanged.connect(self._refresh_preview)
        dns_form.addRow("Search domain:", self._dns_search_edit)
        form_layout.addLayout(dns_form)

        # 4. Remote Logging & Monitoring
        form_layout.addWidget(SectionHeader("Remote Logging & Monitoring"))
        mon_layout = QVBoxLayout()
        mon_layout.setSpacing(6)

        self._install_node_exporter = QCheckBox(
            "Install prometheus-node-exporter  (OS metrics on port 9100)"
        )
        self._install_node_exporter.setChecked(True)
        self._enable_pve_metrics = QCheckBox(
            "Install prometheus-pve-exporter  (PVE cluster/VM metrics on port 9221)"
        )
        self._enable_pve_metrics.setChecked(False)
        self._install_promtail = QCheckBox(
            "Install Promtail  (log shipping agent for Loki)"
        )
        self._install_promtail.setChecked(False)

        for cb in [self._install_node_exporter, self._enable_pve_metrics,
                   self._install_promtail]:
            cb.stateChanged.connect(self._refresh_preview)
            mon_layout.addWidget(cb)

        mon_form = QFormLayout()
        mon_form.setSpacing(8)
        self._loki_edit = QLineEdit()
        self._loki_edit.setPlaceholderText(
            "http://loki-server:3100  (leave blank — configure when stack is ready)"
        )
        self._loki_edit.textChanged.connect(self._refresh_preview)
        mon_form.addRow("Loki URL:", self._loki_edit)

        self._prom_edit = QLineEdit()
        self._prom_edit.setPlaceholderText(
            "http://prometheus:9090  (leave blank — scrape config generated for later)"
        )
        self._prom_edit.textChanged.connect(self._refresh_preview)
        mon_form.addRow("Prometheus URL:", self._prom_edit)

        mon_note = QLabel(
            "URLs can be left blank — Promtail/node-exporter will be installed and\n"
            "configured with placeholder destinations. A ready-to-use prometheus.yml\n"
            "scrape config will be generated regardless."
        )
        mon_note.setStyleSheet("color: #999; font-size: 8pt;")
        mon_layout.addLayout(mon_form)
        mon_layout.addWidget(mon_note)
        form_layout.addLayout(mon_layout)

        # 5. Security Hardening
        form_layout.addWidget(SectionHeader("Security Hardening"))
        sec_layout = QVBoxLayout()
        sec_layout.setSpacing(6)

        self._install_fail2ban = QCheckBox(
            "Install and configure fail2ban  (SSH brute-force protection)"
        )
        self._install_fail2ban.setChecked(True)
        self._ssh_prohibit_password = QCheckBox(
            "Set SSH PermitRootLogin to prohibit-password  (key auth only for root)"
        )
        self._ssh_prohibit_password.setChecked(True)
        self._enable_unattended = QCheckBox(
            "Enable unattended security updates  (Debian security only, excludes PVE/kernel packages)"
        )
        self._enable_unattended.setChecked(True)
        self._verify_log_rotation = QCheckBox(
            "Verify log rotation is configured for /var/log"
        )
        self._verify_log_rotation.setChecked(True)

        for cb in [self._install_fail2ban, self._ssh_prohibit_password,
                   self._enable_unattended, self._verify_log_rotation]:
            cb.stateChanged.connect(self._refresh_preview)
            sec_layout.addWidget(cb)

        unattended_note = QLabel(
            "Unattended upgrades will exclude: proxmox-ve, pve-*, ceph*, linux-image*, linux-headers*\n"
            "PVE and kernel updates remain under manual control."
        )
        unattended_note.setStyleSheet("color: #999; font-size: 8pt;")
        sec_layout.addWidget(unattended_note)
        form_layout.addLayout(sec_layout)

        # 6. Firewall
        form_layout.addWidget(SectionHeader("PVE Datacenter Firewall"))
        fw_layout = QVBoxLayout()
        fw_layout.setSpacing(6)

        self._enable_firewall = QCheckBox(
            "Enable PVE datacenter firewall"
        )
        self._enable_firewall.setChecked(True)
        self._enable_firewall.stateChanged.connect(self._on_firewall_toggled)
        fw_layout.addWidget(self._enable_firewall)

        self._fw_options_widget = QWidget()
        fw_form = QFormLayout(self._fw_options_widget)
        fw_form.setSpacing(8)

        self._fw_mgmt_cidr_edit = QLineEdit()
        self._fw_mgmt_cidr_edit.setPlaceholderText("e.g. 10.80.8.0/24")
        self._fw_mgmt_cidr_edit.textChanged.connect(self._refresh_preview)
        fw_form.addRow("Trusted management CIDR:", self._fw_mgmt_cidr_edit)

        fw_rules_note = QLabel(
            "Default rules allow from management CIDR:\n"
            "  • SSH (TCP 22)\n"
            "  • PVE web UI (TCP 8006)\n"
            "  • SPICE/VNC (TCP 3128, 5900-5999)\n"
            "Corosync (UDP 5405) allowed between cluster nodes only.\n"
            "All other inbound traffic denied and logged."
        )
        fw_rules_note.setStyleSheet(
            "color: #999; font-size: 8pt; font-family: monospace;"
        )
        fw_form.addRow(fw_rules_note)
        fw_layout.addWidget(self._fw_options_widget)
        form_layout.addLayout(fw_layout)

        # 7. Local Users
        form_layout.addWidget(SectionHeader("Local User Account"))
        user_form = QFormLayout()
        user_form.setSpacing(8)

        self._create_user_cb = QCheckBox("Create a local admin user")
        self._create_user_cb.stateChanged.connect(self._on_create_user_toggled)
        user_form.addRow("", self._create_user_cb)

        self._user_options = QWidget()
        user_opts_form = QFormLayout(self._user_options)
        user_opts_form.setSpacing(8)

        self._username_edit = QLineEdit()
        self._username_edit.setPlaceholderText("e.g. jaysellers")
        self._username_edit.textChanged.connect(self._refresh_preview)
        user_opts_form.addRow("Username:", self._username_edit)

        self._user_ssh_key_edit = QLineEdit()
        self._user_ssh_key_edit.setPlaceholderText(
            "ssh-ed25519 AAAA...  (paste public key)"
        )
        self._user_ssh_key_edit.textChanged.connect(self._refresh_preview)
        user_opts_form.addRow("SSH public key:", self._user_ssh_key_edit)

        self._user_sudo_cb = QCheckBox("Grant passwordless sudo")
        self._user_sudo_cb.setChecked(True)
        self._user_sudo_cb.stateChanged.connect(self._refresh_preview)
        user_opts_form.addRow("", self._user_sudo_cb)

        self._user_options.setEnabled(False)
        user_form.addRow(self._user_options)
        form_layout.addLayout(user_form)

        # 8. Cluster
        form_layout.addWidget(SectionHeader("Cluster"))
        cluster_layout = QVBoxLayout()
        cluster_layout.setSpacing(8)

        # Radio buttons
        self._cluster_skip_radio  = QRadioButton("Skip cluster configuration for now")
        self._cluster_create_radio = QRadioButton("Create a new cluster")
        self._cluster_join_radio   = QRadioButton("Join an existing cluster")
        self._cluster_skip_radio.setChecked(True)

        self._cluster_btn_group = QButtonGroup()
        for rb in [self._cluster_skip_radio,
                   self._cluster_create_radio,
                   self._cluster_join_radio]:
            self._cluster_btn_group.addButton(rb)
            rb.toggled.connect(self._on_cluster_mode_changed)
            cluster_layout.addWidget(rb)

        # Create cluster options
        self._cluster_create_widget = QWidget()
        create_form = QFormLayout(self._cluster_create_widget)
        create_form.setSpacing(8)
        self._cluster_name_edit = QLineEdit()
        self._cluster_name_edit.setPlaceholderText("e.g. lab-cluster-01")
        self._cluster_name_edit.textChanged.connect(self._refresh_preview)
        create_form.addRow("Cluster name:", self._cluster_name_edit)
        self._cluster_ring0_edit = QLineEdit()
        self._cluster_ring0_edit.setPlaceholderText(
            "e.g. 10.80.12.11  (Corosync ring 0 IP)"
        )
        self._cluster_ring0_edit.textChanged.connect(self._refresh_preview)
        create_form.addRow("Ring 0 IP:", self._cluster_ring0_edit)
        self._cluster_create_widget.setVisible(False)
        cluster_layout.addWidget(self._cluster_create_widget)

        # Join cluster options
        self._cluster_join_widget = QWidget()
        join_form = QFormLayout(self._cluster_join_widget)
        join_form.setSpacing(8)
        self._cluster_join_host_edit = QLineEdit()
        self._cluster_join_host_edit.setPlaceholderText(
            "e.g. 10.80.8.11  (IP of existing cluster node)"
        )
        self._cluster_join_host_edit.textChanged.connect(self._refresh_preview)
        join_form.addRow("Existing node IP:", self._cluster_join_host_edit)
        self._cluster_join_pass_edit = QLineEdit()
        self._cluster_join_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._cluster_join_pass_edit.setPlaceholderText("Root password of existing node")
        join_form.addRow("Root password:", self._cluster_join_pass_edit)

        # Pre-check button
        self._precheck_btn = QPushButton("Run pre-checks")
        self._precheck_btn.setFixedHeight(28)
        self._precheck_btn.clicked.connect(self._run_prechecks)
        join_form.addRow("", self._precheck_btn)

        self._precheck_results = QTextEdit()
        self._precheck_results.setReadOnly(True)
        self._precheck_results.setMaximumHeight(100)
        self._precheck_results.setFont(QFont("Monospace", 8))
        self._precheck_results.setStyleSheet(
            "background: #1a1a1a; color: #888; border-radius: 4px;"
        )
        self._precheck_results.setPlaceholderText("Pre-check results will appear here…")
        join_form.addRow(self._precheck_results)
        self._cluster_join_widget.setVisible(False)
        cluster_layout.addWidget(self._cluster_join_widget)
        form_layout.addLayout(cluster_layout)

        form_layout.addStretch()
        scroll.setWidget(form_widget)
        vsplit.addWidget(scroll)

        # ── Command preview (bottom) ──────────────────────────────────────────
        preview_group = QGroupBox("Command Preview  (read-only)")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("Monospace", 9))
        self._preview.setStyleSheet(
            "background: #1a1a1a; color: #98c379; border: none;"
        )
        preview_layout.addWidget(self._preview)
        vsplit.addWidget(preview_group)

        vsplit.setSizes([600, 250])
        outer.addWidget(vsplit)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_firewall_toggled(self, state):
        self._fw_options_widget.setEnabled(bool(state))
        self._refresh_preview()

    def _on_create_user_toggled(self, state):
        self._user_options.setEnabled(bool(state))
        self._refresh_preview()

    def _on_cluster_mode_changed(self):
        is_create = self._cluster_create_radio.isChecked()
        is_join   = self._cluster_join_radio.isChecked()
        self._cluster_create_widget.setVisible(is_create)
        self._cluster_join_widget.setVisible(is_join)
        self._refresh_preview()

    def _run_prechecks(self):
        if not self._conn:
            self._precheck_results.setPlainText("Not connected to a host.")
            return
        self._precheck_btn.setEnabled(False)
        self._precheck_results.setPlainText("Running pre-checks…")
        cluster_host = self._cluster_join_host_edit.text().strip()
        self._precheck_worker = ClusterPreCheckWorker(self._conn, cluster_host)
        self._precheck_worker.result.connect(self._on_precheck_done)
        self._precheck_worker.start()

    def _on_precheck_done(self, results: dict):
        self._precheck_btn.setEnabled(True)
        lines = []
        all_ok = True
        for check, (ok, msg) in results.items():
            icon = "✓" if ok else "✗"
            color = "#4caf50" if ok else "#f44336"
            lines.append(f'<span style="color:{color};">{icon} {check}: {msg}</span>')
            if not ok:
                all_ok = False
        self._precheck_results.setHtml("<br>".join(lines))

    # ── Populate from inventory ───────────────────────────────────────────────

    def _populate_from_inventory(self, inv: HostInventory):
        # Timezone
        idx = self._tz_combo.findText(inv.timezone)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        elif inv.timezone:
            self._tz_combo.addItem(inv.timezone)
            self._tz_combo.setCurrentText(inv.timezone)

        # DNS
        if inv.dns_servers:
            self._dns_edit.setText(", ".join(inv.dns_servers))
        if inv.dns_search:
            self._dns_search_edit.setText(inv.dns_search)

        self._refresh_preview()

    # ── Command preview generator ─────────────────────────────────────────────

    def _refresh_preview(self):
        lines = ["#!/bin/bash", "# System configuration commands",
                 "# Generated by PVE Configurator", ""]

        # Repos
        if self._repo_disable_enterprise.isChecked():
            lines += [
                "# ── Repositories ──",
                "mv /etc/apt/sources.list.d/pve-enterprise.sources "
                "/etc/apt/sources.list.d/pve-enterprise.sources.disabled",
            ]
        if self._repo_enable_nosub.isChecked():
            lines += [
                "echo 'deb http://download.proxmox.com/debian/pve bookworm pve-no-subscription' "
                "> /etc/apt/sources.list.d/pve-no-subscription.list",
            ]
        if self._repo_enable_ceph.isChecked():
            lines += [
                "echo 'deb http://download.proxmox.com/debian/ceph-quincy bookworm no-subscription' "
                "> /etc/apt/sources.list.d/ceph-no-subscription.list",
            ]
        if self._repo_remove_nag.isChecked():
            lines += [
                "# Remove subscription nag",
                "sed -i.bak 's/NotFound/Active/g' "
                "/usr/share/perl5/PVE/API2/Subscription.pm",
                "systemctl restart pveproxy",
            ]
        if self._repo_run_update.isChecked():
            lines.append("apt-get update")
        lines.append("")

        # Time & NTP
        tz = self._tz_combo.currentText().strip()
        if tz:
            lines += [
                "# ── Time & NTP ──",
                f"timedatectl set-timezone {tz}",
            ]
        ntp_raw = self._ntp_edit.text().strip()
        if ntp_raw:
            servers = [s.strip() for s in ntp_raw.split(",") if s.strip()]
            lines.append("# Configure Chrony NTP")
            lines.append("cat > /etc/chrony/chrony.conf << 'EOF'")
            for srv in servers:
                lines.append(f"server {srv} iburst")
            lines += [
                "driftfile /var/lib/chrony/drift",
                "makestep 1.0 3",
                "rtcsync",
                "EOF",
                "systemctl restart chrony",
            ]
        lines.append("")

        # DNS
        dns_raw    = self._dns_edit.text().strip()
        dns_search = self._dns_search_edit.text().strip()
        if dns_raw or dns_search:
            lines.append("# ── DNS ──")
            lines.append("cat > /etc/resolv.conf << 'EOF'")
            if dns_search:
                lines.append(f"search {dns_search}")
            for srv in [s.strip() for s in dns_raw.split(",") if s.strip()]:
                lines.append(f"nameserver {srv}")
            lines += ["EOF", ""]

        # Monitoring & logging
        if any([self._install_node_exporter.isChecked(),
                self._enable_pve_metrics.isChecked(),
                self._install_promtail.isChecked()]):
            lines.append("# ── Monitoring & Logging ──")
        if self._install_node_exporter.isChecked():
            lines += [
                "apt-get install -y prometheus-node-exporter",
                "systemctl enable --now prometheus-node-exporter",
            ]
        if self._enable_pve_metrics.isChecked():
            lines += [
                "# Install PVE Prometheus exporter (separate from node-exporter)",
                "apt-get install -y prometheus-pve-exporter",
                "systemctl enable --now prometheus-pve-exporter",
            ]
        if self._install_promtail.isChecked():
            loki = self._loki_edit.text().strip() or "http://LOKI-SERVER:3100"
            hostname = (self._inventory.hostname
                        if self._inventory else "$(hostname -s)")
            lines += [
                "# Promtail — requires manual installation via Grafana repo or binary",
                "# See: https://grafana.com/docs/loki/latest/clients/promtail/installation/",
                f"# Loki URL: {loki}",
                "cat > /etc/promtail/config.yml << 'EOF'",
                "server:",
                "  http_listen_port: 9080",
                "positions:",
                "  filename: /var/lib/promtail/positions.yaml",
                "clients:",
                f"  - url: {loki}/loki/api/v1/push",
                "scrape_configs:",
                "  - job_name: system",
                "    static_configs:",
                f"      - targets: [localhost]",
                f"        labels:",
                f"          job: system",
                f"          host: {hostname}",
                "          __path__: /var/log/*.log",
                "EOF",
                "systemctl enable --now promtail",
            ]
        lines.append("")

        # Security
        lines.append("# ── Security Hardening ──")
        if self._install_fail2ban.isChecked():
            lines += [
                "apt-get install -y fail2ban",
                "cat > /etc/fail2ban/jail.d/sshd.conf << 'EOF'",
                "[sshd]",
                "enabled  = true",
                "maxretry = 5",
                "bantime  = 3600",
                "findtime = 600",
                "EOF",
                "systemctl enable --now fail2ban",
            ]
        if self._ssh_prohibit_password.isChecked():
            lines += [
                "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' "
                "/etc/ssh/sshd_config",
                "systemctl restart sshd",
            ]
        if self._enable_unattended.isChecked():
            lines += [
                "apt-get install -y unattended-upgrades",
                "cat > /etc/apt/apt.conf.d/50unattended-upgrades-pve << 'EOF'",
                'Unattended-Upgrade::Origins-Pattern {',
                '    "origin=Debian,codename=${distro_codename},label=Debian-Security";',
                '};',
                'Unattended-Upgrade::Package-Blacklist {',
                '    "proxmox-ve";',
                '    "pve-*";',
                '    "ceph*";',
                '    "linux-image*";',
                '    "linux-headers*";',
                '};',
                'Unattended-Upgrade::Automatic-Reboot "false";',
                "EOF",
                "systemctl enable --now unattended-upgrades",
            ]
        if self._verify_log_rotation.isChecked():
            lines += [
                "# Verify log rotation",
                "logrotate --debug /etc/logrotate.conf 2>&1 | head -20",
            ]
        lines.append("")

        # Firewall
        if self._enable_firewall.isChecked():
            cidr = self._fw_mgmt_cidr_edit.text().strip() or "10.0.0.0/8"
            lines += [
                "# ── PVE Datacenter Firewall ──",
                "cat > /etc/pve/firewall/cluster.fw << 'EOF'",
                "[OPTIONS]",
                "enable: 1",
                "log_ratelimit: burst=10,rate=5/second",
                "",
                "[RULES]",
                f"IN ACCEPT -source {cidr} -dport 22 -p tcp -log nolog   # SSH",
                f"IN ACCEPT -source {cidr} -dport 8006 -p tcp -log nolog  # PVE UI",
                f"IN ACCEPT -source {cidr} -dport 3128 -p tcp -log nolog  # SPICE",
                f"IN ACCEPT -source {cidr} -dport 5900:5999 -p tcp -log nolog  # VNC",
                "IN ACCEPT -dport 5405 -p udp -log nolog  # Corosync",
                "IN DROP -log warning  # drop everything else",
                "EOF",
            ]
        lines.append("")

        # Local user
        if self._create_user_cb.isChecked():
            user = self._username_edit.text().strip()
            if user:
                lines += [
                    "# ── Local User ──",
                    f"useradd -m -s /bin/bash {user}",
                    f"usermod -aG sudo {user}",
                ]
                if self._user_sudo_cb.isChecked():
                    lines += [
                        f"echo '{user} ALL=(ALL) NOPASSWD:ALL' "
                        f"> /etc/sudoers.d/{user}",
                        f"chmod 440 /etc/sudoers.d/{user}",
                    ]
                pub_key = self._user_ssh_key_edit.text().strip()
                if pub_key:
                    lines += [
                        f"mkdir -p /home/{user}/.ssh",
                        f"echo '{pub_key}' >> /home/{user}/.ssh/authorized_keys",
                        f"chmod 700 /home/{user}/.ssh",
                        f"chmod 600 /home/{user}/.ssh/authorized_keys",
                        f"chown -R {user}:{user} /home/{user}/.ssh",
                    ]
        lines.append("")

        # Cluster
        if self._cluster_create_radio.isChecked():
            name   = self._cluster_name_edit.text().strip()
            ring0  = self._cluster_ring0_edit.text().strip()
            if name:
                lines += [
                    "# ── Create Cluster ──",
                    f"pvecm create {name}" + (f" --link0 {ring0}" if ring0 else ""),
                ]
        elif self._cluster_join_radio.isChecked():
            host = self._cluster_join_host_edit.text().strip()
            if host:
                lines += [
                    "# ── Join Cluster ──",
                    "# Run pre-checks before executing this!",
                    f"pvecm add {host}",
                ]
        lines.append("")

        self._preview.setPlainText("\n".join(lines))

    # ── Public ────────────────────────────────────────────────────────────────

    def apply_host_profile(self, profile: HostProfile):
        """Apply system option checkboxes from a host profile."""
        mapping = {
            "_install_fail2ban":        "install_fail2ban",
            "_ssh_prohibit_password":   "ssh_prohibit_password",
            "_enable_unattended":       "enable_unattended_upgrades",
            "_enable_firewall":         "enable_firewall",
            "_install_node_exporter":   "install_node_exporter",
            "_enable_pve_metrics":      "enable_pve_metrics",
            "_install_promtail":        "install_promtail",
            "_repo_disable_enterprise": "disable_enterprise_repo",
            "_repo_enable_nosub":       "enable_nosub_repo",
            "_repo_remove_nag":         "remove_nag",
        }
        for attr, key in mapping.items():
            widget = getattr(self, attr, None)
            if widget:
                widget.setChecked(getattr(profile, key, True))
        # Cluster mode
        mode = profile.cluster_mode
        if mode == "create":
            self._cluster_create_radio.setChecked(True)
        elif mode == "join":
            self._cluster_join_radio.setChecked(True)
        else:
            self._cluster_skip_radio.setChecked(True)
        self._refresh_preview()

    def _save_as_site_profile(self):
        from core.sites import SiteProfile, get_profile_manager
        mgr = get_profile_manager()
        dlg = SaveProfileDialog(mgr.profile_names, "site", self)
        if dlg.exec():
            profile = SiteProfile(name=dlg.profile_name())
            profile.timezone     = self._tz_combo.currentText().strip()
            profile.ntp_servers  = [s.strip() for s in
                                     self._ntp_edit.text().split(",") if s.strip()]
            profile.dns_servers  = [s.strip() for s in
                                     self._dns_edit.text().split(",") if s.strip()]
            profile.dns_search   = self._dns_search_edit.text().strip()
            profile.loki_url     = self._loki_edit.text().strip()
            profile.prometheus_url = self._prom_edit.text().strip()
            profile.firewall_mgmt_cidr = self._fw_mgmt_cidr_edit.text().strip()
            mgr.add_or_update(profile)
            # Notify parent to refresh combo
            self.config_changed.emit()

    def get_system_config(self) -> dict:
        """Return system config dict for Review tab."""
        return {
            "timezone":       self._tz_combo.currentText().strip(),
            "ntp_servers":    [s.strip() for s in self._ntp_edit.text().split(",") if s.strip()],
            "dns_servers":    [s.strip() for s in self._dns_edit.text().split(",") if s.strip()],
            "dns_search":     self._dns_search_edit.text().strip(),
            "disable_enterprise_repo":    self._repo_disable_enterprise.isChecked(),
            "enable_nosub_repo":          self._repo_enable_nosub.isChecked(),
            "remove_nag":                 self._repo_remove_nag.isChecked(),
            "install_fail2ban":           self._install_fail2ban.isChecked(),
            "ssh_prohibit_password":      self._ssh_prohibit_password.isChecked(),
            "enable_unattended_upgrades": self._enable_unattended.isChecked(),
            "enable_firewall":            self._enable_firewall.isChecked(),
            "firewall_mgmt_cidr":         self._fw_mgmt_cidr_edit.text().strip(),
            "install_node_exporter":      self._install_node_exporter.isChecked(),
            "enable_pve_metrics":         self._enable_pve_metrics.isChecked(),
            "install_promtail":           self._install_promtail.isChecked(),
            "loki_url":                   self._loki_edit.text().strip(),
            "cluster_mode":               (
                "create" if self._cluster_create_radio.isChecked()
                else "join" if self._cluster_join_radio.isChecked()
                else "skip"
            ),
        }
