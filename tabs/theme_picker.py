"""
Theme Picker Dialog
Select from built-in themes or customize colors fully.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QGroupBox, QScrollArea, QWidget, QSplitter,
    QInputDialog, QMessageBox,
    QFrame, QSizePolicy,
)
from tabs.color_picker import ColorPickerDialog
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from core.themes import Theme, ThemeManager, get_theme_manager, BUILTIN_THEMES


# ── Color swatch button ───────────────────────────────────────────────────────

class ColorSwatch(QPushButton):
    """A button that shows a color swatch and opens a color picker on click."""
    color_changed = pyqtSignal(str)   # hex color string

    def __init__(self, hex_color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._hex = hex_color
        self.setFixedSize(48, 28)
        self.setToolTip(hex_color)
        self._update_appearance()
        self.clicked.connect(self._pick_color)

    def set_color(self, hex_color: str):
        self._hex = hex_color
        self.setToolTip(hex_color)
        self._update_appearance()

    def color(self) -> str:
        return self._hex

    def _update_appearance(self):
        # Calculate contrasting text color for the swatch label
        c = QColor(self._hex)
        brightness = (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000
        text_color = "#000000" if brightness > 128 else "#ffffff"
        self.setStyleSheet(
            f"QPushButton {{ background-color: {self._hex}; "
            f"border: 1px solid #888; border-radius: 4px; }}"
            f"QPushButton:hover {{ border: 2px solid #5c9bd6; }}"
        )
        self.setText("")

    def _pick_color(self):
        initial = QColor(self._hex)
        color, accepted = ColorPickerDialog.get_color(initial, self, "Pick Color")
        if accepted and color.isValid():
            self._hex = color.name().lower()
            self._update_appearance()
            self.color_changed.emit(self._hex)


# ── Color field row ───────────────────────────────────────────────────────────

class ColorRow(QWidget):
    """Label + swatch + hex input for one color field."""
    changed = pyqtSignal(str, str)   # field_name, new_hex

    def __init__(self, field_name: str, label: str, hex_color: str, parent=None):
        super().__init__(parent)
        self._field = field_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(200)
        lbl.setStyleSheet("color: #e8e8e8; font-size: 9pt;")
        layout.addWidget(lbl)

        self._swatch = ColorSwatch(hex_color)
        self._swatch.color_changed.connect(self._on_swatch_changed)
        layout.addWidget(self._swatch)

        self._hex_edit = QLineEdit(hex_color.upper())
        self._hex_edit.setFixedWidth(86)
        self._hex_edit.setMaxLength(9)
        self._hex_edit.setFont(QFont("Monospace", 9))
        self._hex_edit.setStyleSheet(
            "QLineEdit { background: #2a2a2a; border: 1px solid #606060; "
            "border-radius: 4px; color: #e8e8e8; padding: 3px 5px; }"
            "QLineEdit:focus { border-color: #5c9bd6; }"
        )
        self._hex_edit.textChanged.connect(self._on_hex_edited)
        layout.addWidget(self._hex_edit)

        layout.addStretch()

    def set_color(self, hex_color: str):
        self._swatch.set_color(hex_color)
        self._hex_edit.blockSignals(True)
        self._hex_edit.setText(hex_color.upper())
        self._hex_edit.blockSignals(False)

    def _on_swatch_changed(self, hex_color: str):
        self._hex_edit.blockSignals(True)
        self._hex_edit.setText(hex_color.upper())
        self._hex_edit.blockSignals(False)
        self.changed.emit(self._field, hex_color)

    def _on_hex_edited(self, text: str):
        if len(text) == 7 and text.startswith("#"):
            try:
                QColor(text)
                self._swatch.set_color(text)
                self.changed.emit(self._field, text)
            except Exception:
                pass


# ── Theme preview panel ───────────────────────────────────────────────────────

class ThemePreview(QWidget):
    """Small live preview of a theme."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(180)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._preview_widget = QWidget()
        self._preview_widget.setAutoFillBackground(True)
        preview_layout = QVBoxLayout(self._preview_widget)
        preview_layout.setSpacing(6)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        # Simulated UI elements
        self._text_lbl    = QLabel("Primary text — label and body copy")
        self._dim_lbl     = QLabel("Secondary text — hints and descriptions")
        self._dim_lbl.setObjectName("dim")

        btn_row = QHBoxLayout()
        self._normal_btn  = QPushButton("Normal Button")
        self._normal_btn.setFixedHeight(26)
        self._accent_btn  = QPushButton("Accent Button")
        self._accent_btn.setFixedHeight(26)
        btn_row.addWidget(self._normal_btn)
        btn_row.addWidget(self._accent_btn)

        self._input_edit  = QLineEdit()
        self._input_edit.setPlaceholderText("Input field placeholder text")
        self._input_edit.setFixedHeight(26)

        preview_layout.addWidget(self._text_lbl)
        preview_layout.addWidget(self._dim_lbl)
        preview_layout.addLayout(btn_row)
        preview_layout.addWidget(self._input_edit)
        preview_layout.addStretch()

        layout.addWidget(self._preview_widget)

    def apply_theme(self, theme: Theme):
        """Apply a theme to the preview widgets directly."""
        self._preview_widget.setStyleSheet(
            f"QWidget {{ background-color: {theme.bg_window}; }}"
        )
        self._text_lbl.setStyleSheet(
            f"color: {theme.text_primary}; background: transparent;"
        )
        self._dim_lbl.setStyleSheet(
            f"color: {theme.text_secondary}; background: transparent;"
        )
        self._normal_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.bg_widget}; "
            f"border: 1px solid {theme.border_normal}; border-radius: 4px; "
            f"color: {theme.text_primary}; padding: 4px 10px; }}"
            f"QPushButton:hover {{ background: {theme.bg_hover}; }}"
        )
        self._accent_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.accent_bg}; "
            f"border: 1px solid {theme.accent}; border-radius: 4px; "
            f"color: #ffffff; padding: 4px 10px; }}"
        )
        self._input_edit.setStyleSheet(
            f"QLineEdit {{ background: {theme.bg_input}; "
            f"border: 1px solid {theme.border_normal}; border-radius: 4px; "
            f"color: {theme.text_primary}; padding: 3px 6px; }}"
        )


