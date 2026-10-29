# SPDX-License-Identifier: MIT

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_art_assistant.settings import (
    append_request_log,
    load_settings,
    remember_prompt,
    request_log_path,
    save_settings,
    settings_path,
)


class SettingsTests(unittest.TestCase):
    def test_roundtrip_without_api_key(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = folder
            try:
                save_settings(
                    {
                        "model": "gpt-image-2.5-flare",
                        "quality": "low",
                        "base_prompt": "Keep it painterly.",
                        "api_key": "sk-should-never-be-saved",
                    }
                )
                text = settings_path().read_text(encoding="utf-8")
                self.assertNotIn("sk-should-never-be-saved", text)
                self.assertNotIn("api_key", json.loads(text))
                loaded = load_settings()
                self.assertEqual(loaded["quality"], "low")
                self.assertEqual(loaded["base_prompt"], "Keep it painterly.")
                self.assertEqual(loaded["prompt_history"], [])
                self.assertEqual(loaded["generate_warn_after"], 5)
                self.assertEqual(loaded["model"], "gpt-image-2.5-flare")
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous

    def test_sunburst_roundtrips_and_unknown_model_falls_back_to_flare(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = folder
            try:
                save_settings({"model": "gpt-image-2.5-sunburst", "quality": "low"})
                loaded = load_settings()
                self.assertEqual(loaded["model"], "gpt-image-2.5-sunburst")
                save_settings({"model": "gpt-image-not-a-real-model", "quality": "low"})
                loaded = load_settings()
                self.assertEqual(loaded["model"], "gpt-image-2.5-flare")
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous

    def test_prompt_history_roundtrip_and_newest_first(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = folder
            try:
                history = remember_prompt([], "Turn the cloak red")
                history = remember_prompt(history, "Add gold trim")
                history = remember_prompt(history, "Turn the cloak red")
                save_settings({"prompt_history": history, "quality": "low"})
                loaded = load_settings()
                self.assertEqual(
                    loaded["prompt_history"][:2],
                    ["Turn the cloak red", "Add gold trim"],
                )
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous

    def test_request_log_omits_secrets_and_fake_prices(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = folder
            try:
                append_request_log(
                    {
                        "time": "2026-10-28T12:00:00",
                        "document": "card.kra",
                        "quality": "low",
                        "scope": "selection",
                        "outcome": "ok",
                        "api_key": "sk-should-never-be-logged",
                        "cost": "$0.04",
                    }
                )
                text = request_log_path().read_text(encoding="utf-8")
                self.assertNotIn("sk-should-never-be-logged", text)
                self.assertNotIn("api_key", text)
                self.assertNotIn("$0.04", text)
                self.assertNotIn("cost", text)
                row = json.loads(text.strip())
                self.assertEqual(row["document"], "card.kra")
                self.assertEqual(row["scope"], "selection")
                self.assertEqual(row["outcome"], "ok")
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
