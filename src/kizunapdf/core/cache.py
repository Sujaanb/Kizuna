import hashlib
import json
import sqlite3
from pathlib import Path


class TranslationCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS translations (key TEXT PRIMARY KEY, target TEXT NOT NULL)"
            )

    @staticmethod
    def key(**parts) -> str:
        return hashlib.sha256(
            json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    def get(self, key: str) -> str | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT target FROM translations WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, target: str):
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO translations VALUES (?, ?)", (key, target))
