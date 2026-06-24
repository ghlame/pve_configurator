"""
Theme engine for PVE Configurator.
Built-in themes + full color customization with persistence.
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

CONFIG_DIR  = Path.home() / ".config" / "pve-configurator"
THEME_FILE  = CONFIG_DIR / "theme.json"


# ── Theme dataclass ───────────────────────────────────────────────────────────

@dataclass
class Theme:
    name: str

    # Backgrounds
    bg_window:    str = "#2b2b2b"   # main window / widget bg
    bg_widget:    str = "#3c3c3c"   # inputs, buttons
    bg_input:     str = "#3c3c3c"   # line edits, spinboxes
    bg_alt_row:   str = "#2d2d2d"   # alternating tree rows
    bg_tree:      str = "#252525"   # tree/table background
    bg_dark:      str = "#1e1e1e"   # preview panels, log areas
    bg_hover:     str = "#4a4a4a"   # button/item hover

    # Text
    text_primary:   str = "#e0e0e0"  # main body text
    text_secondary: str = "#b0b0b0"  # labels, descriptions
    text_dim:       str = "#888888"  # hints, placeholders, notes
    text_disabled:  str = "#777777"  # disabled controls

    # Borders
    border_normal: str = "#606060"
    border_subtle: str = "#505050"
    border_dim:    str = "#444444"

    # Accent / interactive
    accent:        str = "#5c9bd6"   # focus rings, selected tab underline
    accent_bg:     str = "#1a5fa8"   # selected items, default buttons
    accent_hover:  str = "#2272c0"   # hover on accent elements

    # Semantic colors (fixed — not user-customizable in basic mode)
    color_success: str = "#4caf50"
    color_warning: str = "#ff9800"
    color_error:   str = "#f44336"
    color_info:    str = "#5c9bd6"

    # Tab bar
    tab_inactive:  str = "#c0c0c0"
    tab_active:    str = "#ffffff"
    tab_disabled:  str = "#777777"
    tab_bg:        str = "#3c3c3c"

    # Group boxes
    groupbox_title:  str = "#c8c8c8"
    groupbox_border: str = "#555555"

    # Section headers (colored headings in System tab etc.)
    section_header: str = "#5c9bd6"

    builtin: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Theme":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})

    def generate_stylesheet(self) -> str:
        """Generate the full Qt stylesheet from this theme."""
        a  = self.accent
        ab = self.accent_bg
        ah = self.accent_hover
        return f"""
            QMainWindow, QWidget {{
                background-color: {self.bg_window};
                color: {self.text_primary};
            }}
            QTabWidget::pane {{
                border: none;
                background: {self.bg_window};
            }}
            QTabBar::tab {{
                background: {self.tab_bg};
                color: {self.tab_inactive};
                padding: 8px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                min-width: 120px;
            }}
            QTabBar::tab:selected {{
                background: {self.bg_window};
                color: {self.tab_active};
                border-bottom: 2px solid {a};
            }}
            QTabBar::tab:disabled {{
                color: {self.tab_disabled};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {self.groupbox_border};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 8px;
                color: {self.text_primary};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {self.groupbox_title};
            }}
            QLabel {{
                color: {self.text_primary};
                background: transparent;
            }}
            QLineEdit, QSpinBox, QComboBox {{
                background: {self.bg_input};
                border: 1px solid {self.border_normal};
                border-radius: 4px;
                color: {self.text_primary};
                padding: 4px 6px;
            }}
            QTextEdit {{
                background: {self.bg_input};
                border: 1px solid {self.border_normal};
                border-radius: 4px;
                color: {self.text_primary};
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {a};
            }}
            QLineEdit:read-only {{
                background: {self.bg_widget};
                color: {self.text_secondary};
            }}
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
                color: {self.text_disabled};
                border-color: {self.border_dim};
            }}
            QPushButton {{
                background: {self.bg_widget};
                border: 1px solid {self.border_normal};
                border-radius: 4px;
                color: {self.text_primary};
                padding: 5px 14px;
            }}
            QPushButton:hover   {{ background: {self.bg_hover}; border-color: {a}; }}
            QPushButton:pressed {{ background: {self.border_normal}; }}
            QPushButton:disabled {{ color: {self.text_disabled}; border-color: {self.border_dim}; }}
            QPushButton:default {{
                background: {ab};
                border-color: {a};
                color: #ffffff;
            }}
            QPushButton:default:hover {{ background: {ah}; }}
            QTreeWidget {{
                background: {self.bg_tree};
                alternate-background-color: {self.bg_alt_row};
                border: 1px solid {self.border_subtle};
                border-radius: 4px;
                color: {self.text_primary};
            }}
            QTreeWidget::item {{
                color: {self.text_primary};
                padding: 2px 0px;
            }}
            QTreeWidget::item:selected {{
                background: {ab};
                color: #ffffff;
            }}
            QTreeWidget::item:hover {{
                background: {self.bg_hover};
            }}
            QListWidget {{
                background: {self.bg_tree};
                border: 1px solid {self.border_subtle};
                border-radius: 4px;
                color: {self.text_primary};
            }}
            QListWidget::item:selected {{
                background: {ab};
                color: #ffffff;
            }}
            QListWidget::item:hover {{
                background: {self.bg_hover};
            }}
            QHeaderView::section {{
                background: {self.bg_widget};
                color: {self.groupbox_title};
                border: none;
                border-right: 1px solid {self.border_subtle};
                border-bottom: 1px solid {self.border_subtle};
                padding: 4px 8px;
                font-weight: bold;
            }}
            QScrollBar:vertical {{
                background: {self.bg_window};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.border_normal};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {self.bg_hover}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {self.bg_window};
                height: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:horizontal {{
                background: {self.border_normal};
                border-radius: 5px;
                min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QProgressBar {{
                background: {self.bg_widget};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {a};
                border-radius: 3px;
            }}
            QCheckBox {{ color: {self.text_primary}; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {self.border_normal};
                border-radius: 3px;
                background: {self.bg_input};
            }}
            QCheckBox::indicator:checked {{
                background: {ab};
                border-color: {a};
            }}
            QCheckBox::indicator:disabled {{
                border-color: {self.border_dim};
                background: {self.bg_widget};
            }}
            QRadioButton {{ color: {self.text_primary}; }}
            QRadioButton::indicator {{
                width: 14px; height: 14px;
                border: 1px solid {self.border_normal};
                border-radius: 7px;
                background: {self.bg_input};
            }}
            QRadioButton::indicator:checked {{
                background: {ab};
                border-color: {a};
            }}
            QSplitter::handle {{ background: {self.border_subtle}; }}
            QTabWidget QWidget {{ background: {self.bg_window}; }}
            QScrollArea {{ background: {self.bg_window}; border: none; }}
            QDialog {{ background: {self.bg_window}; color: {self.text_primary}; }}
            QMessageBox {{ background: {self.bg_window}; color: {self.text_primary}; }}
            QComboBox QAbstractItemView {{
                background: {self.bg_input};
                color: {self.text_primary};
                selection-background-color: {ab};
                border: 1px solid {self.border_normal};
            }}
            QToolTip {{
                background: {self.bg_widget};
                color: {self.text_primary};
                border: 1px solid {self.border_normal};
                padding: 4px;
            }}
            QMenuBar {{
                background: {self.bg_window};
                color: {self.text_primary};
            }}
            QMenu {{
                background: {self.bg_widget};
                color: {self.text_primary};
                border: 1px solid {self.border_normal};
            }}
            QMenu::item:selected {{
                background: {ab};
                color: #ffffff;
            }}
        """


# ── Built-in themes ───────────────────────────────────────────────────────────

BUILTIN_THEMES = [
    Theme(
        name="Dark (default)",
        builtin=True,
        # all defaults
    ),
    Theme(
        name="Dark High Contrast",
        builtin=True,
        bg_window="#1a1a1a", bg_widget="#2e2e2e", bg_input="#2e2e2e",
        bg_alt_row="#222222", bg_tree="#1a1a1a", bg_dark="#111111",
        bg_hover="#3a3a3a",
        text_primary="#ffffff", text_secondary="#d0d0d0",
        text_dim="#aaaaaa", text_disabled="#888888",
        border_normal="#707070", border_subtle="#606060", border_dim="#505050",
        accent="#60aaff", accent_bg="#1060c0", accent_hover="#2070d0",
        tab_inactive="#d0d0d0", tab_active="#ffffff", tab_disabled="#888888",
        tab_bg="#2e2e2e",
        groupbox_title="#e0e0e0", groupbox_border="#606060",
        section_header="#60aaff",
    ),
    Theme(
        name="Dark Blue",
        builtin=True,
        bg_window="#1c2333", bg_widget="#263047", bg_input="#263047",
        bg_alt_row="#202a3a", bg_tree="#181f2e", bg_dark="#141925",
        bg_hover="#304060",
        text_primary="#dce8ff", text_secondary="#a8c0e8",
        text_dim="#7890b8", text_disabled="#607090",
        border_normal="#405070", border_subtle="#354560", border_dim="#2a3550",
        accent="#5090e0", accent_bg="#2060b0", accent_hover="#3070c8",
        tab_inactive="#a0b8d8", tab_active="#dce8ff", tab_disabled="#506070",
        tab_bg="#263047",
        groupbox_title="#b8d0f0", groupbox_border="#405070",
        section_header="#5090e0",
    ),
    Theme(
        name="Light",
        builtin=True,
        bg_window="#f5f5f5", bg_widget="#ffffff", bg_input="#ffffff",
        bg_alt_row="#f0f0f0", bg_tree="#fafafa", bg_dark="#e8e8e8",
        bg_hover="#e0e8f8",
        text_primary="#1a1a1a", text_secondary="#444444",
        text_dim="#666666", text_disabled="#999999",
        border_normal="#c0c0c0", border_subtle="#d0d0d0", border_dim="#e0e0e0",
        accent="#1a6abf", accent_bg="#1a6abf", accent_hover="#155aa0",
        tab_inactive="#555555", tab_active="#1a1a1a", tab_disabled="#aaaaaa",
        tab_bg="#e8e8e8",
        groupbox_title="#333333", groupbox_border="#c0c0c0",
        section_header="#1a6abf",
    ),
    Theme(
        name="Solarized Dark",
        builtin=True,
        bg_window="#002b36", bg_widget="#073642", bg_input="#073642",
        bg_alt_row="#003847", bg_tree="#002030", bg_dark="#001520",
        bg_hover="#094555",
        text_primary="#839496", text_secondary="#657b83",
        text_dim="#586e75", text_disabled="#4a6068",
        border_normal="#2a6070", border_subtle="#1a5060", border_dim="#0f3a48",
        accent="#268bd2", accent_bg="#1060a0", accent_hover="#1a70b8",
        tab_inactive="#839496", tab_active="#93a1a1", tab_disabled="#586e75",
        tab_bg="#073642",
        groupbox_title="#93a1a1", groupbox_border="#2a6070",
        section_header="#268bd2",
    ),
    Theme(
        name="Nord",
        builtin=True,
        bg_window="#2e3440", bg_widget="#3b4252", bg_input="#3b4252",
        bg_alt_row="#323844", bg_tree="#2a303c", bg_dark="#242933",
        bg_hover="#434c5e",
        text_primary="#eceff4", text_secondary="#d8dee9",
        text_dim="#adb5c5", text_disabled="#7a8694",
        border_normal="#4c566a", border_subtle="#434c5e", border_dim="#3b4252",
        accent="#88c0d0", accent_bg="#5e81ac", accent_hover="#6e91bc",
        tab_inactive="#d8dee9", tab_active="#eceff4", tab_disabled="#6a7585",
        tab_bg="#3b4252",
        groupbox_title="#e5e9f0", groupbox_border="#4c566a",
        section_header="#88c0d0",
    ),
    Theme(
        name="Monokai",
        builtin=True,
        bg_window="#272822", bg_widget="#3e3d32", bg_input="#3e3d32",
        bg_alt_row="#2d2c28", bg_tree="#222220", bg_dark="#1a1917",
        bg_hover="#49483e",
        text_primary="#f8f8f2", text_secondary="#cfcfc2",
        text_dim="#a59f85", text_disabled="#75715e",
        border_normal="#75715e", border_subtle="#605c4e", border_dim="#49483e",
        accent="#a6e22e", accent_bg="#5a6a1a", accent_hover="#6a7a2a",
        tab_inactive="#cfcfc2", tab_active="#f8f8f2", tab_disabled="#75715e",
        tab_bg="#3e3d32",
        groupbox_title="#e8e8d8", groupbox_border="#75715e",
        section_header="#a6e22e",
    ),
]


# ── Theme manager ─────────────────────────────────────────────────────────────

class ThemeManager:
    def __init__(self):
        self._custom_themes: list[Theme] = []
        self._active_theme: Theme = BUILTIN_THEMES[0]
        self._load()

    def _load(self):
        if not THEME_FILE.exists():
            return
        try:
            data = json.loads(THEME_FILE.read_text())
            active_name = data.get("active", "")
            self._custom_themes = [
                Theme.from_dict(t) for t in data.get("custom_themes", [])
            ]
            # Restore active theme
            for t in self.all_themes:
                if t.name == active_name:
                    self._active_theme = t
                    break
        except Exception as e:
            print(f"[ThemeManager] load error: {e}")

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "active": self._active_theme.name,
            "custom_themes": [t.to_dict() for t in self._custom_themes],
        }
        THEME_FILE.write_text(json.dumps(data, indent=2))

    @property
    def all_themes(self) -> list[Theme]:
        return BUILTIN_THEMES + self._custom_themes

    @property
    def theme_names(self) -> list[str]:
        return [t.name for t in self.all_themes]

    @property
    def active(self) -> Theme:
        return self._active_theme

    def set_active(self, name: str) -> bool:
        for t in self.all_themes:
            if t.name == name:
                self._active_theme = t
                self.save()
                return True
        return False

    def get(self, name: str) -> Optional[Theme]:
        return next((t for t in self.all_themes if t.name == name), None)

    def save_custom(self, theme: Theme):
        theme.builtin = False
        existing = next(
            (i for i, t in enumerate(self._custom_themes) if t.name == theme.name),
            None
        )
        if existing is not None:
            self._custom_themes[existing] = theme
        else:
            self._custom_themes.append(theme)
        self.save()

    def delete_custom(self, name: str) -> bool:
        if any(t.name == name for t in BUILTIN_THEMES):
            return False
        self._custom_themes = [t for t in self._custom_themes if t.name != name]
        if self._active_theme.name == name:
            self._active_theme = BUILTIN_THEMES[0]
        self.save()
        return True


# ── Singleton ─────────────────────────────────────────────────────────────────

_manager: Optional[ThemeManager] = None

def get_theme_manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager
