"""Gelbooru engine.

Gelbooru's DAPI:
  GET /index.php?page=dapi&s=post&q=index&json=1&tags=...&pid=N&limit=L
  GET /index.php?page=dapi&s=tag&q=index&json=1&name_pattern=...   (autocomplete-ish)
Auth uses ``api_key`` + ``user_id`` query params.

Note: Gelbooru paginates with a zero-based page id (``pid``), not a 1-based page.
"""

from __future__ import annotations

from ..core.engine import BooruEngine, EngineCapabilities
from ..core.models import Post, Rating, Tag, TagCategory, TagSuggestion
from ..core.registry import register_engine


@register_engine
class GelbooruEngine(BooruEngine):
    id = "gelbooru"
    display_name = "Gelbooru"
    default_base_url = "https://gelbooru.com"
    icon = "🅖"
    capabilities = EngineCapabilities(
        search=True,
        autocomplete=True,
        pools=False,
        favorites=False,
        login=True,
    )

    def _auth_params(self) -> dict:
        acc = self.account
        if acc and acc.is_authenticated:
            # Gelbooru: username field carries user_id, secret carries api_key.
            return {"user_id": acc.username, "api_key": acc.secret}
        return {}

    def search_posts(self, tags: str, page: int = 1, limit: int = 40) -> list[Post]:
        params = {
            "page": "dapi",
            "s": "post",
            "q": "index",
            "json": "1",
            "tags": tags,
            "pid": max(page - 1, 0),  # zero-based
            "limit": limit,
        }
        params.update(self._auth_params())
        resp = self.client.get("/index.php", params=params)
        resp.raise_for_status()
        data = resp.json()
        # Gelbooru returns either a bare list or {"post": [...], "@attributes": {...}}.
        if isinstance(data, dict):
            data = data.get("post", [])
        if not isinstance(data, list):
            return []
        return [self._parse_post(item) for item in data if item.get("id")]

    def autocomplete_tags(self, query: str, limit: int = 12) -> list[TagSuggestion]:
        query = query.strip()
        if not query:
            return []
        params = {
            "page": "dapi",
            "s": "tag",
            "q": "index",
            "json": "1",
            "name_pattern": f"{query}%",
            "orderby": "count",
            "limit": limit,
        }
        params.update(self._auth_params())
        resp = self.client.get("/index.php", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("tag", [])
        if not isinstance(data, list):
            return []
        out: list[TagSuggestion] = []
        for item in data:
            name = item.get("name", "") or item.get("tag", "")
            if not name:
                continue
            out.append(
                TagSuggestion(
                    name=name,
                    label=name.replace("_", " "),
                    category=self._tag_type(item.get("type")),
                    post_count=int(item.get("count", 0) or 0),
                )
            )
        return out

    @staticmethod
    def _tag_type(value) -> TagCategory:
        mapping = {
            0: TagCategory.GENERAL,
            1: TagCategory.ARTIST,
            3: TagCategory.COPYRIGHT,
            4: TagCategory.CHARACTER,
            5: TagCategory.META,
        }
        try:
            return mapping.get(int(value), TagCategory.GENERAL)
        except (TypeError, ValueError):
            return TagCategory.GENERAL

    def _parse_post(self, item: dict) -> Post:
        # Gelbooru gives a flat tag string with no per-category breakdown.
        tags = [Tag(name=n, category=TagCategory.GENERAL)
                for n in str(item.get("tags", "")).split()]
        return Post(
            id=int(item.get("id", 0)),
            source_engine=self.id,
            preview_url=item.get("preview_url", ""),
            sample_url=item.get("sample_url", "") or item.get("file_url", ""),
            file_url=item.get("file_url", ""),
            width=int(item.get("width", 0) or 0),
            height=int(item.get("height", 0) or 0),
            preview_width=int(item.get("preview_width", 0) or 0),
            preview_height=int(item.get("preview_height", 0) or 0),
            rating=Rating.parse(item.get("rating")),
            score=int(item.get("score", 0) or 0),
            file_ext=(item.get("image", "").rsplit(".", 1)[-1] if item.get("image") else ""),
            md5=item.get("md5", ""),
            source=item.get("source", ""),
            uploader=item.get("owner", ""),
            created_at=item.get("created_at", ""),
            tags=tags,
            raw=item,
        )
