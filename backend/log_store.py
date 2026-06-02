"""SQLite-backed metadata log storage."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path("backend/data/ingest_logs.db")


def _now() -> str:
    """Return UTC timestamp; args: none; returns: str."""
    return datetime.now(timezone.utc).isoformat()


def _conn() -> sqlite3.Connection:
    """Open sqlite connection; args: none; returns: sqlite3.Connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_log_store() -> None:
    """Create sqlite log tables; args: none; returns: None."""
    con: sqlite3.Connection = _conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            run_id TEXT,
            level TEXT NOT NULL,
            event TEXT NOT NULL,
            duration_ms REAL,
            metadata_json TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            run_id TEXT,
            step TEXT NOT NULL,
            model TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            finish_reason TEXT,
            latency_ms REAL,
            retries INTEGER,
            error TEXT
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_llm_usage_run_id ON llm_usage(run_id)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage(created_at)"
    )
    con.commit()
    con.close()


def write_event(
    level: str,
    event: str,
    run_id: str = "",
    duration_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist event row; args: level (str), event (str), run_id (str), duration_ms (float | None), metadata (dict[str, Any] | None); returns: None."""
    con: sqlite3.Connection = _conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        "INSERT INTO events (created_at, run_id, level, event, duration_ms, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
        (
            _now(),
            run_id or None,
            level,
            event,
            duration_ms,
            json.dumps(metadata or {}, default=str),
        ),
    )
    con.commit()
    con.close()


def write_llm_usage(
    step: str,
    model: str,
    run_id: str = "",
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    finish_reason: str | None = None,
    latency_ms: float | None = None,
    retries: int = 0,
    error: str = "",
) -> None:
    """Persist llm usage row; args: step (str), model (str), run_id (str), prompt_tokens (int | None), completion_tokens (int | None), total_tokens (int | None), finish_reason (str | None), latency_ms (float | None), retries (int), error (str); returns: None."""
    con: sqlite3.Connection = _conn()
    cur: sqlite3.Cursor = con.cursor()
    cur.execute(
        """
        INSERT INTO llm_usage (
            created_at, run_id, step, model, prompt_tokens, completion_tokens,
            total_tokens, finish_reason, latency_ms, retries, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _now(),
            run_id or None,
            step,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            finish_reason,
            latency_ms,
            retries,
            error or None,
        ),
    )
    con.commit()
    con.close()
