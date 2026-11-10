"""
database.py — SQLite-схема, операції збереження та курсор.

Канонічна модель: author · url · date · text (+ media)
Всі INSERT використовують OR IGNORE → повторний запуск ідемпотентний.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional


DDL = """
-- ── Результати ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,          -- username каналу
    message_id    INTEGER NOT NULL,          -- id повідомлення в Telegram
    author        TEXT,                      -- username або "channel:<source>"
    url           TEXT    NOT NULL UNIQUE,   -- канонічний permalink
    date          TEXT    NOT NULL,          -- ISO-8601 UTC
    text          TEXT    NOT NULL DEFAULT '',
    media_type    TEXT,                      -- photo / video / document / NULL
    media_url     TEXT,                      -- шлях до локального файлу або NULL
    raw_json      TEXT,                      -- повний JSON для відтворення
    collected_at  TEXT    NOT NULL           -- коли зібрано
);
CREATE INDEX IF NOT EXISTS idx_messages_source     ON messages(source);
CREATE INDEX IF NOT EXISTS idx_messages_date       ON messages(date);
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(source, message_id);

-- ── Курсор (стан збору) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cursors (
    source          TEXT PRIMARY KEY,
    last_message_id INTEGER NOT NULL DEFAULT 0,  -- продовжуємо звідси
    updated_at      TEXT    NOT NULL
);

-- ── Entity-кеш (урок лекції: resolve лише раз!) ───────────────────────────────
CREATE TABLE IF NOT EXISTS entity_cache (
    url         TEXT PRIMARY KEY,     -- @username або t.me/...
    peer_id     INTEGER NOT NULL,     -- channel_id
    access_hash INTEGER NOT NULL,
    title       TEXT,
    resolved_at TEXT NOT NULL
);

-- ── Лог подій ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT    NOT NULL,     -- UUID прогону
    source     TEXT,
    event      TEXT    NOT NULL,     -- start / finish / floodwait / error
    detail     TEXT,
    ts         TEXT    NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(DDL)
        self._conn.commit()

    # ── Повідомлення ──────────────────────────────────────────────────────────

    def insert_message(
        self,
        *,
        source: str,
        message_id: int,
        author: Optional[str],
        url: str,
        date: datetime,
        text: str,
        media_type: Optional[str] = None,
        media_url: Optional[str] = None,
        raw: Optional[dict] = None,
    ) -> bool:
        """Вставляє повідомлення. Повертає True якщо вставлено (нове), False якщо вже є."""
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO messages
              (source, message_id, author, url, date, text,
               media_type, media_url, raw_json, collected_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                source,
                message_id,
                author,
                url,
                date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                text or "",
                media_type,
                media_url,
                json.dumps(raw, ensure_ascii=False) if raw else None,
                datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def insert_messages_bulk(self, rows: list[dict]) -> int:
        """Вставляє пакет повідомлень. Повертає кількість нових."""
        inserted = 0
        for r in rows:
            if self.insert_message(**r):
                inserted += 1
        return inserted

    def export_jsonl(self, path: Path, source: Optional[str] = None) -> int:
        """Експортує повідомлення у JSONL-файл. Повертає кількість рядків."""
        q = "SELECT * FROM messages"
        params: tuple = ()
        if source:
            q += " WHERE source = ?"
            params = (source,)
        q += " ORDER BY date"
        rows = self._conn.execute(q, params).fetchall()
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                record = {
                    "author":     row["author"],
                    "url":        row["url"],
                    "date":       row["date"],
                    "text":       row["text"],
                    "media_type": row["media_type"],
                    "source":     row["source"],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return len(rows)

    # ── Курсор ────────────────────────────────────────────────────────────────

    def get_cursor(self, source: str) -> int:
        """Повертає last_message_id для каналу (0 — ще не збирали)."""
        row = self._conn.execute(
            "SELECT last_message_id FROM cursors WHERE source = ?", (source,)
        ).fetchone()
        return row["last_message_id"] if row else 0

    def set_cursor(self, source: str, last_message_id: int) -> None:
        self._conn.execute(
            """
            INSERT INTO cursors (source, last_message_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
              last_message_id = excluded.last_message_id,
              updated_at      = excluded.updated_at
            """,
            (source, last_message_id, datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        self._conn.commit()

    # ── Entity cache ──────────────────────────────────────────────────────────

    def get_cached_entity(self, url: str) -> Optional[tuple[int, int]]:
        """Повертає (peer_id, access_hash) або None."""
        row = self._conn.execute(
            "SELECT peer_id, access_hash FROM entity_cache WHERE url = ?", (url,)
        ).fetchone()
        return (row["peer_id"], row["access_hash"]) if row else None

    def cache_entity(self, url: str, peer_id: int, access_hash: int, title: Optional[str] = None) -> None:
        self._conn.execute(
            """
            INSERT INTO entity_cache (url, peer_id, access_hash, title, resolved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              peer_id     = excluded.peer_id,
              access_hash = excluded.access_hash,
              title       = excluded.title,
              resolved_at = excluded.resolved_at
            """,
            (url, peer_id, access_hash, title,
             datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        self._conn.commit()

    # ── Лог ──────────────────────────────────────────────────────────────────

    def log_event(self, run_id: str, event: str,
                  source: Optional[str] = None, detail: Optional[str] = None) -> None:
        self._conn.execute(
            "INSERT INTO run_log (run_id, source, event, detail, ts) VALUES (?,?,?,?,?)",
            (run_id, source, event,
             detail, datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        self._conn.commit()

    # ── Статистика ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        by_source = self._conn.execute(
            "SELECT source, COUNT(*) AS cnt FROM messages GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        cursors = self._conn.execute(
            "SELECT source, last_message_id, updated_at FROM cursors ORDER BY source"
        ).fetchall()
        floodwaits = self._conn.execute(
            "SELECT COUNT(*) FROM run_log WHERE event='floodwait'"
        ).fetchone()[0]
        return {
            "total": total,
            "by_source": [dict(r) for r in by_source],
            "cursors": [dict(r) for r in cursors],
            "floodwaits": floodwaits,
        }

    def close(self) -> None:
        self._conn.close()
