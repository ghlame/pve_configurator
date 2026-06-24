"""
Tab 2: Discover
Runs hardware discovery against connected host.
Displays NICs, disks, current network config, and system info.
Operator reviews before proceeding to configure.
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QTextEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush

from core.models import HostInventory, NICInfo, DiskInfo, NICRole, StorageRole
from core.connection import PVEConnection, HardwareDiscovery


# ── Worker ────────────────────────────────────────────────────────────────────

class DiscoveryWorker(QThread):
    progress  = pyqtSignal(str)
    finished  = pyqtSignal(object)   # HostInventory

    def __init__(self, conn: PVEConnection):
        super().__init__()
        self.conn = conn

    def run(self):
        try:
            disc = HardwareDiscovery(self.conn)
            inv  = disc.discover(progress_callback=lambda m: self.progress.emit(m))
            self.finished.emit(inv)
        except Exception as e:
            traceback.print_exc()
            self.finished.emit(None)


# ── Colour helpers ────────────────────────────────────────────────────────────

STATE_COLORS = {
    "UP ✓":   "#4caf50",
    "DOWN":   "#888888",
    "Virtual":"#5c9bd6",
}

ROLE_COLORS = {
    NICRole.MANAGEMENT:  "#5c9bd6",
    NICRole.VM_TRAFFIC:  "#4caf50",
    NICRole.STORAGE:     "#ff9800",
    NICRole.ISCSI_A:     "#ff9800",
    NICRole.ISCSI_B:     "#ff9800",
    NICRole.COROSYNC:    "#9c27b0",
    NICRole.MIGRATION:   "#9c27b0",
    NICRole.EXCLUDE:     "#555555",
    NICRole.UNASSIGNED:  "#888888",
}

DISK_ROLE_COLORS = {
    StorageRole.OS_DISK:   "#5c9bd6",
    StorageRole.LOCAL_LVM: "#4caf50",
    StorageRole.BACKUP_DIR:"#ff9800",
    StorageRole.ZFS_POOL:  "#9c27b0",
    StorageRole.EXCLUDE:   "#555555",
    StorageRole.UNASSIGNED:"#888888",
}


def _colored_item(texts: list[str], color: str = None) -> QTreeWidgetItem:
    item = QTreeWidgetItem(texts)
    if color:
        for col in range(len(texts)):
            item.setForeground(col, QBrush(QColor(color)))
    return item


# ── Discovery Tab ─────────────────────────────────────────────────────────────

class DiscoveryTab(QWidget):
    # Emitted when discovery completes — carries the HostInventory
    discovered = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn:   PVEConnection | None = None
        self._worker: DiscoveryWorker | None = None
        self._inventory: HostInventory | None = None
        self._build_ui()

    def set_connection(self, conn: PVEConnection):
        self._conn = conn
        self._discover_btn.setEnabled(True)
        self._status_label.setText(
            f"Ready — connected to {conn.creds.host}. Click Discover to scan hardware."
        )

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(24, 24, 24, 24)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Hardware Discovery")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self._discover_btn = QPushButton("Run Discovery")
        self._discover_btn.setFixedHeight(32)
        self._discover_btn.setEnabled(False)
        self._discover_btn.clicked.connect(self._on_discover)
        title_row.addWidget(self._discover_btn)
        root.addLayout(title_row)

        self._status_label = QLabel("Connect to a host first (Tab 1).")
        self._status_label.setStyleSheet("color: #b0b0b0;")
        root.addWidget(self._status_label)

        # Progress bar (hidden until running)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        root.addWidget(self._progress)

        # ── Splitter: left=summary cards, right=detail trees ─────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT: summary cards
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self._host_group  = self._make_info_group("Host")
        self._net_group   = self._make_info_group("Current Network")
        self._sys_group   = self._make_info_group("System")
        left_layout.addWidget(self._host_group)
        left_layout.addWidget(self._net_group)
        left_layout.addWidget(self._sys_group)
        left_layout.addStretch()
        splitter.addWidget(left)

        # RIGHT: NIC + Disk trees
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(8, 0, 0, 0)

        # NIC tree
        nic_header = QLabel("Network Interfaces")
        nic_header.setFont(QFont("Sans", 11, QFont.Weight.Bold))
        right_layout.addWidget(nic_header)
        self._nic_tree = QTreeWidget()
        self._nic_tree.setHeaderLabels(["Interface", "MAC", "Speed", "State", "Suggested Role"])
        self._nic_tree.setAlternatingRowColors(True)
        self._nic_tree.setSortingEnabled(False)
        self._nic_tree.setMinimumHeight(180)
        right_layout.addWidget(self._nic_tree)

        # Disk tree
        disk_header = QLabel("Block Devices")
        disk_header.setFont(QFont("Sans", 11, QFont.Weight.Bold))
        right_layout.addWidget(disk_header)
        self._disk_tree = QTreeWidget()
        self._disk_tree.setHeaderLabels(["Device", "Size", "Type", "Transport", "Model", "Suggested Role"])
        self._disk_tree.setAlternatingRowColors(True)
        self._disk_tree.setSortingEnabled(False)
        self._disk_tree.setMinimumHeight(160)
        right_layout.addWidget(self._disk_tree)

        splitter.addWidget(right)
        splitter.setSizes([300, 600])
        root.addWidget(splitter, stretch=1)

        # Log strip at bottom
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(80)
        self._log.setFont(QFont("Monospace", 8))
        self._log.setStyleSheet(
            "background:#1e1e1e; color:#888; border-radius:4px;"
        )
        root.addWidget(self._log)

    def _make_info_group(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setLayout(QVBoxLayout())
        box.layout().setSpacing(4)
        placeholder = QLabel("—")
        placeholder.setStyleSheet("color: #999;")
        box.layout().addWidget(placeholder)
        return box

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_discover(self):
        if not self._conn:
            return
        self._discover_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._log_msg("Starting discovery…")
        self._worker = DiscoveryWorker(self._conn)
        self._worker.progress.connect(self._log_msg)
        self._worker.finished.connect(self._on_discovery_done)
        self._worker.start()

    def _on_discovery_done(self, inv: HostInventory | None):
        self._discover_btn.setEnabled(True)
        self._progress.setVisible(False)

        if inv is None:
            self._status_label.setText("✗ Discovery failed — check the log below.")
            self._status_label.setStyleSheet("color: #f44;")
            return

        self._inventory = inv
        self._status_label.setText(
            f"✓ Discovery complete — {inv.hostname} "
            f"({len(inv.physical_nics)} NICs, {len(inv.configurable_disks)} disks)"
        )
        self._status_label.setStyleSheet("color: #4caf50;")
        self._populate(inv)
        self.discovered.emit(inv)

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate(self, inv: HostInventory):
        self._populate_host_card(inv)
        self._populate_net_card(inv)
        self._populate_sys_card(inv)
        self._populate_nics(inv)
        self._populate_disks(inv)

    def _clear_group(self, group: QGroupBox):
        layout = group.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_row(self, group: QGroupBox, label: str, value: str, color: str = None):
        row = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setStyleSheet("color: #b0b0b0; min-width: 110px;")
        val = QLabel(value)
        if color:
            val.setStyleSheet(f"color: {color};")
        row.addWidget(lbl)
        row.addWidget(val, stretch=1)
        container = QWidget()
        container.setLayout(row)
        group.layout().addWidget(container)

    def _populate_host_card(self, inv: HostInventory):
        self._clear_group(self._host_group)
        self._add_row(self._host_group, "Hostname", inv.hostname or "—")
        self._add_row(self._host_group, "FQDN",     inv.fqdn or "—")
        self._add_row(self._host_group, "PVE",      inv.pve_version or "—")
        self._add_row(self._host_group, "CPU",      inv.cpu_model or "—")
        self._add_row(self._host_group, "Threads",  str(inv.cpu_threads) if inv.cpu_threads else "—")
        self._add_row(self._host_group, "RAM",      f"{inv.ram_gb} GB" if inv.ram_gb else "—")

    def _populate_net_card(self, inv: HostInventory):
        self._clear_group(self._net_group)
        self._add_row(self._net_group, "Mgmt IP",   inv.current_ip or "—")
        self._add_row(self._net_group, "Gateway",   inv.current_gateway or "—")
        vlan = str(inv.current_vlan) if inv.current_vlan else "—"
        self._add_row(self._net_group, "VLAN",      vlan)

    def _populate_sys_card(self, inv: HostInventory):
        self._clear_group(self._sys_group)
        dns = ", ".join(inv.dns_servers) if inv.dns_servers else "—"
        self._add_row(self._sys_group, "DNS",       dns)
        self._add_row(self._sys_group, "Search",    inv.dns_search or "—")
        self._add_row(self._sys_group, "Timezone",  inv.timezone or "—")
        ntp_color = "#4caf50" if inv.ntp_active else "#f44"
        ntp_label = "Active" if inv.ntp_active else "Inactive"
        self._add_row(self._sys_group, "NTP",       ntp_label, color=ntp_color)
        repo_color = "#f44" if inv.has_enterprise_repo else "#4caf50"
        repo_label = "Enterprise (needs fix)" if inv.has_enterprise_repo else "OK"
        self._add_row(self._sys_group, "Repo",      repo_label, color=repo_color)
        cluster = inv.cluster_status if inv.cluster_status else "Not in cluster"
        self._add_row(self._sys_group, "Cluster",   cluster[:50])

    def _populate_nics(self, inv: HostInventory):
        self._nic_tree.clear()

        # Sections: Physical, Virtual, Excluded
        sections = {
            "Physical NICs": [n for n in inv.nics if not n.is_virtual and not n.is_wifi],
            "WiFi / Excluded": [n for n in inv.nics if n.is_wifi],
            "Virtual (bridges/VLANs)": [n for n in inv.nics if n.is_virtual],
        }

        for section_name, nics in sections.items():
            if not nics:
                continue
            section_item = QTreeWidgetItem([section_name])
            section_item.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
            section_item.setExpanded(True)
            self._nic_tree.addTopLevelItem(section_item)

            for nic in nics:
                role_color = ROLE_COLORS.get(nic.role, "#888")
                state_color = STATE_COLORS.get(nic.state_label, "#888")
                item = QTreeWidgetItem([
                    nic.name,
                    nic.mac,
                    nic.speed_label,
                    nic.state_label,
                    nic.suggested_role.value,
                ])
                item.setForeground(3, QBrush(QColor(state_color)))
                item.setForeground(4, QBrush(QColor(role_color)))
                item.setData(0, Qt.ItemDataRole.UserRole, nic)
                section_item.addChild(item)

        for i in range(self._nic_tree.columnCount()):
            self._nic_tree.resizeColumnToContents(i)

    def _populate_disks(self, inv: HostInventory):
        self._disk_tree.clear()

        sections = {
            "Configurable": [d for d in inv.disks if not d.is_usb and not d.is_pve_os],
            "OS Disk (protected)": [d for d in inv.disks if d.is_pve_os],
            "USB / Excluded": [d for d in inv.disks if d.is_usb],
        }

        for section_name, disks in sections.items():
            if not disks:
                continue
            section_item = QTreeWidgetItem([section_name])
            section_item.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
            section_item.setExpanded(True)
            self._disk_tree.addTopLevelItem(section_item)

            for disk in disks:
                role_color = DISK_ROLE_COLORS.get(disk.suggested_role, "#888")
                item = QTreeWidgetItem([
                    f"/dev/{disk.name}",
                    disk.size_label,
                    disk.type_label,
                    disk.transport,
                    disk.model,
                    disk.suggested_role.value,
                ])
                item.setForeground(5, QBrush(QColor(role_color)))
                item.setData(0, Qt.ItemDataRole.UserRole, disk)
                section_item.addChild(item)

        for i in range(self._disk_tree.columnCount()):
            self._disk_tree.resizeColumnToContents(i)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str):
        self._log.append(f'<span style="color:#888;">{msg}</span>')

    @property
    def inventory(self) -> HostInventory | None:
        return self._inventory
