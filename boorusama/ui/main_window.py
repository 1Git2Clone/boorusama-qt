"""Main window: source switcher, navigation rail, and the content stack."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __version__
from ..core.models import Pool, Post
from ..core.workers import run_async
from .pages import DownloadsPage, FavoritesPage, HistoryPage, PoolsPage
from .post_grid import PostGrid
from .post_viewer import PostViewer
from .search_bar import SearchBar
from .settings_dialog import SettingsDialog
from .theme import build_stylesheet


@dataclass
class NavSnapshot:
    """One entry in the browser-style back/forward history."""

    kind: str  # "browse" | "viewer" | "page"
    # browse:
    mode: str = "search"  # "search" | "pool"
    query: str = ""
    pool: Pool | None = None
    # viewer:
    posts: list[Post] = field(default_factory=list)
    index: int = 0
    # page (sidebar destination: "favorites" | "pools" | "history" | "downloads"):
    page: str = ""


class MainWindow(QMainWindow):
    def __init__(self, context):
        super().__init__()
        self.context = context
        self.setWindowTitle(__app_name__)
        self.resize(1280, 840)

        # Browse/search state.
        self._query = ""
        self._page = 1
        self._mode = "search"  # "search" | "pool"
        self._active_pool: Pool | None = None

        # Browser-style navigation history (back/forward).
        self._history: list[NavSnapshot] = []
        self._hist_pos = -1
        self._navigating = False  # guard: don't push while restoring

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), 1)

        self.statusBar().showMessage("Ready")

        # Wire context signals.
        context.source_changed.connect(self._on_source_changed)
        context.settings_changed.connect(self._apply_theme)
        context.downloads.item_added.connect(
            lambda _i: self.statusBar().showMessage("Download queued", 3000)
        )

        # App-wide filter for back/forward inputs (mouse4/5, Alt+←/→).
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self._apply_theme()
        self._refresh_source_combo()
        # Initial search to populate the grid.
        self.do_search("")

    # --- sidebar -----------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(220)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        title = QLabel(f"🖼  {__app_name__}")
        title.setStyleSheet("font-size:18px; font-weight:700; padding:4px 6px 10px;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Source"))
        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_source_combo_changed)
        layout.addWidget(self.source_combo)
        layout.addSpacing(12)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self._nav_buttons: dict[str, QPushButton] = {}
        for key, label in [
            ("browse", "🔍  Browse"),
            ("favorites", "♥  Favorites"),
            ("pools", "📚  Pools"),
            ("history", "🕘  History"),
            ("downloads", "⤓  Downloads"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _c=False, k=key: self._navigate_user(k))
            layout.addWidget(btn)
            self.nav_group.addButton(btn)
            self._nav_buttons[key] = btn

        layout.addStretch(1)
        settings_btn = QPushButton("⚙  Settings")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)
        version = QLabel(f"v{__version__}")
        version.setObjectName("Subtitle")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        self._nav_buttons["browse"].setChecked(True)
        return bar

    # --- content -----------------------------------------------------------
    def _build_content(self) -> QWidget:
        container = QWidget()
        container.setObjectName("ContentArea")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search bar header (only visible on the browse page).
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(16, 12, 16, 8)
        self.search_bar = SearchBar(self.context)
        self.search_bar.search_requested.connect(lambda q: self.do_search(q))
        header_layout.addWidget(self.search_bar)
        layout.addWidget(self.header)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        # Browse page (grid).
        self.browse_grid = PostGrid(self.context)
        self.browse_grid.post_clicked.connect(self._open_viewer_from_browse)
        self.browse_grid.load_more.connect(self._load_more)
        self.stack.addWidget(self.browse_grid)  # index 0

        # Favorites.
        self.favorites_page = FavoritesPage(self.context)
        self.favorites_page.post_clicked.connect(self._open_viewer)
        self.stack.addWidget(self.favorites_page)  # 1

        # Pools.
        self.pools_page = PoolsPage(self.context)
        self.pools_page.pool_selected.connect(self._open_pool)
        self.stack.addWidget(self.pools_page)  # 2

        # History.
        self.history_page = HistoryPage(self.context)
        self.history_page.search_requested.connect(self._search_from_history)
        self.stack.addWidget(self.history_page)  # 3

        # Downloads.
        self.downloads_page = DownloadsPage(self.context)
        self.stack.addWidget(self.downloads_page)  # 4

        # Viewer.
        self.viewer = PostViewer(self.context)
        self.viewer.back_requested.connect(self._close_viewer)
        self.viewer.search_tag.connect(self._search_from_tag)
        self.viewer.download_requested.connect(self.context.downloads.queue)
        self.viewer.favorite_toggled.connect(
            lambda _p: self._refresh_browse_fav_marks()
        )
        self.stack.addWidget(self.viewer)  # 5

        self._page_index = {
            "browse": 0,
            "favorites": 1,
            "pools": 2,
            "history": 3,
            "downloads": 4,
        }
        return container

    # --- navigation --------------------------------------------------------
    def _navigate_user(self, key: str) -> None:
        """A user-initiated sidebar switch: record it in the back/forward history."""
        cur = (
            self._history[self._hist_pos]
            if 0 <= self._hist_pos < len(self._history)
            else None
        )
        if cur is not None:
            if (
                key == "browse"
                and cur.kind in ("browse", "page")
                and (cur.kind == "browse" or cur.page == "browse")
            ):
                # Already on a browse view — just show it, don't add a duplicate.
                self._navigate("browse")
                return
            if key != "browse" and cur.kind == "page" and cur.page == key:
                return  # already here
        self._push_nav(NavSnapshot(kind="page", page=key))
        self._navigate(key)

    def _navigate(self, key: str) -> None:
        index = self._page_index[key]
        self.stack.setCurrentIndex(index)
        self.header.setVisible(key == "browse")
        self._nav_buttons[key].setChecked(True)
        if key == "favorites":
            self.favorites_page.refresh()
        elif key == "history":
            self.history_page.refresh()
        elif key == "pools" and self.pools_page.list.count() == 0:
            self.pools_page.refresh()

    # --- searching ---------------------------------------------------------
    def do_search(self, query: str, record: bool = True, push: bool = True) -> None:
        self._mode = "search"
        self._query = query.strip()
        self._page = 1
        self.search_bar.set_text(self._query)
        self.browse_grid.clear()
        self._show_browse()
        self._nav_buttons["browse"].setChecked(True)
        self.statusBar().showMessage(f"Searching “{self._query or 'latest'}”…")
        self.browse_grid.set_loading(True)
        if record and self._query and self.context.engine:
            self.context.storage.add_history(self.context.engine.id, self._query)
        if push:
            self._push_nav(NavSnapshot(kind="browse", mode="search", query=self._query))
        self._fetch_page(append=False)

    def _load_more(self) -> None:
        self._page += 1
        self._fetch_page(append=True)

    def _fetch_page(self, append: bool) -> None:
        engine = self.context.engine
        if engine is None:
            self.statusBar().showMessage("No source configured.")
            return
        limit = self.context.config.posts_per_page
        if self._mode == "pool" and self._active_pool is not None:
            fn = engine.get_pool_posts
            args = (self._active_pool, self._page, limit)
        else:
            fn = engine.search_posts
            args = (self._query, self._page, limit)
        run_async(
            fn,
            *args,
            on_result=lambda posts: self._on_posts(posts, append),
            on_error=self._on_search_error,
        )

    def _on_posts(self, posts: list[Post], append: bool) -> None:
        filtered = self.context.blacklist.filter(posts)
        hidden = len(posts) - len(filtered)

        # If the backend returned posts but everything got filtered out, explain
        # why instead of showing a bare "No results." — most often Safe Mode.
        if not filtered and posts:
            blocked_by_safe = self.context.config.safe_mode and any(
                p.rating.value in {"q", "e"} for p in posts
            )
            if blocked_by_safe:
                self.browse_grid.set_empty_message(
                    f"All {len(posts)} results are hidden by Safe Mode.\n"
                    "Turn it off in Settings → Content to view "
                    "questionable/explicit posts."
                )
            else:
                self.browse_grid.set_empty_message(
                    f"All {len(posts)} results are hidden by your blacklist "
                    "(Settings → Content)."
                )
        else:
            self.browse_grid.set_empty_message(
                "No results. Try different tags." if not posts else "No results."
            )

        if append:
            self.browse_grid.append_posts(filtered)
        else:
            self.browse_grid.set_posts(filtered)
        msg = f"{len(self.browse_grid._posts)} posts"
        if hidden:
            msg += f"  ·  {hidden} hidden (Safe Mode / blacklist)"
        self.statusBar().showMessage(msg)
        self.browse_grid.set_loading(False)

    def _on_search_error(self, message: str) -> None:
        self.browse_grid.set_loading(False)
        first = message.splitlines()[0] if message else "Unknown error"
        self.statusBar().showMessage(f"Error: {first}")

    def _search_from_tag(self, tag: str) -> None:
        # do_search switches to the browse grid, leaving the viewer.
        self.do_search(tag)

    def _search_from_history(self, query: str) -> None:
        self._navigate("browse")
        self._nav_buttons["browse"].setChecked(True)
        self.do_search(query)

    # --- pools -------------------------------------------------------------
    def _open_pool(self, pool: Pool, push: bool = True) -> None:
        self._mode = "pool"
        self._active_pool = pool
        self._page = 1
        self.browse_grid.clear()
        self._navigate("browse")
        self._nav_buttons["browse"].setChecked(True)
        self.header.setVisible(True)
        self.search_bar.set_text(f"pool: {pool.label}")
        self.statusBar().showMessage(f"Loading pool “{pool.label}”…")
        self.browse_grid.set_loading(True)
        if push:
            self._push_nav(NavSnapshot(kind="browse", mode="pool", pool=pool))
        self._fetch_page(append=False)

    # --- viewer ------------------------------------------------------------
    def _show_browse(self) -> None:
        self.stack.setCurrentIndex(0)
        self.header.setVisible(True)

    def _open_viewer_from_browse(self, post: Post) -> None:
        posts = list(self.browse_grid._posts)
        self._open_viewer(post, posts)

    def _open_viewer(self, post: Post, posts: list[Post]) -> None:
        try:
            index = posts.index(post)
        except ValueError:
            index = 0
        self._show_viewer(posts, index)

    def _show_viewer(self, posts: list[Post], index: int, push: bool = True) -> None:
        self.viewer.show_posts(posts, index)
        self.stack.setCurrentIndex(5)
        self.header.setVisible(False)
        self.viewer.setFocus()
        if push:
            self._push_nav(NavSnapshot(kind="viewer", posts=posts, index=index))

    def _close_viewer(self) -> None:
        # Return to whichever list page is checked.
        checked = self.nav_group.checkedButton()
        for key, btn in self._nav_buttons.items():
            if btn is checked:
                self._navigate(key)
                return
        self._navigate("browse")

    # --- back/forward navigation history -----------------------------------
    def _push_nav(self, snap: NavSnapshot) -> None:
        if self._navigating:
            return
        # Drop any forward history, then append.
        del self._history[self._hist_pos + 1 :]
        self._history.append(snap)
        self._hist_pos = len(self._history) - 1

    def _sync_viewer_index(self) -> None:
        # Keep the current viewer snapshot's index in step with arrow-key paging,
        # so Forward later reopens the viewer where the user left off.
        if 0 <= self._hist_pos < len(self._history):
            snap = self._history[self._hist_pos]
            if snap.kind == "viewer":
                snap.index = self.viewer._index

    def nav_back(self) -> None:
        self._sync_viewer_index()
        if self._hist_pos <= 0:
            self.statusBar().showMessage("Nothing to go back to", 1500)
            return
        self._hist_pos -= 1
        self._restore(self._history[self._hist_pos])

    def nav_forward(self) -> None:
        self._sync_viewer_index()
        if self._hist_pos >= len(self._history) - 1:
            self.statusBar().showMessage("Nothing to go forward to", 1500)
            return
        self._hist_pos += 1
        self._restore(self._history[self._hist_pos])

    def _restore(self, snap: NavSnapshot) -> None:
        self._navigating = True
        try:
            if snap.kind == "viewer":
                self._show_viewer(snap.posts, snap.index, push=False)
            elif snap.kind == "page":
                # A sidebar destination. "browse" just shows the current grid;
                # the others switch (and refresh) their page.
                self._navigate(snap.page or "browse")
            elif snap.mode == "pool" and snap.pool is not None:
                self._open_pool(snap.pool, push=False)
            else:
                self.do_search(snap.query, record=False, push=False)
        finally:
            self._navigating = False

    def _refresh_browse_fav_marks(self) -> None:
        for thumb in self.browse_grid._thumbs:
            thumb.set_favorite(self.context.is_favorite(thumb.post))

    # --- sources -----------------------------------------------------------
    def _refresh_source_combo(self) -> None:
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for src in self.context.config.sources:
            self.source_combo.addItem(src.name)
        self.source_combo.setCurrentIndex(self.context.config.active_source)
        self.source_combo.blockSignals(False)

    def _on_source_combo_changed(self, index: int) -> None:
        self.context.set_active_source(index)

    def _on_source_changed(self) -> None:
        self.pools_page.list.clear()
        # Switching backend starts a fresh navigation history.
        self._history.clear()
        self._hist_pos = -1
        self.do_search("")

    # --- global input: back/forward ---------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.MouseButtonPress:
            btn = event.button()
            if btn == Qt.MouseButton.BackButton:
                self.nav_back()
                return True
            if btn == Qt.MouseButton.ForwardButton:
                self.nav_forward()
                return True
        elif et == QEvent.Type.KeyPress and self.isActiveWindow():
            # Alt+←/→ act as back/forward everywhere on the main window (including
            # the search field — Alt+arrows have no text-editing meaning). The
            # modal settings dialog is excluded via isActiveWindow().
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                if event.key() == Qt.Key.Key_Left:
                    self.nav_back()
                    return True
                if event.key() == Qt.Key.Key_Right:
                    self.nav_forward()
                    return True
        return super().eventFilter(obj, event)

    # --- settings & theme --------------------------------------------------
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.context, self)
        if dialog.exec():
            self._refresh_source_combo()
            self._apply_theme()
            self._apply_grid_columns()
            # Re-run current search with new filters (a refresh, not a new nav).
            self.do_search(self._query, record=False, push=False)

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(
                build_stylesheet(self.context.config.theme, self.context.config.accent)
            )
        self._apply_grid_columns()

    def _apply_grid_columns(self) -> None:
        cols = self.context.config.grid_columns
        self.browse_grid.set_fixed_columns(cols)
        self.favorites_page.grid.set_fixed_columns(cols)

    # --- lifecycle ---------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.context.shutdown()
        super().closeEvent(event)
