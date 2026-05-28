"""Application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import __app_name__
from .context import AppContext
from .ui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("boorusama-qt")
    # Match the installed boorusama-qt.desktop so the Wayland app_id (and X11
    # WM_CLASS) line up with the launcher entry — gives the running window the
    # right icon and grouping in shells like caelestia/Hyprland.
    app.setDesktopFileName("boorusama-qt")

    context = AppContext()
    window = MainWindow(context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
