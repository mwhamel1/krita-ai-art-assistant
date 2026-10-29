# SPDX-License-Identifier: MIT

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ai_art_assistant.image_pipeline import (
    CoverageError,
    DimensionError,
    api_size_string,
    export_directory,
    openai_mask_rgba_from_coverage,
    png_dimensions,
    require_coverage_size,
    require_same_size,
    stencil_rgba_from_coverage,
    write_png_gray,
    write_png_rgba,
)


class RequireSameSizeTests(unittest.TestCase):
    def test_matching_sizes_pass(self):
        require_same_size(1024, 1536, 1024, 1536)

    def test_mismatch_raises_and_does_not_invent_a_resize(self):
        with self.assertRaises(DimensionError) as caught:
            require_same_size(512, 512, 1024, 1536)
        message = str(caught.exception)
        self.assertIn("512×512", message)
        self.assertIn("1024×1536", message)
        self.assertIn("will not stretch", message)


class CoverageTests(unittest.TestCase):
    def test_full_selection_is_opaque_white(self):
        width, height = 2, 2
        coverage = bytes([255, 255, 255, 255])
        rgba = stencil_rgba_from_coverage(coverage, width, height)
        self.assertEqual(len(rgba), 16)
        self.assertEqual(rgba[0:4], b"\xff\xff\xff\xff")

    def test_empty_selection_is_transparent_white(self):
        coverage = bytes([0, 0, 0, 0])
        rgba = stencil_rgba_from_coverage(coverage, 2, 2)
        self.assertEqual(rgba[3], 0)
        self.assertEqual(rgba[0:3], b"\xff\xff\xff")

    def test_feathered_edge_keeps_partial_alpha(self):
        coverage = bytes([0, 64, 128, 255])
        rgba = stencil_rgba_from_coverage(coverage, 2, 2)
        alphas = rgba[3::4]
        self.assertEqual(list(alphas), [0, 64, 128, 255])

    def test_wrong_length_is_an_error(self):
        with self.assertRaises(CoverageError):
            require_coverage_size(b"\x00\x01", 2, 2)

    def test_openai_mask_inverts_coverage_to_alpha(self):
        coverage = bytes([0, 64, 128, 255])
        rgba = openai_mask_rgba_from_coverage(coverage, 2, 2)
        alphas = list(rgba[3::4])
        self.assertEqual(alphas, [255, 191, 127, 0])
        self.assertEqual(rgba[0:3], b"\x00\x00\x00")

    def test_full_selection_is_fully_transparent_for_openai(self):
        rgba = openai_mask_rgba_from_coverage(bytes([255, 255, 255, 255]), 2, 2)
        self.assertEqual(list(rgba[3::4]), [0, 0, 0, 0])


class PngTests(unittest.TestCase):
    def test_rgba_roundtrip_dimensions(self):
        rgba = stencil_rgba_from_coverage(bytes([255, 0, 128, 64]), 2, 2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stencil.png"
            write_png_rgba(path, rgba, 2, 2)
            self.assertEqual(png_dimensions(path), (2, 2))

    def test_gray_roundtrip_dimensions(self):
        gray = bytes([0, 128, 255, 40])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gray.png"
            write_png_gray(path, gray, 2, 2)
            self.assertEqual(png_dimensions(path), (2, 2))


class ApiSizeTests(unittest.TestCase):
    def test_card_size_is_allowed(self):
        self.assertEqual(api_size_string(1024, 1536), "1024x1536")

    def test_non_multiple_of_16_is_rejected(self):
        with self.assertRaises(DimensionError):
            api_size_string(1000, 1536)

    def test_tiny_document_is_rejected(self):
        with self.assertRaises(DimensionError):
            api_size_string(512, 512)


class ExportDirectoryTests(unittest.TestCase):
    def test_uses_localappdata_and_creates_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = folder
            try:
                path = export_directory()
                self.assertTrue(path.is_dir())
                self.assertEqual(path.parent.name, "krita-ai-art-assistant")
            finally:
                if previous is None:
                    del os.environ["LOCALAPPDATA"]
                else:
                    os.environ["LOCALAPPDATA"] = previous


if __name__ == "__main__":
    unittest.main()
