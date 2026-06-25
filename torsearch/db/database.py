from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    collection TEXT NOT NULL,
    id         TEXT NOT NULL,
    data       TEXT NOT NULL,
    PRIMARY KEY (collection, id)
)
"""


class Database:
    """Tiny document store over SQLite (WAL). Rows hold JSON blobs keyed by id.

    Each operation uses its own short-lived connection: SQLite serialises writes at the
    file level (with a busy timeout) and WAL lets readers and a writer run concurrently,
    so the monitor loop and web requests no longer clobber each other's writes.
    """

    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._path, timeout=10)
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def collection(self, name: str) -> Collection:
        return Collection(self, name)


class Collection:
    def __init__(self, db: Database, name: str):
        self._db = db
        self._name = name

    def all(self) -> list[dict]:
        with self._db._connect() as con:
            rows = con.execute(
                "SELECT data FROM documents WHERE collection=? ORDER BY rowid",
                (self._name,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def get(self, id: str) -> dict | None:
        with self._db._connect() as con:
            row = con.execute(
                "SELECT data FROM documents WHERE collection=? AND id=?",
                (self._name, id),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def upsert(self, id: str, data: dict) -> None:
        with self._db._connect() as con:
            con.execute(
                "INSERT INTO documents(collection, id, data) VALUES(?, ?, ?) "
                "ON CONFLICT(collection, id) DO UPDATE SET data=excluded.data",
                (self._name, id, json.dumps(data)),
            )

    def delete(self, id: str) -> None:
        with self._db._connect() as con:
            con.execute(
                "DELETE FROM documents WHERE collection=? AND id=?", (self._name, id)
            )

    def replace_all(self, items: list[tuple[str, dict]]) -> None:
        with self._db._connect() as con:
            con.execute("DELETE FROM documents WHERE collection=?", (self._name,))
            con.executemany(
                "INSERT INTO documents(collection, id, data) VALUES(?, ?, ?)",
                [(self._name, id, json.dumps(data)) for id, data in items],
            )

    def count(self) -> int:
        with self._db._connect() as con:
            return con.execute(
                "SELECT COUNT(*) FROM documents WHERE collection=?", (self._name,)
            ).fetchone()[0]

    def is_empty(self) -> bool:
        return self.count() == 0
