"""Pydantic models."""

from typing import Optional

from pydantic import BaseModel, Field


class IdeaCreate(BaseModel):
    raw_text: str = Field(..., min_length=1)


class IdeaResponse(BaseModel):
    id: str
    raw_text: str
    ai_summary: Optional[str] = None
    ai_tags: Optional[str] = None
    status: str
    linked_ids: Optional[str] = None
    created_at: str
    updated_at: str


class IdeaListResponse(BaseModel):
    ideas: list[IdeaResponse]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total_ideas: int
    recent_week_count: int


class AIConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


