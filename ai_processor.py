"""AI processing — instant analysis + daily summary."""

import json
import time
from pathlib import Path

from openai import AsyncOpenAI

from config import load_config
from logger import get_logger

log = get_logger("ai")
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load(name: str) -> str:
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    log.warning("Prompt file not found: %s", name)
    return ""


def _get_client() -> AsyncOpenAI:
    cfg = load_config()
    ai_cfg = cfg["ai"]
    return AsyncOpenAI(base_url=ai_cfg["base_url"], api_key=ai_cfg["api_key"])


def _get_model() -> str:
    return load_config()["ai"]["model"]


async def _call_ai(prompt: str, temperature: float = 0.3, max_tokens: int = 500) -> str:
    client = _get_client()
    model = _get_model()
    t0 = time.time()
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    elapsed = (time.time() - t0) * 1000
    content = (response.choices[0].message.content or "").strip()
    finish = response.choices[0].finish_reason or "unknown"
    log.debug("AI call model=%s prompt_len=%d resp_len=%d time=%dms finish=%s",
              model, len(prompt), len(content), int(elapsed), finish)
    return content


def _parse_json(content: str) -> dict | list:
    cleaned = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Try stripping trailing commas before closing brackets
    import re
    fixed = re.sub(r',\s*([}\]])', r'\1', cleaned)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Try extracting the first JSON object/array with a regex
    m = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Last resort: return empty
    log.error("JSON parse failed for: %s", content[:200])
    return {}


# ---------------------------------------------------------------------------
# 1. Instant processing — extract summary + tags
# ---------------------------------------------------------------------------

async def process_idea_instant(raw_text: str) -> dict:
    template = _load("instant_analysis.txt")
    if not template:
        return {"summary": raw_text[:100], "tags": []}

    # Fetch existing frequent tags for vocabulary guidance
    from db import get_tag_frequencies
    top_tags = get_tag_frequencies(days=90)
    if top_tags:
        vocab = "已有的标签词汇表（请优先使用）：\n" + ", ".join(t["name"] for t in top_tags[:50])
    else:
        vocab = "（暂无已有标签，可自由创建）"

    prompt = template.replace("{vocabulary}", vocab) + "\n" + raw_text

    try:
        content = await _call_ai(prompt, temperature=0.3, max_tokens=500)
        result = _parse_json(content)
        tags = result.get("tags", [])
        summary = result.get("summary", "")
        log.info("AI analysis done | tags=%s | summary=%s",
                 ", ".join(tags) if tags else "(none)",
                 summary[:80] if summary else "(none)")
        return {"summary": summary, "tags": tags}
    except Exception as e:
        log.error("AI analysis failed: %s", e)
        return {"summary": raw_text[:100], "tags": []}


# ---------------------------------------------------------------------------
# 2. Weekly summary — one week into one entry
# ---------------------------------------------------------------------------

async def summarize_weekly_ideas(week_start: str, week_end: str, daily_summaries: list[dict]) -> str:
    """Summarize a week's daily summaries into one paragraph."""
    template = _load("weekly_summary.txt")
    if not template:
        return "；".join(d.get("summary", "") for d in daily_summaries if d.get("summary"))

    items = [f"- {d['date']}: {d.get('summary', '')}" for d in daily_summaries]
    prompt = template + "\n".join(items)

    try:
        content = await _call_ai(prompt, temperature=0.4, max_tokens=400)
        result = _parse_json(content)
        summary = result.get("summary", "")
        log.info("Weekly summary: %s~%s -> %d chars", week_start, week_end, len(summary))
        return summary
    except Exception as e:
        log.error("Weekly summary failed: %s", e)
        return "；".join(d.get("summary", "") for d in daily_summaries if d.get("summary"))


# ---------------------------------------------------------------------------
# 3. Daily summary — one day's ideas into one entry
# ---------------------------------------------------------------------------

async def summarize_daily_ideas(date: str, ideas: list[dict]) -> str:
    template = _load("daily_summary.txt")
    if not template:
        summaries = [i.get("ai_summary", i.get("raw_text", "")[:80]) for i in ideas]
        return "；".join(s for s in summaries if s)

    items = []
    for i, idea in enumerate(ideas, 1):
        text = idea.get("raw_text", "")[:200]
        summary = idea.get("ai_summary", "")
        items.append(f"{i}. {summary}\n   原文：{text}")

    prompt = template + "\n".join(items)

    try:
        content = await _call_ai(prompt, temperature=0.4, max_tokens=400)
        result = _parse_json(content)
        summary = result.get("summary", "")
        log.info("Daily summary for %s: %d ideas -> %d chars", date, len(ideas), len(summary))
        return summary
    except Exception as e:
        log.error("Daily summary failed for %s: %s", date, e)
        return "；".join(i.get("ai_summary", "") for i in ideas if i.get("ai_summary"))
