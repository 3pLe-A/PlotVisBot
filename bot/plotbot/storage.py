"""SQLite store: one row per plot (text only, no images) plus per-user language."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS plots (
    id          TEXT PRIMARY KEY,
    guild_id    INTEGER,
    channel_id  INTEGER,
    message_id  INTEGER,
    user_id     INTEGER NOT NULL,
    lang        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    spec_json   TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS plots_updated ON plots(updated_at);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    lang    TEXT NOT NULL
);
"""


@dataclass
class PlotRow:
    id: str
    guild_id: int | None
    channel_id: int | None
    message_id: int | None
    user_id: int
    lang: str
    prompt: str
    spec_json: str
    state: dict
    created_at: float
    updated_at: float


class Store:
    def __init__(self, path: str, retention_days: int = 30) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()
        self.retention_s = retention_days * 86400

    def add(self, row: PlotRow) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO plots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (row.id, row.guild_id, row.channel_id, row.message_id, row.user_id, row.lang, row.prompt,
                 row.spec_json, json.dumps(row.state), row.created_at, row.updated_at),
            )

    def get(self, plot_id: str) -> PlotRow | None:
        with self._lock:
            cur = self._db.execute("SELECT * FROM plots WHERE id = ?", (plot_id,))
            r = cur.fetchone()
        if r is None:
            return None
        return PlotRow(*r[:8], json.loads(r[8]), r[9], r[10])

    def update(self, plot_id: str, *, spec_json: str | None = None, state: dict | None = None,
               message_id: int | None = None) -> None:
        sets, args = ["updated_at = ?"], [time.time()]
        if spec_json is not None:
            sets.append("spec_json = ?")
            args.append(spec_json)
        if state is not None:
            sets.append("state_json = ?")
            args.append(json.dumps(state))
        if message_id is not None:
            sets.append("message_id = ?")
            args.append(message_id)
        with self._lock, self._db:
            self._db.execute(f"UPDATE plots SET {', '.join(sets)} WHERE id = ?", (*args, plot_id))

    def purge_expired(self) -> int:
        cutoff = time.time() - self.retention_s
        with self._lock, self._db:
            return self._db.execute("DELETE FROM plots WHERE updated_at < ?", (cutoff,)).rowcount

    def get_lang(self, user_id: int) -> str | None:
        with self._lock:
            r = self._db.execute("SELECT lang FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
        return r[0] if r else None

    def set_lang(self, user_id: int, lang: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO user_settings VALUES (?, ?)", (user_id, lang))
