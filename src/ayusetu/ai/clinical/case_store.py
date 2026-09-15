"""
Case persistence store using SQLite.

Stores submitted clinical cases so they survive backend restarts.
Uses Python's built-in sqlite3 — no additional dependencies required.

Schema: submitted_cases table
  case_id        TEXT PRIMARY KEY   (e.g. CASE-ABCD1234)
  session_id     TEXT UNIQUE
  status         TEXT               (SUBMITTED | UNDER_REVIEW | REVIEWED)
  submitted_at   TEXT               (ISO 8601 UTC)
  reviewed_at    TEXT               (nullable)
  reviewed_by    TEXT               (nullable)
  collected_info TEXT               (JSON)
  red_flags      TEXT               (JSON)
  documents      TEXT               (JSON)
  summary        TEXT               (JSON, serialized ClinicalSummary)
  transcript     TEXT               (JSON, dialogue history)
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Database file path: data/cases.db relative to project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # src/ayusetu/ai/clinical → project root
DB_PATH = _PROJECT_ROOT / "data" / "cases.db"


def _init_db(conn: sqlite3.Connection) -> None:
    """Create table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS submitted_cases (
            case_id       TEXT PRIMARY KEY,
            session_id    TEXT UNIQUE NOT NULL,
            status        TEXT NOT NULL DEFAULT 'SUBMITTED',
            submitted_at  TEXT,
            reviewed_at   TEXT,
            reviewed_by   TEXT,
            collected_info TEXT,
            red_flags     TEXT,
            documents     TEXT,
            summary       TEXT,
            transcript    TEXT
        )
        """
    )
    conn.commit()


@contextmanager
def _get_conn():
    """Context manager for a SQLite connection with WAL mode for concurrency."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


# ── Public API ──────────────────────────────────────────────────────────────

def save_case(
    case_id: str,
    session_id: str,
    status: str,
    submitted_at: str,
    collected_info: Dict[str, Any],
    red_flags: List[Any],
    documents: List[Any],
    summary: Optional[Dict[str, Any]],
    transcript: List[Any],
) -> None:
    """Persist a submitted case. Replaces any existing record with the same case_id."""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO submitted_cases
                (case_id, session_id, status, submitted_at,
                 collected_info, red_flags, documents, summary, transcript)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                session_id,
                status,
                submitted_at,
                json.dumps(collected_info, default=str),
                json.dumps(red_flags, default=str),
                json.dumps(documents, default=str),
                json.dumps(summary, default=str) if summary is not None else None,
                json.dumps(transcript, default=str),
            ),
        )
        conn.commit()
    logger.info("Case %s persisted to %s", case_id, DB_PATH)


def update_case_status(
    case_id: str,
    status: str,
    reviewed_at: Optional[str] = None,
    reviewed_by: Optional[str] = None,
    summary: Optional[Dict[str, Any]] = None,
) -> None:
    """Update status (and optionally review metadata + summary) for an existing case."""
    with _get_conn() as conn:
        if summary is not None:
            conn.execute(
                """
                UPDATE submitted_cases
                SET status = ?, reviewed_at = ?, reviewed_by = ?, summary = ?
                WHERE case_id = ?
                """,
                (status, reviewed_at, reviewed_by, json.dumps(summary, default=str), case_id),
            )
        else:
            conn.execute(
                """
                UPDATE submitted_cases
                SET status = ?, reviewed_at = ?, reviewed_by = ?
                WHERE case_id = ?
                """,
                (status, reviewed_at, reviewed_by, case_id),
            )
        conn.commit()
    logger.info("Case %s status updated to %s", case_id, status)


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single case by case_id. Returns None if not found."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM submitted_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def get_case_by_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a case by session_id."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM submitted_cases WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def list_cases(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all cases, optionally filtered by status. Ordered by submitted_at descending."""
    with _get_conn() as conn:
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM submitted_cases WHERE status = ? ORDER BY submitted_at DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM submitted_cases ORDER BY submitted_at DESC"
            ).fetchall()
    return [_row_to_dict(r) for r in rows]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    for key in ("collected_info", "red_flags", "documents", "summary", "transcript"):
        raw = d.get(key)
        if raw:
            try:
                d[key] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[key] = raw
        else:
            d[key] = None
    return d
