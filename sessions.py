"""
SQLite-backed session storage.

DB lives at ~/.local/share/cli-interview-recorder/sessions.db.

A session is a titled conversation with its full history. Messages are appended
as each turn happens (auto-save on every turn) so nothing is lost on crash.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_DIR = Path.home() / ".local" / "share" / "interview-coach"
DB_PATH = DB_DIR / "sessions.db"


def _connect() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            mode         TEXT NOT NULL,
            llm_provider TEXT,
            llm_model    TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role       TEXT NOT NULL,   -- 'user' | 'assistant'
            speaker    TEXT,            -- 'you' | 'interviewer' | 'unknown' | NULL for assistant
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """
    )
    return conn


def create_session(title: str, mode: str,
                   llm_provider: str = "", llm_model: str = "") -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (title, mode, llm_provider, llm_model, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, mode, llm_provider, llm_model, now, now),
        )
        return cur.lastrowid


def rename_session(session_id: int, new_title: str):
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (new_title, datetime.utcnow().isoformat(timespec="seconds"), session_id),
        )


def delete_session(session_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def append_message(session_id: int, role: str, content: str, speaker: Optional[str] = None):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, speaker, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, role, speaker, content, now),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )


def list_sessions(limit: int = 20) -> list[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT s.id, s.title, s.mode, s.llm_provider, s.llm_model, "
            "       s.created_at, s.updated_at, "
            "       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS turns "
            "FROM sessions s ORDER BY s.updated_at DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()


def load_messages(session_id: int) -> list[dict]:
    """Return messages in the {role, content} shape LLMs expect."""
    with _connect() as conn:
        cur = conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]


def get_session(session_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return cur.fetchone()
