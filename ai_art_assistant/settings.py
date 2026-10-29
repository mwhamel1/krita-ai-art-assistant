# SPDX-License-Identifier: MIT

"""Non-secret plugin settings. API keys must never go in this file."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .prompts import DEFAULT_BASE_PROMPT

ALLOWED_MODELS = ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst")
ALLOWED_QUALITIES = ("low", "medium", "high")
DEFAULT_MODEL = "gpt-image-2.5-flare"
MODEL_CHOICES = (
    ("gpt-image-2.5-flare", "flare (faster)"),
    ("gpt-image-2.5-sunburst", "sunburst (more precise)"),
)
DEFAULT_QUALITY = "medium"
DEFAULT_GENERATE_WARN_AFTER = 5
PROMPT_HISTORY_LIMIT = 8


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
        "prompt_history": [],
        "generate_warn_after": DEFAULT_GENERATE_WARN_AFTER,
    }


def remember_prompt(history, instruction: str, limit: int = PROMPT_HISTORY_LIMIT) -> list:
    text = (instruction or "").strip()
    items = [str(item).strip() for item in (history or []) if str(item).strip()]
    if not text:
        return items[:limit]
    if text in items:
        items.remove(text)
    items.insert(0, text)
    return items[:limit]


def request_log_path() -> Path:
    return settings_directory() / "request_log.jsonl"


def append_request_log(entry: dict) -> None:
    clean = {
        "time": str(entry.get("time") or ""),
        "document": str(entry.get("document") or ""),
        "quality": str(entry.get("quality") or ""),
        "scope": str(entry.get("scope") or ""),
        "outcome": str(entry.get("outcome") or ""),
    }
    path = request_log_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(clean, ensure_ascii=False) + "\n")


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
    history = raw.get("prompt_history") or []
    if isinstance(history, list):
        data["prompt_history"] = remember_prompt(history, "")
    try:
        warn_after = int(raw.get("generate_warn_after", DEFAULT_GENERATE_WARN_AFTER))
    except (TypeError, ValueError):
        warn_after = DEFAULT_GENERATE_WARN_AFTER
    data["generate_warn_after"] = max(1, min(100, warn_after))
    return data


def save_settings(data: dict) -> None:
    clean = default_settings()
    model = data.get("model", DEFAULT_MODEL)
    quality = data.get("quality", DEFAULT_QUALITY)
    clean["model"] = model if model in ALLOWED_MODELS else DEFAULT_MODEL
    clean["quality"] = quality if quality in ALLOWED_QUALITIES else DEFAULT_QUALITY
    clean["base_prompt"] = str(data.get("base_prompt") or DEFAULT_BASE_PROMPT)
    clean["prompt_history"] = remember_prompt(data.get("prompt_history") or [], "")
    try:
        warn_after = int(data.get("generate_warn_after", DEFAULT_GENERATE_WARN_AFTER))
    except (TypeError, ValueError):
        warn_after = DEFAULT_GENERATE_WARN_AFTER
    clean["generate_warn_after"] = max(1, min(100, warn_after))
    path = settings_path()
    path.write_text(json.dumps(clean, indent=2) + "\n", encoding="utf-8")
