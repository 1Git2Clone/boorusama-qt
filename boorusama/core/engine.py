"""The pluggable booru engine interface.

A *engine* knows how to talk to one family of booru sites. Concrete engines
(Danbooru, Gelbooru, ...) subclass :class:`BooruEngine` and translate the site's
API into the backend-agnostic models in :mod:`boorusama.core.models`.

Engines are deliberately thin and synchronous: all network calls run on a
background thread pool (see :mod:`boorusama.core.workers`), so engines may block.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from .models import Account, Pool, Post, TagSuggestion


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Declares which features an engine supports so the UI can adapt."""
    search: bool = True
    autocomplete: bool = False
    pools: bool = False
    favorites: bool = False          # server-side favorites
    login: bool = False
    notes: bool = False
    artist_commentary: bool = False


@dataclass(slots=True)
class EngineConfig:
    """User-editable configuration for an engine instance."""
    base_url: str
    name: str = ""
    account: Account | None = None
    extra: dict = field(default_factory=dict)


class BooruEngine(ABC):
    """Abstract base class every backend implements.

    Subclasses must set :attr:`id`, :attr:`display_name`, :attr:`default_base_url`
    and :attr:`capabilities`, then implement :meth:`search_posts`.
    """

    id: str = ""
    display_name: str = ""
    default_base_url: str = ""
    capabilities: EngineCapabilities = EngineCapabilities()
    # A small icon hint (emoji) used in the source switcher until real favicons land.
    icon: str = "🔞"

    def __init__(self, config: EngineConfig):
        self.config = config
        self._client: httpx.Client | None = None

    # --- networking --------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self.config.base_url.rstrip("/")

    @property
    def account(self) -> Account | None:
        return self.config.account

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                headers={"User-Agent": "Boorusama-Qt/0.1 (+https://github.com)"},
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # --- API surface (override in subclasses) ------------------------------
    @abstractmethod
    def search_posts(
        self, tags: str, page: int = 1, limit: int = 40
    ) -> list[Post]:
        """Return a page of posts matching the space-separated *tags* query."""
        raise NotImplementedError

    def autocomplete_tags(self, query: str, limit: int = 12) -> list[TagSuggestion]:
        """Return tag suggestions for *query*. Default: unsupported -> empty."""
        return []

    def get_post(self, post_id: int) -> Post | None:
        """Fetch a single post by id. Default: search by id: metatag if possible."""
        results = self.search_posts(f"id:{post_id}", page=1, limit=1)
        return results[0] if results else None

    def search_pools(self, query: str = "", page: int = 1, limit: int = 24) -> list[Pool]:
        return []

    def get_pool_posts(self, pool: Pool, page: int = 1, limit: int = 40) -> list[Post]:
        return []

    # --- helpers for subclasses -------------------------------------------
    def _auth_params(self) -> dict:
        """Override to inject login params into requests when authenticated."""
        return {}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<{type(self).__name__} id={self.id!r} base={self.base_url!r}>"
