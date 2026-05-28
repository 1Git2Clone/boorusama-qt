"""A config-driven engine for Danbooru/Moebooru/Gelbooru-style JSON APIs.

This is the "pluggable without code" path: many boorus differ only in their URL
shape and field names, so :class:`GenericJsonEngine` is parameterized by a
``profile`` dict stored in ``EngineConfig.extra['profile']``. Drop a new profile
into :data:`PROFILES` (or load from JSON) and a new site works with no new class.
"""

from __future__ import annotations

from ..core.engine import BooruEngine, EngineCapabilities
from ..core.models import Post, Rating, Tag, TagCategory
from ..core.registry import register_engine

# A profile describes how to build requests and read fields for one API family.
PROFILES: dict[str, dict] = {
    "moebooru": {
        # yande.re / konachan style
        "search_path": "/post.json",
        "search_params": {"tags": "{tags}", "page": "{page}", "limit": "{limit}"},
        "page_base": 1,
        "fields": {
            "id": "id",
            "preview_url": "preview_url",
            "sample_url": "sample_url",
            "file_url": "file_url",
            "width": "width",
            "height": "height",
            "rating": "rating",
            "score": "score",
            "md5": "md5",
            "source": "source",
            "tags": "tags",
            "file_ext": "file_ext",
        },
    },
    "philomena": {
        # derpibooru / furbooru style
        "search_path": "/api/v1/json/search/images",
        "search_params": {"q": "{tags}", "page": "{page}", "per_page": "{limit}"},
        "page_base": 1,
        "results_key": "images",
        "fields": {
            "id": "id",
            "preview_url": "representations.thumb",
            "sample_url": "representations.medium",
            "file_url": "representations.full",
            "width": "width",
            "height": "height",
            "score": "score",
            "source": "source_url",
            "tags": "tags",
        },
    },
}


def _dig(obj: dict, dotted: str):
    """Read a possibly-nested value via 'a.b.c' dotted path."""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


@register_engine
class GenericJsonEngine(BooruEngine):
    id = "generic"
    display_name = "Generic (config-driven)"
    default_base_url = ""
    icon = "🧩"
    capabilities = EngineCapabilities(search=True, login=False)

    @property
    def profile(self) -> dict:
        prof = self.config.extra.get("profile")
        if isinstance(prof, str):
            return PROFILES.get(prof, PROFILES["moebooru"])
        if isinstance(prof, dict):
            return prof
        return PROFILES["moebooru"]

    def search_posts(self, tags: str, page: int = 1, limit: int = 40) -> list[Post]:
        prof = self.profile
        page_base = prof.get("page_base", 1)
        page_value = page if page_base == 1 else page - 1
        params = {}
        for key, template in prof["search_params"].items():
            params[key] = (
                template.replace("{tags}", tags)
                .replace("{page}", str(page_value))
                .replace("{limit}", str(limit))
            )
        resp = self.client.get(prof["search_path"], params=params)
        resp.raise_for_status()
        data = resp.json()
        results_key = prof.get("results_key")
        if results_key and isinstance(data, dict):
            data = data.get(results_key, [])
        if not isinstance(data, list):
            return []
        return [self._parse(item, prof) for item in data if _dig(item, prof["fields"]["id"])]

    def _parse(self, item: dict, prof: dict) -> Post:
        f = prof["fields"]

        def get(key: str, default=""):
            field_path = f.get(key)
            if not field_path:
                return default
            value = _dig(item, field_path)
            return default if value is None else value

        raw_tags = get("tags", "")
        if isinstance(raw_tags, str):
            tag_names = raw_tags.split()
        elif isinstance(raw_tags, list):
            tag_names = [str(t) for t in raw_tags]
        else:
            tag_names = []

        def as_int(key) -> int:
            value = get(key, "")
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip():
                try:
                    return int(value.strip())
                except ValueError:
                    return 0
            return 0

        return Post(
            id=as_int("id"),
            source_engine=self.config.name or self.id,
            preview_url=str(get("preview_url", "")),
            sample_url=str(get("sample_url", "")),
            file_url=str(get("file_url", "")),
            width=as_int("width"),
            height=as_int("height"),
            rating=Rating.parse(str(get("rating", "")) or None),
            score=as_int("score"),
            file_ext=str(get("file_ext", "")),
            md5=str(get("md5", "")),
            source=str(get("source", "")),
            tags=[Tag(name=n, category=TagCategory.GENERAL) for n in tag_names],
            raw=item,
        )
