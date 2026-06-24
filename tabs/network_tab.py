"""
Tab 3: Network Configuration
NIC role assignment, bond/bridge/VLAN builder, live /etc/network/interfaces preview.
Supports both simple (one trunk NIC + VLANs) and complex (dedicated NICs per role) layouts.
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QTextEdit,
    QSpinBox, QCheckBox, QFrame, QScrollArea, QSizePolicy,
    QMenu, QMessageBox, QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush, QAction

from core.models import (
    HostInventory, NICInfo, NICRole, DesiredConfig,
    BondConfig, BondMode, BridgeConfig, VLANConfig,
)


# ── Constants ─────────────────────────────────────────────────────────────────

ROLE_COLORS = {
    NICRole.MANAGEMENT:  "#5c9bd6",
    NICRole.VM_TRAFFIC:  "#4caf50",
    NICRole.STORAGE:     "#ff9800",
    NICRole.ISCSI_A:     "#ff9800",
    NICRole.ISCSI_B:     "#ff9800",
    NICRole.COROSYNC:    "#9c27b0",
    NICRole.MIGRATION:   "#ce93d8",
    NICRole.EXCLUDE:     "#555555",
    NICRole.UNASSIGNED:  "#888888",
}

ROLE_DESCRIPTIONS = {
    NICRole.MANAGEMENT:  "Management traffic, host access",
    NICRole.VM_TRAFFIC:  "VM guest network traffic",
    NICRole.STORAGE:     "Storage traffic — NFS or iSCSI",
    NICRole.ISCSI_A:     "iSCSI storage path A (jumbo frames)",
    NICRole.ISCSI_B:     "iSCSI storage path B (jumbo frames)",
    NICRole.COROSYNC:    "Proxmox cluster heartbeat",
    NICRole.MIGRATION:   "VM live migration traffic",
    NICRole.EXCLUDE:     "Not used / ignore",
    NICRole.UNASSIGNED:  "Not yet assigned",
}


# ── Small reusable widgets ────────────────────────────────────────────────────

class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        self.setStyleSheet("color: #ccc; margin-top: 6px;")


class HLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #444;")


class RoleCombo(QComboBox):
    """Role selector combo with colour-coded items."""
    def __init__(self, parent=None):
        super().__init__(parent)
        for role in NICRole:
            self.addItem(role.value, role)
        self.setMinimumWidth(160)

    def set_role(self, role: NICRole):
        idx = self.findData(role)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def current_role(self) -> NICRole:
        return self.currentData()


# ── NIC Assignment Panel ──────────────────────────────────────────────────────

class NICAssignmentPanel(QWidget):
    """
    Top panel — one row per physical NIC showing name, speed, state, role dropdown.
    Emits role_changed(nic_name, new_role) whenever operator changes a role.
    """
    role_changed = pyqtSignal(str, object)   # nic_name, NICRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, RoleCombo] = {}
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(4)
        self._layout.setContentsMargins(0, 0, 0, 0)

        # Header row
        hdr = QWidget()
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(8, 4, 8, 4)
        for text, width in [("Interface", 90), ("Speed", 70), ("State", 70),
                             ("MAC", 140), ("Role", 180), ("Description", 0)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #999; font-size: 9pt;")
            if width:
                lbl.setFixedWidth(width)
            hdr_row.addWidget(lbl)
        hdr_row.addStretch()
        self._layout.addWidget(hdr)
        self._layout.addWidget(HLine())

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setSpacing(2)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._rows_container)

    def populate(self, nics: list[NICInfo]):
        # Clear existing
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        physical = [n for n in nics if not n.is_virtual and not n.is_wifi]
        for nic in physical:
            row = self._make_nic_row(nic)
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch()

    def _make_nic_row(self, nic: NICInfo) -> QWidget:
        row = QWidget()
        row.setFixedHeight(36)
        row.setStyleSheet(
            "QWidget { background: #2f2f2f; border-radius: 4px; }"
            "QWidget:hover { background: #363636; }"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # Name
        name_lbl = QLabel(nic.name)
        name_lbl.setFixedWidth(90)
        name_lbl.setFont(QFont("Monospace", 9))
        layout.addWidget(name_lbl)

        # Speed
        speed_lbl = QLabel(nic.speed_label)
        speed_lbl.setFixedWidth(70)
        speed_lbl.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(speed_lbl)

        # State
        state_color = "#4caf50" if nic.state == "UP" else "#666"
        state_lbl = QLabel(nic.state_label)
        state_lbl.setFixedWidth(70)
        state_lbl.setStyleSheet(f"color: {state_color};")
        layout.addWidget(state_lbl)

        # MAC
        mac_lbl = QLabel(nic.mac)
        mac_lbl.setFixedWidth(140)
        mac_lbl.setStyleSheet("color: #999; font-size: 8pt;")
        layout.addWidget(mac_lbl)

        # Role combo
        combo = RoleCombo()
        combo.set_role(nic.role)
        combo.currentIndexChanged.connect(
            lambda _idx, n=nic.name, c=combo: self._on_role_changed(n, c)
        )
        self._rows[nic.name] = combo
        layout.addWidget(combo)

        # Description (updates with role)
        desc_lbl = QLabel(ROLE_DESCRIPTIONS.get(nic.role, ""))
        desc_lbl.setStyleSheet("color: #999; font-size: 8pt;")
        combo.currentIndexChanged.connect(
            lambda _idx, c=combo, d=desc_lbl: d.setText(
                ROLE_DESCRIPTIONS.get(c.current_role(), "")
            )
        )
        layout.addWidget(desc_lbl, stretch=1)

        return row

    def _on_role_changed(self, nic_name: str, combo: RoleCombo):
        self.role_changed.emit(nic_name, combo.current_role())

    def get_assignments(self) -> dict[str, NICRole]:
        return {name: combo.current_role() for name, combo in self._rows.items()}

    def set_role(self, nic_name: str, role: NICRole):
        if nic_name in self._rows:
            self._rows[nic_name].set_role(role)


# ── Network Object Tree ───────────────────────────────────────────────────────

class NetworkObjectTree(QTreeWidget):
    """
    Left panel — tree of bonds, bridges, VLANs the operator has defined.
    Right-click to add/remove objects.
    """
    object_selected = pyqtSignal(str, object)   # type, object

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("Network Objects")
        self.setMinimumWidth(200)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemClicked.connect(self._on_item_clicked)
        self._bonds:   list[BondConfig]   = []
        self._bridges: list[BridgeConfig] = []
        self._vlans:   list[VLANConfig]   = []
        self._rebuild()

    def _rebuild(self):
        self.clear()
        # Bonds
        self._bond_root = QTreeWidgetItem(["Bonds"])
        self._bond_root.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
        self._bond_root.setExpanded(True)
        self.addTopLevelItem(self._bond_root)
        for b in self._bonds:
            item = QTreeWidgetItem([b.name])
            item.setData(0, Qt.ItemDataRole.UserRole, ("bond", b))
            item.setForeground(0, QBrush(QColor("#5c9bd6")))
            self._bond_root.addChild(item)

        # Bridges
        self._bridge_root = QTreeWidgetItem(["Bridges"])
        self._bridge_root.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
        self._bridge_root.setExpanded(True)
        self.addTopLevelItem(self._bridge_root)
        for b in self._bridges:
            item = QTreeWidgetItem([b.name])
            item.setData(0, Qt.ItemDataRole.UserRole, ("bridge", b))
            item.setForeground(0, QBrush(QColor("#4caf50")))
            self._bridge_root.addChild(item)

        # VLANs
        self._vlan_root = QTreeWidgetItem(["VLANs / IPs"])
        self._vlan_root.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
        self._vlan_root.setExpanded(True)
        self.addTopLevelItem(self._vlan_root)
        for v in self._vlans:
            label = f"{v.name}  {v.ip}/{v.prefix}" if v.ip else v.name
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, ("vlan", v))
            item.setForeground(0, QBrush(QColor("#ff9800")))
            self._vlan_root.addChild(item)

    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu(self)

        add_bond_act   = QAction("Add Bond…", self)
        add_bridge_act = QAction("Add Bridge…", self)
        add_vlan_act   = QAction("Add VLAN / IP…", self)
        menu.addAction(add_bond_act)
        menu.addAction(add_bridge_act)
        menu.addAction(add_vlan_act)

        if item and item.data(0, Qt.ItemDataRole.UserRole):
            menu.addSeparator()
            remove_act = QAction("Remove", self)
            remove_act.triggered.connect(lambda: self._remove_item(item))
            menu.addAction(remove_act)

        add_bond_act.triggered.connect(self._add_bond)
        add_bridge_act.triggered.connect(self._add_bridge)
        add_vlan_act.triggered.connect(self._add_vlan)
        menu.exec(self.viewport().mapToGlobal(pos))

    def _on_item_clicked(self, item, _col):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            self.object_selected.emit(data[0], data[1])

    def _add_bond(self):
        n = len(self._bonds)
        bond = BondConfig(name=f"bond{n}", members=[], mode=BondMode.ACTIVE_BACKUP)
        self._bonds.append(bond)
        self._rebuild()
        self.object_selected.emit("bond", bond)

    def _add_bridge(self):
        n = len(self._bridges)
        bridge = BridgeConfig(name=f"vmbr{n}", bond_or_nic="")
        self._bridges.append(bridge)
        self._rebuild()
        self.object_selected.emit("bridge", bridge)

    def _add_vlan(self):
        parent = self._bridges[0].name if self._bridges else "vmbr0"
        vlan = VLANConfig(name=f"{parent}.0", parent=parent, vlan_id=0)
        self._vlans.append(vlan)
        self._rebuild()
        self.object_selected.emit("vlan", vlan)

    def _remove_item(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, obj = data
        if kind == "bond":
            self._bonds = [b for b in self._bonds if b is not obj]
        elif kind == "bridge":
            self._bridges = [b for b in self._bridges if b is not obj]
        elif kind == "vlan":
            self._vlans = [v for v in self._vlans if v is not obj]
        self._rebuild()

    def set_objects(self, bonds, bridges, vlans):
        self._bonds   = bonds
        self._bridges = bridges
        self._vlans   = vlans
        self._rebuild()

    def refresh(self):
        self._rebuild()

    @property
    def bonds(self):   return self._bonds
    @property
    def bridges(self): return self._bridges
    @property
    def vlans(self):   return self._vlans


# ── Config panels (right side, one per object type) ───────────────────────────

class BondConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, available_nics: list[str], parent=None):
        super().__init__(parent)
        self._bond: BondConfig | None = None
        self._nic_checks: dict[str, QCheckBox] = {}
        self._available_nics = available_nics
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Bond name:", self._name_edit)

        self._mode_combo = QComboBox()
        for m in BondMode:
            self._mode_combo.addItem(m.value, m)
        self._mode_combo.currentIndexChanged.connect(self._sync)
        layout.addRow("Mode:", self._mode_combo)

        self._mtu_spin = QSpinBox()
        self._mtu_spin.setRange(1500, 9000)
        self._mtu_spin.setSingleStep(500)
        self._mtu_spin.setValue(1500)
        self._mtu_spin.valueChanged.connect(self._sync)
        layout.addRow("MTU:", self._mtu_spin)

        # NIC member checkboxes
        members_group = QGroupBox("Member NICs")
        members_layout = QVBoxLayout(members_group)
        self._nic_checks = {}
        for nic_name in self._available_nics:
            cb = QCheckBox(nic_name)
            cb.stateChanged.connect(self._sync)
            self._nic_checks[nic_name] = cb
            members_layout.addWidget(cb)
        layout.addRow(members_group)

    def load(self, bond: BondConfig):
        for w in [self._name_edit, self._mode_combo, self._mtu_spin]:
            w.blockSignals(True)
        for cb in self._nic_checks.values():
            cb.blockSignals(True)
        self._bond = bond
        self._name_edit.setText(bond.name)
        idx = self._mode_combo.findData(bond.mode)
        self._mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._mtu_spin.setValue(bond.mtu)
        for name, cb in self._nic_checks.items():
            cb.setChecked(name in bond.members)
        for w in [self._name_edit, self._mode_combo, self._mtu_spin]:
            w.blockSignals(False)
        for cb in self._nic_checks.values():
            cb.blockSignals(False)

    def _sync(self):
        if not self._bond:
            return
        self._bond.name    = self._name_edit.text().strip()
        self._bond.mode    = self._mode_combo.currentData()
        self._bond.mtu     = self._mtu_spin.value()
        self._bond.members = [n for n, cb in self._nic_checks.items() if cb.isChecked()]
        self.changed.emit()


class BridgeConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge: BridgeConfig | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Bridge name:", self._name_edit)

        self._port_edit = QLineEdit()
        self._port_edit.setPlaceholderText("e.g. bond0  or  nic3")
        self._port_edit.textChanged.connect(self._sync)
        layout.addRow("Port (NIC or bond):", self._port_edit)

        self._vlan_aware = QCheckBox("VLAN aware")
        self._vlan_aware.setChecked(False)
        self._vlan_aware.stateChanged.connect(self._sync)
        layout.addRow("", self._vlan_aware)

        self._vlan_ids_edit = QLineEdit("")
        self._vlan_ids_edit.textChanged.connect(self._sync)
        layout.addRow("VLAN IDs:", self._vlan_ids_edit)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("e.g. 10.0.2.10  (leave blank for inet manual)")
        self._ip_edit.textChanged.connect(self._sync)
        layout.addRow("IP address:", self._ip_edit)

        self._prefix_spin = QSpinBox()
        self._prefix_spin.setRange(1, 32)
        self._prefix_spin.setValue(24)
        self._prefix_spin.valueChanged.connect(self._sync)
        layout.addRow("Prefix length:", self._prefix_spin)

        self._gw_edit = QLineEdit()
        self._gw_edit.setPlaceholderText("e.g. 10.0.0.1  (leave blank if not gateway)")
        self._gw_edit.textChanged.connect(self._sync)
        layout.addRow("Gateway:", self._gw_edit)

        self._mtu_spin = QSpinBox()
        self._mtu_spin.setRange(1500, 9000)
        self._mtu_spin.setSingleStep(500)
        self._mtu_spin.setValue(1500)
        self._mtu_spin.valueChanged.connect(self._sync)
        layout.addRow("MTU:", self._mtu_spin)

    def load(self, bridge: BridgeConfig):
        for w in [self._name_edit, self._port_edit, self._vlan_aware,
                  self._vlan_ids_edit, self._ip_edit, self._prefix_spin,
                  self._gw_edit, self._mtu_spin]:
            w.blockSignals(True)
        self._bridge = bridge
        self._name_edit.setText(bridge.name)
        self._port_edit.setText(bridge.bond_or_nic)
        self._vlan_aware.setChecked(bridge.vlan_aware)
        self._vlan_ids_edit.setText(bridge.vlan_ids)
        self._ip_edit.setText(bridge.ip)
        self._prefix_spin.setValue(bridge.prefix)
        self._gw_edit.setText(bridge.gateway)
        self._mtu_spin.setValue(bridge.mtu)
        for w in [self._name_edit, self._port_edit, self._vlan_aware,
                  self._vlan_ids_edit, self._ip_edit, self._prefix_spin,
                  self._gw_edit, self._mtu_spin]:
            w.blockSignals(False)

    def _sync(self):
        if not self._bridge:
            return
        self._bridge.name        = self._name_edit.text().strip()
        self._bridge.bond_or_nic = self._port_edit.text().strip()
        self._bridge.vlan_aware  = self._vlan_aware.isChecked()
        self._bridge.vlan_ids    = self._vlan_ids_edit.text().strip()
        self._bridge.ip          = self._ip_edit.text().strip()
        self._bridge.prefix      = self._prefix_spin.value()
        self._bridge.gateway     = self._gw_edit.text().strip()
        self._bridge.mtu         = self._mtu_spin.value()
        self.changed.emit()


class VLANConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vlan: VLANConfig | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. vmbr0.2008")
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Interface name:", self._name_edit)

        self._parent_edit = QLineEdit()
        self._parent_edit.setPlaceholderText("e.g. vmbr0")
        self._parent_edit.textChanged.connect(self._sync)
        layout.addRow("Parent bridge:", self._parent_edit)

        self._vlan_spin = QSpinBox()
        self._vlan_spin.setRange(1, 4094)
        self._vlan_spin.valueChanged.connect(self._on_vlan_id_changed)
        layout.addRow("VLAN ID:", self._vlan_spin)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("e.g. 10.80.8.11")
        self._ip_edit.textChanged.connect(self._sync)
        layout.addRow("IP address:", self._ip_edit)

        self._prefix_spin = QSpinBox()
        self._prefix_spin.setRange(1, 32)
        self._prefix_spin.setValue(24)
        self._prefix_spin.valueChanged.connect(self._sync)
        layout.addRow("Prefix length:", self._prefix_spin)

        self._gw_edit = QLineEdit()
        self._gw_edit.setPlaceholderText("e.g. 10.80.8.1  (leave blank if not gateway)")
        self._gw_edit.textChanged.connect(self._sync)
        layout.addRow("Gateway:", self._gw_edit)

        # Role hint
        self._role_label = QLabel()
        self._role_label.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        layout.addRow("Role hint:", self._role_label)
        self._update_role_hint(0)

    def _update_role_hint(self, vlan_id: int):
        hints = {
            2008: "Management — host access",
            2009: "VM Network — guest traffic",
            2010: "Storage — iSCSI / NFS",
            2011: "Migration — live VM migration",
            2012: "Corosync — cluster heartbeat",
        }
        self._role_label.setText(hints.get(vlan_id, ""))

    def load(self, vlan: VLANConfig):
        # Block all signals during load to prevent _sync firing mid-population
        for w in [self._name_edit, self._parent_edit, self._vlan_spin,
                  self._ip_edit, self._prefix_spin, self._gw_edit]:
            w.blockSignals(True)
        self._vlan = vlan
        self._name_edit.setText(vlan.name)
        self._parent_edit.setText(vlan.parent)
        self._vlan_spin.setValue(vlan.vlan_id if vlan.vlan_id else 1)
        self._ip_edit.setText(vlan.ip)
        self._prefix_spin.setValue(vlan.prefix)
        self._gw_edit.setText(vlan.gateway)
        for w in [self._name_edit, self._parent_edit, self._vlan_spin,
                  self._ip_edit, self._prefix_spin, self._gw_edit]:
            w.blockSignals(False)
        self._update_role_hint(vlan.vlan_id)

    def _on_vlan_id_changed(self, value: int):
        if self._vlan:
            # Auto-update interface name to match vlan id
            parent = self._parent_edit.text().strip() or "vmbr0"
            self._name_edit.blockSignals(True)
            self._name_edit.setText(f"{parent}.{value}")
            self._name_edit.blockSignals(False)
        self._update_role_hint(value)
        self._sync()

    def _sync(self):
        if not self._vlan:
            return
        self._vlan.name    = self._name_edit.text().strip()
        self._vlan.parent  = self._parent_edit.text().strip()
        self._vlan.vlan_id = self._vlan_spin.value()
        self._vlan.ip      = self._ip_edit.text().strip()
        self._vlan.prefix  = self._prefix_spin.value()
        self._vlan.gateway = self._gw_edit.text().strip()
        self.changed.emit()


class PlainNICConfigPanel(QWidget):
    """Config panel for NICs used directly (iSCSI, Corosync) without a bond/bridge."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        info = QLabel(
            "This NIC will be configured with a static IP directly\n"
            "(no bond or bridge). Typical for iSCSI or Corosync."
        )
        info.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        layout.addRow(info)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("e.g. 10.80.10.11")
        layout.addRow("IP address:", self._ip_edit)

        self._prefix_spin = QSpinBox()
        self._prefix_spin.setRange(1, 32)
        self._prefix_spin.setValue(24)
        layout.addRow("Prefix length:", self._prefix_spin)

        self._mtu_spin = QSpinBox()
        self._mtu_spin.setRange(1500, 9000)
        self._mtu_spin.setSingleStep(500)
        self._mtu_spin.setValue(9000)
        layout.addRow("MTU (9000 for iSCSI):", self._mtu_spin)


