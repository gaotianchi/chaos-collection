"""Configuration management for Chaos Collection."""

import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "data" / "config.json"

DEFAULT_CONFIG = {
    "ai": {
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
    },
    "processing": {
        "frequency": "manual",  # "daily" | "weekly" | "manual"
        "threshold": 15,        # min ideas before suggesting a new category
    },
}


def load_config() -> dict:
    """Load config from JSON file, creating with defaults if missing."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        # Merge with defaults to fill any missing keys
        merged = DEFAULT_CONFIG.copy()
        _deep_merge(merged, config)
        return merged
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save config to JSON file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
