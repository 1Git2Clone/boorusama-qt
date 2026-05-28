"""Async image loading with a two-tier (memory + disk) cache.

Thumbnails and full images are fetched off the main thread. Decoded pixmaps are
held in a bounded in-memory LRU; raw bytes are persisted to a disk cache keyed by
a hash of the URL so restarts and re-scrolls are cheap.

We deliberately use a plain ``OrderedDict`` rather than ``QPixmapCache`` to avoid
the latter's overload ambiguity across Qt versions, and to keep cache ownership
explicit. All QPixmap construction happens on the GUI thread.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

from .workers import run_async


def _key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


class ImageLoader(QObject):
    """Loads images by URL and emits ``loaded(url, QPixmap)`` when ready."""

    loaded = Signal(str, QPixmap)
    failed = Signal(str, str)

    def __init__(self, cache_dir: Path, mem_capacity: int = 600, parent: QObject | None = None):
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: "OrderedDict[str, QPixmap]" = OrderedDict()
        self._mem_capacity = mem_capacity
        self._inflight: set[str] = set()
        # Each loader owns its httpx client; it is only ever touched from worker
        # threads via _fetch_bytes, never concurrently with construction.
        self._http = httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={"User-Agent": "Boorusama-Qt/0.1"},
        )

    def close(self) -> None:
        self._http.close()

    # --- public API --------------------------------------------------------
    def get_cached(self, url: str) -> QPixmap | None:
        pm = self._mem.get(url)
        if pm is not None:
            self._mem.move_to_end(url)
        return pm

    def request(self, url: str) -> QPixmap | None:
        """Return a cached pixmap immediately, or kick off a load and return None."""
        if not url:
            return None
        cached = self.get_cached(url)
        if cached is not None:
            return cached
        if url in self._inflight:
            return None
        self._inflight.add(url)
        run_async(
            self._fetch_bytes,
            url,
            on_result=lambda data, u=url: self._on_bytes(u, data),
            on_error=lambda msg, u=url: self._on_error(u, msg),
        )
        return None

    # --- internals ---------------------------------------------------------
    def _disk_path(self, url: str) -> Path:
        return self.cache_dir / _key(url)

    def _fetch_bytes(self, url: str) -> bytes:
        disk = self._disk_path(url)
        if disk.exists():
            return disk.read_bytes()
        resp = self._http.get(url)
        resp.raise_for_status()
        data = resp.content
        try:
            disk.write_bytes(data)
        except OSError:
            pass  # disk cache is best-effort
        return data

    def _store(self, url: str, pixmap: QPixmap) -> None:
        self._mem[url] = pixmap
        self._mem.move_to_end(url)
        while len(self._mem) > self._mem_capacity:
            self._mem.popitem(last=False)

    def _on_bytes(self, url: str, data: bytes) -> None:
        self._inflight.discard(url)
        pm = QPixmap()
        if pm.loadFromData(data):
            self._store(url, pm)
            self.loaded.emit(url, pm)
        else:
            self.failed.emit(url, "Could not decode image data")

    def _on_error(self, url: str, msg: str) -> None:
        self._inflight.discard(url)
        self.failed.emit(url, msg)
