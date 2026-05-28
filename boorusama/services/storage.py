"""SQLite-backed local storage for favorites and search history.

A single database file holds all locally-persisted, structured user data. Posts
are stored as a JSON snapshot so favorites survive even if a remote post is
deleted, and so the grid can render them offline from cache.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from ..core.models import Post, Rating, Tag, TagCategory

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    engine_id   TEXT NOT NULL,
    post_id     INTEGER NOT NULL,
    added_at    REAL NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (engine_id, post_id)
);

CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    engine_id   TEXT NOT NULL,
    query       TEXT NOT NULL,
    searched_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_time ON history (searched_at DESC);
"""


def _post_to_payload(post: Post) -> str:
    return json.dumps(
        {
            "id": post.id,
            "source_engine": post.source_engine,
            "preview_url": post.preview_url,
            "sample_url": post.sample_url,
            "file_url": post.file_url,
            "width": post.width,
            "height": post.height,
            "rating": post.rating.value,
            "score": post.score,
            "file_ext": post.file_ext,
            "source": post.source,
            "tags": [[t.name, t.category.value] for t in post.tags],
        }
    )


def _payload_to_post(payload: str) -> Post:
    d = json.loads(payload)
    return Post(
        id=d["id"],
        source_engine=d.get("source_engine", ""),
        preview_url=d.get("preview_url", ""),
        sample_url=d.get("sample_url", ""),
        file_url=d.get("file_url", ""),
        width=d.get("width", 0),
        height=d.get("height", 0),
        rating=Rating.parse(d.get("rating")),
        score=d.get("score", 0),
        file_ext=d.get("file_ext", ""),
        source=d.get("source", ""),
        tags=[Tag(name=n, category=TagCategory(c)) for n, c in d.get("tags", [])],
    )


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- favorites ---------------------------------------------------------
    def add_favorite(self, post: Post) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO favorites (engine_id, post_id, added_at, payload) "
            "VALUES (?, ?, ?, ?)",
            (post.source_engine, post.id, time.time(), _post_to_payload(post)),
        )
        self._conn.commit()

    def remove_favorite(self, engine_id: str, post_id: int) -> None:
        self._conn.execute(
            "DELETE FROM favorites WHERE engine_id = ? AND post_id = ?",
            (engine_id, post_id),
        )
        self._conn.commit()

    def is_favorite(self, engine_id: str, post_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM favorites WHERE engine_id = ? AND post_id = ? LIMIT 1",
            (engine_id, post_id),
        )
        return cur.fetchone() is not None

    def list_favorites(self, engine_id: str | None = None) -> list[Post]:
        if engine_id:
            cur = self._conn.execute(
                "SELECT payload FROM favorites WHERE engine_id = ? ORDER BY added_at DESC",
                (engine_id,),
            )
        else:
            cur = self._conn.execute(
                "SELECT payload FROM favorites ORDER BY added_at DESC"
            )
        return [_payload_to_post(row["payload"]) for row in cur.fetchall()]

    def favorite_ids(self, engine_id: str) -> set[int]:
        cur = self._conn.execute(
            "SELECT post_id FROM favorites WHERE engine_id = ?", (engine_id,)
        )
        return {row["post_id"] for row in cur.fetchall()}

    # --- history -----------------------------------------------------------
    def add_history(self, engine_id: str, query: str) -> None:
        query = query.strip()
        if not query:
            return
        # De-duplicate consecutive identical searches.
        cur = self._conn.execute(
            "SELECT query FROM history WHERE engine_id = ? ORDER BY searched_at DESC LIMIT 1",
            (engine_id,),
        )
        last = cur.fetchone()
        if last and last["query"] == query:
            return
        self._conn.execute(
            "INSERT INTO history (engine_id, query, searched_at) VALUES (?, ?, ?)",
            (engine_id, query, time.time()),
        )
        self._conn.commit()

    def list_history(self, limit: int = 100) -> list[tuple[str, str, float]]:
        cur = self._conn.execute(
            "SELECT engine_id, query, searched_at FROM history "
            "ORDER BY searched_at DESC LIMIT ?",
            (limit,),
        )
        return [(r["engine_id"], r["query"], r["searched_at"]) for r in cur.fetchall()]

    def clear_history(self) -> None:
        self._conn.execute("DELETE FROM history")
        self._conn.commit()
