"""Secondary pages: Favorites, History, Downloads, and Pools."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Pool
from ..core.workers import run_async
from ..services.downloads import DownloadItem, DownloadState
from .post_grid import PostGrid


def open_path(path: Path) -> bool:
    """Open a file or folder in the OS default handler (cross-platform)."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def _page_header(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(16, 16, 16, 4)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("Title")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Subtitle")
        lay.addWidget(s)
    return w


class FavoritesPage(QWidget):
    post_clicked = Signal(object, list)  # post, full_list

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_page_header("Favorites", "Posts you've saved locally"))

        self.grid = PostGrid(context)
        self.grid.post_clicked.connect(self._on_post)
        layout.addWidget(self.grid, 1)

        context.favorites_changed.connect(self.refresh)

    def refresh(self) -> None:
        posts = self.context.storage.list_favorites()
        self.grid.set_posts(posts)

    def _on_post(self, post) -> None:
        self.post_clicked.emit(post, list(self.grid._posts))


class HistoryPage(QWidget):
    search_requested = Signal(str)

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.addWidget(_page_header("Search History"), 1)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        header.setContentsMargins(0, 0, 16, 0)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.itemActivated.connect(self._on_item)
        self.list.itemClicked.connect(self._on_item)
        layout.addWidget(self.list, 1)

    def refresh(self) -> None:
        self.list.clear()
        for engine_id, query, ts in self.context.storage.list_history():
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            item = QListWidgetItem(f"{query}")
            item.setData(Qt.ItemDataRole.UserRole, query)
            item.setToolTip(f"{engine_id} · {when}")
            self.list.addItem(item)

    def _on_item(self, item: QListWidgetItem) -> None:
        self.search_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _clear(self) -> None:
        self.context.storage.clear_history()
        self.refresh()


class DownloadsPage(QWidget):
    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self._bars: dict[int, QProgressBar] = {}
        self._titles: dict[int, QLabel] = {}
        self._open_btns: dict[int, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_page_header("Downloads"))

        # Folder bar: where downloads are saved + an OS-agnostic "open folder".
        folder_row = QHBoxLayout()
        folder_row.setContentsMargins(16, 0, 16, 8)
        dl_dir = context.downloads.download_dir
        path_label = QLabel(f"Saving to:  {dl_dir}")
        path_label.setObjectName("Subtitle")
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_folder = QPushButton("📂  Open folder")
        open_folder.clicked.connect(lambda: open_path(dl_dir))
        folder_row.addWidget(path_label, 1)
        folder_row.addWidget(open_folder)
        layout.addLayout(folder_row)

        self.list = QListWidget()
        layout.addWidget(self.list, 1)

        dm = context.downloads
        dm.item_added.connect(self._add_item)
        dm.item_updated.connect(self._update_item)
        dm.item_finished.connect(self._update_item)

    def _add_item(self, item: DownloadItem) -> None:
        row = QWidget()
        lay = QVBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(f"{item.post.source_engine} #{item.post.id} → {item.dest.name}")
        open_btn = QPushButton("Open")
        open_btn.setFixedWidth(72)
        open_btn.setVisible(False)
        open_btn.clicked.connect(lambda _=False, it=item: open_path(it.dest))
        top.addWidget(title, 1)
        top.addWidget(open_btn)

        bar = QProgressBar()
        bar.setRange(0, 100)
        lay.addLayout(top)
        lay.addWidget(bar)

        list_item = QListWidgetItem()
        list_item.setSizeHint(row.sizeHint())
        self.list.insertItem(0, list_item)
        self.list.setItemWidget(list_item, row)
        self._bars[item.raw_index] = bar
        self._titles[item.raw_index] = title
        self._open_btns[item.raw_index] = open_btn

    def _update_item(self, item: DownloadItem) -> None:
        bar = self._bars.get(item.raw_index)
        title = self._titles.get(item.raw_index)
        open_btn = self._open_btns.get(item.raw_index)
        if bar is None:
            return
        if item.state == DownloadState.DONE:
            bar.setValue(100)
            bar.setFormat("Done")
            if open_btn is not None:
                open_btn.setVisible(True)
        elif item.state == DownloadState.FAILED:
            bar.setFormat(f"Failed: {item.error}")
            if title is not None:
                title.setStyleSheet("color:#ff6b6b;")
        else:
            bar.setValue(int(item.progress * 100))
            bar.setFormat("%p%")


class PoolsPage(QWidget):
    pool_selected = Signal(object)  # Pool

    def __init__(self, context, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(_page_header("Pools", "Curated, ordered collections"))

        from PySide6.QtWidgets import QLineEdit

        search_row = QHBoxLayout()
        search_row.setContentsMargins(16, 0, 16, 8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search pools…")
        self.search.returnPressed.connect(self.refresh)
        btn = QPushButton("Search")
        btn.setObjectName("Primary")
        btn.clicked.connect(self.refresh)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(btn)
        layout.addLayout(search_row)

        self.status = QLabel("")
        self.status.setObjectName("Subtitle")
        self.status.setContentsMargins(16, 0, 16, 0)
        layout.addWidget(self.status)

        self.list = QListWidget()
        self.list.itemActivated.connect(self._on_item)
        self.list.itemClicked.connect(self._on_item)
        layout.addWidget(self.list, 1)

    def refresh(self) -> None:
        engine = self.context.engine
        if engine is None or not engine.capabilities.pools:
            self.status.setText("This source does not support pools.")
            self.list.clear()
            return
        self.status.setText("Loading…")
        self.list.clear()
        run_async(
            engine.search_pools,
            self.search.text().strip(),
            on_result=self._show_pools,
            on_error=lambda msg: self.status.setText(f"Error: {msg.splitlines()[0]}"),
        )

    def _show_pools(self, pools: list[Pool]) -> None:
        self.status.setText(f"{len(pools)} pools")
        self.list.clear()
        for pool in pools:
            item = QListWidgetItem(f"{pool.label}   ·   {pool.post_count} posts")
            item.setData(Qt.ItemDataRole.UserRole, pool)
            self.list.addItem(item)

    def _on_item(self, item: QListWidgetItem) -> None:
        pool = item.data(Qt.ItemDataRole.UserRole)
        if pool is not None:
            self.pool_selected.emit(pool)
