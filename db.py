"""Database layer — idea_pool + daily_summaries."""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger("db")
DB_PATH = Path(__file__).parent / "data" / "ideas.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS idea_pool (
                id          TEXT PRIMARY KEY,
                raw_text    TEXT NOT NULL,
                ai_summary  TEXT DEFAULT '',
                ai_tags     TEXT DEFAULT '[]',
                status      TEXT DEFAULT 'pool',
                linked_ids  TEXT DEFAULT '[]',
                retry_count INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weekly_summaries (
                week_start  TEXT PRIMARY KEY,
                week_end    TEXT NOT NULL,
                summary     TEXT NOT NULL,
                idea_count  INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_summaries (
                date        TEXT PRIMARY KEY,
                summary     TEXT NOT NULL,
                idea_count  INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );
        """)
        conn.commit()
        log.info("Database initialized: %s", DB_PATH)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Idea CRUD
# ---------------------------------------------------------------------------

def create_idea(raw_text: str) -> dict:
    conn = get_connection()
    try:
        now = _now()
        idea_id = _uid()
        conn.execute(
            "INSERT INTO idea_pool (id, raw_text, status, created_at, updated_at) "
            "VALUES (?, ?, 'pool', ?, ?)",
            (idea_id, raw_text, now, now),
        )
        conn.commit()
        log.debug("Idea %s saved", idea_id)
        return _row_to_dict(
            conn.execute("SELECT * FROM idea_pool WHERE id=?", (idea_id,)).fetchone()
        )
    finally:
        conn.close()


def update_idea(idea_id: str, **fields) -> Optional[dict]:
    allowed = {"raw_text", "ai_summary", "ai_tags", "status", "linked_ids", "retry_count"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_idea(idea_id)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [idea_id]
    conn = get_connection()
    try:
        conn.execute(f"UPDATE idea_pool SET {set_clause} WHERE id=?", values)
        conn.commit()
        return _row_to_dict(
            conn.execute("SELECT * FROM idea_pool WHERE id=?", (idea_id,)).fetchone()
        )
    except Exception as e:
        log.error("Failed to update idea %s: %s", idea_id, e)
        conn.rollback()
        return None
    finally:
        conn.close()


def delete_idea(idea_id: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM idea_pool WHERE id=?", (idea_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_idea(idea_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM idea_pool WHERE id=?", (idea_id,)).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_ideas(
    status: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    conn = get_connection()
    try:
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if tag:
            conditions.append("ai_tags LIKE ?")
            params.append(f"%{tag}%")
        if search:
            conditions.append("(raw_text LIKE ? OR ai_summary LIKE ? OR ai_tags LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        total = conn.execute(f"SELECT COUNT(*) FROM idea_pool {where}", params).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM idea_pool {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Weekly summaries
# ---------------------------------------------------------------------------

def upsert_weekly_summary(week_start: str, week_end: str, summary: str, idea_count: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO weekly_summaries (week_start, week_end, summary, idea_count, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(week_start) DO UPDATE SET summary=?, idea_count=?, week_end=?""",
            (week_start, week_end, summary, idea_count, _now(), summary, idea_count, week_end),
        )
        conn.commit()
        log.info("Weekly summary saved: %s~%s (%d ideas)", week_start, week_end, idea_count)
    finally:
        conn.close()


def get_weekly_data(days: int = 90) -> list[dict]:
    """Return complete past weeks with summaries for the archive page. Excludes current week."""
    conn = get_connection()
    try:
        today = _now()[:10]

        # Only complete weeks: week_end (Sunday) < today
        weeks = conn.execute(
            """SELECT * FROM weekly_summaries
               WHERE week_end < ? AND week_end >= date(?, ? || ' days')
               ORDER BY week_start DESC""",
            (today, today, f"-{days}"),
        ).fetchall()

        result = []
        for w in weeks:
            wd = _row_to_dict(w)
            dailies = conn.execute(
                """SELECT * FROM daily_summaries
                   WHERE date >= ? AND date <= ?
                   ORDER BY date DESC""",
                (wd["week_start"], wd["week_end"]),
            ).fetchall()
            wd["dailies"] = [_row_to_dict(d) for d in dailies]
            result.append(wd)

        return result
    finally:
        conn.close()


def get_ideas_for_week(week_start: str, week_end: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM idea_pool
               WHERE created_at >= ? AND created_at <= ?
               ORDER BY created_at ASC""",
            (week_start, week_end + "T23:59:59"),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Daily summaries
# ---------------------------------------------------------------------------

def upsert_daily_summary(date: str, summary: str, idea_count: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO daily_summaries (date, summary, idea_count, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET summary=?, idea_count=?""",
            (date, summary, idea_count, _now(), summary, idea_count),
        )
        conn.commit()
        log.info("Daily summary saved: %s (%d ideas)", date, idea_count)
    finally:
        conn.close()


def get_homepage_data(days: int = 7) -> dict:
    conn = get_connection()
    try:
        today = _now()[:10]

        # Today's ideas
        today_ideas = conn.execute(
            """SELECT id, raw_text, ai_summary, ai_tags, status, created_at
               FROM idea_pool WHERE date(created_at) = ?
               ORDER BY created_at DESC""",
            (today,),
        ).fetchall()

        # This week's past daily summaries (since Monday, excluding today)
        from datetime import datetime, timedelta
        d = datetime.strptime(today, "%Y-%m-%d")
        monday = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        week_dailies = []
        if monday < today:
            week_dailies = conn.execute(
                """SELECT * FROM daily_summaries
                   WHERE date >= ? AND date < ?
                   ORDER BY date DESC""",
                (monday, today),
            ).fetchall()

        return {
            "today": [_row_to_dict(i) for i in today_ideas],
            "week_dailies": [_row_to_dict(s) for s in week_dailies],
        }
    finally:
        conn.close()


def get_ideas_for_date(date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM idea_pool WHERE date(created_at) = ? ORDER BY created_at ASC",
            (date,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tag stats
# ---------------------------------------------------------------------------

def get_tag_frequencies(days: int = 7) -> list[dict]:
    """Return tag frequency for the past N days, sorted by count desc."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT ai_tags FROM idea_pool "
            "WHERE created_at >= datetime('now', ? || ' days')",
            (f"-{days}",),
        ).fetchall()

        counts: dict[str, int] = {}
        for (tags_str,) in rows:
            try:
                tags = json.loads(tags_str)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(tags, list):
                for t in tags:
                    counts[t] = counts.get(t, 0) + 1

        sorted_tags = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"name": t, "count": c} for t, c in sorted_tags]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM idea_pool").fetchone()[0]
        recent = conn.execute(
            "SELECT COUNT(*) FROM idea_pool WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        return {"total_ideas": total, "recent_week_count": recent}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

BACKUP_DIR = DB_PATH.parent / "backups"


def backup_database() -> str:
    """Create a timestamped backup using SQLite's safe backup API. Returns the backup path."""
    import shutil
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    name = f"ideas_{now.strftime('%Y%m%d_%H%M%S')}.db"
    dst = BACKUP_DIR / name

    src_conn = get_connection()
    try:
        dst_conn = sqlite3.connect(str(dst))
        src_conn.backup(dst_conn)
        dst_conn.close()
    finally:
        src_conn.close()

    # Keep only last 30 backups
    files = sorted(BACKUP_DIR.glob("ideas_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[30:]:
        old.unlink()

    log.info("Backup created: %s (%d bytes)", name, dst.stat().st_size)
    return str(dst)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)
