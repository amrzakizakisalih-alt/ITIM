"""
persistence – Base class for SQLite persistence.

Factorizes common boilerplate for ExerciseLibrary, BuggyRuleLearner
and ProfileManager (_init_db, JSON migration, upsert, load).
"""

import json
import logging
import os
import sqlite3
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class SQLiteStore:
    """Generic SQLite storage with legacy JSON migration."""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def _ensure_table(self, create_sql: str) -> None:
        """Create the table if it does not exist."""
        try:
            with sqlite3.connect(self.storage_path) as conn:
                conn.execute(create_sql)
        except Exception as exc:
            logger.error("Failed to init DB %s: %s", self.storage_path, exc)

    def _migrate_json(
        self,
        json_path: str,
        migrate_fn: Callable[[Any], None],
    ) -> None:
        """Migrate an old JSON file to SQLite."""
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else list(data.values())
            for item in items:
                migrate_fn(item)
            logger.info("Migrated %d item(s) from %s", len(items), json_path)
            os.rename(json_path, json_path + ".migrated")
        except Exception as exc:
            logger.warning("JSON migration failed for %s: %s", json_path, exc)

    def _upsert(
        self,
        table: str,
        columns: List[str],
        pk: str,
        values: tuple,
    ) -> None:
        """INSERT … ON CONFLICT(pk) DO UPDATE."""
        placeholders = ", ".join("?" for _ in columns)
        updates = ", ".join(f"{c}=excluded.{c}" for c in columns if c != pk)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT({pk}) DO UPDATE SET {updates}"
        )
        with sqlite3.connect(self.storage_path) as conn:
            conn.execute(sql, values)

    def _fetch_all(self, table: str) -> List[sqlite3.Row]:
        """Return all rows from the table."""
        if not os.path.exists(self.storage_path):
            return []
        try:
            with sqlite3.connect(self.storage_path) as conn:
                conn.row_factory = sqlite3.Row
                return conn.execute(f"SELECT * FROM {table}").fetchall()
        except Exception as exc:
            logger.warning("Failed to load from %s: %s", self.storage_path, exc)
            return []

    def _fetch_one(
        self, table: str, pk_col: str, pk_val: str
    ) -> Optional[sqlite3.Row]:
        """Return a row by primary key."""
        if not os.path.exists(self.storage_path):
            return None
        try:
            with sqlite3.connect(self.storage_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"SELECT * FROM {table} WHERE {pk_col} = ?", (pk_val,)
                ).fetchone()
                return row
        except Exception as exc:
            logger.warning("Failed to fetch from %s: %s", self.storage_path, exc)
            return None

    def _delete(self, table: str, pk_col: str, pk_val: str) -> bool:
        """Delete a row by primary key."""
        try:
            with sqlite3.connect(self.storage_path) as conn:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE {pk_col} = ?", (pk_val,)
                )
                return cur.rowcount > 0
        except Exception as exc:
            logger.error("Delete error in %s: %s", self.storage_path, exc)
            return False

    def _list_ids(self, table: str, pk_col: str) -> List[str]:
        """List all values of a PK column."""
        try:
            with sqlite3.connect(self.storage_path) as conn:
                rows = conn.execute(f"SELECT {pk_col} FROM {table}").fetchall()
                return [r[0] for r in rows]
        except Exception as exc:
            logger.error("List error in %s: %s", self.storage_path, exc)
            return []
