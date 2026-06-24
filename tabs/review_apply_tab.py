"""
Tab 6: Review & Apply
Shows a full summary of all planned changes, requires operator
confirmation, then executes via ApplyWorker with live progress.
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QPushButton, QTextEdit,
    QCheckBox, QSplitter, QScrollArea, QFrame,
    QProgressBar, QTreeWidget, QTreeWidgetItem,
    QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush

from core.models import (
    HostInventory, StorageConfig, NFSShare, ISCSITarget,
    BondConfig, BridgeConfig, VLANConfig,
)
from core.connection import PVEConnection
from core.apply_engine import (
    CommandBuilder, ApplyWorker, ApplyCommand,
    CommandSection, SECTION_COLORS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

class HLine(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #444;")


class SummaryCard(QGroupBox):
    """Small card showing change count for a section."""
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(80)
        self.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {color}; border-radius: 6px; "
            f"background: #252525; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10pt;")
        self._count_lbl = QLabel("0 changes")
        self._count_lbl.setStyleSheet("color: #b0b0b0; font-size: 9pt;")
        layout.addWidget(self._title_lbl)
        layout.addWidget(self._count_lbl)

    def set_count(self, n: int):
        self._count_lbl.setText(f"{n} command{'s' if n != 1 else ''}")
        color = self._color if n > 0 else "#555"
        self._count_lbl.setStyleSheet(f"color: {color}; font-size: 9pt;")


# ── Review & Apply Tab ────────────────────────────────────────────────────────

class ReviewApplyTab(QWidget):
    apply_completed = pyqtSignal(bool)   # success

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn:      PVEConnection | None = None
        self._inventory: HostInventory | None = None
        self._commands:  list[ApplyCommand]   = []
        self._worker:    ApplyWorker | None   = None
        self._system_config:  dict = {}
        self._storage_configs: list[StorageConfig] = []
        self._nfs_shares:      list[NFSShare] = []
        self._iscsi_targets:   list[ISCSITarget] = []
        self._bonds:    list[BondConfig]  = []
        self._bridges:  list[BridgeConfig] = []
        self._vlans:    list[VLANConfig]  = []
        self._interfaces_content: str = ""
        self._build_ui()

    def set_connection(self, conn: PVEConnection):
        self._conn = conn

    def set_inventory(self, inv: HostInventory):
        self._inventory = inv

    def set_network_config(self, bonds, bridges, vlans, interfaces_content):
        self._bonds    = bonds
        self._bridges  = bridges
        self._vlans    = vlans
        self._interfaces_content = interfaces_content

    def set_storage_config(self, configs, nfs_shares, iscsi_targets):
        self._storage_configs = configs
        self._nfs_shares      = nfs_shares
        self._iscsi_targets   = iscsi_targets

    def set_system_config(self, config: dict):
        self._system_config = config

    def refresh(self):
        """Rebuild command list from current configuration state."""
        if not self._inventory:
            return
        builder = CommandBuilder(
            inv=self._inventory,
            system_config=self._system_config,
            storage_configs=self._storage_configs,
            nfs_shares=self._nfs_shares,
            iscsi_targets=self._iscsi_targets,
            bonds=self._bonds,
            bridges=self._bridges,
            vlans=self._vlans,
            interfaces_content=self._interfaces_content,
            hostname=self._inventory.hostname,
        )
        self._commands = builder.build()
        self._populate_command_tree()
        self._update_summary_cards()
        self._update_apply_button_state()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(16, 16, 16, 16)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Review & Apply")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        title_row.addWidget(title)
        title_row.addStretch()
        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.setFixedHeight(28)
        self._refresh_btn.clicked.connect(self.refresh)
        title_row.addWidget(self._refresh_btn)
        root.addLayout(title_row)

        hint = QLabel(
            "Review all planned changes below. Check all three confirmation boxes "
            "before Apply becomes available."
        )
        hint.setStyleSheet("color: #b0b0b0;")
        root.addWidget(hint)

        # ── Vertical splitter ─────────────────────────────────────────────────
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setStyleSheet("QSplitter::handle { background: #444; height: 4px; }")

        # ── Top: summary cards + command tree ─────────────────────────────────
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Summary cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._cards: dict[CommandSection, SummaryCard] = {}
        card_specs = [
            (CommandSection.REPOS,    "Repositories",  "#5c9bd6"),
            (CommandSection.PACKAGES, "Packages",      "#5c9bd6"),
            (CommandSection.SYSTEM,   "System",        "#9c27b0"),
            (CommandSection.STORAGE,  "Storage",       "#ff9800"),
            (CommandSection.NETWORK,  "Network",       "#4caf50"),
            (CommandSection.PVE,      "PVE Settings",  "#5c9bd6"),
            (CommandSection.USERS,    "Users",         "#9c27b0"),
            (CommandSection.CLUSTER,  "Cluster",       "#f44336"),
        ]
        for section, label, color in card_specs:
            card = SummaryCard(label, color)
            self._cards[section] = card
            cards_row.addWidget(card)
        top_layout.addLayout(cards_row)

        # Command tree
        cmd_label = QLabel("Commands to execute  (in order):")
        cmd_label.setStyleSheet("color: #ccc; font-weight: bold;")
        top_layout.addWidget(cmd_label)

        self._cmd_tree = QTreeWidget()
        self._cmd_tree.setHeaderLabels(["#", "Section", "Description", "Command"])
        self._cmd_tree.setAlternatingRowColors(True)
        self._cmd_tree.setRootIsDecorated(False)
        self._cmd_tree.setFont(QFont("Monospace", 8))
        self._cmd_tree.setStyleSheet(
            "QTreeWidget { background: #1e1e1e; alternate-background-color: #222; "
            "border: 1px solid #444; border-radius: 4px; }"
            "QHeaderView::section { background: #2f2f2f; color: #888; "
            "border: none; padding: 4px 6px; }"
        )
        top_layout.addWidget(self._cmd_tree, stretch=1)
        vsplit.addWidget(top_widget)

        # ── Bottom: confirmations + apply + progress ──────────────────────────
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 8, 0, 0)
        bottom_layout.setSpacing(8)

        # Confirmation checkboxes
        confirm_group = QGroupBox("Confirmation Required")
        confirm_layout = QVBoxLayout(confirm_group)
        confirm_layout.setSpacing(6)

        self._check_reviewed = QCheckBox(
            "I have reviewed all commands listed above and understand what they will do."
        )
        self._check_network = QCheckBox(
            "I understand that network changes may briefly interrupt SSH connectivity "
            "during apply. The tool will automatically attempt to reconnect."
        )
        self._check_backup = QCheckBox(
            "Configuration files will be backed up before changes are applied. "
            "For VMs, a snapshot is recommended before proceeding."
        )
        for cb in [self._check_reviewed, self._check_network, self._check_backup]:
            cb.stateChanged.connect(self._update_apply_button_state)
            confirm_layout.addWidget(cb)

        bottom_layout.addWidget(confirm_group)

        # Apply row
        apply_row = QHBoxLayout()
        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setVisible(False)
        self._stop_btn.setStyleSheet(
            "QPushButton { background: #5a1a1a; border: 1px solid #f44; "
            "border-radius: 4px; color: #f44; padding: 5px 14px; }"
            "QPushButton:hover { background: #6a2a2a; }"
        )
        self._stop_btn.clicked.connect(self._on_stop)

        self._apply_btn = QPushButton("▶  Apply Now")
        self._apply_btn.setFixedHeight(36)
        self._apply_btn.setEnabled(False)
        self._apply_btn.setStyleSheet(
            "QPushButton { background: #1a5a1a; border: 1px solid #4caf50; "
            "border-radius: 4px; color: #4caf50; font-weight: bold; padding: 5px 18px; }"
            "QPushButton:hover { background: #2a6a2a; }"
            "QPushButton:disabled { background: #252525; border-color: #444; color: #555; }"
        )
        self._apply_btn.clicked.connect(self._on_apply)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setVisible(False)

        apply_row.addWidget(self._stop_btn)
        apply_row.addStretch()
        apply_row.addWidget(self._progress_bar, stretch=1)
        apply_row.addWidget(self._apply_btn)
        bottom_layout.addLayout(apply_row)

        # Progress log
        log_label = QLabel("Progress log:")
        log_label.setStyleSheet("color: #ccc; font-weight: bold;")
        bottom_layout.addWidget(log_label)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Monospace", 8))
        self._log.setStyleSheet(
            "background: #0d0d0d; color: #d4d4d4; border: 1px solid #333; border-radius: 4px;"
        )
        bottom_layout.addWidget(self._log, stretch=1)

        # Post-apply actions (hidden until complete)
        self._post_apply_widget = QWidget()
        post_row = QHBoxLayout(self._post_apply_widget)
        post_row.setContentsMargins(0, 0, 0, 0)
        self._rediscover_btn = QPushButton("↻  Re-discover host")
        self._rediscover_btn.setFixedHeight(28)
        self._rediscover_btn.clicked.connect(self._on_rediscover)
        self._reapply_btn = QPushButton("▶  Re-apply")
        self._reapply_btn.setFixedHeight(28)
        self._reapply_btn.setStyleSheet(
            "QPushButton { background: #1a3a5a; border: 1px solid #5c9bd6; color: #fff; }"
            "QPushButton:hover { background: #2a4a6a; }"
        )
        self._reapply_btn.clicked.connect(self._on_reapply)
        self._save_log_btn = QPushButton("💾  Save log")
        self._save_log_btn.setFixedHeight(28)
        self._save_log_btn.clicked.connect(self._on_save_log)
        post_row.addWidget(QLabel("Apply complete:"))
        post_row.addWidget(self._rediscover_btn)
        post_row.addWidget(self._reapply_btn)
        post_row.addWidget(self._save_log_btn)
        post_row.addStretch()
        self._post_apply_widget.setVisible(False)
        bottom_layout.addWidget(self._post_apply_widget)

        vsplit.addWidget(bottom_widget)
        vsplit.setSizes([420, 380])
        root.addWidget(vsplit, stretch=1)

    # ── Populate ──────────────────────────────────────────────────────────────

    def _populate_command_tree(self):
        self._cmd_tree.clear()
        for i, cmd in enumerate(self._commands, start=1):
            color = SECTION_COLORS.get(cmd.section, "#888")
            # Truncate long commands for display
            short_cmd = cmd.command.replace("\n", " ↵ ")
            if len(short_cmd) > 80:
                short_cmd = short_cmd[:77] + "…"
            item = QTreeWidgetItem([
                str(i),
                cmd.section.value,
                cmd.description,
                short_cmd,
            ])
            item.setForeground(1, QBrush(QColor(color)))
            item.setForeground(2, QBrush(QColor("#d4d4d4")))
            item.setForeground(3, QBrush(QColor("#666")))
            item.setData(0, Qt.ItemDataRole.UserRole, cmd)
            self._cmd_tree.addTopLevelItem(item)

        for i in range(self._cmd_tree.columnCount()):
            self._cmd_tree.resizeColumnToContents(i)

    def _update_summary_cards(self):
        counts: dict[CommandSection, int] = {s: 0 for s in CommandSection}
        for cmd in self._commands:
            counts[cmd.section] = counts.get(cmd.section, 0) + 1
        for section, card in self._cards.items():
            card.set_count(counts.get(section, 0))

    def _update_apply_button_state(self):
        all_checked = (
            self._check_reviewed.isChecked() and
            self._check_network.isChecked() and
            self._check_backup.isChecked()
        )
        has_commands = len(self._commands) > 0
        not_running  = self._worker is None or not self._worker.isRunning()
        self._apply_btn.setEnabled(all_checked and has_commands and not_running)

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _on_apply(self):
        if not self._conn:
            QMessageBox.warning(self, "Not Connected", "No active connection to a host.")
            return
        if not self._commands:
            QMessageBox.warning(self, "Nothing to Apply", "No commands to run.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Apply",
            f"Apply {len(self._commands)} commands to {self._conn.creds.host}?\n\n"
            "This cannot be undone. Configuration file backups will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._log.clear()
        self._log_line(
            f"Starting apply — {len(self._commands)} commands — "
            f"target: {self._conn.creds.host}", "#5c9bd6"
        )

        self._apply_btn.setEnabled(False)
        self._apply_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._progress_bar.setVisible(True)
        self._post_apply_widget.setVisible(False)

        self._worker = ApplyWorker(self._conn, self._commands)
        self._worker.command_started.connect(self._on_cmd_started)
        self._worker.command_finished.connect(self._on_cmd_finished)
        self._worker.log_line.connect(self._log_line)
        self._worker.finished_all.connect(self._on_apply_finished)
        self._worker.start()

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._log_line("⏹ Stop requested by operator — will halt after current command.", "#ff9800")

    def _on_cmd_started(self, section: str, description: str):
        pass  # log_line handles output

    def _on_cmd_finished(self, section: str, description: str,
                         ok: bool, stdout: str, stderr: str, elapsed: float):
        # Update tree item with result indicator
        for i in range(self._cmd_tree.topLevelItemCount()):
            item = self._cmd_tree.topLevelItem(i)
            if item.text(2) == description:
                icon = "✓" if ok else "✗"
                color = "#4caf50" if ok else "#f44336"
                item.setText(0, f"{icon} {item.text(0)}")
                item.setForeground(0, QBrush(QColor(color)))
                break

    def _on_apply_finished(self, success: bool, summary: str):
        self._stop_btn.setVisible(False)
        self._progress_bar.setVisible(False)
        self._post_apply_widget.setVisible(True)

        color = "#4caf50" if success else "#f44336"
        self._log_line(f"\n{'─' * 60}", "#444")
        self._log_line(summary, color)

        if success:
            self._log_line(
                "✓ All changes applied successfully. "
                "Click 'Re-discover host' to verify the final state.", "#4caf50"
            )
        else:
            self._log_line(
                "✗ Apply stopped due to an error. "
                "Review the log above. The host may be in a partial state.", "#f44336"
            )

        self.apply_completed.emit(success)
        self._update_apply_button_state()

    # ── Post-apply actions ────────────────────────────────────────────────────

    def _on_rediscover(self):
        """Signal parent to re-run discovery."""
        self.apply_completed.emit(True)  # parent wires this to re-discovery

    def _on_reapply(self):
        """Reset the apply UI and run apply again with the same commands."""
        self._log.clear()
        self._post_apply_widget.setVisible(False)
        self._apply_btn.setVisible(True)
        # Uncheck confirmations so operator must re-confirm before re-applying
        for cb in [self._check_reviewed, self._check_network, self._check_backup]:
            cb.setChecked(False)
        self._update_apply_button_state()

    def _on_save_log(self):
        from PyQt6.QtWidgets import QFileDialog
        from datetime import datetime
        hostname = self._inventory.hostname if self._inventory else "unknown"
        default = f"pve_apply_{hostname}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Apply Log", default, "Log files (*.log);;All files (*)"
        )
        if path:
            try:
                with open(path, "w") as f:
                    f.write(self._log.toPlainText())
            except Exception as e:
                QMessageBox.warning(self, "Save Failed", str(e))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_line(self, text: str, color: str = "#d4d4d4"):
        self._log.append(f'<span style="color:{color};">{text}</span>')
        # Auto-scroll to bottom
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )
