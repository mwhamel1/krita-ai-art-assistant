# SPDX-License-Identifier: MIT

"""Non-secret plugin settings. API keys must never go in this file."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .prompts import DEFAULT_BASE_PROMPT

ALLOWED_MODELS = ("gpt-image-2.5-flare",)
ALLOWED_QUALITIES = ("low", "medium", "high")
DEFAULT_MODEL = "gpt-image-2.5-flare"
DEFAULT_QUALITY = "medium"


def settings_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    path = Path(base) / "krita-ai-art-assistant"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return settings_directory() / "settings.json"


def default_settings() -> dict:
    return {
        "model": DEFAULT_MODEL,
        "quality": DEFAULT_QUALITY,
        "base_prompt": DEFAULT_BASE_PROMPT,
    }


def load_settings() -> dict:
    data = default_settings()
    path = settings_path()
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    if "api_key" in raw or "openai_api_key" in raw:
        raw.pop("api_key", None)
        raw.pop("openai_api_key", None)
    model = raw.get("model", DEFAULT_MODEL)
    quality = raw.get("quality", DEFAULT_QUALITY)
    base_prompt = raw.get("base_prompt", DEFAULT_BASE_PROMPT)
    data["model"] = model if model in ALLOWED_MODELS else DEFAULT_MODEL
    data["quality"] = quality if quality in ALLOWED_QUALITIES else DEFAULT_QUALITY
    data["base_prompt"] = str(base_prompt) if base_prompt is not None else DEFAULT_BASE_PROMPT
    return data


def save_settings(data: dict) -> None:
    clean = default_settings()
    model = data.get("model", DEFAULT_MODEL)
    quality = data.get("quality", DEFAULT_QUALITY)
    clean["model"] = model if model in ALLOWED_MODELS else DEFAULT_MODEL
    clean["quality"] = quality if quality in ALLOWED_QUALITIES else DEFAULT_QUALITY
    clean["base_prompt"] = str(data.get("base_prompt") or DEFAULT_BASE_PROMPT)
    path = settings_path()
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
