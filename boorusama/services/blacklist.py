"""Tag blacklist filtering.

Mirrors Danbooru-style blacklist semantics: each blacklist *entry* is a line of
space-separated tags, and a post is hidden if it matches ALL tags on any single
line (AND within a line, OR across lines). A leading ``-`` negates a term.
Ratings can be matched via the ``rating:<x>`` pseudo-tag.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..core.models import Post


class Blacklist:
    def __init__(self, entries: Iterable[str] | None = None, safe_mode: bool = False):
        self.entries: list[list[str]] = []
        self.safe_mode = safe_mode
        self.set_entries(entries or [])

    def set_entries(self, entries: Iterable[str]) -> None:
        self.entries = []
        for line in entries:
            terms = [t.strip().lower() for t in line.split() if t.strip()]
            if terms:
                self.entries.append(terms)

    def _post_token_set(self, post: Post) -> set[str]:
        tokens = {t.name.lower() for t in post.tags}
        tokens.add(f"rating:{post.rating.value}")
        return tokens

    def _line_matches(self, terms: list[str], tokens: set[str]) -> bool:
        for term in terms:
            if term.startswith("-"):
                if term[1:] in tokens:
                    return False
            elif term not in tokens:
                return False
        return True

    def is_blocked(self, post: Post) -> bool:
        tokens = self._post_token_set(post)
        if self.safe_mode and post.rating.value in {"q", "e"}:
            return True
        return any(self._line_matches(terms, tokens) for terms in self.entries)

    def filter(self, posts: Iterable[Post]) -> list[Post]:
        return [p for p in posts if not self.is_blocked(p)]
