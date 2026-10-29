# SPDX-License-Identifier: MIT

"""PNG size checks and selection-coverage helpers.

This module must not import krita. Tests run with a normal Python.
"""

from __future__ import annotations

import os
import struct
import zlib
from datetime import datetime
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class DimensionError(ValueError):
    """Source and destination pixel sizes do not match."""


class CoverageError(ValueError):
    """Selection coverage bytes are the wrong length."""


def export_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    path = Path(base) / "krita-ai-art-assistant" / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_export_path(kind: str, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return export_directory() / f"{kind}-{stamp}.png"


def require_same_size(width_a: int, height_a: int, width_b: int, height_b: int) -> None:
    if (width_a, height_a) != (width_b, height_b):
        raise DimensionError(
            f"Image is {width_a}×{height_a}, but the document is {width_b}×{height_b}. "
            "The plugin will not stretch or crop it."
        )


def require_coverage_size(coverage: bytes, width: int, height: int) -> None:
    expected = width * height
    if len(coverage) != expected:
        raise CoverageError(
            f"Selection stencil has {len(coverage)} pixels; expected {expected} "
            f"({width}×{height})."
        )


def stencil_rgba_from_coverage(coverage: bytes, width: int, height: int) -> bytes:
    """White RGB, alpha = coverage. Selected area is visible; empty is transparent."""
    require_coverage_size(coverage, width, height)
    out = bytearray(width * height * 4)
    for index, value in enumerate(coverage):
        offset = index * 4
        out[offset] = 255
        out[offset + 1] = 255
        out[offset + 2] = 255
        out[offset + 3] = value
    return bytes(out)


def clip_candidate_rgba_to_coverage(
    candidate_rgba: bytes,
    coverage: bytes,
    width: int,
    height: int,
) -> bytes:
    """RGB from the AI image; alpha from the Generate-time selection coverage.

    Unselected pixels become fully transparent. Feathered coverage stays soft.
    """
    require_coverage_size(coverage, width, height)
    expected = width * height * 4
    if len(candidate_rgba) != expected:
        raise DimensionError(
            f"AI image has {len(candidate_rgba)} bytes; expected {expected} "
            f"for {width}×{height}."
        )
    out = bytearray(expected)
    for index, value in enumerate(coverage):
        offset = index * 4
        out[offset] = candidate_rgba[offset]
        out[offset + 1] = candidate_rgba[offset + 1]
        out[offset + 2] = candidate_rgba[offset + 2]
        out[offset + 3] = value
    return bytes(out)


def openai_mask_rgba_from_coverage(coverage: bytes, width: int, height: int) -> bytes:
    """OpenAI Image Edit: alpha 0 means 'edit this pixel'. Invert Krita coverage."""
    require_coverage_size(coverage, width, height)
    out = bytearray(width * height * 4)
    for index, value in enumerate(coverage):
        offset = index * 4
        out[offset] = 0
        out[offset + 1] = 0
        out[offset + 2] = 0
        out[offset + 3] = 255 - value
    return bytes(out)


def api_size_string(width: int, height: int) -> str:
    """Return WIDTHxHEIGHT if OpenAI Image Edit can use it. Never stretch."""
    if width <= 0 or height <= 0:
        raise DimensionError("The document has no pixel size.")
    if width % 16 != 0 or height % 16 != 0:
        raise DimensionError(
            f"OpenAI needs width and height in multiples of 16. "
            f"This document is {width}×{height}."
        )
    if width > 3840 or height > 3840:
        raise DimensionError(
            f"OpenAI rejects edges over 3840 pixels. This document is {width}×{height}."
        )
    ratio = width / height
    if ratio < 1 / 3 or ratio > 3:
        raise DimensionError(
            f"OpenAI only allows aspect ratios between 1:3 and 3:1. "
            f"This document is {width}×{height}."
        )
    pixels = width * height
    if pixels < 655_360 or pixels > 8_294_400:
        raise DimensionError(
            f"OpenAI pixel count must be between 655,360 and 8,294,400. "
            f"This document is {width}×{height} ({pixels} pixels)."
        )
    return f"{width}x{height}"


def png_dimensions(path: str | Path) -> tuple[int, int]:
    with Path(path).open("rb") as handle:
        signature = handle.read(8)
        if signature != PNG_SIGNATURE:
            raise ValueError(f"Not a PNG file: {path}")
        length = int.from_bytes(handle.read(4), "big")
        chunk_type = handle.read(4)
        if chunk_type != b"IHDR" or length < 8:
            raise ValueError(f"PNG header missing in {path}")
        width = int.from_bytes(handle.read(4), "big")
        height = int.from_bytes(handle.read(4), "big")
        return width, height


def write_png_rgba(path: str | Path, rgba: bytes, width: int, height: int) -> None:
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(f"RGBA buffer is {len(rgba)} bytes; expected {expected}.")
    _write_png(path, rgba, width, height, color_type=6, channels=4)


def write_png_gray(path: str | Path, gray: bytes, width: int, height: int) -> None:
    require_coverage_size(gray, width, height)
    _write_png(path, gray, width, height, color_type=0, channels=1)


def _write_png(
    path: str | Path,
    pixels: bytes,
    width: int,
    height: int,
    color_type: int,
    channels: int,
) -> None:
    raw = bytearray()
    stride = width * channels
    for row in range(height):
        raw.append(0)
        start = row * stride
        raw.extend(pixels[start : start + stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    png = (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    Path(path).write_bytes(png)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)
