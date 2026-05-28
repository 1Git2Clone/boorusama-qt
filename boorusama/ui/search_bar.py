"""Search bar with debounced, per-token tag autocomplete.

Autocompletes only the token under the cursor (the last space-separated word), so
multi-tag queries like ``1girl solo rating:`` work naturally. Suggestions come
from the active engine on a background thread.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QWidget,
)

from ..core.models import TagSuggestion
from ..core.workers import run_async


class SearchBar(QWidget):
    search_requested = Signal(str)

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(220)
        self._debounce.timeout.connect(self._fetch_suggestions)
        self._current_worker = None

        # Suggestions list. It is NOT a top-level window: a Qt.Popup grabs the
        # keyboard (so you can't keep typing), and a Qt.Tool window gets managed
        # as a real window by tiling compositors like Hyprland (it pops out and
        # gets centered). Instead this is re-parented to the top-level window as a
        # raised child overlay at show time, so it floats over the content while
        # the line edit keeps focus. Created here so the input's event filter can
        # reference it safely during construction.
        self.popup = QListWidget()
        self.popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.popup.setMouseTracking(True)
        self.popup.hide()
        self.popup.itemClicked.connect(self._apply_suggestion)
        self.popup.setStyleSheet(
            "QListWidget { border: 1px solid #555; border-radius: 8px; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Search tags…  (e.g. 1girl solo rating:general)")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._on_submit)
        self.input.textEdited.connect(self._on_text_edited)
        self.input.installEventFilter(self)
        layout.addWidget(self.input, 1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("Primary")
        self.search_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.search_btn)

    # --- text handling -----------------------------------------------------
    def text(self) -> str:
        return self.input.text().strip()

    def set_text(self, value: str) -> None:
        self.input.setText(value)

    def _current_token(self) -> str:
        text = self.input.text()
        cursor = self.input.cursorPosition()
        before = text[:cursor]
        return before.split(" ")[-1] if before else ""

    def _on_text_edited(self, _text: str) -> None:
        if not self.context.config.autocomplete_enabled:
            return
        engine = self.context.engine
        if engine is None or not engine.capabilities.autocomplete:
            return
        token = self._current_token().lstrip("-")
        # Skip metatag prefixes like "rating:" for tag autocomplete.
        if not token or ":" in token:
            self.popup.hide()
            return
        self._debounce.start()

    def _fetch_suggestions(self) -> None:
        engine = self.context.engine
        token = self._current_token().lstrip("-")
        if engine is None or not token:
            return
        if self._current_worker is not None:
            self._current_worker.cancel()
        self._current_worker = run_async(
            engine.autocomplete_tags,
            token,
            on_result=self._show_suggestions,
            on_error=lambda _msg: self.popup.hide(),
        )

    def _show_suggestions(self, suggestions: list[TagSuggestion]) -> None:
        if not suggestions or not self.input.hasFocus():
            self.popup.hide()
            return
        self.popup.clear()
        for s in suggestions:
            count = f"   {s.post_count:,}" if s.post_count else ""
            alias = f"  ← {s.antecedent}" if s.antecedent else ""
            item = QListWidgetItem(f"{s.label}{alias}{count}")
            item.setData(Qt.ItemDataRole.UserRole, s.name)
            item.setForeground(Qt.GlobalColor.white)
            color = s.category.color
            item.setData(Qt.ItemDataRole.DecorationRole, None)
            item.setToolTip(s.category.value)
            # Tint text by category via a colored bullet prefix.
            item.setText(f"●  {s.label}{alias}{count}")
            item.setForeground(QColor(color))
            self.popup.addItem(item)

        self.popup.setCurrentRow(0)

        # Re-parent to the top-level window as a raised child overlay (see the
        # note in __init__) and position it just below the input, in the host's
        # local coordinate space.
        host = self.window()
        if self.popup.parentWidget() is not host:
            self.popup.setParent(host)
        top_left = self.input.mapTo(host, self.input.rect().bottomLeft())
        self.popup.setFixedWidth(self.input.width())
        rows = min(self.popup.count(), 10)
        self.popup.setFixedHeight(rows * 28 + 8)
        self.popup.move(top_left)
        self.popup.raise_()
        self.popup.show()

    def _apply_suggestion(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        text = self.input.text()
        cursor = self.input.cursorPosition()
        before = text[:cursor]
        after = text[cursor:]
        parts = before.split(" ")
        # Preserve a leading '-' on the token being completed.
        prefix = "-" if parts[-1].startswith("-") else ""
        parts[-1] = f"{prefix}{name}"
        new_before = " ".join(parts) + " "
        self.input.setText(new_before + after.lstrip())
        self.input.setCursorPosition(len(new_before))
        self.popup.hide()
        self.input.setFocus()

    def _on_submit(self) -> None:
        self.popup.hide()
        self.search_requested.emit(self.text())

    def _hide_if_unfocused(self) -> None:
        # Called shortly after the input loses focus. If focus didn't bounce back
        # to the input (e.g. a suggestion was clicked, which re-focuses it), the
        # user clicked elsewhere and the popup should close.
        if not self.input.hasFocus():
            self.popup.hide()

    # --- keyboard nav through the popup -----------------------------------
    def eventFilter(self, obj, event):  # noqa: N802
        try:
            popup_visible = self.popup.isVisible()
        except RuntimeError:  # underlying C++ object torn down during shutdown
            return False
        if obj is self.input and event.type() == QEvent.Type.FocusOut and popup_visible:
            # Defer: clicking a suggestion deactivates the window (FocusOut) just
            # before itemClicked fires, so don't dismiss immediately.
            QTimer.singleShot(150, self._hide_if_unfocused)
            return False
        if obj is self.input and popup_visible:
            if isinstance(event, QKeyEvent) and event.type() == QKeyEvent.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Down:
                    self.popup.setCurrentRow(
                        min(self.popup.currentRow() + 1, self.popup.count() - 1)
                    )
                    return True
                if key == Qt.Key.Key_Up:
                    self.popup.setCurrentRow(max(self.popup.currentRow() - 1, 0))
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                    current = self.popup.currentItem()
                    if current is not None:
                        self._apply_suggestion(current)
                        return True
                if key == Qt.Key.Key_Escape:
                    self.popup.hide()
                    return True
        return super().eventFilter(obj, event)
