"""Download manager: fetches original files to disk off the main thread.

Each download is tracked as a :class:`DownloadItem`; the manager emits Qt signals
so a downloads view can show live progress. Streaming keeps memory flat for large
videos/originals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Signal

from ..core.models import Post
from ..core.workers import run_async


class DownloadState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class DownloadItem:
    post: Post
    dest: Path
    state: DownloadState = DownloadState.QUEUED
    received: int = 0
    total: int = 0
    error: str = ""
    raw_index: int = field(default=0)

    @property
    def progress(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.received / self.total


def _safe_filename(post: Post) -> str:
    ext = post.file_ext or (post.file_url.rsplit(".", 1)[-1] if "." in post.file_url else "bin")
    return f"{post.source_engine}_{post.id}.{ext}"


class DownloadManager(QObject):
    item_added = Signal(object)      # DownloadItem
    item_updated = Signal(object)    # DownloadItem
    item_finished = Signal(object)   # DownloadItem

    def __init__(self, download_dir: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.items: list[DownloadItem] = []

    def queue(self, post: Post, dest_dir: Path | None = None) -> DownloadItem | None:
        url = post.file_url or post.sample_url
        if not url:
            return None
        dest = (dest_dir or self.download_dir) / _safe_filename(post)
        item = DownloadItem(post=post, dest=dest)
        item.raw_index = len(self.items)
        self.items.append(item)
        self.item_added.emit(item)
        run_async(
            self._download,
            item,
            url,
            on_error=lambda msg, it=item: self._on_error(it, msg),
        )
        return item

    def _download(self, item: DownloadItem, url: str) -> None:
        item.state = DownloadState.RUNNING
        self.item_updated.emit(item)
        tmp = item.dest.with_suffix(item.dest.suffix + ".part")
        # A real User-Agent is required: booru CDNs (e.g. cdn.donmai.us) return
        # 403 for the default python-httpx agent. A same-origin Referer also helps
        # with hotlink protection on some sites.
        from urllib.parse import urlsplit

        origin = urlsplit(url)
        headers = {
            "User-Agent": "Boorusama-Qt/0.1 (+https://github.com)",
            "Referer": f"{origin.scheme}://{origin.netloc}/",
        }
        with httpx.stream(
            "GET", url, headers=headers, follow_redirects=True, timeout=60.0
        ) as resp:
            resp.raise_for_status()
            item.total = int(resp.headers.get("content-length", 0) or 0)
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    fh.write(chunk)
                    item.received += len(chunk)
                    self.item_updated.emit(item)
        tmp.replace(item.dest)
        item.state = DownloadState.DONE
        self.item_finished.emit(item)

    def _on_error(self, item: DownloadItem, msg: str) -> None:
        item.state = DownloadState.FAILED
        item.error = msg.splitlines()[0] if msg else "Download failed"
        self.item_finished.emit(item)
