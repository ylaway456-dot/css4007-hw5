"""Part 3: per-user persistent preferences. Conversation state uses SqliteSaver."""
import re
import sqlite3
from pathlib import Path

PREFERENCE_PATTERN = re.compile(
    r"\b(?:prefer\s+(?:replies|answers)\s+in|reply\s+in|respond\s+in)\s+(Kazakh|Russian|English)\b",
    re.IGNORECASE,
)


def parse_language_preference(message: str) -> str | None:
    match = PREFERENCE_PATTERN.search(message)
    return match.group(1).capitalize() if match else None


class UserMemory:
    """SQLite preferences indexed by application-supplied user_id only."""

    def __init__(self, storage_dir: str | Path):
        self.directory = Path(storage_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / "preferences.sqlite"
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS user_preferences (user_id TEXT PRIMARY KEY, language TEXT NOT NULL)")

    def get_language(self, user_id: str) -> str | None:
        with sqlite3.connect(self.db_path) as connection:
            row = connection.execute("SELECT language FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
        return row[0] if row else None

    def set_language(self, user_id: str, language: str):
        if language not in {"Kazakh", "English", "Russian"}:
            raise ValueError("Unsupported language")
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("INSERT INTO user_preferences (user_id, language) VALUES (?, ?) "
                               "ON CONFLICT(user_id) DO UPDATE SET language = excluded.language",
                               (user_id, language))


def checkpoint_thread_id(user_id: str, thread_id: str) -> str:
    """An arbitrary thread_id never grants access to another user's thread."""
    if not user_id or not thread_id or "::" in user_id or "::" in thread_id:
        raise ValueError("Invalid user_id or thread_id")
    return f"{user_id}::{thread_id}"
