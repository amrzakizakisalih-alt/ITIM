"""
ProfileManager – Persistence of the learner profile across sessions.

Saves and reloads the StudentModel state (ACT-R chunks, behavioral
history) in a JSON file. Allows the tutor to remember the student
from one session to the next.
"""

import json
import logging
import os
import time
from typing import Dict, Any, Optional

from core.persistence import SQLiteStore
from domain.cognitive.student_model import StudentModel

logger = logging.getLogger(__name__)

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "profiles")
os.makedirs(PROFILE_DIR, exist_ok=True)
DB_PATH = os.path.join(PROFILE_DIR, "profiles.db")


class ProfileManager(SQLiteStore):
    """
    Manages the persistence of student profiles via SQLite.
    """

    _TABLE = "profiles"
    _PK = "user_id"
    _CREATE_SQL = """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY,
            last_session REAL NOT NULL DEFAULT 0,
            chunks TEXT NOT NULL DEFAULT '{}',
            behavioral_summary TEXT NOT NULL DEFAULT '{}'
        )
    """

    def __init__(self, user_id: str = "default"):
        super().__init__(DB_PATH)
        self.user_id = user_id
        self._ensure_table(self._CREATE_SQL)
        self._maybe_migrate_json_legacy()

    def _maybe_migrate_json_legacy(self) -> None:
        """Migrate individual old JSON files to SQLite."""
        for fname in os.listdir(PROFILE_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(PROFILE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                user_id = profile.get("user_id", fname[:-5])
                self._upsert(
                    self._TABLE,
                    ["user_id", "last_session", "chunks", "behavioral_summary"],
                    self._PK,
                    (
                        user_id,
                        profile.get("last_session", 0),
                        json.dumps(profile.get("chunks", {})),
                        json.dumps(profile.get("behavioral_summary", {})),
                    ),
                )
                os.rename(fpath, fpath + ".migrated")
                logger.info("Migrated profile '%s' to SQLite", user_id)
            except Exception as exc:
                logger.warning("Profile JSON migration failed for %s: %s", fname, exc)

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self, student_model: StudentModel) -> bool:
        """Save the StudentModel to SQLite."""
        try:
            chunks = {
                name: {
                    "activation": chunk.activation,
                    "success_count": chunk.success_count,
                    "failure_count": chunk.failure_count,
                    "last_accessed": chunk.last_accessed,
                }
                for name, chunk in student_model.chunks.items()
            }
            behavioral_summary = {
                "total_actions": len(student_model.behavioral_history),
                "eraser_count": student_model.eraser_count,
                "idle_time": student_model.idle_time,
            }
            self._upsert(
                self._TABLE,
                ["user_id", "last_session", "chunks", "behavioral_summary"],
                self._PK,
                (
                    self.user_id,
                    time.time(),
                    json.dumps(chunks),
                    json.dumps(behavioral_summary),
                ),
            )
            logger.info("[ProfileManager] Saved profile for '%s'", self.user_id)
            return True
        except Exception as e:
            logger.error("[ProfileManager] Save error: %s", e)
            return False

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self, student_model: StudentModel) -> bool:
        """Reload the profile from SQLite and update the StudentModel."""
        try:
            row = self._fetch_one(self._TABLE, self._PK, self.user_id)
            if row is None:
                logger.info("[ProfileManager] No existing profile for '%s'", self.user_id)
                return False

            profile = dict(row)
            for name, data in json.loads(profile.get("chunks", "{}")).items():
                student_model.add_chunk(name, data.get("activation", 0.0))
                chunk = student_model.chunks[name]
                chunk.success_count = data.get("success_count", 0)
                chunk.failure_count = data.get("failure_count", 0)
                chunk.last_accessed = data.get("last_accessed", time.time())

            logger.info("[ProfileManager] Loaded profile for '%s' (%s chunks)",
                        self.user_id, len(json.loads(profile.get("chunks", "{}"))))
            return True
        except Exception as e:
            logger.error("[ProfileManager] Load error: %s", e)
            return False

    def load_or_create(self, student_model: StudentModel) -> Dict[str, Any]:
        """
        Load the profile if it exists, otherwise return an empty profile.
        Always returns a dict with the welcome info.
        """
        loaded = self.load(student_model)
        if loaded:
            return {
                "status": "welcome_back",
                "message": self._welcome_back_message(student_model),
            }
        return {
            "status": "new_user",
            "message": "Welcome! I'm your AI tutor. Let's start learning! 🎓",
        }

    def _welcome_back_message(self, student_model: StudentModel) -> str:
        """Generate a personalized welcome message based on the profile."""
        weak_chunks = [
            name for name, chunk in student_model.chunks.items()
            if chunk.failure_count > chunk.success_count
        ]
        strong_chunks = [
            name for name, chunk in student_model.chunks.items()
            if chunk.success_count > chunk.failure_count
        ]

        msg = "Welcome back! 🎓"
        if weak_chunks:
            concepts = ", ".join(c.replace("_", " ") for c in weak_chunks[:3])
            msg += f"\nLast time you struggled with: **{concepts}**. Let's review those!"
        if strong_chunks and not weak_chunks:
            concepts = ", ".join(c.replace("_", " ") for c in strong_chunks[:3])
            msg += f"\nYou're doing great at: **{concepts}**. Ready for a challenge?"
        return msg

