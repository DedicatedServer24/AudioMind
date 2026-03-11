"""SQLite-Datenbank für Job-Verwaltung."""

import sqlite3
import uuid
from datetime import datetime, timezone

from config import DB_PATH

_connection: sqlite3.Connection | None = None


def _get_connection() -> sqlite3.Connection:
    """Gibt eine thread-safe SQLite-Verbindung zurück (Singleton)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
    return _connection


def init_db() -> None:
    """Erstellt die jobs-Tabelle falls nicht vorhanden."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            filename TEXT NOT NULL,
            diarize INTEGER NOT NULL DEFAULT 0,
            timestamps INTEGER NOT NULL DEFAULT 0,
            language TEXT,
            template_name TEXT,
            custom_prompt TEXT,
            upload_path TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            progress TEXT,
            progress_percent REAL DEFAULT 0.0,
            transcript TEXT,
            summary TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    conn.commit()


def create_job(
    username: str,
    filename: str,
    diarize: bool,
    timestamps: bool,
    language: str | None,
    template_name: str | None,
    custom_prompt: str | None,
    upload_path: str,
) -> str:
    """Erstellt einen neuen Job mit Status 'queued'. Gibt die job_id zurück."""
    conn = _get_connection()
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO jobs (id, username, filename, diarize, timestamps, language,
           template_name, custom_prompt, upload_path, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)""",
        (job_id, username, filename, int(diarize), int(timestamps),
         language, template_name, custom_prompt, upload_path, now),
    )
    conn.commit()
    return job_id


def get_job(job_id: str) -> dict | None:
    """Gibt einen Job als Dict zurück oder None."""
    conn = _get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs_by_user(username: str) -> list[dict]:
    """Gibt alle Jobs eines Users zurück, neueste zuerst."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE username = ? ORDER BY created_at DESC",
        (username,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_job_status(job_id: str, status: str, progress: str | None = None) -> None:
    """Aktualisiert Status und optionalen Fortschritts-Text."""
    conn = _get_connection()
    conn.execute(
        "UPDATE jobs SET status = ?, progress = ? WHERE id = ?",
        (status, progress, job_id),
    )
    conn.commit()


def update_job_progress_percent(job_id: str, percent: float) -> None:
    """Aktualisiert den numerischen Fortschritt (0.0-1.0)."""
    conn = _get_connection()
    conn.execute(
        "UPDATE jobs SET progress_percent = ? WHERE id = ?",
        (percent, job_id),
    )
    conn.commit()


def complete_job(job_id: str, transcript: str, summary: str) -> None:
    """Markiert einen Job als abgeschlossen mit Ergebnissen."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE jobs SET status = 'completed', transcript = ?, summary = ?,
           progress_percent = 1.0, completed_at = ? WHERE id = ?""",
        (transcript, summary, now, job_id),
    )
    conn.commit()


def fail_job(job_id: str, error_message: str) -> None:
    """Markiert einen Job als fehlgeschlagen."""
    conn = _get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE jobs SET status = 'failed', error_message = ?,
           completed_at = ? WHERE id = ?""",
        (error_message, now, job_id),
    )
    conn.commit()


def delete_job(job_id: str, username: str) -> bool:
    """Löscht einen Job (nur wenn er dem User gehört und nicht in Bearbeitung ist)."""
    conn = _get_connection()
    result = conn.execute(
        """DELETE FROM jobs WHERE id = ? AND username = ?
           AND status NOT IN ('compressing', 'transcribing', 'summarizing')""",
        (job_id, username),
    )
    conn.commit()
    return result.rowcount > 0


def delete_all_jobs(username: str) -> int:
    """Löscht alle abgeschlossenen/fehlgeschlagenen Jobs eines Users."""
    conn = _get_connection()
    result = conn.execute(
        """DELETE FROM jobs WHERE username = ?
           AND status IN ('completed', 'failed')""",
        (username,),
    )
    conn.commit()
    return result.rowcount


def get_next_queued_job() -> dict | None:
    """Gibt den ältesten Job mit Status 'queued' zurück."""
    conn = _get_connection()
    row = conn.execute(
        "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1",
    ).fetchone()
    return dict(row) if row else None
