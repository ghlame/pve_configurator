"""
Tab 4: Storage Configuration
Local disk assignment (LVM-thin, backup dir, ZFS) plus
shared storage scanner (NFS and iSCSI).
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QComboBox, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QSplitter, QTextEdit,
    QSpinBox, QCheckBox, QFrame, QScrollArea, QTabWidget,
    QStackedWidget, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush

from core.models import (
    HostInventory, DiskInfo, StorageRole, StorageConfig,
    NFSShare, ISCSITarget, ZFSLevel,
    ALL_CONTENT_TYPES, CONTENT_BY_ROLE,
    CONTENT_IMAGES, CONTENT_ROOTDIR, CONTENT_BACKUP,
    CONTENT_ISO, CONTENT_VZTMPL, CONTENT_SNIPPETS,
)
from core.connection import PVEConnection


# ── Content type labels ───────────────────────────────────────────────────────

CONTENT_LABELS = {
    CONTENT_IMAGES:   "images  (VM disks)",
    CONTENT_ROOTDIR:  "rootdir  (CT filesystems)",
    CONTENT_BACKUP:   "backup  (vzdump archives)",
    CONTENT_ISO:      "iso  (ISO images)",
    CONTENT_VZTMPL:   "vztmpl  (CT templates)",
    CONTENT_SNIPPETS: "snippets  (hook scripts)",
}

ROLE_COLORS = {
    StorageRole.OS_DISK:    "#5c9bd6",
    StorageRole.LOCAL_LVM:  "#4caf50",
    StorageRole.BACKUP_DIR: "#ff9800",
    StorageRole.ZFS_POOL:   "#9c27b0",
    StorageRole.EXCLUDE:    "#555555",
    StorageRole.UNASSIGNED: "#888888",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

class HLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #444;")


class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(QFont("Sans", 10, QFont.Weight.Bold))
        self.setStyleSheet("color: #ccc; margin-top: 4px;")


def _make_content_checkboxes(defaults: list[str]) -> dict[str, QCheckBox]:
    boxes = {}
    for ct in ALL_CONTENT_TYPES:
        cb = QCheckBox(CONTENT_LABELS[ct])
        cb.setChecked(ct in defaults)
        boxes[ct] = cb
    return boxes


# ── Scan workers ──────────────────────────────────────────────────────────────

class NFSScanWorker(QThread):
    result  = pyqtSignal(list, str)   # [export_paths], error_msg

    def __init__(self, conn: PVEConnection, server: str):
        super().__init__()
        self.conn   = conn
        self.server = server

    def run(self):
        try:
            out, err, rc = self.conn.ssh_run(
                f"showmount -e {self.server} --no-headers 2>&1"
            )
            if rc != 0 or "clnt_create" in out.lower() or "failed" in out.lower():
                self.result.emit([], out.strip() or err.strip())
                return
            exports = []
            for line in out.splitlines():
                parts = line.split()
                if parts:
                    exports.append(parts[0])
            self.result.emit(exports, "")
        except Exception as e:
            traceback.print_exc()
            self.result.emit([], str(e))


class ISCSIScanWorker(QThread):
    result = pyqtSignal(list, str)    # [iqn_strings], error_msg

    def __init__(self, conn: PVEConnection, portal: str):
        super().__init__()
        self.conn   = conn
        self.portal = portal

    def run(self):
        try:
            out, err, rc = self.conn.ssh_run(
                f"iscsiadm -m discovery -t sendtargets -p {self.portal} 2>&1"
            )
            if rc != 0:
                self.result.emit([], out.strip() or err.strip())
                return
            targets = []
            for line in out.splitlines():
                # Format: "ip:port,tpgt iqn...."
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("iqn."):
                    targets.append(parts[1])
            self.result.emit(targets, "")
        except Exception as e:
            traceback.print_exc()
            self.result.emit([], str(e))


# ── Disk assignment row ───────────────────────────────────────────────────────

class DiskAssignmentPanel(QWidget):
    """Top panel — one row per disk with role dropdown."""
    role_changed = pyqtSignal(str, object)   # disk_path, StorageRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, QComboBox] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = QWidget()
        hdr_row = QHBoxLayout(hdr)
        hdr_row.setContentsMargins(8, 4, 8, 4)
        for text, width in [("Device", 100), ("Size", 80), ("Type", 80),
                             ("Model", 200), ("Existing data", 140), ("Role", 0)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #999; font-size: 9pt;")
            if width:
                lbl.setFixedWidth(width)
            hdr_row.addWidget(lbl)
        hdr_row.addStretch()
        layout.addWidget(hdr)
        layout.addWidget(HLine())

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(2)
        layout.addLayout(self._rows_layout)
        layout.addStretch()

    def populate(self, disks: list[DiskInfo]):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows.clear()

        for disk in disks:
            row = self._make_row(disk)
            self._rows_layout.addWidget(row)

    def _make_row(self, disk: DiskInfo) -> QWidget:
        row = QWidget()
        row.setFixedHeight(36)
        is_protected = disk.is_pve_os or disk.is_usb
        bg = "#2f2f2f" if not is_protected else "#252525"
        row.setStyleSheet(
            f"QWidget {{ background: {bg}; border-radius: 4px; }}"
            f"QWidget:hover {{ background: #363636; }}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # Device
        dev_lbl = QLabel(disk.path)
        dev_lbl.setFixedWidth(100)
        dev_lbl.setFont(QFont("Monospace", 9))
        layout.addWidget(dev_lbl)

        # Size
        size_lbl = QLabel(disk.size_label)
        size_lbl.setFixedWidth(80)
        size_lbl.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(size_lbl)

        # Type
        type_lbl = QLabel(disk.type_label)
        type_lbl.setFixedWidth(80)
        type_lbl.setStyleSheet("color: #b0b0b0;")
        layout.addWidget(type_lbl)

        # Model
        model_lbl = QLabel(disk.model or "—")
        model_lbl.setFixedWidth(200)
        model_lbl.setStyleSheet("color: #999; font-size: 8pt;")
        layout.addWidget(model_lbl)

        # Existing data warning
        if disk.is_pve_os:
            warn = QLabel("⚑ OS disk — protected")
            warn.setStyleSheet("color: #5c9bd6; font-size: 8pt;")
        elif disk.has_partitions:
            warn = QLabel("⚠ Has existing partitions")
            warn.setStyleSheet("color: #ff9800; font-size: 8pt;")
        else:
            warn = QLabel("Clean")
            warn.setStyleSheet("color: #a0a0a0; font-size: 8pt;")
        warn.setFixedWidth(140)
        layout.addWidget(warn)

        # Role combo (disabled for protected disks)
        combo = QComboBox()
        for role in StorageRole:
            combo.addItem(role.value, role)
        idx = combo.findData(disk.role)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setEnabled(not is_protected)
        combo.currentIndexChanged.connect(
            lambda _i, d=disk.path, c=combo: self.role_changed.emit(d, c.currentData())
        )
        self._rows[disk.path] = combo
        layout.addWidget(combo, stretch=1)

        return row

    def get_assignments(self) -> dict[str, StorageRole]:
        return {path: combo.currentData() for path, combo in self._rows.items()}


# ── Config panels ─────────────────────────────────────────────────────────────

class LVMThinConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: StorageConfig | None = None
        self._content_boxes: dict[str, QCheckBox] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Local-SSD-01")
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Storage ID:", self._name_edit)

        self._vg_edit = QLineEdit()
        self._vg_edit.setPlaceholderText("e.g. pve-ssd-01  (VG name)")
        self._vg_edit.textChanged.connect(self._sync)
        layout.addRow("Volume Group:", self._vg_edit)

        self._pool_edit = QLineEdit("data")
        self._pool_edit.textChanged.connect(self._sync)
        layout.addRow("Thin pool name:", self._pool_edit)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(50, 100)
        self._size_spin.setValue(95)
        self._size_spin.setSuffix("% of VG")
        self._size_spin.setToolTip(
            "Percentage of the VG to allocate to the thin pool.\n"
            "Leave ~5% free for LVM metadata."
        )
        self._size_spin.valueChanged.connect(self._sync)
        layout.addRow("Pool size:", self._size_spin)

        self._wipe_cb = QCheckBox("Wipe disk before setup  (wipefs -a)")
        self._wipe_cb.setStyleSheet("color: #ff9800;")
        self._wipe_cb.stateChanged.connect(self._sync)
        layout.addRow("", self._wipe_cb)

        # Content types
        ct_group = QGroupBox("Content types")
        ct_layout = QVBoxLayout(ct_group)
        self._content_boxes = _make_content_checkboxes(
            [CONTENT_IMAGES, CONTENT_ROOTDIR]
        )
        for cb in self._content_boxes.values():
            cb.stateChanged.connect(self._sync)
            ct_layout.addWidget(cb)
        layout.addRow(ct_group)

    def load(self, config: StorageConfig):
        for w in [self._name_edit, self._vg_edit, self._pool_edit, self._size_spin]:
            w.blockSignals(True)
        self._config = config
        self._name_edit.setText(config.name)
        self._vg_edit.setText(config.vg_name)
        self._pool_edit.setText(config.thin_pool_name)
        self._size_spin.setValue(config.thin_pool_size_pct)
        self._wipe_cb.setChecked(config.wipe_disk)
        for ct, cb in self._content_boxes.items():
            cb.setChecked(ct in config.content_types)
        for w in [self._name_edit, self._vg_edit, self._pool_edit, self._size_spin]:
            w.blockSignals(False)

    def _sync(self):
        if not self._config:
            return
        self._config.name               = self._name_edit.text().strip()
        self._config.vg_name            = self._vg_edit.text().strip()
        self._config.thin_pool_name     = self._pool_edit.text().strip()
        self._config.thin_pool_size_pct = self._size_spin.value()
        self._config.wipe_disk          = self._wipe_cb.isChecked()
        self._config.content_types = [
            ct for ct, cb in self._content_boxes.items() if cb.isChecked()
        ]
        self.changed.emit()


class BackupDirConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: StorageConfig | None = None
        self._content_boxes: dict[str, QCheckBox] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Backup-HDD-01")
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Storage ID:", self._name_edit)

        self._mount_edit = QLineEdit()
        self._mount_edit.setPlaceholderText("e.g. /mnt/pve/backup-hdd-01")
        self._mount_edit.textChanged.connect(self._sync)
        layout.addRow("Mount point:", self._mount_edit)

        self._fs_combo = QComboBox()
        for fs in ["ext4", "xfs"]:
            self._fs_combo.addItem(fs)
        self._fs_combo.currentIndexChanged.connect(self._sync)
        layout.addRow("Filesystem:", self._fs_combo)

        self._wipe_cb = QCheckBox("Wipe disk before setup  (wipefs -a)")
        self._wipe_cb.setStyleSheet("color: #ff9800;")
        self._wipe_cb.stateChanged.connect(self._sync)
        layout.addRow("", self._wipe_cb)

        note = QLabel(
            "The disk will be partitioned, formatted, and added\n"
            "to /etc/fstab for persistent mounting."
        )
        note.setStyleSheet("color: #999; font-size: 8pt;")
        layout.addRow(note)

        ct_group = QGroupBox("Content types")
        ct_layout = QVBoxLayout(ct_group)
        self._content_boxes = _make_content_checkboxes(
            [CONTENT_BACKUP, CONTENT_ISO, CONTENT_VZTMPL]
        )
        for cb in self._content_boxes.values():
            cb.stateChanged.connect(self._sync)
            ct_layout.addWidget(cb)
        layout.addRow(ct_group)

    def load(self, config: StorageConfig):
        for w in [self._name_edit, self._mount_edit]:
            w.blockSignals(True)
        self._config = config
        self._name_edit.setText(config.name)
        mount = config.dir_path or f"/mnt/pve/{config.name.lower()}"
        self._mount_edit.setText(mount)
        self._wipe_cb.setChecked(config.wipe_disk)
        for ct, cb in self._content_boxes.items():
            cb.setChecked(ct in config.content_types)
        for w in [self._name_edit, self._mount_edit]:
            w.blockSignals(False)

    def _sync(self):
        if not self._config:
            return
        self._config.name       = self._name_edit.text().strip()
        self._config.dir_path   = self._mount_edit.text().strip()
        self._config.wipe_disk  = self._wipe_cb.isChecked()
        self._config.content_types = [
            ct for ct, cb in self._content_boxes.items() if cb.isChecked()
        ]
        self.changed.emit()


class ZFSConfigPanel(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: StorageConfig | None = None
        self._content_boxes: dict[str, QCheckBox] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. ZFS-Pool-01")
        self._name_edit.textChanged.connect(self._sync)
        layout.addRow("Storage ID:", self._name_edit)

        self._pool_edit = QLineEdit()
        self._pool_edit.setPlaceholderText("e.g. tank")
        self._pool_edit.textChanged.connect(self._sync)
        layout.addRow("ZFS pool name:", self._pool_edit)

        self._level_combo = QComboBox()
        for level in ZFSLevel:
            self._level_combo.addItem(level.value, level)
        self._level_combo.currentIndexChanged.connect(self._sync)
        layout.addRow("RAID level:", self._level_combo)

        self._wipe_cb = QCheckBox("Wipe disk(s) before setup  (wipefs -a)")
        self._wipe_cb.setStyleSheet("color: #ff9800;")
        self._wipe_cb.stateChanged.connect(self._sync)
        layout.addRow("", self._wipe_cb)

        note = QLabel(
            "ZFS will be configured via Proxmox's built-in ZFS support.\n"
            "The pool will be added directly as PVE storage."
        )
        note.setStyleSheet("color: #999; font-size: 8pt;")
        layout.addRow(note)

        ct_group = QGroupBox("Content types")
        ct_layout = QVBoxLayout(ct_group)
        self._content_boxes = _make_content_checkboxes(
            [CONTENT_IMAGES, CONTENT_ROOTDIR]
        )
        for cb in self._content_boxes.values():
            cb.stateChanged.connect(self._sync)
            ct_layout.addWidget(cb)
        layout.addRow(ct_group)

    def load(self, config: StorageConfig):
        for w in [self._name_edit, self._pool_edit]:
            w.blockSignals(True)
        self._config = config
        self._name_edit.setText(config.name)
        self._pool_edit.setText(config.zfs_pool_name or config.name.lower())
        self._wipe_cb.setChecked(config.wipe_disk)
        for ct, cb in self._content_boxes.items():
            cb.setChecked(ct in config.content_types)
        for w in [self._name_edit, self._pool_edit]:
            w.blockSignals(False)

    def _sync(self):
        if not self._config:
            return
        self._config.name          = self._name_edit.text().strip()
        self._config.zfs_pool_name = self._pool_edit.text().strip()
        self._config.zfs_level     = self._level_combo.currentData()
        self._config.wipe_disk     = self._wipe_cb.isChecked()
        self._config.content_types = [
            ct for ct, cb in self._content_boxes.items() if cb.isChecked()
        ]
        self.changed.emit()


# ── NFS shared storage panel ──────────────────────────────────────────────────

class NFSPanel(QWidget):
    shares_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn: PVEConnection | None = None
        self._shares: list[NFSShare] = []
        self._worker: NFSScanWorker | None = None
        self._build_ui()

    def set_connection(self, conn: PVEConnection):
        self._conn = conn

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Scan row
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("NAS IP:"))
        self._server_edit = QLineEdit()
        self._server_edit.setPlaceholderText("e.g. 10.80.10.50")
        scan_row.addWidget(self._server_edit, stretch=1)
        self._scan_btn = QPushButton("Scan for exports")
        self._scan_btn.setFixedHeight(28)
        self._scan_btn.clicked.connect(self._on_scan)
        scan_row.addWidget(self._scan_btn)
        layout.addLayout(scan_row)

        self._scan_status = QLabel("")
        self._scan_status.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        layout.addWidget(self._scan_status)

        # Available exports tree
        avail_label = SectionLabel("Available Exports")
        layout.addWidget(avail_label)
        self._exports_tree = QTreeWidget()
        self._exports_tree.setHeaderLabels(["Export path", "Add"])
        self._exports_tree.setMaximumHeight(120)
        self._exports_tree.setRootIsDecorated(False)
        layout.addWidget(self._exports_tree)

        layout.addWidget(HLine())

        # Configured shares
        configured_label = SectionLabel("Configured NFS Shares")
        layout.addWidget(configured_label)
        self._shares_tree = QTreeWidget()
        self._shares_tree.setHeaderLabels(
            ["Storage ID", "Server", "Export", "Content"]
        )
        self._shares_tree.setRootIsDecorated(False)
        self._shares_tree.itemClicked.connect(self._on_share_selected)
        layout.addWidget(self._shares_tree, stretch=1)

        # Share config form (shown when a share is selected)
        self._share_form_group = QGroupBox("Configure Share")
        form = QFormLayout(self._share_form_group)
        self._share_id_edit    = QLineEdit()
        self._share_id_edit.setPlaceholderText("e.g. NAS-Backup")
        self._share_mount_edit = QLineEdit()
        form.addRow("Storage ID:", self._share_id_edit)
        form.addRow("Mount point:", self._share_mount_edit)

        ct_row = QHBoxLayout()
        self._nfs_content_boxes = _make_content_checkboxes(
            [CONTENT_BACKUP, CONTENT_ISO, CONTENT_VZTMPL]
        )
        for cb in self._nfs_content_boxes.values():
            ct_row.addWidget(cb)
        form.addRow("Content:", ct_row)

        remove_btn = QPushButton("Remove share")
        remove_btn.clicked.connect(self._remove_selected_share)
        form.addRow("", remove_btn)
        self._share_form_group.setVisible(False)
        layout.addWidget(self._share_form_group)

        self._current_share: NFSShare | None = None

        # Wire form changes
        self._share_id_edit.textChanged.connect(self._sync_share)
        self._share_mount_edit.textChanged.connect(self._sync_share)
        for cb in self._nfs_content_boxes.values():
            cb.stateChanged.connect(self._sync_share)

    def _on_scan(self):
        server = self._server_edit.text().strip()
        if not server:
            self._scan_status.setText("Enter a NAS IP first.")
            return
        if not self._conn:
            self._scan_status.setText("Not connected to a PVE host.")
            return
        self._scan_btn.setEnabled(False)
        self._scan_status.setText(f"Scanning {server}…")
        self._exports_tree.clear()
        self._worker = NFSScanWorker(self._conn, server)
        self._worker.result.connect(self._on_scan_done)
        self._worker.start()

    def _on_scan_done(self, exports: list, error: str):
        self._scan_btn.setEnabled(True)
        if error:
            self._scan_status.setText(f"✗ {error}")
            return
        if not exports:
            self._scan_status.setText("No exports found.")
            return
        self._scan_status.setText(f"✓ Found {len(exports)} export(s)")
        server = self._server_edit.text().strip()
        for export in exports:
            item = QTreeWidgetItem([export, ""])
            self._exports_tree.addTopLevelItem(item)
            add_btn = QPushButton("+ Add")
            add_btn.setFixedHeight(22)
            add_btn.clicked.connect(
                lambda _checked=False, e=export, s=server: self._add_export(s, e)
            )
            self._exports_tree.setItemWidget(item, 1, add_btn)
        self._exports_tree.resizeColumnToContents(0)

    def _add_export(self, server: str, export: str):
        safe = export.replace("/", "-").strip("-")
        share = NFSShare(
            storage_id=f"NAS-{safe[:20]}",
            server=server,
            export=export,
        )
        self._shares.append(share)
        self._rebuild_shares_tree()
        self.shares_changed.emit()

    def _rebuild_shares_tree(self):
        self._shares_tree.clear()
        for share in self._shares:
            item = QTreeWidgetItem([
                share.storage_id,
                share.server,
                share.export,
                ", ".join(share.content_types),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, share)
            self._shares_tree.addTopLevelItem(item)
        for i in range(self._shares_tree.columnCount()):
            self._shares_tree.resizeColumnToContents(i)

    def _on_share_selected(self, item, _col):
        share = item.data(0, Qt.ItemDataRole.UserRole)
        if not share:
            return
        self._current_share = share
        for w in [self._share_id_edit, self._share_mount_edit]:
            w.blockSignals(True)
        self._share_id_edit.setText(share.storage_id)
        self._share_mount_edit.setText(share.mount_point)
        for ct, cb in self._nfs_content_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(ct in share.content_types)
            cb.blockSignals(False)
        for w in [self._share_id_edit, self._share_mount_edit]:
            w.blockSignals(False)
        self._share_form_group.setVisible(True)

    def _sync_share(self):
        if not self._current_share:
            return
        self._current_share.storage_id  = self._share_id_edit.text().strip()
        self._current_share.mount_point  = self._share_mount_edit.text().strip()
        self._current_share.content_types = [
            ct for ct, cb in self._nfs_content_boxes.items() if cb.isChecked()
        ]
        self._rebuild_shares_tree()
        self.shares_changed.emit()

    def _remove_selected_share(self):
        if self._current_share:
            self._shares = [s for s in self._shares if s is not self._current_share]
            self._current_share = None
            self._share_form_group.setVisible(False)
            self._rebuild_shares_tree()
            self.shares_changed.emit()

    @property
    def shares(self) -> list[NFSShare]:
        return self._shares

    def set_server(self, ip: str) -> None:
        """Pre-populate the NAS IP field from a site profile."""
        self._server_edit.setText(ip)


# ── iSCSI shared storage panel ────────────────────────────────────────────────

class ISCSIPanel(QWidget):
    targets_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn: PVEConnection | None = None
        self._targets: list[ISCSITarget] = []
        self._worker: ISCSIScanWorker | None = None
        self._build_ui()

    def set_connection(self, conn: PVEConnection):
        self._conn = conn

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Scan row
        scan_row = QHBoxLayout()
        scan_row.addWidget(QLabel("Target portal IP:"))
        self._portal_edit = QLineEdit()
        self._portal_edit.setPlaceholderText("e.g. 10.80.10.50")
        scan_row.addWidget(self._portal_edit, stretch=1)
        self._scan_btn = QPushButton("Discover targets")
        self._scan_btn.setFixedHeight(28)
        self._scan_btn.clicked.connect(self._on_scan)
        scan_row.addWidget(self._scan_btn)
        layout.addLayout(scan_row)

        self._scan_status = QLabel("")
        self._scan_status.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        layout.addWidget(self._scan_status)

        # Discovered targets
        avail_label = SectionLabel("Discovered Targets")
        layout.addWidget(avail_label)
        self._targets_avail_tree = QTreeWidget()
        self._targets_avail_tree.setHeaderLabels(["IQN", "Add"])
        self._targets_avail_tree.setMaximumHeight(120)
        self._targets_avail_tree.setRootIsDecorated(False)
        layout.addWidget(self._targets_avail_tree)

        layout.addWidget(HLine())

        # Configured targets
        configured_label = SectionLabel("Configured iSCSI Targets")
        layout.addWidget(configured_label)
        self._configured_tree = QTreeWidget()
        self._configured_tree.setHeaderLabels(["Storage ID", "Portal", "IQN", "LVM on top"])
        self._configured_tree.setRootIsDecorated(False)
        self._configured_tree.itemClicked.connect(self._on_target_selected)
        layout.addWidget(self._configured_tree, stretch=1)

        # Target config form
        self._target_form_group = QGroupBox("Configure Target")
        form = QFormLayout(self._target_form_group)
        self._target_id_edit = QLineEdit()
        self._target_id_edit.setPlaceholderText("e.g. iSCSI-SAN-01")
        form.addRow("Storage ID:", self._target_id_edit)

        self._lvm_cb = QCheckBox("Add LVM-thin layer on top of this target")
        self._lvm_cb.setToolTip(
            "Creates an LVM VG on the iSCSI target so PVE can use it\n"
            "for VM images and CT filesystems."
        )
        self._lvm_cb.stateChanged.connect(self._on_lvm_toggled)
        form.addRow("", self._lvm_cb)

        self._lvm_id_edit = QLineEdit()
        self._lvm_id_edit.setPlaceholderText("e.g. iSCSI-LVM-01")
        self._lvm_id_edit.setEnabled(False)
        form.addRow("LVM Storage ID:", self._lvm_id_edit)

        remove_btn = QPushButton("Remove target")
        remove_btn.clicked.connect(self._remove_selected_target)
        form.addRow("", remove_btn)
        self._target_form_group.setVisible(False)
        layout.addWidget(self._target_form_group)

        self._current_target: ISCSITarget | None = None

        self._target_id_edit.textChanged.connect(self._sync_target)
        self._lvm_id_edit.textChanged.connect(self._sync_target)

    def _on_scan(self):
        portal = self._portal_edit.text().strip()
        if not portal:
            self._scan_status.setText("Enter a portal IP first.")
            return
        if not self._conn:
            self._scan_status.setText("Not connected to a PVE host.")
            return
        self._scan_btn.setEnabled(False)
        self._scan_status.setText(f"Discovering targets on {portal}…")
        self._targets_avail_tree.clear()
        self._worker = ISCSIScanWorker(self._conn, portal)
        self._worker.result.connect(self._on_scan_done)
        self._worker.start()

    def _on_scan_done(self, targets: list, error: str):
        self._scan_btn.setEnabled(True)
        if error:
            self._scan_status.setText(f"✗ {error}")
            return
        if not targets:
            self._scan_status.setText("No targets found.")
            return
        self._scan_status.setText(f"✓ Found {len(targets)} target(s)")
        portal = self._portal_edit.text().strip()
        for iqn in targets:
            item = QTreeWidgetItem([iqn, ""])
            self._targets_avail_tree.addTopLevelItem(item)
            add_btn = QPushButton("+ Add")
            add_btn.setFixedHeight(22)
            add_btn.clicked.connect(
                lambda _checked=False, i=iqn, p=portal: self._add_target(p, i)
            )
            self._targets_avail_tree.setItemWidget(item, 1, add_btn)
        self._targets_avail_tree.resizeColumnToContents(0)

    def _add_target(self, portal: str, iqn: str):
        short = iqn.split(":")[-1][:20] if ":" in iqn else iqn[:20]
        target = ISCSITarget(
            storage_id=f"iSCSI-{short}",
            portal=portal,
            target=iqn,
        )
        self._targets.append(target)
        self._rebuild_tree()
        self.targets_changed.emit()

    def _rebuild_tree(self):
        self._configured_tree.clear()
        for t in self._targets:
            item = QTreeWidgetItem([
                t.storage_id, t.portal,
                t.target[:50],
                "Yes" if t.add_lvm else "No",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, t)
            self._configured_tree.addTopLevelItem(item)
        for i in range(self._configured_tree.columnCount()):
            self._configured_tree.resizeColumnToContents(i)

    def _on_target_selected(self, item, _col):
        target = item.data(0, Qt.ItemDataRole.UserRole)
        if not target:
            return
        self._current_target = target
        for w in [self._target_id_edit, self._lvm_id_edit]:
            w.blockSignals(True)
        self._target_id_edit.setText(target.storage_id)
        self._lvm_cb.setChecked(target.add_lvm)
        self._lvm_id_edit.setText(target.lvm_storage_id)
        self._lvm_id_edit.setEnabled(target.add_lvm)
        for w in [self._target_id_edit, self._lvm_id_edit]:
            w.blockSignals(False)
        self._target_form_group.setVisible(True)

    def _on_lvm_toggled(self, state):
        self._lvm_id_edit.setEnabled(bool(state))
        self._sync_target()

    def _sync_target(self):
        if not self._current_target:
            return
        self._current_target.storage_id     = self._target_id_edit.text().strip()
        self._current_target.add_lvm         = self._lvm_cb.isChecked()
        self._current_target.lvm_storage_id  = self._lvm_id_edit.text().strip()
        self._rebuild_tree()
        self.targets_changed.emit()

    def _remove_selected_target(self):
        if self._current_target:
            self._targets = [t for t in self._targets if t is not self._current_target]
            self._current_target = None
            self._target_form_group.setVisible(False)
            self._rebuild_tree()
            self.targets_changed.emit()

    @property
    def targets(self) -> list[ISCSITarget]:
        return self._targets


# ── Command preview generator ─────────────────────────────────────────────────

def generate_storage_commands(
    disks: list[DiskInfo],
    configs: list[StorageConfig],
    nfs_shares: list[NFSShare],
    iscsi_targets: list[ISCSITarget],
) -> str:
    lines = ["#!/bin/bash", "# Storage configuration commands", "# Generated by PVE Configurator", ""]
    config_map = {c.disk_path: c for c in configs}

    for disk in disks:
        if disk.is_pve_os or disk.is_usb or disk.role in (
            StorageRole.UNASSIGNED, StorageRole.EXCLUDE, StorageRole.OS_DISK
        ):
            continue
        cfg = config_map.get(disk.path)
        if not cfg:
            continue

        lines.append(f"# ── {disk.path} ({disk.size_label} {disk.type_label}) ──")

        if cfg.wipe_disk:
            lines.append(f"wipefs -a {disk.path}")

        if disk.role == StorageRole.LOCAL_LVM:
            vg = cfg.vg_name or f"pve-{cfg.name.lower()}"
            pool = cfg.thin_pool_name or "data"
            pct  = cfg.thin_pool_size_pct
            content = ",".join(cfg.content_types)
            lines += [
                f"pvcreate {disk.path}",
                f"vgcreate {vg} {disk.path}",
                f"lvcreate -l {pct}%FREE -T {vg}/{pool}",
                f"pvesm add lvmthin {cfg.name} --vgname {vg} --thinpool {pool} --content {content}",
            ]

        elif disk.role == StorageRole.BACKUP_DIR:
            mount = cfg.dir_path or f"/mnt/pve/{cfg.name.lower()}"
            content = ",".join(cfg.content_types)
            lines += [
                f"parted -s {disk.path} mklabel gpt",
                f"parted -s {disk.path} mkpart primary 0% 100%",
                f"mkfs.ext4 {disk.path}1",
                f"mkdir -p {mount}",
                f"echo '{disk.path}1  {mount}  ext4  defaults  0  2' >> /etc/fstab",
                f"mount {mount}",
                f"pvesm add dir {cfg.name} --path {mount} --content {content}",
            ]

        elif disk.role == StorageRole.ZFS_POOL:
            pool  = cfg.zfs_pool_name or cfg.name.lower()
            level = cfg.zfs_level.value if cfg.zfs_level else "single"
            raid  = "" if level == "single" else level
            content = ",".join(cfg.content_types)
            lines += [
                f"zpool create {pool} {raid} {disk.path}",
                f"pvesm add zfspool {cfg.name} --pool {pool} --content {content}",
            ]

        lines.append("")

    # NFS shares
    if nfs_shares:
        lines.append("# ── NFS Shares ──")
        for share in nfs_shares:
            content = ",".join(share.content_types)
            opts = f" --options {share.options}" if share.options else ""
            lines.append(
                f"pvesm add nfs {share.storage_id} "
                f"--server {share.server} --export {share.export} "
                f"--content {content}{opts}"
            )
        lines.append("")

    # iSCSI targets
    if iscsi_targets:
        lines.append("# ── iSCSI Targets ──")
        for target in iscsi_targets:
            lines.append(
                f"pvesm add iscsi {target.storage_id} "
                f"--portal {target.portal} --target {target.target} "
                f"--content none"
            )
            if target.add_lvm and target.lvm_storage_id:
                lines += [
                    f"# Allow time for iSCSI device to appear, then:",
                    f"pvesm add lvmthin {target.lvm_storage_id} "
                    f"--vgname pve-{target.lvm_storage_id.lower()} "
                    f"--thinpool data --content images,rootdir",
                ]
        lines.append("")

    if len(lines) <= 4:
        return "# No storage configured yet."
    return "\n".join(lines)


# ── Storage Tab ───────────────────────────────────────────────────────────────

class StorageTab(QWidget):
    config_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inventory: HostInventory | None = None
        self._conn:      PVEConnection | None = None
        self._configs:   list[StorageConfig]  = []
        self._build_ui()

    def set_inventory(self, inv: HostInventory):
        self._inventory = inv
        self._disk_panel.populate(inv.disks)
        self._build_initial_configs(inv)
        self._refresh_preview()

    def apply_site_profile(self, profile) -> None:
        """Pre-populate NAS IP from site profile."""
        if profile.nfs_server:
            self._nfs_panel.set_server(profile.nfs_server)

    def set_connection(self, conn: PVEConnection):
        self._conn = conn
        self._nfs_panel.set_connection(conn)
        self._iscsi_panel.set_connection(conn)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(16, 16, 16, 16)

        # Title
        title_row = QHBoxLayout()
        title = QLabel("Storage Configuration")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        root.addLayout(title_row)

        hint = QLabel(
            "Assign roles to local disks, then configure each one. "
            "Add NFS or iSCSI shared storage via the Shared Storage tab. "
            "The command preview shows exactly what will run on the host."
        )
        hint.setStyleSheet("color: #b0b0b0;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── Vertical splitter ─────────────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setStyleSheet("QSplitter::handle { background: #444; height: 4px; }")

        # ── Section 1: Disk assignment ────────────────────────────────────────
        disk_group = QGroupBox("Local Disk Assignment  (drag divider to resize)")
        disk_layout = QVBoxLayout(disk_group)
        disk_layout.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._disk_panel = DiskAssignmentPanel()
        self._disk_panel.role_changed.connect(self._on_role_changed)
        scroll.setWidget(self._disk_panel)
        disk_layout.addWidget(scroll)
        vsplit.addWidget(disk_group)

        # ── Section 2: Local config + shared storage tabs ─────────────────────
        mid_widget = QWidget()
        mid_layout = QHBoxLayout(mid_widget)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(0)

        # Left: storage object tree
        left = QWidget()
        left.setMaximumWidth(260)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 4, 0, 0)
        left_layout.setSpacing(4)

        left_layout.addWidget(SectionLabel("Local Storage Objects"))
        self._storage_tree = QTreeWidget()
        self._storage_tree.setHeaderLabel("Configured Storage")
        self._storage_tree.itemClicked.connect(self._on_storage_selected)
        left_layout.addWidget(self._storage_tree)
        mid_layout.addWidget(left)

        # Right: tabbed panel (local config + NFS + iSCSI)
        right_tabs = QTabWidget()
        right_tabs.setTabPosition(QTabWidget.TabPosition.North)
        right_tabs.setStyleSheet("""
            QTabBar::tab { padding: 5px 14px; min-width: 80px; }
        """)

        # Local config stack
        self._config_stack = QStackedWidget()
        placeholder = QLabel("← Select a storage object to configure it.")
        placeholder.setStyleSheet("color: #888;")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._config_stack.addWidget(placeholder)   # 0

        self._lvm_panel = LVMThinConfigPanel()
        self._lvm_panel.changed.connect(self._refresh_preview)
        self._config_stack.addWidget(self._lvm_panel)  # 1

        self._backup_panel = BackupDirConfigPanel()
        self._backup_panel.changed.connect(self._refresh_preview)
        self._config_stack.addWidget(self._backup_panel)  # 2

        self._zfs_panel = ZFSConfigPanel()
        self._zfs_panel.changed.connect(self._refresh_preview)
        self._config_stack.addWidget(self._zfs_panel)  # 3

        local_container = QWidget()
        local_layout = QVBoxLayout(local_container)
        local_layout.setContentsMargins(8, 4, 0, 0)
        self._config_section_label = SectionLabel("Select a storage object")
        local_layout.addWidget(self._config_section_label)
        local_layout.addWidget(self._config_stack, stretch=1)
        right_tabs.addTab(local_container, "Local")

        # NFS tab
        self._nfs_panel = NFSPanel()
        self._nfs_panel.shares_changed.connect(self._refresh_preview)
        right_tabs.addTab(self._nfs_panel, "NFS")

        # iSCSI tab
        self._iscsi_panel = ISCSIPanel()
        self._iscsi_panel.targets_changed.connect(self._refresh_preview)
        right_tabs.addTab(self._iscsi_panel, "iSCSI")

        mid_layout.addWidget(right_tabs, stretch=1)
        vsplit.addWidget(mid_widget)

        # ── Section 3: Command preview ────────────────────────────────────────
        preview_group = QGroupBox("Command Preview  (read-only — shown to operator before apply)")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("Monospace", 9))
        self._preview.setStyleSheet("background: #1a1a1a; color: #98c379; border: none;")
        preview_layout.addWidget(self._preview)
        vsplit.addWidget(preview_group)

        vsplit.setSizes([180, 420, 180])
        root.addWidget(vsplit, stretch=1)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_role_changed(self, disk_path: str, role: StorageRole):
        if self._inventory:
            for disk in self._inventory.disks:
                if disk.path == disk_path:
                    disk.role = role
                    break
        # Update or create StorageConfig for this disk
        existing = next((c for c in self._configs if c.disk_path == disk_path), None)
        if role in (StorageRole.UNASSIGNED, StorageRole.EXCLUDE, StorageRole.OS_DISK):
            self._configs = [c for c in self._configs if c.disk_path != disk_path]
        else:
            if existing:
                existing.role = role
            else:
                disk = next((d for d in self._inventory.disks if d.path == disk_path), None)
                if disk:
                    cfg = self._make_config(disk, role)
                    self._configs.append(cfg)
        self._rebuild_storage_tree()
        self._refresh_preview()

    def _on_storage_selected(self, item, _col):
        cfg = item.data(0, Qt.ItemDataRole.UserRole)
        if not cfg:
            return
        self._config_section_label.setText(f"{cfg.name}  ({cfg.disk_path})")
        if cfg.role == StorageRole.LOCAL_LVM:
            self._lvm_panel.load(cfg)
            self._config_stack.setCurrentIndex(1)
        elif cfg.role == StorageRole.BACKUP_DIR:
            self._backup_panel.load(cfg)
            self._config_stack.setCurrentIndex(2)
        elif cfg.role == StorageRole.ZFS_POOL:
            self._zfs_panel.load(cfg)
            self._config_stack.setCurrentIndex(3)

    def _rebuild_storage_tree(self):
        self._storage_tree.clear()
        role_sections = {
            StorageRole.LOCAL_LVM:  "LVM-thin Pools",
            StorageRole.BACKUP_DIR: "Backup Directories",
            StorageRole.ZFS_POOL:   "ZFS Pools",
        }
        sections: dict[str, QTreeWidgetItem] = {}
        for cfg in self._configs:
            sec_name = role_sections.get(cfg.role, "Other")
            if sec_name not in sections:
                sec_item = QTreeWidgetItem([sec_name])
                sec_item.setFont(0, QFont("Sans", 9, QFont.Weight.Bold))
                sec_item.setExpanded(True)
                self._storage_tree.addTopLevelItem(sec_item)
                sections[sec_name] = sec_item
            label = f"{cfg.name}  {cfg.disk_path}"
            child = QTreeWidgetItem([label])
            child.setData(0, Qt.ItemDataRole.UserRole, cfg)
            color = ROLE_COLORS.get(cfg.role, "#888")
            child.setForeground(0, QBrush(QColor(color)))
            sections[sec_name].addChild(child)

    def _refresh_preview(self):
        if not self._inventory:
            return
        text = generate_storage_commands(
            self._inventory.disks,
            self._configs,
            self._nfs_panel.shares,
            self._iscsi_panel.targets,
        )
        self._preview.setPlainText(text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_initial_configs(self, inv: HostInventory):
        self._configs = []
        for disk in inv.disks:
            if disk.role not in (
                StorageRole.UNASSIGNED, StorageRole.EXCLUDE, StorageRole.OS_DISK
            ):
                self._configs.append(self._make_config(disk, disk.role))
        self._rebuild_storage_tree()

    def _make_config(self, disk: DiskInfo, role: StorageRole) -> StorageConfig:
        if role == StorageRole.LOCAL_LVM:
            ssd_n = sum(1 for c in self._configs if c.role == StorageRole.LOCAL_LVM)
            name  = f"Local-SSD-{ssd_n + 1:02d}"
            return StorageConfig(
                name=name, disk_path=disk.path, role=role,
                vg_name=f"pve-{name.lower()}",
                thin_pool_name="data",
                thin_pool_size_pct=95,
                content_types=[CONTENT_IMAGES, CONTENT_ROOTDIR],
            )
        elif role == StorageRole.BACKUP_DIR:
            hdd_n = sum(1 for c in self._configs if c.role == StorageRole.BACKUP_DIR)
            name  = f"Backup-HDD-{hdd_n + 1:02d}"
            return StorageConfig(
                name=name, disk_path=disk.path, role=role,
                dir_path=f"/mnt/pve/{name.lower()}",
                content_types=[CONTENT_BACKUP, CONTENT_ISO, CONTENT_VZTMPL],
            )
        elif role == StorageRole.ZFS_POOL:
            zfs_n = sum(1 for c in self._configs if c.role == StorageRole.ZFS_POOL)
            name  = f"ZFS-Pool-{zfs_n + 1:02d}"
            return StorageConfig(
                name=name, disk_path=disk.path, role=role,
                zfs_pool_name=f"tank{zfs_n + 1 if zfs_n else ''}",
                content_types=[CONTENT_IMAGES, CONTENT_ROOTDIR],
            )
        return StorageConfig(name="", disk_path=disk.path, role=role)

    def get_storage_config(self) -> tuple:
        """Return (local_configs, nfs_shares, iscsi_targets) for Review tab."""
        return self._configs, self._nfs_panel.shares, self._iscsi_panel.targets
