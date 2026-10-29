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

from ai_art_assistant.settings import load_settings, save_settings, settings_path


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
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
