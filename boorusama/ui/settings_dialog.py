"""Settings dialog: manage sources & logins, appearance, and content filters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import SourceConfig
from ..core.registry import available_engines
from .theme import THEMES


class SettingsDialog(QDialog):
    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self.config = context.config
        self.setWindowTitle("Settings")
        self.resize(640, 560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._sources_tab(), "Sources & Login")
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._content_tab(), "Content")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # --- Sources tab -------------------------------------------------------
    def _sources_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)

        left = QVBoxLayout()
        self.sources_list = QListWidget()
        self.sources_list.currentRowChanged.connect(self._on_source_selected)
        left.addWidget(self.sources_list, 1)
        btn_row = QHBoxLayout()
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_source)
        del_btn = QPushButton("– Remove")
        del_btn.clicked.connect(self._remove_source)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        left.addLayout(btn_row)
        layout.addLayout(left, 1)

        # Edit form.
        form_host = QWidget()
        form = QFormLayout(form_host)
        self.f_engine = QComboBox()
        for eid, cls in available_engines().items():
            self.f_engine.addItem(f"{cls.icon}  {cls.display_name}", eid)
        self.f_name = QLineEdit()
        self.f_base = QLineEdit()
        self.f_profile = QLineEdit()
        self.f_profile.setPlaceholderText("moebooru / philomena (generic only)")
        self.f_user = QLineEdit()
        self.f_user.setPlaceholderText("username / user_id")
        self.f_secret = QLineEdit()
        self.f_secret.setPlaceholderText("API key")
        self.f_secret.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Engine", self.f_engine)
        form.addRow("Name", self.f_name)
        form.addRow("Base URL", self.f_base)
        form.addRow("Profile", self.f_profile)
        form.addRow(QLabel("<b>Login (optional)</b>"))
        form.addRow("User", self.f_user)
        form.addRow("API key", self.f_secret)

        apply_btn = QPushButton("Apply to selected source")
        apply_btn.clicked.connect(self._apply_source_edits)
        form.addRow(apply_btn)

        layout.addWidget(form_host, 2)

        self._reload_sources_list()
        return w

    def _reload_sources_list(self) -> None:
        self.sources_list.clear()
        for src in self.config.sources:
            item = QListWidgetItem(f"{src.name}")
            item.setToolTip(src.base_url)
            self.sources_list.addItem(item)
        if self.config.sources:
            self.sources_list.setCurrentRow(self.config.active_source)

    def _on_source_selected(self, row: int) -> None:
        if not (0 <= row < len(self.config.sources)):
            return
        src = self.config.sources[row]
        idx = self.f_engine.findData(src.engine_id)
        self.f_engine.setCurrentIndex(max(0, idx))
        self.f_name.setText(src.name)
        self.f_base.setText(src.base_url)
        self.f_profile.setText(src.profile)
        self.f_user.setText(src.username)
        self.f_secret.setText(src.secret)

    def _collect_source(self) -> SourceConfig:
        return SourceConfig(
            engine_id=self.f_engine.currentData(),
            name=self.f_name.text().strip() or "Unnamed",
            base_url=self.f_base.text().strip(),
            username=self.f_user.text().strip(),
            secret=self.f_secret.text().strip(),
            profile=self.f_profile.text().strip(),
        )

    def _add_source(self) -> None:
        eid = self.f_engine.currentData() or "danbooru"
        cls = available_engines()[eid]
        self.config.sources.append(
            SourceConfig(
                engine_id=eid, name=cls.display_name, base_url=cls.default_base_url
            )
        )
        self._reload_sources_list()
        self.sources_list.setCurrentRow(len(self.config.sources) - 1)

    def _remove_source(self) -> None:
        row = self.sources_list.currentRow()
        if 0 <= row < len(self.config.sources) and len(self.config.sources) > 1:
            self.config.sources.pop(row)
            self.config.active_source = min(
                self.config.active_source, len(self.config.sources) - 1
            )
            self._reload_sources_list()

    def _apply_source_edits(self) -> None:
        row = self.sources_list.currentRow()
        if 0 <= row < len(self.config.sources):
            self.config.sources[row] = self._collect_source()
            self._reload_sources_list()
            self.sources_list.setCurrentRow(row)

    # --- Appearance tab ----------------------------------------------------
    def _appearance_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.f_theme = QComboBox()
        for name in THEMES:
            self.f_theme.addItem(name.capitalize(), name)
        idx = self.f_theme.findData(self.config.theme)
        self.f_theme.setCurrentIndex(max(0, idx))

        self.f_accent = QLineEdit(self.config.accent)
        self.f_accent.setPlaceholderText("#009be6")

        self.f_columns = QSpinBox()
        self.f_columns.setRange(0, 12)
        self.f_columns.setValue(self.config.grid_columns)
        self.f_columns.setSpecialValueText("Auto")

        form.addRow("Theme", self.f_theme)
        form.addRow("Accent color", self.f_accent)
        form.addRow("Grid columns", self.f_columns)
        return w

    # --- Content tab -------------------------------------------------------
    def _content_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.f_safe = QCheckBox("Safe mode (hide questionable & explicit posts)")
        self.f_safe.setChecked(self.config.safe_mode)
        layout.addWidget(self.f_safe)

        self.f_autocomplete = QCheckBox("Enable tag autocomplete")
        self.f_autocomplete.setChecked(self.config.autocomplete_enabled)
        layout.addWidget(self.f_autocomplete)

        layout.addWidget(QLabel("Tag blacklist (one rule per line; space = AND):"))
        self.f_blacklist = QPlainTextEdit()
        self.f_blacklist.setPlainText("\n".join(self.config.blacklist))
        self.f_blacklist.setPlaceholderText("gore\nspoilers rating:e")
        layout.addWidget(self.f_blacklist, 1)
        return w

    # --- save --------------------------------------------------------------
    def _save(self) -> None:
        self.config.theme = self.f_theme.currentData()
        self.config.accent = self.f_accent.text().strip() or "#009be6"
        self.config.grid_columns = self.f_columns.value()
        self.config.safe_mode = self.f_safe.isChecked()
        self.config.autocomplete_enabled = self.f_autocomplete.isChecked()
        self.config.blacklist = [
            line.strip()
            for line in self.f_blacklist.toPlainText().splitlines()
            if line.strip()
        ]
        self.config.active_source = max(
            0, min(self.config.active_source, len(self.config.sources) - 1)
        )
        self.context.apply_settings()
        self.accept()
