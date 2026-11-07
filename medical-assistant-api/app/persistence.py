"""SQLite durable snapshot for in-memory entity dicts (stdlib sqlite3)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

DEFAULT_SQLITE_PATH = "/workspace/medical-assistant-api/data/app.db"


def store_backend() -> str:
    return (os.environ.get("STORE_BACKEND") or "sqlite").strip().lower()


def sqlite_path() -> str:
    return (os.environ.get("SQLITE_PATH") or DEFAULT_SQLITE_PATH).strip()


def reset_requested() -> bool:
    """Honor RESET_STORE; blocked in prod unless ALLOW_RESET_IN_PROD=1."""
    try:
        from app.settings import reset_store_allowed
        return reset_store_allowed()
    except Exception:
        # fallback if settings missing during early import
        return (os.environ.get("RESET_STORE") or "").strip() in ("1", "true", "True", "yes")


class SqliteStore:
    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or sqlite_path()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        # One shared connection is used from FastAPI's threadpool: serialize all access,
        # otherwise concurrent snapshots raise sqlite3.InterfaceError ("bad parameter or other API misuse").
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entities (
                kind TEXT NOT NULL,
                id TEXT NOT NULL,
                data TEXT NOT NULL,
                PRIMARY KEY (kind, id)
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def wipe(self) -> None:
        self._conn.execute("DELETE FROM entities")
        self._conn.execute("DELETE FROM kv_meta")
        self._conn.commit()

    def entity_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()
        return int(row[0] if row else 0)

    def has_data(self) -> bool:
        return self.entity_count() > 0

    def get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM kv_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str, *, commit: bool = True) -> None:
        self._conn.execute(
            "INSERT INTO kv_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        if commit:
            self._conn.commit()

    def save_counters(self, counters: dict[str, Any], *, commit: bool = True) -> None:
        self.set_meta("counters", json.dumps(counters, ensure_ascii=False), commit=commit)

    def load_counters(self) -> dict[str, Any]:
        raw = self.get_meta("counters")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _upsert_unlocked(self, kind: str, eid: str, data: Any, *, commit: bool = True) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        self._conn.execute(
            "INSERT INTO entities(kind, id, data) VALUES(?, ?, ?) "
            "ON CONFLICT(kind, id) DO UPDATE SET data = excluded.data",
            (kind, eid, payload),
        )
        if commit:
            self._conn.commit()

    def _delete_unlocked(self, kind: str, eid: str, *, commit: bool = True) -> None:
        self._conn.execute(
            "DELETE FROM entities WHERE kind = ? AND id = ?", (kind, eid)
        )
        if commit:
            self._conn.commit()

    def _replace_kind_unlocked(self, kind: str, mapping: dict[str, Any], *, commit: bool = True) -> None:
        self._conn.execute("DELETE FROM entities WHERE kind = ?", (kind,))
        rows = [
            (kind, str(eid), json.dumps(data, ensure_ascii=False))
            for eid, data in mapping.items()
        ]
        if rows:
            self._conn.executemany(
                "INSERT INTO entities(kind, id, data) VALUES(?, ?, ?)", rows
            )
        if commit:
            self._conn.commit()

    def _snapshot_unlocked(
        self,
        kinds: dict[str, dict[str, Any]],
        *,
        counters: Optional[dict[str, Any]] = None,
    ) -> None:
        """Atomically replace all provided kinds (+ optional counters)."""
        try:
            for kind, mapping in kinds.items():
                self.replace_kind(kind, mapping, commit=False)
            if counters is not None:
                self.save_counters(counters, commit=False)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def _load_kind_unlocked(self, kind: str) -> dict[str, Any]:
        rows = self._conn.execute(
            "SELECT id, data FROM entities WHERE kind = ?", (kind,)
        ).fetchall()
        out: dict[str, Any] = {}
        for eid, raw in rows:
            try:
                out[eid] = json.loads(raw)
            except json.JSONDecodeError:
                continue
        return out

    def _load_all_unlocked(self) -> dict[str, dict[str, Any]]:
        rows = self._conn.execute("SELECT kind, id, data FROM entities").fetchall()
        out: dict[str, dict[str, Any]] = {}
        for kind, eid, raw in rows:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            out.setdefault(kind, {})[eid] = data
        return out


def _locked(fn_name: str):
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return getattr(self, f"_{fn_name}_unlocked")(*args, **kwargs)
    wrapper.__name__ = fn_name
    return wrapper


for _n in ("upsert", "delete", "replace_kind", "snapshot", "load_kind", "load_all"):
    setattr(SqliteStore, _n, _locked(_n))
