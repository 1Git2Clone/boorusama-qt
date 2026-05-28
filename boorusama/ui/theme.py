"""Theming via Qt stylesheets (QSS).

Three palettes (dark, light, midnight) generated from a small set of tokens plus
a user-chosen accent color, so the whole app restyles from one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    bg: str
    bg_elevated: str
    bg_input: str
    fg: str
    fg_muted: str
    border: str
    hover: str


THEMES: dict[str, Palette] = {
    "dark": Palette(
        bg="#1a1b1e",
        bg_elevated="#25262b",
        bg_input="#2c2e33",
        fg="#e9ecef",
        fg_muted="#909296",
        border="#373a40",
        hover="#2c2e33",
    ),
    "light": Palette(
        bg="#f8f9fa",
        bg_elevated="#ffffff",
        bg_input="#f1f3f5",
        fg="#212529",
        fg_muted="#868e96",
        border="#dee2e6",
        hover="#e9ecef",
    ),
    "midnight": Palette(
        bg="#0d0f14",
        bg_elevated="#141821",
        bg_input="#1b2030",
        fg="#dfe6f2",
        fg_muted="#6b7689",
        border="#222838",
        hover="#1b2030",
    ),
}


def _lighten(hex_color: str, amount: int = 20) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (min(255, c + amount) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_stylesheet(theme: str, accent: str) -> str:
    p = THEMES.get(theme, THEMES["dark"])
    accent_hi = _lighten(accent, 25)
    return f"""
    QWidget {{
        background-color: {p.bg};
        color: {p.fg};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background-color: {p.bg}; }}

    QToolTip {{
        background-color: {p.bg_elevated};
        color: {p.fg};
        border: 1px solid {p.border};
        padding: 4px;
    }}

    /* Sidebar / nav rail */
    #Sidebar {{
        background-color: {p.bg_elevated};
        border-right: 1px solid {p.border};
    }}
    #Sidebar QPushButton {{
        text-align: left;
        padding: 10px 14px;
        border: none;
        border-radius: 8px;
        color: {p.fg_muted};
        background: transparent;
        font-size: 14px;
    }}
    #Sidebar QPushButton:hover {{ background-color: {p.hover}; color: {p.fg}; }}
    #Sidebar QPushButton:checked {{
        background-color: {accent};
        color: #ffffff;
        font-weight: 600;
    }}

    /* Inputs */
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 7px 10px;
        selection-background-color: {accent};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 1px solid {accent};
    }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border};
        selection-background-color: {accent};
        outline: none;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 7px 14px;
    }}
    QPushButton:hover {{ background-color: {p.hover}; border-color: {accent}; }}
    QPushButton:pressed {{ background-color: {p.bg}; }}
    QPushButton#Primary {{
        background-color: {accent};
        color: #ffffff;
        border: none;
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{ background-color: {accent_hi}; }}
    QPushButton:disabled {{ color: {p.fg_muted}; }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background: transparent; width: 12px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {accent}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
    QScrollBar::handle:horizontal {{
        background: {p.border}; border-radius: 5px; min-width: 30px;
    }}

    /* Misc */
    QLabel#Title {{ font-size: 22px; font-weight: 700; }}
    QLabel#Subtitle {{ color: {p.fg_muted}; font-size: 13px; }}
    QLabel#Heading {{ font-size: 15px; font-weight: 600; }}
    #Card {{
        background-color: {p.bg_elevated};
        border: 1px solid {p.border};
        border-radius: 12px;
    }}
    QScrollArea {{ border: none; }}
    #ContentArea {{ background-color: {p.bg}; }}
    QStatusBar {{ background-color: {p.bg_elevated}; color: {p.fg_muted}; }}
    QProgressBar {{
        border: 1px solid {p.border}; border-radius: 6px;
        text-align: center; background: {p.bg_input}; height: 16px;
    }}
    QProgressBar::chunk {{ background-color: {accent}; border-radius: 5px; }}
    QListWidget, QTableWidget {{
        background-color: {p.bg}; border: none; outline: none;
    }}
    QListWidget::item {{ padding: 8px; border-radius: 6px; }}
    QListWidget::item:hover {{ background-color: {p.hover}; }}
    QListWidget::item:selected {{ background-color: {accent}; color: #fff; }}
    """


def palette_for(theme: str) -> Palette:
    return THEMES.get(theme, THEMES["dark"])