# ── interfaces file generator ─────────────────────────────────────────────────

def generate_interfaces(
    nics: list[NICInfo],
    bonds: list[BondConfig],
    bridges: list[BridgeConfig],
    vlans: list[VLANConfig],
) -> str:
    lines = ["auto lo", "iface lo inet loopback", ""]

    # Raw NIC stanzas (manual — members of bonds or bridges)
    bonded_nics  = {m for b in bonds   for m in b.members}
    bridged_nics = {b.bond_or_nic for b in bridges}
    all_managed  = bonded_nics | bridged_nics

    physical_names = [n.name for n in nics if not n.is_virtual and not n.is_wifi]
    for name in physical_names:
        lines.append(f"iface {name} inet manual")
    if physical_names:
        lines.append("")

    # Bonds
    for bond in bonds:
        lines.append(f"auto {bond.name}")
        lines.append(f"iface {bond.name} inet manual")
        lines.append(f"\tbond-slaves {' '.join(bond.members)}")
        lines.append(f"\tbond-miimon 100")
        lines.append(f"\tbond-mode {bond.mode.value}")
        if bond.mode == BondMode.LACP_802_3AD:
            lines.append(f"\tbond-xmit-hash-policy layer2+3")
        if bond.mtu != 1500:
            lines.append(f"\tmtu {bond.mtu}")
        lines.append("")

    # Bridges
    for bridge in bridges:
        lines.append(f"auto {bridge.name}")
        if bridge.ip:
            lines.append(f"iface {bridge.name} inet static")
            lines.append(f"\taddress {bridge.ip}/{bridge.prefix}")
            if bridge.gateway:
                lines.append(f"\tgateway {bridge.gateway}")
        else:
            lines.append(f"iface {bridge.name} inet manual")
        if bridge.bond_or_nic:
            lines.append(f"\tbridge-ports {bridge.bond_or_nic}")
        lines.append(f"\tbridge-stp off")
        lines.append(f"\tbridge-fd 0")
        if bridge.vlan_aware:
            lines.append(f"\tbridge-vlan-aware yes")
            lines.append(f"\tbridge-vids {bridge.vlan_ids}")
        if bridge.mtu != 1500:
            lines.append(f"\tmtu {bridge.mtu}")
        lines.append("")

    # VLAN interfaces
    for vlan in vlans:
        if not vlan.ip:
            continue
        lines.append(f"auto {vlan.name}")
        lines.append(f"iface {vlan.name} inet static")
        lines.append(f"\taddress {vlan.ip}/{vlan.prefix}")
        if vlan.gateway:
            lines.append(f"\tgateway {vlan.gateway}")
        lines.append(f"\tvlan-raw-device {vlan.parent}")
        lines.append("")

    lines.append("source /etc/network/interfaces.d/*")
    return "\n".join(lines)


