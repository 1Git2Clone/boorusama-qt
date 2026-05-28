"""Application context: the single object the UI talks to.

Holds the loaded config, the active engine, and all local services (storage,
image loader, downloads, blacklist). Swapping the active source rebuilds the
engine and re-applies blacklist/safe-mode settings.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .config import AppConfig, SourceConfig
from .core.engine import BooruEngine, EngineConfig
from .core.imageloader import ImageLoader
from .core.registry import create_engine, load_builtin_engines
from .services.blacklist import Blacklist
from .services.downloads import DownloadManager
from .services.storage import Storage
from . import config as cfg_paths


class AppContext(QObject):
    source_changed = Signal()        # active engine swapped
    settings_changed = Signal()      # theme / blacklist / safe-mode changed
    favorites_changed = Signal()     # a favorite was added/removed

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        load_builtin_engines()

        self.config = AppConfig.load()
        self.storage = Storage(cfg_paths.data_dir() / "boorusama.db")
        self.image_loader = ImageLoader(cfg_paths.cache_dir() / "images")
        self.downloads = DownloadManager(cfg_paths.downloads_dir())
        self.blacklist = Blacklist(self.config.blacklist, self.config.safe_mode)

        self._engine: BooruEngine | None = None
        self._build_engine()

    # --- engine ------------------------------------------------------------
    @property
    def engine(self) -> BooruEngine | None:
        return self._engine

    def _build_engine(self) -> None:
        if self._engine is not None:
            self._engine.close()
            self._engine = None
        src = self.config.current_source
        if src is None:
            return
        ec = EngineConfig(
            base_url=src.base_url,
            name=src.name,
            account=src.to_account(),
            extra={"profile": src.profile} if src.profile else {},
        )
        self._engine = create_engine(src.engine_id, ec)

    def set_active_source(self, index: int) -> None:
        if index == self.config.active_source:
            return
        if 0 <= index < len(self.config.sources):
            self.config.active_source = index
            self.config.save()
            self._build_engine()
            self.source_changed.emit()

    def add_source(self, source: SourceConfig) -> None:
        self.config.sources.append(source)
        self.config.save()

    def update_source(self, index: int, source: SourceConfig) -> None:
        if 0 <= index < len(self.config.sources):
            self.config.sources[index] = source
            self.config.save()
            if index == self.config.active_source:
                self._build_engine()
                self.source_changed.emit()

    def remove_source(self, index: int) -> None:
        if 0 <= index < len(self.config.sources) and len(self.config.sources) > 1:
            self.config.sources.pop(index)
            self.config.active_source = min(
                self.config.active_source, len(self.config.sources) - 1
            )
            self.config.save()
            self._build_engine()
            self.source_changed.emit()

    # --- settings ----------------------------------------------------------
    def apply_settings(self) -> None:
        self.blacklist.set_entries(self.config.blacklist)
        self.blacklist.safe_mode = self.config.safe_mode
        self.config.save()
        self.settings_changed.emit()

    # --- favorites ---------------------------------------------------------
    def toggle_favorite(self, post) -> bool:
        eid = post.source_engine or (self.engine.id if self.engine else "")
        if self.storage.is_favorite(eid, post.id):
            self.storage.remove_favorite(eid, post.id)
            result = False
        else:
            self.storage.add_favorite(post)
            result = True
        self.favorites_changed.emit()
        return result

    def is_favorite(self, post) -> bool:
        eid = post.source_engine or (self.engine.id if self.engine else "")
        return self.storage.is_favorite(eid, post.id)

    # --- lifecycle ---------------------------------------------------------
    def shutdown(self) -> None:
        # Drain in-flight workers before tearing down shared HTTP clients/db,
        # otherwise a running thread can use-after-free a closed httpx client.
        from PySide6.QtCore import QThreadPool

        QThreadPool.globalInstance().waitForDone(5000)
        if self._engine:
            self._engine.close()
        self.storage.close()
