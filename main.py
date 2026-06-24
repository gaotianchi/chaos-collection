"""Chaos Collection — main entry point."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import load_config
from db import backup_database, get_homepage_data, get_weekly_data, init_db
from logger import get_logger
from routes import ideas, process, settings_routes

log = get_logger("main")


async def catch_up_ideas():
    """Retry AI processing for ideas that need it (retry_count < 3, no tags)."""
    from ai_processor import process_idea_instant
    from db import get_connection, update_idea
    import json, asyncio as _asyncio

    conn = get_connection()
    unprocessed = conn.execute(
        "SELECT id, raw_text, retry_count FROM idea_pool "
        "WHERE ai_tags = '[]' AND (ai_summary = '' OR ai_summary IS NULL) AND retry_count < 3"
    ).fetchall()
    conn.close()

    if unprocessed:
        log.info("Catching up %d unprocessed ideas...", len(unprocessed))
        for idea_id, raw_text, retries in unprocessed:
            success = False
            for attempt in range(retries + 1, 4):
                try:
                    result = await process_idea_instant(raw_text)
                    tags = result.get("tags", [])
                    summary = result.get("summary", "")
                    if tags or summary:
                        update_idea(idea_id, ai_summary=summary,
                                    ai_tags=json.dumps(tags, ensure_ascii=False),
                                    retry_count=attempt)
                        log.info("  Idea %s caught up on attempt %d", idea_id, attempt)
                        success = True
                        break
                except Exception as e:
                    log.error("  Idea %s attempt %d failed: %s", idea_id, attempt, e)
                await _asyncio.sleep(2)
            if not success:
                update_idea(idea_id, retry_count=3)


async def catch_up_summaries():
    """Generate any missing daily/weekly summaries on startup."""
    from ai_processor import summarize_daily_ideas, summarize_weekly_ideas
    from db import (
        get_connection, get_ideas_for_date, get_ideas_for_week,
        upsert_daily_summary, upsert_weekly_summary,
    )
    import sqlite3

    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()

    # Find missing daily summaries (past days with ideas but no summary)
    missing_days = conn.execute(
        """SELECT DISTINCT date(created_at) as d FROM idea_pool
           WHERE date(created_at) < ?
           AND date(created_at) NOT IN (SELECT date FROM daily_summaries)
           ORDER BY d""",
        (today,),
    ).fetchall()

    if missing_days:
        log.info("Catching up %d missing daily summaries...", len(missing_days))
        for (date,) in missing_days:
            ideas = get_ideas_for_date(date)
            if ideas:
                try:
                    summary = await summarize_daily_ideas(date, ideas)
                    if summary:
                        upsert_daily_summary(date, summary, len(ideas))
                except Exception as e:
                    log.error("Catch-up daily %s failed: %s", date, e)

    # Find missing weekly summaries (complete past weeks with ideas but no summary)
    missing_weeks = conn.execute(
        """SELECT DISTINCT
             date(created_at, 'weekday 0', '-6 days') as mon,
             date(created_at, 'weekday 0') as sun
           FROM idea_pool
           WHERE date(created_at) < ?
           AND date(created_at, 'weekday 0') < ?
           AND date(created_at, 'weekday 0', '-6 days') NOT IN
               (SELECT week_start FROM weekly_summaries)
           ORDER BY mon""",
        (today, today),
    ).fetchall()

    if missing_weeks:
        log.info("Catching up %d missing weekly summaries...", len(missing_weeks))
        for mon, sun in missing_weeks:
            ideas = get_ideas_for_week(mon, sun)
            if ideas:
                try:
                    dailies = conn.execute(
                        "SELECT * FROM daily_summaries WHERE date >= ? AND date <= ? ORDER BY date",
                        (mon, sun),
                    ).fetchall()
                    summary = await summarize_weekly_ideas(mon, sun, [dict(d) for d in dailies])
                    if summary:
                        upsert_weekly_summary(mon, sun, summary, len(ideas))
                except Exception as e:
                    log.error("Catch-up weekly %s failed: %s", mon, e)

    conn.close()
    log.info("Catch-up complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=== Chaos Collection starting ===")
    init_db()
    cfg = load_config()
    log.info("DB initialized | AI: %s (model=%s)", cfg["ai"]["base_url"], cfg["ai"]["model"])
    async def periodic_backup():
        while True:
            await asyncio.sleep(1800)  # every 30 minutes
            try:
                backup_database()
            except Exception as e:
                log.error("Periodic backup failed: %s", e)

    asyncio.create_task(catch_up_ideas())
    asyncio.create_task(catch_up_summaries())
    backup_database()
    backup_task = asyncio.create_task(periodic_backup())
    yield
    backup_task.cancel()
    backup_database()
    log.info("=== Chaos Collection shutting down ===")


app = FastAPI(title="混沌集", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(ideas.router)
app.include_router(process.router)
app.include_router(settings_routes.router)


@app.get("/api/daily")
async def api_daily(days: int = 7):
    return get_homepage_data(days)


@app.get("/api/weekly")
async def api_weekly(days: int = 90):
    return get_weekly_data(days)


@app.get("/")
async def page_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/archive")
async def page_archive(request: Request):
    return templates.TemplateResponse("archive.html", {"request": request})


@app.get("/settings")
async def page_settings(request: Request):
    config = load_config()
    return templates.TemplateResponse("settings.html", {"request": request, "config": config})


if __name__ == "__main__":
    import uvicorn
    log.info("Starting uvicorn on http://127.0.0.1:8000")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
