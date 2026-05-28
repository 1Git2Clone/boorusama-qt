"""Full post viewer: large image + metadata/tag side panel + navigation.

Shown as a page swapped into the main content stack. Holds the surrounding result
list so the user can page through posts with the on-screen arrows or arrow keys.
Clicking a tag triggers a new search via the ``search_tag`` signal.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Post, TagCategory
from .widgets import FlowLayout, TagChip


def _human_size(num: int) -> str:
    if num <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{num} B"


class PostViewer(QWidget):
    back_requested = Signal()
    search_tag = Signal(str)
    favorite_toggled = Signal(object)
    download_requested = Signal(object)

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self._posts: list[Post] = []
        self._index = 0
        self._current: Post | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- image area ----------------------------------------------------
        image_col = QVBoxLayout()
        image_col.setContentsMargins(0, 0, 0, 0)

        topbar = QHBoxLayout()
        topbar.setContentsMargins(10, 10, 10, 6)
        self.back_btn = QPushButton("←  Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        topbar.addWidget(self.back_btn)
        topbar.addStretch(1)
        self.prev_btn = QPushButton("‹ Prev")
        self.prev_btn.clicked.connect(self.show_prev)
        self.next_btn = QPushButton("Next ›")
        self.next_btn.clicked.connect(self.show_next)
        topbar.addWidget(self.prev_btn)
        topbar.addWidget(self.next_btn)
        image_col.addLayout(topbar)

        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_scroll.setObjectName("ContentArea")
        self.image_label = QLabel("Loading…")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(200, 200)
        self.image_scroll.setWidget(self.image_label)
        image_col.addWidget(self.image_scroll, 1)
        root.addLayout(image_col, 1)

        # --- side panel ----------------------------------------------------
        self.panel = self._build_panel()
        root.addWidget(self.panel)

        self.context.image_loader.loaded.connect(self._on_image_loaded)

    # --- panel construction ------------------------------------------------
    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Card")
        panel.setFixedWidth(330)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.panel_layout = QVBoxLayout(inner)
        self.panel_layout.setContentsMargins(16, 16, 16, 16)
        self.panel_layout.setSpacing(12)
        self.panel_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # Action buttons row.
        actions = QHBoxLayout()
        self.fav_btn = QPushButton("♥  Favorite")
        self.fav_btn.clicked.connect(self._toggle_favorite)
        self.dl_btn = QPushButton("⤓  Download")
        self.dl_btn.clicked.connect(self._download)
        actions.addWidget(self.fav_btn)
        actions.addWidget(self.dl_btn)
        self.panel_layout.addLayout(actions)

        self.open_btn = QPushButton("↗  Open original in browser")
        self.open_btn.clicked.connect(self._open_browser)
        self.panel_layout.addWidget(self.open_btn)

        # Metadata block.
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setTextFormat(Qt.TextFormat.RichText)
        self.meta_label.setObjectName("Subtitle")
        self.panel_layout.addWidget(self.meta_label)

        # Tag sections placeholder; rebuilt per post.
        self.tags_container = QWidget()
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(10)
        self.panel_layout.addWidget(self.tags_container)
        self.panel_layout.addStretch(1)
        return panel

    # --- public API --------------------------------------------------------
    def show_posts(self, posts: list[Post], index: int) -> None:
        self._posts = posts
        self._index = max(0, min(index, len(posts) - 1))
        self._load_current()

    def show_next(self) -> None:
        if self._index < len(self._posts) - 1:
            self._index += 1
            self._load_current()

    def show_prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._load_current()

    # --- rendering ---------------------------------------------------------
    def _load_current(self) -> None:
        if not self._posts:
            return
        post = self._posts[self._index]
        self._current = post
        self.prev_btn.setEnabled(self._index > 0)
        self.next_btn.setEnabled(self._index < len(self._posts) - 1)

        self.image_label.setText("Loading…")
        self.image_label.setPixmap(QPixmap())
        url = post.best_display_url
        cached = self.context.image_loader.request(url)
        if cached is not None:
            self._apply_pixmap(cached)

        self._update_meta(post)
        self._update_fav_button(post)
        self._rebuild_tags(post)

    def _apply_pixmap(self, pixmap: QPixmap) -> None:
        viewport = self.image_scroll.viewport().size()
        scaled = pixmap.scaled(
            max(viewport.width() - 20, 100),
            max(viewport.height() - 20, 100),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def _on_image_loaded(self, url: str, pixmap: QPixmap) -> None:
        if self._current and url == self._current.best_display_url:
            self._apply_pixmap(pixmap)

    def _update_meta(self, post: Post) -> None:
        rows = [
            ("ID", str(post.id)),
            ("Source", post.source_engine),
            ("Rating", post.rating.label),
            ("Score", str(post.score)),
            ("Size", f"{post.width}×{post.height}" if post.width else "—"),
            ("File", f"{post.file_ext.upper()}  {_human_size(post.file_size)}"),
        ]
        html = "<table cellspacing='0' cellpadding='3'>"
        for key, value in rows:
            html += (
                f"<tr><td style='color:#888'>{key}</td>"
                f"<td>&nbsp;&nbsp;{value}</td></tr>"
            )
        if post.source:
            html += (
                f"<tr><td style='color:#888'>Link</td>"
                f"<td>&nbsp;&nbsp;<a href='{post.source}' style='color:#4ea1ff'>"
                f"source</a></td></tr>"
            )
        html += "</table>"
        self.meta_label.setText(html)
        self.meta_label.setOpenExternalLinks(True)

    def _update_fav_button(self, post: Post) -> None:
        is_fav = self.context.is_favorite(post)
        self.fav_btn.setText("♥  Favorited" if is_fav else "♡  Favorite")
        self.fav_btn.setObjectName("Primary" if is_fav else "")
        self.fav_btn.setStyleSheet(
            "background-color:#ff5d6c; color:white; border:none; font-weight:600;"
            if is_fav
            else ""
        )

    def _rebuild_tags(self, post: Post) -> None:
        # Clear existing tag sections.
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.deleteLater()

        order = [
            (TagCategory.ARTIST, "Artist"),
            (TagCategory.COPYRIGHT, "Copyright"),
            (TagCategory.CHARACTER, "Character"),
            (TagCategory.GENERAL, "General"),
            (TagCategory.META, "Meta"),
        ]
        for category, title in order:
            tags = post.tags_by_category(category)
            if not tags:
                continue
            heading = QLabel(f"{title}  ·  {len(tags)}")
            heading.setStyleSheet(f"color:{category.color}; font-weight:600;")
            self.tags_layout.addWidget(heading)

            chips_host = QWidget()
            flow = FlowLayout(chips_host, spacing=5)
            for tag in tags:
                chip = TagChip(tag)
                chip.clicked_tag.connect(self.search_tag.emit)
                flow.addWidget(chip)
            self.tags_layout.addWidget(chips_host)

    # --- actions -----------------------------------------------------------
    def _toggle_favorite(self) -> None:
        if self._current:
            self.context.toggle_favorite(self._current)
            self._update_fav_button(self._current)
            self.favorite_toggled.emit(self._current)

    def _download(self) -> None:
        if self._current:
            self.download_requested.emit(self._current)

    def _open_browser(self) -> None:
        if self._current and self._current.file_url:
            webbrowser.open(self._current.file_url)

    # --- keyboard ----------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Left,):
            self.show_prev()
        elif key in (Qt.Key.Key_Right,):
            self.show_next()
        elif key == Qt.Key.Key_Escape:
            self.back_requested.emit()
        elif key == Qt.Key.Key_F:
            self._toggle_favorite()
        else:
            super().keyPressEvent(event)
