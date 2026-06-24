"""Settings management routes."""

from fastapi import APIRouter

from config import load_config, save_config
from models import AIConfigUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.put("/ai")
async def update_ai_config(body: AIConfigUpdate):
    config = load_config()
    if body.base_url is not None:
        config["ai"]["base_url"] = body.base_url
    if body.api_key is not None:
        config["ai"]["api_key"] = body.api_key
    if body.model is not None:
        config["ai"]["model"] = body.model
    save_config(config)
    return {"ok": True}
