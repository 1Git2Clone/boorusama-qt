"""Application configuration and on-disk paths.

Settings persist to a JSON file under the platform config dir. Sources (engine
instances the user has configured) are stored here too, including credentials.
Larger/structured data (favorites, history) lives in SQLite — see
:mod:`boorusama.services.storage`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from .core.models import Account

APP_DIR_NAME = "boorusama-qt"


def _base_dir(location: QStandardPaths.StandardLocation) -> Path:
    root = QStandardPaths.writableLocation(location)
    if not root:
        root = str(Path.home() / ".local" / "share")
    path = Path(root) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    return _base_dir(QStandardPaths.StandardLocation.AppConfigLocation)


def data_dir() -> Path:
    return _base_dir(QStandardPaths.StandardLocation.AppDataLocation)


def cache_dir() -> Path:
    return _base_dir(QStandardPaths.StandardLocation.CacheLocation)


def downloads_dir() -> Path:
    root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DownloadLocation
    )
    path = Path(root or (Path.home() / "Downloads")) / "Boorusama-Qt"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class SourceConfig:
    """A user-configured engine instance shown in the source switcher."""
    engine_id: str
    name: str
    base_url: str
    username: str = ""
    secret: str = ""
    profile: str = ""  # only for the generic engine

    def to_account(self) -> Account:
        return Account(engine_id=self.engine_id, username=self.username, secret=self.secret)


@dataclass
class AppConfig:
    sources: list[SourceConfig] = field(default_factory=list)
    active_source: int = 0
    theme: str = "dark"          # "dark" | "light" | "midnight"
    accent: str = "#009be6"
    grid_columns: int = 0        # 0 = auto
    safe_mode: bool = True       # hide explicit/questionable by default
    blacklist: list[str] = field(default_factory=list)
    posts_per_page: int = 40
    autocomplete_enabled: bool = True

    # --- persistence -------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        path = cls.path()
        if not path.exists():
            return cls.with_defaults()
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls.with_defaults()
        sources = [SourceConfig(**s) for s in raw.get("sources", [])]
        cfg = cls(
            sources=sources,
            active_source=raw.get("active_source", 0),
            theme=raw.get("theme", "dark"),
            accent=raw.get("accent", "#009be6"),
            grid_columns=raw.get("grid_columns", 0),
            safe_mode=raw.get("safe_mode", True),
            blacklist=raw.get("blacklist", []),
            posts_per_page=raw.get("posts_per_page", 40),
            autocomplete_enabled=raw.get("autocomplete_enabled", True),
        )
        if not cfg.sources:
            cfg.sources = cls.default_sources()
        cfg.active_source = max(0, min(cfg.active_source, len(cfg.sources) - 1))
        return cfg

    def save(self) -> None:
        payload = {
            "sources": [asdict(s) for s in self.sources],
            "active_source": self.active_source,
            "theme": self.theme,
            "accent": self.accent,
            "grid_columns": self.grid_columns,
            "safe_mode": self.safe_mode,
            "blacklist": self.blacklist,
            "posts_per_page": self.posts_per_page,
            "autocomplete_enabled": self.autocomplete_enabled,
        }
        self.path().write_text(json.dumps(payload, indent=2), "utf-8")

    # --- defaults ----------------------------------------------------------
    @staticmethod
    def default_sources() -> list[SourceConfig]:
        return [
            SourceConfig("danbooru", "Danbooru", "https://danbooru.donmai.us"),
            SourceConfig("danbooru", "Safebooru", "https://safebooru.donmai.us"),
            SourceConfig("gelbooru", "Gelbooru", "https://gelbooru.com"),
            SourceConfig("generic", "yande.re", "https://yande.re", profile="moebooru"),
            SourceConfig("generic", "Konachan", "https://konachan.com", profile="moebooru"),
        ]

    @classmethod
    def with_defaults(cls) -> "AppConfig":
        cfg = cls(sources=cls.default_sources())
        return cfg

    @property
    def current_source(self) -> SourceConfig | None:
        if 0 <= self.active_source < len(self.sources):
            return self.sources[self.active_source]
        return None
