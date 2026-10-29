# SPDX-License-Identifier: MIT

import base64
import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_art_assistant.image_pipeline import write_png_rgba
from ai_art_assistant.openai_provider import (
    OpenAIRequestError,
    decode_result_png,
    edit_image,
    map_http_error,
)


class MapHttpErrorTests(unittest.TestCase):
    def test_401_mentions_api_key(self):
        error = map_http_error(401, "{}")
        self.assertIn("API key", str(error))
        self.assertEqual(error.status_code, 401)

    def test_429_quota(self):
        error = map_http_error(429, '{"error":{"message":"insufficient_quota"}}')
        self.assertIn("credits", str(error).lower())

    def test_429_rate_limit(self):
        error = map_http_error(429, "{}")
        self.assertIn("rate limit", str(error).lower())


class EditImageTests(unittest.TestCase):
    def test_successful_fake_response(self):
        rgba = bytes([0, 0, 0, 255] * 4)
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.png"
            write_png_rgba(path, rgba, 2, 2)
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")

        def poster(url, body, headers, timeout):
            self.assertIn("Authorization", headers)
            self.assertTrue(headers["Authorization"].startswith("Bearer "))
            self.assertNotIn(b"sk-test", body)
            payload = {"data": [{"b64_json": encoded}]}
            return 200, json.dumps(payload).encode("utf-8")

        result = edit_image(
            api_key="sk-test",
            image_png=b"fake-png",
            prompt="test",
            model="gpt-image-2.5-flare",
            quality="medium",
            size="1024x1536",
            poster=poster,
        )
        self.assertTrue(result.startswith(b"\x89PNG"))

    def test_401_does_not_raise_raw_http(self):
        def poster(url, body, headers, timeout):
            return 401, b'{"error":{"message":"Incorrect API key"}}'

        with self.assertRaises(OpenAIRequestError) as caught:
            edit_image(
                api_key="sk-bad",
                image_png=b"fake-png",
                prompt="test",
                model="gpt-image-2.5-flare",
                quality="medium",
                size="1024x1536",
                poster=poster,
            )
        self.assertIn("API key", str(caught.exception))

    def test_missing_image_payload(self):
        with self.assertRaises(OpenAIRequestError):
            decode_result_png({"data": [{}]})


if __name__ == "__main__":
    unittest.main()
