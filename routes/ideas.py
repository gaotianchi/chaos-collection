"""Idea routes."""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ai_processor import process_idea_instant
from db import create_idea, delete_idea, get_idea, list_ideas, update_idea
from logger import get_logger
from models import IdeaCreate, IdeaListResponse, IdeaResponse

log = get_logger("api.ideas")
router = APIRouter(prefix="/api/ideas", tags=["ideas"])


@router.post("", response_model=IdeaResponse)
async def submit_idea(body: IdeaCreate):
    idea = create_idea(body.raw_text)
    log.info("Idea created: id=%s text_len=%d", idea["id"], len(body.raw_text))
    asyncio.create_task(_process_async(idea["id"], body.raw_text))
    return IdeaResponse(**idea)


async def _process_async(idea_id: str, raw_text: str):
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            result = await process_idea_instant(raw_text)
            tags = result.get("tags", [])
            summary = result.get("summary", "")
            if tags or summary:
                update_idea(
                    idea_id,
                    ai_summary=summary,
                    ai_tags=json.dumps(tags, ensure_ascii=False),
                    retry_count=attempt,
                )
                log.info("Idea %s processed on attempt %d", idea_id, attempt)
                return
        except Exception as e:
            log.error("Idea %s attempt %d failed: %s", idea_id, attempt, e)
        await asyncio.sleep(2)

    update_idea(idea_id, retry_count=max_retries)
    log.error("Idea %s failed after %d attempts", idea_id, max_retries)


@router.get("", response_model=IdeaListResponse)
async def list_ideas_endpoint(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    ideas, total = list_ideas(status=status, search=search, tag=tag, page=page, page_size=page_size)
    return IdeaListResponse(
        ideas=[IdeaResponse(**i) for i in ideas],
        total=total, page=page, page_size=page_size,
    )


@router.get("/{idea_id}", response_model=IdeaResponse)
async def get_idea_endpoint(idea_id: str):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="想法不存在")
    return IdeaResponse(**idea)


@router.delete("/{idea_id}")
async def delete_idea_endpoint(idea_id: str):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="想法不存在")
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    if not idea["created_at"].startswith(today):
        raise HTTPException(status_code=403, detail="已归档的想法不可删除")
    delete_idea(idea_id)
    return {"ok": True}


@router.get("/{idea_id}/related")
async def related_ideas(idea_id: str):
    idea = get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="想法不存在")
    related = find_related_ideas(idea_id)
    return [IdeaResponse(**r) for r in related]
