"""Danbooru engine.

Danbooru exposes a clean JSON API:
  GET /posts.json?tags=...&page=N&limit=L
  GET /autocomplete.json?search[query]=...&search[type]=tag_query
  GET /pools.json?search[name_matches]=...
Authentication is via ``login`` + ``api_key`` query params.
"""

from __future__ import annotations

from ..core.engine import BooruEngine, EngineCapabilities
from ..core.models import Pool, Post, Rating, Tag, TagCategory, TagSuggestion
from ..core.registry import register_engine

_AUTOCOMPLETE_CATEGORY = {
    "general": TagCategory.GENERAL,
    "artist": TagCategory.ARTIST,
    "copyright": TagCategory.COPYRIGHT,
    "character": TagCategory.CHARACTER,
    "meta": TagCategory.META,
}


@register_engine
class DanbooruEngine(BooruEngine):
    id = "danbooru"
    display_name = "Danbooru"
    default_base_url = "https://danbooru.donmai.us"
    icon = "🅓"
    capabilities = EngineCapabilities(
        search=True,
        autocomplete=True,
        pools=True,
        favorites=True,
        login=True,
        notes=True,
        artist_commentary=True,
    )

    # --- auth --------------------------------------------------------------
    def _auth_params(self) -> dict:
        acc = self.account
        if acc and acc.is_authenticated:
            return {"login": acc.username, "api_key": acc.secret}
        return {}

    # --- search ------------------------------------------------------------
    def search_posts(self, tags: str, page: int = 1, limit: int = 40) -> list[Post]:
        params = {"tags": tags, "page": page, "limit": limit}
        params.update(self._auth_params())
        resp = self.client.get("/posts.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):  # error payloads come back as objects
            return []
        return [self._parse_post(item) for item in data if item.get("id")]

    def get_post(self, post_id: int) -> Post | None:
        params = self._auth_params()
        resp = self.client.get(f"/posts/{post_id}.json", params=params)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._parse_post(resp.json())

    # --- autocomplete ------------------------------------------------------
    def autocomplete_tags(self, query: str, limit: int = 12) -> list[TagSuggestion]:
        query = query.strip()
        if not query:
            return []
        params = {
            "search[query]": query,
            "search[type]": "tag_query",
            "limit": limit,
        }
        params.update(self._auth_params())
        resp = self.client.get("/autocomplete.json", params=params)
        resp.raise_for_status()
        out: list[TagSuggestion] = []
        for item in resp.json():
            name = item.get("value") or item.get("name") or ""
            if not name:
                continue
            cat = _AUTOCOMPLETE_CATEGORY.get(item.get("category", ""), TagCategory.GENERAL)
            out.append(
                TagSuggestion(
                    name=name,
                    label=item.get("label", name).replace("_", " "),
                    category=cat,
                    post_count=item.get("post_count"),
                    antecedent=item.get("antecedent"),
                )
            )
        return out

    # --- pools -------------------------------------------------------------
    def search_pools(self, query: str = "", page: int = 1, limit: int = 24) -> list[Pool]:
        params = {
            "search[name_matches]": f"*{query}*" if query else "",
            "search[order]": "post_count",
            "page": page,
            "limit": limit,
        }
        params.update(self._auth_params())
        resp = self.client.get("/pools.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return []
        return [self._parse_pool(item) for item in data]

    def get_pool_posts(self, pool: Pool, page: int = 1, limit: int = 40) -> list[Post]:
        # Use the pool: metatag with custom ordering so posts come back in pool order.
        params = {"tags": f"pool:{pool.id} order:custom", "limit": limit, "page": page}
        params.update(self._auth_params())
        resp = self.client.get("/posts.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return []
        return [self._parse_post(item) for item in data if item.get("id")]

    # --- parsing -----------------------------------------------------------
    def _parse_post(self, item: dict) -> Post:
        tags = self._parse_tags(item)
        return Post(
            id=int(item.get("id", 0)),
            source_engine=self.id,
            preview_url=item.get("preview_file_url", ""),
            sample_url=item.get("large_file_url", "") or item.get("file_url", ""),
            file_url=item.get("file_url", ""),
            width=int(item.get("image_width", 0) or 0),
            height=int(item.get("image_height", 0) or 0),
            rating=Rating.parse(item.get("rating")),
            score=int(item.get("score", 0) or 0),
            fav_count=int(item.get("fav_count", 0) or 0),
            file_ext=item.get("file_ext", ""),
            file_size=int(item.get("file_size", 0) or 0),
            md5=item.get("md5", ""),
            source=item.get("source", ""),
            uploader=str(item.get("uploader_id", "")),
            created_at=item.get("created_at", ""),
            tags=tags,
            raw=item,
        )

    def _parse_tags(self, item: dict) -> list[Tag]:
        buckets = {
            TagCategory.GENERAL: "tag_string_general",
            TagCategory.ARTIST: "tag_string_artist",
            TagCategory.COPYRIGHT: "tag_string_copyright",
            TagCategory.CHARACTER: "tag_string_character",
            TagCategory.META: "tag_string_meta",
        }
        tags: list[Tag] = []
        any_bucket = False
        for category, field_name in buckets.items():
            value = item.get(field_name, "")
            if value:
                any_bucket = True
                tags.extend(Tag(name=n, category=category) for n in value.split())
        if not any_bucket:  # fall back to the flat tag string
            for n in item.get("tag_string", "").split():
                tags.append(Tag(name=n, category=TagCategory.GENERAL))
        return tags

    def _parse_pool(self, item: dict) -> Pool:
        return Pool(
            id=int(item.get("id", 0)),
            name=item.get("name", ""),
            description=item.get("description", ""),
            post_count=int(item.get("post_count", 0) or 0),
            category=item.get("category", ""),
            post_ids=[int(x) for x in item.get("post_ids", [])],
            source_engine=self.id,
            raw=item,
        )
