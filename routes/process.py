"""Processing routes — daily summary + stats."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from ai_processor import summarize_daily_ideas, summarize_weekly_ideas
from db import (
    backup_database, get_ideas_for_date, get_ideas_for_week,
    get_stats, get_tag_frequencies, upsert_daily_summary, upsert_weekly_summary,
)
from models import StatsResponse

router = APIRouter(prefix="/api", tags=["processing"])


@router.post("/backup")
async def trigger_backup():
    path = backup_database()
    return {"ok": True, "path": path}


@router.get("/tags")
async def tag_frequencies(days: int = 7):
    return get_tag_frequencies(days)


@router.get("/stats", response_model=StatsResponse)
async def stats_endpoint():
    return StatsResponse(**get_stats())


@router.post("/process/weekly-summary")
async def trigger_weekly_summary(date: str | None = None):
    """Generate weekly summary. Accepts any date in the target week (Mon-Sun). Defaults to yesterday."""
    from datetime import datetime, timedelta
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Calculate Monday and Sunday for the given date
    d = datetime.strptime(date, "%Y-%m-%d")
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    week_start = monday.strftime("%Y-%m-%d")
    week_end = sunday.strftime("%Y-%m-%d")

    ideas = get_ideas_for_week(week_start, week_end)
    if not ideas:
        return {"ok": True, "message": "该周没有想法", "week_start": week_start, "week_end": week_end}

    import sqlite3
    conn = sqlite3.connect("data/ideas.db")
    conn.row_factory = sqlite3.Row
    dailies = conn.execute(
        "SELECT * FROM daily_summaries WHERE date >= ? AND date <= ? ORDER BY date",
        (week_start, week_end),
    ).fetchall()
    conn.close()

    summary = await summarize_weekly_ideas(
        week_start, week_end, [dict(d) for d in dailies]
    )
    if summary:
        upsert_weekly_summary(week_start, week_end, summary, len(ideas))

    return {"ok": True, "week_start": week_start, "week_end": week_end, "idea_count": len(ideas), "summary": summary}


@router.post("/process/daily-summary")
async def trigger_daily_summary(date: str | None = None):
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    ideas = get_ideas_for_date(date)
    if not ideas:
        return {"ok": True, "message": f"{date}: 没有想法", "date": date}

    summary = await summarize_daily_ideas(date, ideas)
    if summary:
        upsert_daily_summary(date, summary, len(ideas))

    return {"ok": True, "date": date, "idea_count": len(ideas), "summary": summary}
