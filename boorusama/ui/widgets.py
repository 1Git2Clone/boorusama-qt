"""Reusable widgets: a wrapping FlowLayout, colored tag chips, and post thumbnails."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QWidget,
)

from ..core.imageloader import ImageLoader
from ..core.models import Post, Tag


class FlowLayout(QLayout):
    """A layout that wraps its child widgets to the next line as needed."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        x, y = rect.x(), rect.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._spacing
            if next_x - self._spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._spacing
                next_x = x + hint.width() + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


class TagChip(QPushButton):
    """A small colored pill representing a tag; clicking emits the tag name."""

    clicked_tag = Signal(str)

    def __init__(self, tag: Tag, parent: QWidget | None = None):
        super().__init__(parent)
        self.tag = tag
        count = f"  {tag.post_count}" if tag.post_count else ""
        self.setText(f"{tag.label}{count}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        color = tag.category.color
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {color};
                border-radius: 11px;
                padding: 3px 10px;
                color: {color};
                font-size: 12px;
                text-align: left;
            }}
            QPushButton:hover {{ background-color: {color}; color: #111; }}
            """
        )
        self.clicked.connect(lambda: self.clicked_tag.emit(self.tag.name))


class PostThumbnail(QFrame):
    """A single grid cell: an async-loaded, cropped thumbnail with overlays."""

    clicked = Signal(object)  # emits the Post

    SIZE = 200

    def __init__(
        self,
        post: Post,
        image_loader: ImageLoader,
        is_favorite: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.post = post
        self.image_loader = image_loader
        self._pixmap: QPixmap | None = None
        self.setObjectName("Thumb")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "#Thumb { background-color: rgba(127,127,127,0.12); border-radius: 10px; }"
            "#Thumb:hover { border: 2px solid #009be6; }"
        )

        self._image = QLabel(self)
        self._image.setGeometry(0, 0, self.SIZE, self.SIZE)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setText("…")

        # Badge for rating / media type, bottom-left.
        self._badge = QLabel(self)
        self._badge.setStyleSheet(
            "background: rgba(0,0,0,0.6); color: white; border-radius: 5px;"
            "padding: 1px 5px; font-size: 10px; font-weight: 600;"
        )
        badge_parts = [post.rating.value.upper()]
        if post.is_video:
            badge_parts.append("▶")
        elif post.is_animated:
            badge_parts.append("GIF")
        self._badge.setText(" ".join(badge_parts))
        self._badge.adjustSize()
        self._badge.move(6, self.SIZE - self._badge.height() - 6)

        self._fav = QLabel("♥", self)
        self._fav.setStyleSheet("color: #ff5d6c; font-size: 16px; background: transparent;")
        self._fav.adjustSize()
        self._fav.move(self.SIZE - self._fav.width() - 8, 6)
        self._fav.setVisible(is_favorite)

        self._request_image()

    def set_favorite(self, value: bool) -> None:
        self._fav.setVisible(value)

    def _request_image(self) -> None:
        url = self.post.thumbnail_url
        if not url:
            self._image.setText("no image")
            return
        cached = self.image_loader.request(url)
        if cached is not None:
            self._set_pixmap(cached)
        else:
            self.image_loader.loaded.connect(self._on_loaded)

    def _on_loaded(self, url: str, pixmap: QPixmap) -> None:
        if url == self.post.thumbnail_url:
            self._set_pixmap(pixmap)
            try:
                self.image_loader.loaded.disconnect(self._on_loaded)
            except (RuntimeError, TypeError):
                pass

    def _set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        scaled = pixmap.scaled(
            self.SIZE,
            self.SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center-crop to the cell.
        x = max(0, (scaled.width() - self.SIZE) // 2)
        y = max(0, (scaled.height() - self.SIZE) // 2)
        cropped = scaled.copy(x, y, self.SIZE, self.SIZE)
        self._image.setText("")
        self._image.setPixmap(cropped)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.post)
        super().mousePressEvent(event)


class SectionHeader(QWidget):
    """A bold heading with an optional trailing action button."""

    def __init__(self, title: str, action: str = "", on_action: Callable | None = None):
        super().__init__()
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setObjectName("Heading")
        lay.addWidget(label)
        lay.addStretch(1)
        if action:
            btn = QPushButton(action)
            if on_action:
                btn.clicked.connect(on_action)
            lay.addWidget(btn)


def make_color_dot(hex_color: str, size: int = 12) -> QLabel:
    dot = QLabel()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"background-color: {hex_color}; border-radius: {size // 2}px;")
    return dot


__all__ = [
    "FlowLayout",
    "TagChip",
    "PostThumbnail",
    "SectionHeader",
    "make_color_dot",
]
