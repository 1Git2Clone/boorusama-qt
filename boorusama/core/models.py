"""Backend-agnostic domain models.

Every engine maps its raw API payloads into these dataclasses so the rest of the
application never has to know which booru a post came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TagCategory(str, Enum):
    GENERAL = "general"
    ARTIST = "artist"
    COPYRIGHT = "copyright"
    CHARACTER = "character"
    META = "meta"
    DEFERRED = "deferred"

    @property
    def color(self) -> str:
        """A representative hex color used for tag chips (Danbooru-ish palette)."""
        return {
            TagCategory.GENERAL: "#009be6",
            TagCategory.ARTIST: "#ff8a8b",
            TagCategory.COPYRIGHT: "#c797ff",
            TagCategory.CHARACTER: "#35c64a",
            TagCategory.META: "#ead084",
            TagCategory.DEFERRED: "#bbbbbb",
        }[self]


class Rating(str, Enum):
    GENERAL = "g"
    SENSITIVE = "s"
    QUESTIONABLE = "q"
    EXPLICIT = "e"
    UNKNOWN = "?"

    @classmethod
    def parse(cls, value: str | None) -> "Rating":
        if not value:
            return cls.UNKNOWN
        v = value.strip().lower()
        # Accept both single-letter and full-word forms.
        mapping = {
            "g": cls.GENERAL,
            "general": cls.GENERAL,
            "safe": cls.GENERAL,
            "s": cls.SENSITIVE,
            "sensitive": cls.SENSITIVE,
            "q": cls.QUESTIONABLE,
            "questionable": cls.QUESTIONABLE,
            "e": cls.EXPLICIT,
            "explicit": cls.EXPLICIT,
        }
        return mapping.get(v, cls.UNKNOWN)

    @property
    def label(self) -> str:
        return {
            Rating.GENERAL: "General",
            Rating.SENSITIVE: "Sensitive",
            Rating.QUESTIONABLE: "Questionable",
            Rating.EXPLICIT: "Explicit",
            Rating.UNKNOWN: "Unknown",
        }[self]


@dataclass(slots=True)
class Tag:
    name: str
    category: TagCategory = TagCategory.GENERAL
    post_count: int | None = None

    @property
    def label(self) -> str:
        return self.name.replace("_", " ")


@dataclass(slots=True)
class TagSuggestion:
    """An autocomplete result."""

    name: str
    label: str
    category: TagCategory = TagCategory.GENERAL
    post_count: int | None = None
    antecedent: str | None = None  # set when the match is an alias


@dataclass(slots=True)
class Post:
    """A single image/video result, normalized across backends."""

    id: int
    source_engine: str = ""

    # Media URLs at three sizes; any may be empty if the backend lacks it.
    preview_url: str = ""  # small thumbnail
    sample_url: str = ""  # medium / sample
    file_url: str = ""  # original / full resolution

    width: int = 0
    height: int = 0
    preview_width: int = 0
    preview_height: int = 0

    rating: Rating = Rating.UNKNOWN
    score: int = 0
    fav_count: int = 0
    file_ext: str = ""
    file_size: int = 0
    md5: str = ""
    source: str = ""
    uploader: str = ""
    created_at: str = ""

    tags: list[Tag] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    # --- convenience -------------------------------------------------------
    @property
    def aspect_ratio(self) -> float:
        if self.width and self.height:
            return self.width / self.height
        return 1.0

    @property
    def is_video(self) -> bool:
        return self.file_ext.lower() in {"mp4", "webm", "mkv", "mov", "avi"}

    @property
    def is_animated(self) -> bool:
        return self.is_video or self.file_ext.lower() in {"gif", "apng"}

    @property
    def best_display_url(self) -> str:
        """URL suited to the full viewer (avoid huge originals when a sample exists)."""
        return self.sample_url or self.file_url or self.preview_url

    @property
    def thumbnail_url(self) -> str:
        return self.preview_url or self.sample_url or self.file_url

    @property
    def tag_string(self) -> str:
        return " ".join(t.name for t in self.tags)

    def tags_by_category(self, category: TagCategory) -> list[Tag]:
        return [t for t in self.tags if t.category == category]


@dataclass(slots=True)
class Pool:
    """A named, ordered collection of posts."""

    id: int
    name: str
    description: str = ""
    post_count: int = 0
    category: str = ""
    post_ids: list[int] = field(default_factory=list)
    source_engine: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.name.replace("_", " ")


@dataclass(slots=True)
class Account:
    """Per-engine credentials. The 'secret' is an API key/password depending on site."""

    engine_id: str
    username: str = ""
    secret: str = ""

    @property
    def is_authenticated(self) -> bool:
        return bool(self.username and self.secret)
