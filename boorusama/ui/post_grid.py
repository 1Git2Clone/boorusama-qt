"""Responsive thumbnail grid with infinite scroll.

Thumbnails reflow into as many columns as the viewport width allows (or a fixed
count from settings). Scrolling near the bottom emits ``load_more`` so the owner
can fetch the next page.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Post
from .widgets import PostThumbnail


class PostGrid(QWidget):
    post_clicked = Signal(object)
    load_more = Signal()

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self._posts: list[Post] = []
        self._thumbs: list[PostThumbnail] = []
        self._fixed_columns = 0
        self._columns = 0
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("ContentArea")
        outer.addWidget(self.scroll_area)

        self.container = QWidget()
        self.container.setObjectName("ContentArea")
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(10)
        self.grid.setContentsMargins(12, 12, 12, 12)
        self.grid.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )
        self.scroll_area.setWidget(self.container)

        self.empty_label = QLabel("No results.")
        self.empty_label.setObjectName("Subtitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setVisible(False)
        self._empty_text = "No results."
        outer.addWidget(self.empty_label)

        self.scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # --- public API --------------------------------------------------------
    def set_empty_message(self, text: str) -> None:
        """Set the message shown when the grid has no posts."""
        self._empty_text = text
        self.empty_label.setText(text)

    def set_fixed_columns(self, count: int) -> None:
        self._fixed_columns = count
        self._relayout()

    def set_posts(self, posts: list[Post]) -> None:
        self.clear()
        self.append_posts(posts)

    def append_posts(self, posts: list[Post]) -> None:
        self._loading = False
        for post in posts:
            self._posts.append(post)
            thumb = PostThumbnail(
                post,
                self.context.image_loader,
                is_favorite=self.context.is_favorite(post),
            )
            thumb.clicked.connect(self.post_clicked.emit)
            self._thumbs.append(thumb)
        self.empty_label.setVisible(not self._posts)
        self.scroll_area.setVisible(bool(self._posts))
        self._relayout()

    def clear(self) -> None:
        for thumb in self._thumbs:
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumbs.clear()
        self._posts.clear()
        self._loading = False

    def set_loading(self, value: bool) -> None:
        self._loading = value

    # --- layout ------------------------------------------------------------
    def _compute_columns(self) -> int:
        if self._fixed_columns > 0:
            return self._fixed_columns
        width = self.scroll_area.viewport().width()
        cell = PostThumbnail.SIZE + self.grid.spacing()
        return max(1, (width - 24) // cell)

    def _relayout(self) -> None:
        columns = self._compute_columns()
        # Remove all from layout (without deleting) then re-add in order.
        while self.grid.count():
            self.grid.takeAt(0)
        for index, thumb in enumerate(self._thumbs):
            row, col = divmod(index, columns)
            self.grid.addWidget(thumb, row, col)
        self._columns = columns

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._compute_columns() != self._columns:
            self._relayout()

    # --- infinite scroll ---------------------------------------------------
    def _on_scroll(self, value: int) -> None:
        bar = self.scroll_area.verticalScrollBar()
        if self._loading or not self._posts:
            return
        if value >= bar.maximum() - PostThumbnail.SIZE:
            self._loading = True
            self.load_more.emit()