# ── Network Tab ───────────────────────────────────────────────────────────────

class NetworkTab(QWidget):
    config_changed = pyqtSignal(object)   # DesiredConfig

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inventory: HostInventory | None = None
        self._bonds:   list[BondConfig]   = []
        self._bridges: list[BridgeConfig] = []
        self._vlans:   list[VLANConfig]   = []
        self._build_ui()

    def set_inventory(self, inv: HostInventory):
        self._inventory = inv
        self._nic_panel.populate(inv.nics)
        self._load_current_config(inv)
        self._refresh_preview()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Fixed header (title + hint) ───────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("Network Configuration")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        suggest_btn = QPushButton("⚡ Auto-suggest from roles")
        suggest_btn.setToolTip(
            "Automatically build bonds/bridges based on NIC role assignments"
        )
        suggest_btn.clicked.connect(self._auto_suggest)
        title_row.addWidget(suggest_btn)
        root.addLayout(title_row)

        hint = QLabel(
            "Assign roles to each NIC, then build bonds/bridges/VLANs manually "
            "or use Auto-suggest. The interfaces preview updates live."
        )
        hint.setStyleSheet("color: #b0b0b0;")
        root.addWidget(hint)

        # ── Main vertical splitter (all three resizable sections) ─────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setStyleSheet("QSplitter::handle { background: #444; height: 4px; }")

        # ── Section 1: NIC Role Assignment ────────────────────────────────────
        nic_group = QGroupBox("NIC Role Assignment  (drag divider to resize)")
        nic_layout = QVBoxLayout(nic_group)
        nic_layout.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._nic_panel = NICAssignmentPanel()
        self._nic_panel.role_changed.connect(self._on_role_changed)
        scroll.setWidget(self._nic_panel)
        nic_layout.addWidget(scroll)
        vsplit.addWidget(nic_group)

        # ── Section 2: Object tree + config panel (horizontal split) ──────────
        mid_splitter = QSplitter(Qt.Orientation.Horizontal)
        mid_splitter.setChildrenCollapsible(False)

        # Left: object tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        btn_row = QHBoxLayout()
        for label, slot in [
            ("+ Bond",   self._add_bond),
            ("+ Bridge", self._add_bridge),
            ("+ VLAN",   self._add_vlan),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        left_layout.addLayout(btn_row)

        self._obj_tree = NetworkObjectTree()
        self._obj_tree.object_selected.connect(self._on_object_selected)
        left_layout.addWidget(self._obj_tree)
        mid_splitter.addWidget(left)

        # Right: stacked config panels
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(4)

        self._config_label = SectionLabel("Select an object to configure")
        right_layout.addWidget(self._config_label)

        self._config_stack = QStackedWidget()

        # Page 0: placeholder
        placeholder = QLabel("← Select a bond, bridge, or VLAN\nto configure it here.")
        placeholder.setStyleSheet("color: #888;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._config_stack.addWidget(placeholder)

        # Page 1: bond
        nic_names = []  # populated when inventory arrives
        self._bond_panel = BondConfigPanel(nic_names)
        self._bond_panel.changed.connect(self._refresh_preview)
        self._bond_panel.changed.connect(self._obj_tree.refresh)
        self._config_stack.addWidget(self._bond_panel)

        # Page 2: bridge
        self._bridge_panel = BridgeConfigPanel()
        self._bridge_panel.changed.connect(self._refresh_preview)
        self._bridge_panel.changed.connect(self._obj_tree.refresh)
        self._config_stack.addWidget(self._bridge_panel)

        # Page 3: vlan
        self._vlan_panel = VLANConfigPanel()
        self._vlan_panel.changed.connect(self._refresh_preview)
        self._vlan_panel.changed.connect(self._obj_tree.refresh)
        self._config_stack.addWidget(self._vlan_panel)

        # Page 4: plain NIC (iSCSI/Corosync)
        self._plain_nic_panel = PlainNICConfigPanel()
        self._config_stack.addWidget(self._plain_nic_panel)

        right_layout.addWidget(self._config_stack, stretch=1)
        mid_splitter.addWidget(right)
        mid_splitter.setSizes([240, 500])
        vsplit.addWidget(mid_splitter)

        # ── Section 3: interfaces preview ─────────────────────────────────────
        preview_group = QGroupBox("/etc/network/interfaces  (live preview)")
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

        # Default proportions: NIC panel ~25%, middle ~50%, preview ~25%
        vsplit.setSizes([200, 400, 200])
        root.addWidget(vsplit, stretch=1)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_role_changed(self, nic_name: str, role: NICRole):
        """Update NIC role in inventory when operator changes a dropdown."""
        if self._inventory:
            for nic in self._inventory.nics:
                if nic.name == nic_name:
                    nic.role = role
                    break

    def _on_object_selected(self, kind: str, obj):
        if kind == "bond":
            self._config_label.setText(f"Bond: {obj.name}")
            # Refresh available NICs in bond panel
            if self._inventory:
                names = [n.name for n in self._inventory.physical_nics]
                self._bond_panel._available_nics = names
                self._bond_panel._build_ui()
            self._bond_panel.load(obj)
            self._config_stack.setCurrentIndex(1)
        elif kind == "bridge":
            self._config_label.setText(f"Bridge: {obj.name}")
            self._bridge_panel.load(obj)
            self._config_stack.setCurrentIndex(2)
        elif kind == "vlan":
            self._config_label.setText(f"VLAN interface: {obj.name}")
            self._vlan_panel.load(obj)
            self._config_stack.setCurrentIndex(3)

    def _add_bond(self):
        n = len(self._bonds)
        bond = BondConfig(name=f"bond{n}", members=[], mode=BondMode.ACTIVE_BACKUP)
        self._bonds.append(bond)
        self._obj_tree.set_objects(self._bonds, self._bridges, self._vlans)
        self._on_object_selected("bond", bond)

    def _add_bridge(self):
        n = len(self._bridges)
        bridge = BridgeConfig(name=f"vmbr{n}", bond_or_nic="")
        self._bridges.append(bridge)
        self._obj_tree.set_objects(self._bonds, self._bridges, self._vlans)
        self._on_object_selected("bridge", bridge)

    def _add_vlan(self):
        parent = self._bridges[0].name if self._bridges else "vmbr0"
        vlan = VLANConfig(name=f"{parent}.0", parent=parent, vlan_id=0)
        self._vlans.append(vlan)
        self._obj_tree.set_objects(self._bonds, self._bridges, self._vlans)
        self._on_object_selected("vlan", vlan)

    def _refresh_preview(self):
        if not self._inventory:
            return
        text = generate_interfaces(
            self._inventory.nics,
            self._bonds,
            self._bridges,
            self._vlans,
        )
        self._preview.setPlainText(text)

    # ── Load current config from inventory ────────────────────────────────────

    def _load_current_config(self, inv: HostInventory):
        """
        Pre-populate bonds/bridges/VLANs from what was discovered on the host.
        This reflects the current running config so the operator sees a starting
        point rather than a blank slate.
        """
        self._bonds   = []
        self._bridges = []
        self._vlans   = []

        # If there's an existing vmbr0 in the inventory, add it
        # Only pre-populate IPs/gateway — leave port blank so auto-suggest
        # assigns the correct NIC based on role assignment rather than
        # falling back to "first UP NIC" which is wrong when nic order differs.
        vmbr_nics = [n for n in inv.nics if n.name.startswith("vmbr") and "." not in n.name]
        for vnic in vmbr_nics:
            bridge = BridgeConfig(
                name=vnic.name,
                bond_or_nic="",
                vlan_aware=False,
                vlan_ids="",
                ip=vnic.ip,
                prefix=vnic.prefix if vnic.prefix else 24,
                gateway=vnic.gateway,
            )
            self._bridges.append(bridge)

        # Add VLAN interfaces from inventory
        vlan_nics = [n for n in inv.nics if "." in n.name and n.name.startswith("vmbr")]
        for vnic in vlan_nics:
            parts = vnic.name.split(".")
            try:
                vlan_id = int(parts[-1])
            except ValueError:
                continue
            parent = parts[0]
            vlan = VLANConfig(
                name=vnic.name,
                parent=parent,
                vlan_id=vlan_id,
                ip=inv.current_ip,
                prefix=24,
                gateway=inv.current_gateway,
            )
            self._vlans.append(vlan)

        self._obj_tree.set_objects(self._bonds, self._bridges, self._vlans)

    # ── Auto-suggest ──────────────────────────────────────────────────────────

    def _auto_suggest(self):
        """
        Build a suggested network topology based on NIC role assignments.
        Called when operator clicks the Auto-suggest button.
        Clears existing objects and rebuilds from scratch.
        """
        if not self._inventory:
            return

        assignments = self._nic_panel.get_assignments()
        nics_by_role: dict[NICRole, list[str]] = {}
        for nic_name, role in assignments.items():
            nics_by_role.setdefault(role, []).append(nic_name)

        self._bonds   = []
        self._bridges = []
        self._vlans   = []

        # VM Traffic or Management -> vmbr0 (flat bridge, not VLAN-aware)
        # On a flat network, management and VM traffic share the same NIC/bridge
        vm_nics = (
            nics_by_role.get(NICRole.VM_TRAFFIC, []) or
            nics_by_role.get(NICRole.MANAGEMENT, [])
        )
        # Carry over the node's current management IP/gateway so vmbr0 doesn't
        # end up with no address (which would drop connectivity on apply).
        # Prefer whichever discovered NIC/bridge has a gateway set (the most
        # direct signal of the true management interface) over current_ip,
        # since a host can have multiple static interfaces (e.g. storage).
        mgmt_ip = self._inventory.current_ip
        mgmt_gw = self._inventory.current_gateway
        mgmt_prefix = 24
        gw_nic = next(
            (n for n in self._inventory.nics if n.gateway), None
        )
        if gw_nic:
            mgmt_ip, mgmt_gw, mgmt_prefix = gw_nic.ip, gw_nic.gateway, (gw_nic.prefix or 24)
        else:
            existing_vmbr0 = next(
                (n for n in self._inventory.nics if n.name == "vmbr0" and n.prefix), None
            )
            if existing_vmbr0:
                mgmt_prefix = existing_vmbr0.prefix
            else:
                matching_nic = next(
                    (n for n in self._inventory.nics if n.ip == mgmt_ip and n.prefix), None
                )
                if matching_nic:
                    mgmt_prefix = matching_nic.prefix

        if len(vm_nics) == 1:
            bridge = BridgeConfig(
                name="vmbr0", bond_or_nic=vm_nics[0],
                vlan_aware=False, vlan_ids="",
                ip=mgmt_ip, prefix=mgmt_prefix, gateway=mgmt_gw,
            )
            self._bridges.append(bridge)
        elif len(vm_nics) >= 2:
            bond = BondConfig(
                name="bond0", members=vm_nics, mode=BondMode.ACTIVE_BACKUP
            )
            self._bonds.append(bond)
            bridge = BridgeConfig(
                name="vmbr0", bond_or_nic="bond0",
                vlan_aware=False, vlan_ids="",
                ip=mgmt_ip, prefix=mgmt_prefix, gateway=mgmt_gw,
            )
            self._bridges.append(bridge)

        # Storage NIC -> vmbr_nfs (flat bridge, no VLANs)
        storage_nics = [
            nic_name for nic_name, role in assignments.items()
            if role in (NICRole.STORAGE, NICRole.ISCSI_A, NICRole.ISCSI_B)
        ]
        if len(storage_nics) == 1:
            # Carry over any existing IP already configured on vmbr_nfs
            storage_ip, storage_prefix = "", 24
            for n in self._inventory.nics:
                if n.name == "vmbr_nfs" and n.ip:
                    storage_ip, storage_prefix = n.ip, (n.prefix or 24)
                    break
            bridge = BridgeConfig(
                name="vmbr_nfs", bond_or_nic=storage_nics[0],
                vlan_aware=False, vlan_ids="",
                ip=storage_ip, prefix=storage_prefix,
            )
            self._bridges.append(bridge)

        self._obj_tree.set_objects(self._bonds, self._bridges, self._vlans)
        self._refresh_preview()

    # ── Public ────────────────────────────────────────────────────────────────

    def get_network_config(self) -> tuple:
        """Return (bonds, bridges, vlans) for use by Review tab."""
        return self._bonds, self._bridges, self._vlans