# ── Color editor panel ────────────────────────────────────────────────────────

class ColorEditorPanel(QWidget):
    """Full color editor for a theme — all configurable fields."""
    changed = pyqtSignal()

    # Field definitions: (attribute_name, display_label, group)
    FIELDS = [
        # Backgrounds
        ("bg_window",    "Window / main background",    "Backgrounds"),
        ("bg_widget",    "Widget / button background",   "Backgrounds"),
        ("bg_input",     "Input field background",       "Backgrounds"),
        ("bg_tree",      "Tree / table background",      "Backgrounds"),
        ("bg_alt_row",   "Alternating row background",   "Backgrounds"),
        ("bg_dark",      "Dark panels (log, preview)",   "Backgrounds"),
        ("bg_hover",     "Hover highlight",              "Backgrounds"),
        # Text
        ("text_primary",   "Primary text",              "Text"),
        ("text_secondary", "Secondary text / labels",   "Text"),
        ("text_dim",       "Dim text / hints / notes",  "Text"),
        ("text_disabled",  "Disabled text",             "Text"),
        # Borders
        ("border_normal", "Normal border",              "Borders"),
        ("border_subtle", "Subtle border",              "Borders"),
        ("border_dim",    "Dim border",                 "Borders"),
        # Accent
        ("accent",       "Accent color",                "Accent"),
        ("accent_bg",    "Accent background",           "Accent"),
        ("accent_hover", "Accent hover",                "Accent"),
        # Tab bar
        ("tab_bg",       "Tab background",              "Tab Bar"),
        ("tab_inactive", "Inactive tab text",           "Tab Bar"),
        ("tab_active",   "Active tab text",             "Tab Bar"),
        ("tab_disabled", "Disabled tab text",           "Tab Bar"),
        # Group boxes
        ("groupbox_title",  "Group box title",          "Group Boxes"),
        ("groupbox_border", "Group box border",         "Group Boxes"),
        ("section_header",  "Section header color",     "Group Boxes"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme: Theme | None = None
        self._rows: dict[str, ColorRow] = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        # Group fields by category
        groups: dict[str, list] = {}
        for field, label, group in self.FIELDS:
            groups.setdefault(group, []).append((field, label))

        for group_name, fields in groups.items():
            group_box = QGroupBox(group_name)
            group_box.setStyleSheet(
                "QGroupBox { font-weight: bold; font-size: 10pt; color: #c8c8c8; "
                "border: 1px solid #505050; border-radius: 6px; "
                "margin-top: 8px; padding-top: 8px; }"
                "QGroupBox::title { color: #c8c8c8; subcontrol-origin: margin; "
                "left: 10px; padding: 0 4px; }"
            )
            group_layout = QVBoxLayout(group_box)
            group_layout.setSpacing(4)
            group_layout.setContentsMargins(8, 10, 8, 8)
            for field, label in fields:
                row = ColorRow(field, label, "#ffffff")
                row.changed.connect(self._on_color_changed)
                self._rows[field] = row
                group_layout.addWidget(row)
            layout.addWidget(group_box)

        layout.addStretch()
        scroll.setWidget(container)
        outer.addWidget(scroll)

    def load(self, theme: Theme):
        self._theme = None  # prevent signals during load
        for field, row in self._rows.items():
            row.set_color(getattr(theme, field, "#888888"))
        self._theme = theme

    def _on_color_changed(self, field: str, hex_color: str):
        if self._theme:
            setattr(self._theme, field, hex_color)
            self.changed.emit()

    def set_enabled(self, enabled: bool):
        for row in self._rows.values():
            row.setEnabled(enabled)


# ── Theme Picker Dialog ───────────────────────────────────────────────────────

class ThemePickerDialog(QDialog):
    theme_changed = pyqtSignal(str)   # theme name — apply immediately

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Theme & Colors")
        self.setMinimumSize(820, 620)
        self._mgr = get_theme_manager()
        self._editing_theme: Theme | None = None
        self._build_ui()
        self._populate_list()
        self._select_active()

    def _build_ui(self):
        # Force dialog to always use a consistent dark style
        # (prevents the active theme making the dialog unreadable while editing)
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #252525;
                color: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #505050;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                color: #e0e0e0;
            }
            QGroupBox::title {
                color: #c8c8c8;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel { color: #e0e0e0; background: transparent; }
            QLineEdit, QSpinBox, QComboBox {
                background: #333333;
                border: 1px solid #606060;
                border-radius: 4px;
                color: #e8e8e8;
                padding: 3px 6px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #5c9bd6;
            }
            QPushButton {
                background: #3c3c3c;
                border: 1px solid #606060;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 4px 12px;
            }
            QPushButton:hover  { background: #4a4a4a; border-color: #5c9bd6; }
            QPushButton:pressed{ background: #303030; }
            QPushButton:disabled { color: #666; border-color: #444; }
            QScrollArea { background: #252525; border: none; }
            QScrollBar:vertical {
                background: #252525; width: 10px; border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #555; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QListWidget {
                background: #1e1e1e;
                border: 1px solid #505050;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QListWidget::item:selected { background: #1a5fa8; color: #fff; }
            QListWidget::item:hover    { background: #353535; }
            QSplitter::handle { background: #444; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("Theme & Colors")
        title.setFont(QFont("Sans", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: theme list ──────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(220)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(6)

        themes_lbl = QLabel("Themes:")
        themes_lbl.setStyleSheet("color: #e0e0e0; font-weight: bold;")
        left_layout.addWidget(themes_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.currentTextChanged.connect(self._on_theme_selected)
        left_layout.addWidget(self._theme_combo)

        # Buttons
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedHeight(28)
        self._apply_btn.clicked.connect(self._on_apply)
        left_layout.addWidget(self._apply_btn)

        self._duplicate_btn = QPushButton("Duplicate & Edit")
        self._duplicate_btn.setFixedHeight(28)
        self._duplicate_btn.clicked.connect(self._on_duplicate)
        left_layout.addWidget(self._duplicate_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedHeight(28)
        self._delete_btn.setStyleSheet("color: #f44;")
        self._delete_btn.clicked.connect(self._on_delete)
        left_layout.addWidget(self._delete_btn)

        left_layout.addStretch()

        self._builtin_label = QLabel("⚑ Built-in theme — read only")
        self._builtin_label.setStyleSheet("color: #ff9800; font-size: 9pt;")
        self._builtin_label.setVisible(False)
        left_layout.addWidget(self._builtin_label)

        splitter.addWidget(left)

        # ── Right: preview + color editor ────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        # Theme name editor (for custom themes)
        name_row = QHBoxLayout()
        name_lbl = QLabel("Theme name:")
        name_lbl.setStyleSheet("color: #e0e0e0;")
        name_row.addWidget(name_lbl)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("My Custom Theme")
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_edit)
        self._save_btn = QPushButton("💾  Save")
        self._save_btn.setFixedHeight(26)
        self._save_btn.clicked.connect(self._on_save)
        name_row.addWidget(self._save_btn)
        right_layout.addLayout(name_row)

        # Preview
        preview_label = QLabel("Preview:")
        preview_label.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 10pt;")
        right_layout.addWidget(preview_label)
        self._preview = ThemePreview()
        right_layout.addWidget(self._preview)

        # Color editor
        editor_label = QLabel("Colors  (click swatch or type hex value):")
        editor_label.setStyleSheet("font-weight: bold; color: #e0e0e0; font-size: 10pt;")
        right_layout.addWidget(editor_label)
        self._color_editor = ColorEditorPanel()
        self._color_editor.changed.connect(self._on_colors_changed)
        right_layout.addWidget(self._color_editor, stretch=1)

        splitter.addWidget(right)
        splitter.setSizes([200, 600])
        layout.addWidget(splitter, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _populate_list(self):
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        for t in self._mgr.all_themes:
            self._theme_combo.addItem(t.name)
        self._theme_combo.blockSignals(False)

    def _select_active(self):
        idx = self._theme_combo.findText(self._mgr.active.name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

    def _on_theme_selected(self, name: str):
        theme = self._mgr.get(name)
        if not theme:
            return
        # Work on a copy for editing
        import copy
        self._editing_theme = copy.deepcopy(theme)
        self._name_edit.blockSignals(True)
        self._name_edit.setText(theme.name)
        self._name_edit.blockSignals(False)
        self._color_editor.load(self._editing_theme)
        self._color_editor.set_enabled(not theme.builtin)
        self._preview.apply_theme(self._editing_theme)
        self._builtin_label.setVisible(theme.builtin)
        self._name_edit.setEnabled(not theme.builtin)
        self._save_btn.setEnabled(not theme.builtin)
        self._delete_btn.setEnabled(not theme.builtin)

    def _on_colors_changed(self):
        if self._editing_theme:
            self._preview.apply_theme(self._editing_theme)

    def _on_name_changed(self, name: str):
        if self._editing_theme:
            self._editing_theme.name = name

    def _on_apply(self):
        name = self._theme_combo.currentText()
        if self._mgr.set_active(name):
            self.theme_changed.emit(name)

    def _on_duplicate(self):
        name = self._theme_combo.currentText()
        theme = self._mgr.get(name)
        if not theme:
            return
        import copy
        new_theme = copy.deepcopy(theme)
        new_theme.name = f"{theme.name} (custom)"
        new_theme.builtin = False
        self._mgr.save_custom(new_theme)
        self._populate_list()
        idx = self._theme_combo.findText(new_theme.name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

    def _on_save(self):
        if not self._editing_theme:
            return
        if not self._editing_theme.name.strip():
            QMessageBox.warning(self, "Save Theme", "Theme name cannot be blank.")
            return
        self._mgr.save_custom(self._editing_theme)
        self._populate_list()
        idx = self._theme_combo.findText(self._editing_theme.name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)

    def _on_delete(self):
        name = self._theme_combo.currentText()
        reply = QMessageBox.question(
            self, "Delete Theme",
            f"Delete custom theme '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self._mgr.delete_custom(name):
                self._populate_list()
                self._select_active()
