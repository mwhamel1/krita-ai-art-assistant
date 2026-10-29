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
    api_upload_size,
    clip_candidate_rgba_to_coverage,
    export_directory,
    openai_mask_rgba_from_coverage,
    paste_crop_rgba,
    png_dimensions,
    require_coverage_size,
    require_same_size,
    selection_crop_rect,
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

    def test_clip_keeps_ai_rgb_and_uses_coverage_as_alpha(self):
        candidate = bytes(
            [
                10, 20, 30, 255,
                40, 50, 60, 255,
                70, 80, 90, 128,
                100, 110, 120, 0,
            ]
        )
        coverage = bytes([0, 64, 255, 128])
        clipped = clip_candidate_rgba_to_coverage(candidate, coverage, 2, 2)
        self.assertEqual(clipped[0:3], b"\x0a\x14\x1e")
        self.assertEqual(clipped[3], 0)
        self.assertEqual(clipped[4:8], bytes([40, 50, 60, 64]))
        self.assertEqual(clipped[8:12], bytes([70, 80, 90, 255]))
        self.assertEqual(clipped[12:16], bytes([100, 110, 120, 128]))

    def test_clip_outside_box_is_fully_transparent(self):
        candidate = bytes([255, 0, 0, 255] * 4)
        coverage = bytes([0, 0, 0, 255])
        clipped = clip_candidate_rgba_to_coverage(candidate, coverage, 2, 2)
        self.assertEqual(list(clipped[3::4]), [0, 0, 0, 255])
        self.assertEqual(clipped[12:15], b"\xff\x00\x00")

    def test_clip_wrong_coverage_length_is_an_error(self):
        with self.assertRaises(CoverageError):
            clip_candidate_rgba_to_coverage(bytes(16), b"\x00", 2, 2)

    def test_clip_wrong_candidate_length_is_an_error(self):
        with self.assertRaises(DimensionError):
            clip_candidate_rgba_to_coverage(bytes(8), bytes([255, 255, 255, 255]), 2, 2)


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


class SelectionCropRectTests(unittest.TestCase):
    def test_margin_is_applied_and_selection_stays_inside(self):
        x, y, width, height = selection_crop_rect(200, 400, 160, 160, 1024, 1536, margin=64)
        self.assertLessEqual(x, 200)
        self.assertLessEqual(y, 400)
        self.assertGreaterEqual(x + width, 360)
        self.assertGreaterEqual(y + height, 560)
        self.assertEqual(width % 16, 0)
        self.assertEqual(height % 16, 0)
        self.assertLess(width * height, 655_360)

    def test_corner_selection_clamps_to_document(self):
        x, y, width, height = selection_crop_rect(0, 0, 80, 80, 1024, 1536, margin=64)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertLessEqual(x + width, 1024)
        self.assertLessEqual(y + height, 1536)
        self.assertLess(width * height, 655_360)

    def test_tiny_box_stays_tight_and_does_not_pad_the_canvas(self):
        x, y, width, height = selection_crop_rect(40, 40, 32, 32, 1024, 1536, margin=64)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + width, 200)
        self.assertLessEqual(y + height, 200)
        self.assertLess(width * height, 655_360)

    def test_tiny_document_still_yields_a_crop(self):
        x, y, width, height = selection_crop_rect(0, 0, 64, 64, 512, 512, margin=64)
        self.assertEqual(x, 0)
        self.assertEqual(y, 0)
        self.assertLessEqual(width, 512)
        self.assertLessEqual(height, 512)

    def test_non_multiple_of_16_is_snapped(self):
        x, y, width, height = selection_crop_rect(10, 20, 100, 100, 1024, 1536, margin=64)
        self.assertEqual(width % 16, 0)
        self.assertEqual(height % 16, 0)
        self.assertLessEqual(x, 10)
        self.assertLessEqual(y, 20)
        self.assertGreaterEqual(x + width, 110)
        self.assertGreaterEqual(y + height, 120)


class PasteCropTests(unittest.TestCase):
    def test_paste_keeps_alignment_and_transparent_outside(self):
        crop = bytes(
            [
                1, 2, 3, 255,
                4, 5, 6, 255,
                7, 8, 9, 128,
                10, 11, 12, 64,
            ]
        )
        full = paste_crop_rgba(crop, 1, 1, 2, 2, 4, 4)
        self.assertEqual(len(full), 4 * 4 * 4)
        self.assertEqual(full[0:4], b"\x00\x00\x00\x00")
        dest = ((1 * 4) + 1) * 4
        self.assertEqual(full[dest : dest + 4], bytes([1, 2, 3, 255]))
        dest2 = ((2 * 4) + 2) * 4
        self.assertEqual(full[dest2 : dest2 + 4], bytes([10, 11, 12, 64]))

    def test_paste_that_does_not_fit_is_an_error(self):
        with self.assertRaises(DimensionError) as caught:
            paste_crop_rgba(bytes(2 * 2 * 4), 3, 3, 2, 2, 4, 4)
        self.assertIn("will not stretch", str(caught.exception))


class ApiUploadSizeTests(unittest.TestCase):
    def test_card_size_is_unchanged(self):
        self.assertEqual(api_upload_size(1024, 1536), (1024, 1536))

    def test_tiny_square_is_enlarged_to_a_valid_filled_size(self):
        width, height = api_upload_size(160, 160)
        self.assertEqual(width, height)
        self.assertGreaterEqual(width, 160)
        self.assertEqual(width % 16, 0)
        api_size_string(width, height)

    def test_integer_scale_keeps_aspect(self):
        width, height = api_upload_size(288, 288)
        self.assertEqual(width, height)
        self.assertEqual(width % 288, 0)
        api_size_string(width, height)


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
