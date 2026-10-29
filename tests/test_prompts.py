# SPDX-License-Identifier: MIT

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_art_assistant.prompts import (
    EmptyInstructionError,
    compose_edit_prompt,
)


class ComposeEditPromptTests(unittest.TestCase):
    def test_requires_instruction(self):
        with self.assertRaises(EmptyInstructionError):
            compose_edit_prompt("base", "   ", False)

    def test_includes_instruction_and_whole_canvas_scope(self):
        text = compose_edit_prompt(
            "Painterly fantasy.",
            "Turn the armor into leather.",
            False,
        )
        self.assertIn("Painterly fantasy.", text)
        self.assertIn("Artist instruction: Turn the armor into leather.", text)
        self.assertIn("entire image", text)

    def test_selection_mentions_mask(self):
        text = compose_edit_prompt("base", "fix the sword", True)
        self.assertIn("mask", text.lower())
        self.assertIn("Artist instruction: fix the sword", text)


if __name__ == "__main__":
    unittest.main()
