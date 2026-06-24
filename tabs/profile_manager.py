"""
Profile Manager Dialog
View, create, edit, and delete site and host profiles.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QTabWidget, QWidget, QLabel, QPushButton, QLineEdit,
    QTextEdit, QListWidget, QListWidgetItem, QComboBox,
    QSpinBox, QCheckBox, QGroupBox, QMessageBox,
    QSplitter, QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from core.sites import (
    SiteProfile, HostProfile, NICRoleAssignment, DiskRoleAssignment,
    get_profile_manager, get_host_profile_manager,
    BUILTIN_SITE_PROFILES, BUILTIN_HOST_PROFILES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Site Profile Editor
# ─────────────────────────────────────────────────────────────────────────────

class SiteProfileEditor(QWidget):
    """Form for editing a single site profile."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile: SiteProfile | None = None
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        layout = QFormLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self.changed)
        layout.addRow("Profile name:", self._name_edit)

        self._tz_combo = QComboBox()
        self._tz_combo.setEditable(True)
        for tz in [
            "UTC", "America/Chicago", "America/Los_Angeles",
            "America/New_York", "America/Denver", "America/Phoenix",
            "America/Anchorage", "Europe/London", "Europe/Paris",
            "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney",
        ]:
            self._tz_combo.addItem(tz)
        self._tz_combo.currentTextChanged.connect(self.changed)
        layout.addRow("Timezone:", self._tz_combo)

        self._ntp_edit = QLineEdit()
        self._ntp_edit.setPlaceholderText("10.80.0.5, 10.80.0.6, pool.ntp.org")
        self._ntp_edit.textChanged.connect(self.changed)
        layout.addRow("NTP servers:", self._ntp_edit)

        self._dns_edit = QLineEdit()
        self._dns_edit.setPlaceholderText("10.80.0.5, 10.80.0.6")
        self._dns_edit.textChanged.connect(self.changed)
        layout.addRow("DNS servers:", self._dns_edit)

        self._dns_search_edit = QLineEdit()
        self._dns_search_edit.setPlaceholderText("probablymonsters.com")
        self._dns_search_edit.textChanged.connect(self.changed)
        layout.addRow("DNS search:", self._dns_search_edit)

        self._ad_domain_edit = QLineEdit()
        self._ad_domain_edit.textChanged.connect(self.changed)
        layout.addRow("AD domain:", self._ad_domain_edit)

        # VLANs
        vlan_group = QGroupBox("VLANs  (0 = not configured)")
        vlan_form = QFormLayout(vlan_group)
        self._vlan_spins = {}
        for label, key in [
            ("Management", "vlan_management"),
            ("VM Network",  "vlan_vm"),
            ("Storage",     "vlan_storage"),
            ("Migration",   "vlan_migration"),
            ("Corosync",    "vlan_corosync"),
        ]:
            spin = QSpinBox()
            spin.setRange(0, 4094)
            spin.valueChanged.connect(self.changed)
            self._vlan_spins[key] = spin
            vlan_form.addRow(f"{label}:", spin)
        layout.addRow(vlan_group)

        self._mgmt_subnet_edit = QLineEdit()
        self._mgmt_subnet_edit.setPlaceholderText("10.80.8.0/24")
        self._mgmt_subnet_edit.textChanged.connect(self.changed)
        layout.addRow("Mgmt subnet:", self._mgmt_subnet_edit)

        self._fw_cidr_edit = QLineEdit()
        self._fw_cidr_edit.setPlaceholderText("10.80.8.0/24")
        self._fw_cidr_edit.textChanged.connect(self.changed)
        layout.addRow("Firewall CIDR:", self._fw_cidr_edit)

        self._loki_edit = QLineEdit()
        self._loki_edit.setPlaceholderText("http://loki:3100  (leave blank if not ready)")
        self._loki_edit.textChanged.connect(self.changed)
        layout.addRow("Loki URL:", self._loki_edit)

        self._prom_edit = QLineEdit()
        self._prom_edit.setPlaceholderText("http://prometheus:9090")
        self._prom_edit.textChanged.connect(self.changed)
        layout.addRow("Prometheus URL:", self._prom_edit)

        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.textChanged.connect(self.changed)
        layout.addRow("Notes:", self._notes_edit)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self, profile: SiteProfile):
        self._profile = None   # prevent changed signal during load
        self._name_edit.setText(profile.name)
        idx = self._tz_combo.findText(profile.timezone)
        if idx >= 0:
            self._tz_combo.setCurrentIndex(idx)
        else:
            self._tz_combo.setCurrentText(profile.timezone)
        self._ntp_edit.setText(", ".join(profile.ntp_servers))
        self._dns_edit.setText(", ".join(profile.dns_servers))
        self._dns_search_edit.setText(profile.dns_search)
        self._ad_domain_edit.setText(profile.ad_domain)
        for key, spin in self._vlan_spins.items():
            spin.setValue(getattr(profile, key, 0))
        self._mgmt_subnet_edit.setText(profile.mgmt_subnet)
        self._fw_cidr_edit.setText(profile.firewall_mgmt_cidr)
        self._loki_edit.setText(profile.loki_url)
        self._prom_edit.setText(profile.prometheus_url)
        self._notes_edit.setPlainText(profile.notes)
        self._profile = profile

    def read(self) -> SiteProfile:
        """Read form values into a new SiteProfile."""
        p = SiteProfile(name=self._name_edit.text().strip())
        p.timezone          = self._tz_combo.currentText().strip()
        p.ntp_servers       = [s.strip() for s in self._ntp_edit.text().split(",") if s.strip()]
        p.dns_servers       = [s.strip() for s in self._dns_edit.text().split(",") if s.strip()]
        p.dns_search        = self._dns_search_edit.text().strip()
        p.ad_domain         = self._ad_domain_edit.text().strip()
        p.mgmt_subnet       = self._mgmt_subnet_edit.text().strip()
        p.firewall_mgmt_cidr = self._fw_cidr_edit.text().strip()
        p.loki_url          = self._loki_edit.text().strip()
        p.prometheus_url    = self._prom_edit.text().strip()
        p.notes             = self._notes_edit.toPlainText().strip()
        for key, spin in self._vlan_spins.items():
            setattr(p, key, spin.value())
        return p

    def set_readonly(self, readonly: bool):
        for w in [self._name_edit, self._ntp_edit, self._dns_edit,
                  self._dns_search_edit, self._ad_domain_edit,
                  self._mgmt_subnet_edit, self._fw_cidr_edit,
                  self._loki_edit, self._prom_edit, self._notes_edit]:
            w.setReadOnly(readonly)
        for spin in self._vlan_spins.values():
            spin.setEnabled(not readonly)
        self._tz_combo.setEnabled(not readonly)


