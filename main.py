"""
PVE Configurator — main window entry point.
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QLabel, QStatusBar, QVBoxLayout, QHBoxLayout, QToolBar, QComboBox, QPushButton,
    QSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtGui import QFont

from tabs.connect_tab   import ConnectTab
from tabs.discovery_tab import DiscoveryTab
from tabs.network_tab   import NetworkTab
from tabs.storage_tab   import StorageTab
from tabs.system_tab    import SystemTab
from core.sites         import get_profile_manager, get_host_profile_manager, SiteProfile
from tabs.profile_manager import ProfileManagerDialog, SaveProfileDialog
from tabs.review_apply_tab import ReviewApplyTab
from tabs.theme_picker   import ThemePickerDialog
from core.themes         import get_theme_manager


# ── Placeholder tab (for tabs not yet implemented) ────────────────────────────

class PlaceholderTab(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(label)
        lbl.setFont(QFont("Sans", 13))
        lbl.setStyleSheet("color: #888;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PVE Configurator")
        self.setMinimumSize(1100, 750)
        self._conn      = None
        self._inventory = None
        self._build_ui()
        self._setup_shortcuts()
        self._load_zoom()

    def _build_ui(self):
        # Apply saved theme (replaces hardcoded stylesheet)
        self._apply_theme()
        if False:  # old hardcoded stylesheet kept for reference only
         self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: none;
                background: #2b2b2b;
            }
            QTabBar::tab {
                background: #3c3c3c;
                color: #c0c0c0;
                padding: 8px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                min-width: 120px;
            }
            QTabBar::tab:selected {
                background: #2b2b2b;
                color: #ffffff;
                border-bottom: 2px solid #5c9bd6;
            }
            QTabBar::tab:disabled {
                color: #777;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                color: #e0e0e0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #c8c8c8;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background: #3c3c3c;
                border: 1px solid #606060;
                border-radius: 4px;
                color: #e8e8e8;
                padding: 4px 6px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #5c9bd6;
            }
            QLineEdit:read-only {
                background: #333;
                color: #b0b0b0;
            }
            QLineEdit::placeholder {
                color: #787878;
            }
            QPushButton {
                background: #3c3c3c;
                border: 1px solid #606060;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 5px 14px;
            }
            QPushButton:hover  { background: #4a4a4a; border-color: #5c9bd6; }
            QPushButton:pressed{ background: #555; }
            QPushButton:disabled { color: #777; border-color: #484848; }
            QPushButton:default {
                background: #1a5fa8;
                border-color: #5c9bd6;
                color: #fff;
            }
            QPushButton:default:hover { background: #2272c0; }
            QTreeWidget {
                background: #252525;
                alternate-background-color: #2d2d2d;
                border: 1px solid #505050;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QTreeWidget::item {
                color: #e0e0e0;
                padding: 2px 0px;
            }
            QTreeWidget::item:selected {
                background: #1a5fa8;
                color: #ffffff;
            }
            QTreeWidget::item:hover {
                background: #353535;
            }
            QHeaderView::section {
                background: #383838;
                color: #c8c8c8;
                border: none;
                border-right: 1px solid #505050;
                border-bottom: 1px solid #505050;
                padding: 4px 8px;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background: #2b2b2b;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #666; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QProgressBar {
                background: #3c3c3c;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #5c9bd6;
                border-radius: 3px;
            }
            QCheckBox { color: #e0e0e0; }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #606060;
                border-radius: 3px;
                background: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background: #1a5fa8;
                border-color: #5c9bd6;
            }
            QRadioButton { color: #e0e0e0; }
            QRadioButton::indicator {
                width: 14px; height: 14px;
                border: 1px solid #606060;
                border-radius: 7px;
                background: #3c3c3c;
            }
            QRadioButton::indicator:checked {
                background: #1a5fa8;
                border-color: #5c9bd6;
            }
            QSplitter::handle { background: #505050; }
            QTabWidget QWidget { background: #2b2b2b; }
            QScrollArea { background: #2b2b2b; border: none; }
            QDialog { background: #2b2b2b; color: #e0e0e0; }
            QMessageBox { background: #2b2b2b; color: #e0e0e0; }
            QComboBox QAbstractItemView {
                background: #3c3c3c;
                color: #e0e0e0;
                selection-background-color: #1a5fa8;
                border: 1px solid #606060;
            }
            QToolTip {
                background: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #606060;
                padding: 4px;
            }
        """)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

        # 1. Connect
        self._connect_tab = ConnectTab()
        self._connect_tab.connected.connect(self._on_connected)
        self._tabs.addTab(self._connect_tab, "1 · Connect")

        # 2. Discover
        self._discovery_tab = DiscoveryTab()
        self._discovery_tab.discovered.connect(self._on_discovered)
        self._tabs.addTab(self._discovery_tab, "2 · Discover")
        self._tabs.setTabEnabled(1, False)

        # 3. Network (real tab)
        self._network_tab = NetworkTab()
        self._tabs.addTab(self._network_tab, "3 · Network")
        self._tabs.setTabEnabled(2, False)

        # 4. Storage (real tab)
        self._storage_tab = StorageTab()
        self._tabs.addTab(self._storage_tab, "4 · Storage")
        self._tabs.setTabEnabled(3, False)

        # 5. System (real tab)
        self._system_tab = SystemTab()
        self._tabs.addTab(self._system_tab, "5 · System")
        self._tabs.setTabEnabled(4, False)

        # 6. Review & Apply (real tab)
        self._review_tab = ReviewApplyTab()
        self._review_tab.apply_completed.connect(self._on_apply_completed)
        self._tabs.addTab(self._review_tab, "6 · Review & Apply")
        self._tabs.setTabEnabled(5, False)

        # ── Site profile toolbar ─────────────────────────────────────────────
        toolbar = QToolBar("Site Profile")
        toolbar.setMovable(False)
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            "QToolBar { background: #222222; border-bottom: 1px solid #444; "
            "padding: 4px 8px; spacing: 4px; }"
            "QToolBar QLabel { color: #c0c0c0; font-size: 9pt; }"
            "QToolBar QComboBox { background: #3c3c3c; border: 1px solid #606060; "
            "border-radius: 4px; color: #e8e8e8; padding: 3px 6px; min-height: 26px; }"
            "QToolBar QPushButton { background: #3c3c3c; border: 1px solid #606060; "
            "border-radius: 4px; color: #e8e8e8; padding: 3px 10px; min-height: 26px; }"
            "QToolBar QPushButton:hover { background: #4a4a4a; border-color: #5c9bd6; }"
            "QToolBar QSplitter { background: #444; width: 1px; }"
        )
        combo_style = (
            "QComboBox { background: #3c3c3c; border: 1px solid #555; "
            "border-radius: 4px; color: #d4d4d4; padding: 3px 8px; }"
        )

        toolbar.addWidget(QLabel("Site: "))
        self._site_combo = QComboBox()
        self._site_combo.setMinimumWidth(180)
        self._site_combo.setStyleSheet(combo_style)
        site_mgr = get_profile_manager()
        for name in site_mgr.profile_names:
            self._site_combo.addItem(name)
        self._site_combo.currentTextChanged.connect(self._on_site_profile_changed)
        toolbar.addWidget(self._site_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("  Host type: "))
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(200)
        self._host_combo.setStyleSheet(combo_style)
        host_mgr = get_host_profile_manager()
        for name in host_mgr.profile_names:
            self._host_combo.addItem(name)
        self._host_combo.currentTextChanged.connect(self._on_host_profile_changed)
        toolbar.addWidget(self._host_combo)

        toolbar.addSeparator()
        manage_btn = QPushButton("Manage Profiles…")
        manage_btn.clicked.connect(self._open_profile_manager)
        toolbar.addWidget(manage_btn)

        toolbar.addSeparator()
        theme_btn = QPushButton("🎨  Theme")
        theme_btn.clicked.connect(self._open_theme_picker)
        toolbar.addWidget(theme_btn)

        toolbar.addSeparator()

        # Zoom controls — wrap in a QWidget so we control layout/spacing
        zoom_container = QWidget()
        zoom_container.setStyleSheet("QWidget { background: transparent; }")
        zoom_layout = QHBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(6, 0, 6, 0)
        zoom_layout.setSpacing(4)

        zoom_lbl = QLabel("Zoom:")
        zoom_lbl.setStyleSheet("color: #c0c0c0; font-size: 9pt;")
        zoom_layout.addWidget(zoom_lbl)

        btn_style = (
            "QPushButton { background: #4a4a4a; border: 1px solid #707070; "
            "border-radius: 4px; color: #ffffff; font-size: 13pt; font-weight: bold; "
            "min-width: 28px; min-height: 28px; max-width: 28px; max-height: 28px; "
            "padding: 0px; }"
            "QPushButton:hover  { background: #606060; border-color: #5c9bd6; }"
            "QPushButton:pressed{ background: #383838; }"
        )

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setToolTip("Zoom out  (Ctrl+-)")
        zoom_out_btn.setStyleSheet(btn_style)
        zoom_out_btn.clicked.connect(self._zoom_out)
        zoom_layout.addWidget(zoom_out_btn)

        self._zoom_spin = QSpinBox()
        self._zoom_spin.setRange(70, 200)
        self._zoom_spin.setValue(100)
        self._zoom_spin.setSuffix("%")
        self._zoom_spin.setFixedWidth(72)
        self._zoom_spin.setFixedHeight(28)
        self._zoom_spin.setToolTip("Font zoom level (Ctrl+0 to reset)")
        self._zoom_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_spin.setStyleSheet(
            "QSpinBox { background: #3c3c3c; border: 1px solid #707070; "
            "border-radius: 4px; color: #ffffff; font-size: 10pt; "
            "padding: 0px 2px; }"
            "QSpinBox::up-button, QSpinBox::down-button { width: 0px; }"
        )
        self._zoom_spin.valueChanged.connect(self._on_zoom_changed)
        zoom_layout.addWidget(self._zoom_spin)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setToolTip("Zoom in  (Ctrl+=)")
        zoom_in_btn.setStyleSheet(btn_style)
        zoom_in_btn.clicked.connect(self._zoom_in)
        zoom_layout.addWidget(zoom_in_btn)

        zoom_reset_btn = QPushButton("↺")
        zoom_reset_btn.setToolTip("Reset zoom to 100%  (Ctrl+0)")
        zoom_reset_btn.setStyleSheet(btn_style)
        zoom_reset_btn.clicked.connect(self._zoom_reset)
        zoom_layout.addWidget(zoom_reset_btn)

        toolbar.addWidget(zoom_container)
        self.addToolBar(toolbar)

        # Status bar
        self._statusbar = QStatusBar()
        self._statusbar.setStyleSheet("color: #b0b0b0; background: #252525;")
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Not connected")

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_connected(self, conn):
        self._conn = conn
        self._tabs.setTabEnabled(1, True)
        self._discovery_tab.set_connection(conn)
        self._storage_tab.set_connection(conn)
        self._system_tab.set_connection(conn)
        self._review_tab.set_connection(conn)
        self._tabs.setCurrentIndex(1)
        self._statusbar.showMessage(
            f"Connected to {conn.creds.host}  ·  {conn.creds.method.value}"
        )

    def _on_discovered(self, inv):
        self._inventory = inv
        # Wire inventory into tabs that need it
        self._network_tab.set_inventory(inv)
        self._storage_tab.set_inventory(inv)
        self._system_tab.set_inventory(inv)
        self._review_tab.set_inventory(inv)
        # Enable remaining tabs once we have inventory
        for i in range(2, self._tabs.count()):
            self._tabs.setTabEnabled(i, True)
        self._tabs.setCurrentIndex(2)
        self._statusbar.showMessage(
            f"Connected to {inv.hostname}  ·  "
            f"{len(inv.physical_nics)} NICs  ·  "
            f"{len(inv.configurable_disks)} disks"
        )
        # Wire all tab configs into review tab
        self._sync_review_tab()


    def _apply_theme(self):
        """Apply the active theme stylesheet to the application."""
        mgr = get_theme_manager()
        self.setStyleSheet(mgr.active.generate_stylesheet())

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self._zoom_reset)

    def _zoom_in(self):
        current = self._zoom_spin.value()
        self._zoom_spin.setValue(min(200, current + 10))

    def _zoom_out(self):
        current = self._zoom_spin.value()
        self._zoom_spin.setValue(max(70, current - 10))

    def _zoom_reset(self):
        self._zoom_spin.setValue(100)

    def _on_zoom_changed(self, pct: int):
        """Scale application font size by percentage."""
        base_pt = 10  # base font size in points
        scaled   = max(7, round(base_pt * pct / 100))
        font = QApplication.instance().font()
        font.setPointSize(scaled)
        QApplication.instance().setFont(font)
        # Re-apply theme so stylesheet em/pt values stay consistent
        self._apply_theme()
        # Save zoom preference
        from core.themes import get_theme_manager, CONFIG_DIR
        import json
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            prefs_file = CONFIG_DIR / "prefs.json"
            prefs = {}
            if prefs_file.exists():
                prefs = json.loads(prefs_file.read_text())
            prefs["zoom"] = pct
            prefs_file.write_text(json.dumps(prefs, indent=2))
        except Exception:
            pass

    def _load_zoom(self):
        """Restore saved zoom preference."""
        from core.themes import CONFIG_DIR
        import json
        try:
            prefs_file = CONFIG_DIR / "prefs.json"
            if prefs_file.exists():
                prefs = json.loads(prefs_file.read_text())
                zoom = prefs.get("zoom", 100)
                self._zoom_spin.blockSignals(True)
                self._zoom_spin.setValue(zoom)
                self._zoom_spin.blockSignals(False)
                self._on_zoom_changed(zoom)
        except Exception:
            pass

    def _open_theme_picker(self):
        dlg = ThemePickerDialog(self)
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.exec()

    def _on_theme_changed(self, name: str):
        self._apply_theme()

    def _on_tab_changed(self, index: int):
        """When switching to the Review tab, sync all configs."""
        if index == 5 and self._inventory is not None:
            self._sync_review_tab()

    def _sync_review_tab(self):
        """Push current config from all tabs into the review tab and refresh."""
        try:
            bonds, bridges, vlans = self._network_tab.get_network_config()
            interfaces = self._network_tab._preview.toPlainText()
            self._review_tab.set_network_config(bonds, bridges, vlans, interfaces)

            storage_configs, nfs_shares, iscsi_targets = self._storage_tab.get_storage_config()
            self._review_tab.set_storage_config(storage_configs, nfs_shares, iscsi_targets)

            sys_config = self._system_tab.get_system_config()
            self._review_tab.set_system_config(sys_config)

            self._review_tab.refresh()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _on_apply_completed(self, success: bool):
        if success:
            # Switch back to discovery tab and re-run discovery
            self._tabs.setCurrentIndex(1)
            self._discovery_tab._on_discover()

    def _on_site_profile_changed(self, name: str):
        mgr = get_profile_manager()
        profile = mgr.get(name)
        if profile:
            self._system_tab.apply_site_profile(profile)
            self._statusbar.showMessage(
                f"Site: {profile.name}  ·  {profile.timezone}"
            )

    def _on_host_profile_changed(self, name: str):
        mgr = get_host_profile_manager()
        profile = mgr.get(name)
        if profile:
            # Apply system options to system tab
            self._system_tab.apply_host_profile(profile)
            self._statusbar.showMessage(
                f"Host type: {profile.name}"
            )

    def _open_profile_manager(self):
        dlg = ProfileManagerDialog(self)
        dlg.profiles_changed.connect(self._refresh_profile_combos)
        dlg.exec()

    def _refresh_profile_combos(self):
        """Reload both combos after profile manager changes."""
        site_mgr = get_profile_manager()
        current_site = self._site_combo.currentText()
        self._site_combo.blockSignals(True)
        self._site_combo.clear()
        for name in site_mgr.profile_names:
            self._site_combo.addItem(name)
        idx = self._site_combo.findText(current_site)
        self._site_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._site_combo.blockSignals(False)

        host_mgr = get_host_profile_manager()
        current_host = self._host_combo.currentText()
        self._host_combo.blockSignals(True)
        self._host_combo.clear()
        for name in host_mgr.profile_names:
            self._host_combo.addItem(name)
        idx = self._host_combo.findText(current_host)
        self._host_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._host_combo.blockSignals(False)


# ── Entry point ───────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PVE Configurator")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
