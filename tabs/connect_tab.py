"""
Tab 1: Connect
Operator enters host address and credentials, tests connection.
"""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QComboBox,
    QCheckBox, QTextEdit, QSpinBox, QFileDialog, QStackedWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDir
from PyQt6.QtGui import QFont

from core.models import HostCredentials, ConnectMethod
from core.connection import PVEConnection


# ── Worker thread for connection test ─────────────────────────────────────────

class ConnectWorker(QThread):
    result = pyqtSignal(bool, str, object)   # success, message, PVEConnection|None

    def __init__(self, creds: HostCredentials):
        super().__init__()
        self.creds = creds

    def run(self):
        try:
            conn = PVEConnection(self.creds)
            ok, msg = conn.connect()
            self.result.emit(ok, msg, conn if ok else None)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.result.emit(False, str(e), None)


# ── Connect Tab ───────────────────────────────────────────────────────────────

class ConnectTab(QWidget):
    # Emitted when connection succeeds — carries the live PVEConnection
    connected = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: ConnectWorker | None = None
        self._conn:   PVEConnection | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(24, 24, 24, 24)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("Connect to PVE Host")
        title.setFont(QFont("Sans", 14, QFont.Weight.Bold))
        root.addWidget(title)

        subtitle = QLabel(
            "Enter the host address and credentials. The tool will attempt the\n"
            "Proxmox API first, then fall back to SSH as needed."
        )
        subtitle.setStyleSheet("color: #b0b0b0;")
        root.addWidget(subtitle)

        # ── Host group ────────────────────────────────────────────────────────
        host_group = QGroupBox("Host")
        host_form  = QFormLayout(host_group)
        host_form.setSpacing(8)

        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("IP address or hostname  (e.g. 10.80.8.11)")
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(8006)
        self._verify_ssl = QCheckBox("Verify SSL certificate")

        host_form.addRow("Host:", self._host_edit)
        host_form.addRow("API Port:", self._port_spin)
        host_form.addRow("", self._verify_ssl)
        root.addWidget(host_group)

        # ── Credentials group ─────────────────────────────────────────────────
        cred_group = QGroupBox("Credentials")
        cred_layout = QVBoxLayout(cred_group)
        cred_layout.setSpacing(8)

        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Method:"))
        self._method_combo = QComboBox()
        for m in ConnectMethod:
            self._method_combo.addItem(m.value, m)
        # Default to SSH Key
        ssh_key_index = next(
            (i for i, m in enumerate(ConnectMethod) if m == ConnectMethod.SSH_KEY), 0
        )
        self._method_combo.setCurrentIndex(ssh_key_index)
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_row.addWidget(self._method_combo)
        method_row.addStretch()
        cred_layout.addLayout(method_row)

        # Stacked pages: one per ConnectMethod
        self._cred_stack = QStackedWidget()

        # Page 0: Password
        pw_widget = QWidget()
        pw_form   = QFormLayout(pw_widget)
        pw_form.setSpacing(8)
        self._user_edit = QLineEdit("root@pam")
        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pw_form.addRow("Username:", self._user_edit)
        pw_form.addRow("Password:", self._pass_edit)
        self._cred_stack.addWidget(pw_widget)

        # Page 1: API Token
        token_widget = QWidget()
        token_form   = QFormLayout(token_widget)
        token_form.setSpacing(8)
        self._token_id_edit     = QLineEdit()
        self._token_id_edit.setPlaceholderText("root@pam!mytoken")
        self._token_secret_edit = QLineEdit()
        self._token_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._token_secret_edit.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
        token_form.addRow("Token ID:", self._token_id_edit)
        token_form.addRow("Token Secret:", self._token_secret_edit)
        self._cred_stack.addWidget(token_widget)

        # Page 2: SSH Key
        ssh_widget = QWidget()
        ssh_form   = QFormLayout(ssh_widget)
        ssh_form.setSpacing(8)
        self._ssh_pass_edit = QLineEdit()
        self._ssh_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._ssh_pass_edit.setPlaceholderText("Root password (for Proxmox API)")
        key_row = QHBoxLayout()
        self._key_path_edit = QLineEdit()
        self._key_path_edit.setPlaceholderText("~/.ssh/id_ed25519")
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_key)
        key_row.addWidget(self._key_path_edit)
        key_row.addWidget(browse_btn)
        ssh_form.addRow("Root Password:", self._ssh_pass_edit)
        ssh_form.addRow("Key file:", key_row)
        self._cred_stack.addWidget(ssh_widget)

        cred_layout.addWidget(self._cred_stack)
        root.addWidget(cred_group)

        # ── Connect button ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.setFixedHeight(36)
        self._connect_btn.setDefault(True)
        self._connect_btn.clicked.connect(self._on_connect)
        btn_row.addStretch()
        btn_row.addWidget(self._connect_btn)
        root.addLayout(btn_row)

        # ── Status output ─────────────────────────────────────────────────────
        self._status_box = QTextEdit()
        self._status_box.setReadOnly(True)
        self._status_box.setMaximumHeight(160)
        self._status_box.setFont(QFont("Monospace", 9))
        self._status_box.setStyleSheet(
            "background: #1e1e1e; color: #d4d4d4; border-radius: 4px;"
        )
        root.addWidget(self._status_box)

        # ── Connected summary (hidden until connected) ────────────────────────
        self._summary_group = QGroupBox("Connected Host")
        summary_form = QFormLayout(self._summary_group)
        self._sum_host    = QLabel()
        self._sum_version = QLabel()
        self._sum_method  = QLabel()
        summary_form.addRow("Host:",    self._sum_host)
        summary_form.addRow("PVE:",     self._sum_version)
        summary_form.addRow("Via:",     self._sum_method)
        self._summary_group.setVisible(False)
        root.addWidget(self._summary_group)

        root.addStretch()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_method_changed(self, index: int):
        self._cred_stack.setCurrentIndex(index)

    def _browse_key(self):
        dialog = QFileDialog(self, "Select SSH Private Key")
        dialog.setDirectory(str(Path.home() / ".ssh"))
        dialog.setFilter(dialog.filter() | QDir.Filter.Hidden)
        dialog.setNameFilter("All files (*)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if dialog.exec():
            files = dialog.selectedFiles()
            if files:
                self._key_path_edit.setText(files[0])

    def _on_connect(self):
        host = self._host_edit.text().strip()
        if not host:
            self._log("⚠ Please enter a host address.", error=True)
            return

        creds = self._build_creds()
        self._connect_btn.setEnabled(False)
        self._connect_btn.setText("Connecting…")
        self._log(f"Connecting to {host}…")

        self._worker = ConnectWorker(creds)
        self._worker.result.connect(self._on_connect_result)
        self._worker.start()

    def _on_connect_result(self, ok: bool, msg: str, conn):
        self._connect_btn.setEnabled(True)
        self._connect_btn.setText("Connect")

        if ok:
            self._conn = conn
            self._log(f"✓ {msg}", success=True)
            self._update_summary(conn)
            self._summary_group.setVisible(True)
            self.connected.emit(conn)
        else:
            self._log(f"✗ {msg}", error=True)
            self._summary_group.setVisible(False)

    def _update_summary(self, conn: PVEConnection):
        self._sum_host.setText(conn.creds.host)
        self._sum_version.setText("(will populate after discovery)")
        self._sum_method.setText(conn.creds.method.value)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_creds(self) -> HostCredentials:
        method = self._method_combo.currentData()
        creds  = HostCredentials(
            host=self._host_edit.text().strip(),
            port=self._port_spin.value(),
            method=method,
            verify_ssl=self._verify_ssl.isChecked(),
        )
        if method == ConnectMethod.PASSWORD:
            creds.username = self._user_edit.text().strip()
            creds.password = self._pass_edit.text()
        elif method == ConnectMethod.API_TOKEN:
            creds.api_token_id     = self._token_id_edit.text().strip()
            creds.api_token_secret = self._token_secret_edit.text().strip()
        elif method == ConnectMethod.SSH_KEY:
            creds.password     = self._ssh_pass_edit.text()
            creds.ssh_key_path = self._key_path_edit.text().strip()
        return creds

    def _log(self, msg: str, error: bool = False, success: bool = False):
        color = "#f44" if error else ("#4f4" if success else "#d4d4d4")
        self._status_box.append(
            f'<span style="color:{color};">{msg}</span>'
        )