# ─────────────────────────────────────────────────────────────────────────────
# Host Profile Editor
# ─────────────────────────────────────────────────────────────────────────────

class HostProfileEditor(QWidget):
    """Form for editing a single host profile."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile: HostProfile | None = None
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        layout = QFormLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self.changed)
        layout.addRow("Profile name:", self._name_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Brief description of this host type")
        self._desc_edit.textChanged.connect(self.changed)
        layout.addRow("Description:", self._desc_edit)

        # Network
        net_group = QGroupBox("Network Defaults")
        net_form = QFormLayout(net_group)
        self._vm_bond_combo = QComboBox()
        for m in ["802.3ad", "active-backup", "balance-alb"]:
            self._vm_bond_combo.addItem(m)
        self._vm_bond_combo.currentTextChanged.connect(self.changed)
        net_form.addRow("VM traffic bond mode:", self._vm_bond_combo)

        self._mgmt_bond_combo = QComboBox()
        for m in ["active-backup", "802.3ad", "balance-alb"]:
            self._mgmt_bond_combo.addItem(m)
        self._mgmt_bond_combo.currentTextChanged.connect(self.changed)
        net_form.addRow("Management bond mode:", self._mgmt_bond_combo)

        self._vlan_aware_cb = QCheckBox("VLAN-aware bridge")
        self._vlan_aware_cb.setChecked(True)
        self._vlan_aware_cb.stateChanged.connect(self.changed)
        net_form.addRow("", self._vlan_aware_cb)
        layout.addRow(net_group)

        # System options
        sys_group = QGroupBox("System Options")
        sys_layout = QVBoxLayout(sys_group)
        self._sys_checks = {}
        for label, key, default in [
            ("Install fail2ban",                    "install_fail2ban",           True),
            ("SSH prohibit-password for root",      "ssh_prohibit_password",      True),
            ("Enable unattended security updates",  "enable_unattended_upgrades", True),
            ("Enable PVE datacenter firewall",      "enable_firewall",            True),
            ("Install prometheus-node-exporter",    "install_node_exporter",      True),
            ("Install Promtail",                    "install_promtail",           True),
            ("Disable enterprise repo",             "disable_enterprise_repo",    True),
            ("Enable no-subscription repo",         "enable_nosub_repo",          True),
            ("Remove subscription nag",             "remove_nag",                 True),
        ]:
            cb = QCheckBox(label)
            cb.setChecked(default)
            cb.stateChanged.connect(self.changed)
            self._sys_checks[key] = cb
            sys_layout.addWidget(cb)
        layout.addRow(sys_group)

        # Cluster default
        self._cluster_combo = QComboBox()
        for m in ["skip", "create", "join"]:
            self._cluster_combo.addItem(m)
        self._cluster_combo.currentTextChanged.connect(self.changed)
        layout.addRow("Default cluster mode:", self._cluster_combo)

        self._notes_edit = QTextEdit()
        self._notes_edit.setMaximumHeight(80)
        self._notes_edit.textChanged.connect(self.changed)
        layout.addRow("Notes:", self._notes_edit)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self, profile: HostProfile):
        self._profile = None
        self._name_edit.setText(profile.name)
        self._desc_edit.setText(profile.description)
        idx = self._vm_bond_combo.findText(profile.vm_bond_mode)
        self._vm_bond_combo.setCurrentIndex(idx if idx >= 0 else 0)
        idx = self._mgmt_bond_combo.findText(profile.mgmt_bond_mode)
        self._mgmt_bond_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._vlan_aware_cb.setChecked(profile.vlan_aware_bridge)
        for key, cb in self._sys_checks.items():
            cb.setChecked(getattr(profile, key, True))
        idx = self._cluster_combo.findText(profile.cluster_mode)
        self._cluster_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._notes_edit.setPlainText(profile.notes)
        self._profile = profile

    def read(self) -> HostProfile:
        p = HostProfile(name=self._name_edit.text().strip())
        p.description       = self._desc_edit.text().strip()
        p.vm_bond_mode      = self._vm_bond_combo.currentText()
        p.mgmt_bond_mode    = self._mgmt_bond_combo.currentText()
        p.vlan_aware_bridge = self._vlan_aware_cb.isChecked()
        p.cluster_mode      = self._cluster_combo.currentText()
        p.notes             = self._notes_edit.toPlainText().strip()
        for key, cb in self._sys_checks.items():
            setattr(p, key, cb.isChecked())
        # Preserve NIC/disk role assignments from original if editing
        if self._profile:
            p.nic_roles  = self._profile.nic_roles
            p.disk_roles = self._profile.disk_roles
        return p

    def set_readonly(self, readonly: bool):
        for w in [self._name_edit, self._desc_edit, self._notes_edit]:
            w.setReadOnly(readonly)
        for w in [self._vm_bond_combo, self._mgmt_bond_combo,
                  self._cluster_combo, self._vlan_aware_cb]:
            w.setEnabled(not readonly)
        for cb in self._sys_checks.values():
            cb.setEnabled(not readonly)


# ─────────────────────────────────────────────────────────────────────────────
# Profile list panel (left side of dialog)
# ─────────────────────────────────────────────────────────────────────────────

class ProfileListPanel(QWidget):
    """Left panel — list of profiles with New/Delete buttons."""
    selection_changed = pyqtSignal(str)   # profile name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._list = QListWidget()
        self._list.currentTextChanged.connect(self.selection_changed)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._new_btn = QPushButton("+ New")
        self._new_btn.setFixedHeight(26)
        self._del_btn = QPushButton("Delete")
        self._del_btn.setFixedHeight(26)
        self._del_btn.setStyleSheet("color: #f44;")
        btn_row.addWidget(self._new_btn)
        btn_row.addWidget(self._del_btn)
        layout.addLayout(btn_row)

    def populate(self, names: list[str], builtin_names: set[str]):
        self._list.clear()
        for name in names:
            item = QListWidgetItem(name)
            if name in builtin_names:
                item.setForeground(QColor("#5c9bd6"))
                item.setToolTip("Built-in profile — cannot be deleted")
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def current_name(self) -> str:
        item = self._list.currentItem()
        return item.text() if item else ""

    def select(self, name: str):
        for i in range(self._list.count()):
            if self._list.item(i).text() == name:
                self._list.setCurrentRow(i)
                return

    @property
    def new_btn(self): return self._new_btn
    @property
    def del_btn(self): return self._del_btn


# ─────────────────────────────────────────────────────────────────────────────
# Main Profile Manager Dialog
# ─────────────────────────────────────────────────────────────────────────────

class ProfileManagerDialog(QDialog):
    """
    Full profile manager — tabbed for Site and Host profiles.
    Allows viewing, creating, editing, and deleting profiles.
    """
    profiles_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Profile Manager")
        self.setMinimumSize(900, 620)
        self._site_mgr = get_profile_manager()
        self._host_mgr = get_host_profile_manager()
        self._site_dirty = False
        self._host_dirty = False
        self._build_ui()
        self._populate_site_list()
        self._populate_host_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Profile Manager")
        title.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        hint = QLabel(
            "Blue entries are built-in profiles (read-only). "
            "Create new profiles or duplicate a built-in to customize it."
        )
        hint.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(hint)

        tabs = QTabWidget()
        tabs.addTab(self._build_site_tab(), "Site Profiles")
        tabs.addTab(self._build_host_tab(), "Host Profiles")
        layout.addWidget(tabs, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("Close")
        self._close_btn.setFixedHeight(32)
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

    # ── Site tab ──────────────────────────────────────────────────────────────

    def _build_site_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: list
        left = QWidget()
        left.setMaximumWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(QLabel("Site Profiles"))
        self._site_list = ProfileListPanel()
        self._site_list.selection_changed.connect(self._on_site_selected)
        self._site_list.new_btn.clicked.connect(self._new_site_profile)
        self._site_list.del_btn.clicked.connect(self._delete_site_profile)
        left_layout.addWidget(self._site_list)
        splitter.addWidget(left)

        # Right: editor + save
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        self._site_readonly_label = QLabel("⚑ Built-in profile — read only. Use 'Duplicate' to create an editable copy.")
        self._site_readonly_label.setStyleSheet("color: #ff9800; font-size: 8pt;")
        self._site_readonly_label.setVisible(False)
        right_layout.addWidget(self._site_readonly_label)

        self._site_editor = SiteProfileEditor()
        right_layout.addWidget(self._site_editor, stretch=1)

        site_btn_row = QHBoxLayout()
        self._site_duplicate_btn = QPushButton("Duplicate")
        self._site_duplicate_btn.setToolTip("Create an editable copy of this profile")
        self._site_duplicate_btn.clicked.connect(self._duplicate_site_profile)
        self._site_save_btn = QPushButton("Save")
        self._site_save_btn.setDefault(True)
        self._site_save_btn.clicked.connect(self._save_site_profile)
        site_btn_row.addWidget(self._site_duplicate_btn)
        site_btn_row.addStretch()
        site_btn_row.addWidget(self._site_save_btn)
        right_layout.addLayout(site_btn_row)
        splitter.addWidget(right)

        splitter.setSizes([200, 680])
        layout.addWidget(splitter)
        return widget

    # ── Host tab ──────────────────────────────────────────────────────────────

    def _build_host_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left.setMaximumWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.addWidget(QLabel("Host Profiles"))
        self._host_list = ProfileListPanel()
        self._host_list.selection_changed.connect(self._on_host_selected)
        self._host_list.new_btn.clicked.connect(self._new_host_profile)
        self._host_list.del_btn.clicked.connect(self._delete_host_profile)
        left_layout.addWidget(self._host_list)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        self._host_readonly_label = QLabel("⚑ Built-in profile — read only. Use 'Duplicate' to create an editable copy.")
        self._host_readonly_label.setStyleSheet("color: #ff9800; font-size: 8pt;")
        self._host_readonly_label.setVisible(False)
        right_layout.addWidget(self._host_readonly_label)

        self._host_editor = HostProfileEditor()
        right_layout.addWidget(self._host_editor, stretch=1)

        host_btn_row = QHBoxLayout()
        self._host_duplicate_btn = QPushButton("Duplicate")
        self._host_duplicate_btn.clicked.connect(self._duplicate_host_profile)
        self._host_save_btn = QPushButton("Save")
        self._host_save_btn.setDefault(True)
        self._host_save_btn.clicked.connect(self._save_host_profile)
        host_btn_row.addWidget(self._host_duplicate_btn)
        host_btn_row.addStretch()
        host_btn_row.addWidget(self._host_save_btn)
        right_layout.addLayout(host_btn_row)
        splitter.addWidget(right)

        splitter.setSizes([200, 680])
        layout.addWidget(splitter)
        return widget

    # ── Site profile actions ──────────────────────────────────────────────────

    def _populate_site_list(self):
        builtin = {p.name for p in BUILTIN_SITE_PROFILES}
        self._site_list.populate(self._site_mgr.profile_names, builtin)

    def _on_site_selected(self, name: str):
        profile = self._site_mgr.get(name)
        if not profile:
            return
        self._site_editor.load(profile)
        is_builtin = profile.builtin
        self._site_editor.set_readonly(is_builtin)
        self._site_readonly_label.setVisible(is_builtin)
        self._site_save_btn.setEnabled(not is_builtin)

    def _new_site_profile(self):
        profile = SiteProfile(name="New Site Profile")
        self._site_mgr.add_or_update(profile)
        self._populate_site_list()
        self._site_list.select(profile.name)
        self.profiles_changed.emit()

    def _duplicate_site_profile(self):
        name = self._site_list.current_name()
        profile = self._site_mgr.get(name)
        if not profile:
            return
        new_profile = SiteProfile.from_dict(profile.to_dict())
        new_profile.name    = f"{profile.name} (copy)"
        new_profile.builtin = False
        self._site_mgr.add_or_update(new_profile)
        self._populate_site_list()
        self._site_list.select(new_profile.name)
        self.profiles_changed.emit()

    def _save_site_profile(self):
        profile = self._site_editor.read()
        if not profile.name:
            QMessageBox.warning(self, "Save Profile", "Profile name cannot be blank.")
            return
        self._site_mgr.add_or_update(profile)
        self._populate_site_list()
        self._site_list.select(profile.name)
        self.profiles_changed.emit()

    def _delete_site_profile(self):
        name = self._site_list.current_name()
        if not name:
            return
        if not self._site_mgr.delete(name):
            QMessageBox.information(self, "Delete Profile",
                                    "Built-in profiles cannot be deleted.")
            return
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete site profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._site_mgr.delete(name)
            self._populate_site_list()
            self.profiles_changed.emit()

    # ── Host profile actions ──────────────────────────────────────────────────

    def _populate_host_list(self):
        builtin = {p.name for p in BUILTIN_HOST_PROFILES}
        self._host_list.populate(self._host_mgr.profile_names, builtin)

    def _on_host_selected(self, name: str):
        profile = self._host_mgr.get(name)
        if not profile:
            return
        self._host_editor.load(profile)
        is_builtin = profile.builtin
        self._host_editor.set_readonly(is_builtin)
        self._host_readonly_label.setVisible(is_builtin)
        self._host_save_btn.setEnabled(not is_builtin)

    def _new_host_profile(self):
        profile = HostProfile(name="New Host Profile")
        self._host_mgr.add_or_update(profile)
        self._populate_host_list()
        self._host_list.select(profile.name)
        self.profiles_changed.emit()

    def _duplicate_host_profile(self):
        name = self._host_list.current_name()
        profile = self._host_mgr.get(name)
        if not profile:
            return
        new_profile = HostProfile.from_dict(profile.to_dict())
        new_profile.name    = f"{profile.name} (copy)"
        new_profile.builtin = False
        self._host_mgr.add_or_update(new_profile)
        self._populate_host_list()
        self._host_list.select(new_profile.name)
        self.profiles_changed.emit()

    def _save_host_profile(self):
        profile = self._host_editor.read()
        if not profile.name:
            QMessageBox.warning(self, "Save Profile", "Profile name cannot be blank.")
            return
        self._host_mgr.add_or_update(profile)
        self._populate_host_list()
        self._host_list.select(profile.name)
        self.profiles_changed.emit()

    def _delete_host_profile(self):
        name = self._host_list.current_name()
        if not name:
            return
        if not self._host_mgr.delete(name):
            QMessageBox.information(self, "Delete Profile",
                                    "Built-in profiles cannot be deleted.")
            return
        reply = QMessageBox.question(
            self, "Delete Profile",
            f"Delete host profile '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._host_mgr.delete(name)
            self._populate_host_list()
            self.profiles_changed.emit()


# ─────────────────────────────────────────────────────────────────────────────
# Quick "Save current as profile" dialog
# ─────────────────────────────────────────────────────────────────────────────

class SaveProfileDialog(QDialog):
    """Lightweight dialog to name and save the current settings as a profile."""

    def __init__(self, existing_names: list[str], profile_type: str = "site", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Save as {profile_type.title()} Profile")
        self.setFixedSize(400, 150)
        self._build_ui(existing_names)

    def _build_ui(self, existing_names: list[str]):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Fort Worth Custom")
        form.addRow("Profile name:", self._name_edit)
        layout.addLayout(form)

        self._warn_label = QLabel()
        self._warn_label.setStyleSheet("color: #ff9800; font-size: 8pt;")
        self._warn_label.setVisible(False)
        layout.addWidget(self._warn_label)
        self._existing = existing_names
        self._name_edit.textChanged.connect(self._check_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addWidget(save)
        layout.addLayout(btn_row)

    def _check_name(self, name: str):
        if name in self._existing:
            self._warn_label.setText(f"⚠ '{name}' already exists — saving will overwrite it.")
            self._warn_label.setVisible(True)
        else:
            self._warn_label.setVisible(False)

    def _on_save(self):
        if not self._name_edit.text().strip():
            self._warn_label.setText("Profile name cannot be blank.")
            self._warn_label.setVisible(True)
            return
        self.accept()

    def profile_name(self) -> str:
        return self._name_edit.text().strip()
