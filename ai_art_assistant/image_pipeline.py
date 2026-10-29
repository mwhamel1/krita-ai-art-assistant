# SPDX-License-Identifier: MIT

"""PNG size checks and selection-coverage helpers.

This module must not import krita. Tests run with a normal Python.
"""

from __future__ import annotations

import math
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


DEFAULT_CROP_MARGIN = 64


def selection_crop_rect(
    sel_x: int,
    sel_y: int,
    sel_w: int,
    sel_h: int,
    doc_w: int,
    doc_h: int,
    margin: int = DEFAULT_CROP_MARGIN,
) -> tuple[int, int, int, int]:
    """Selection box plus real-pixel margin. Does not pad empty canvas to API size."""
    if doc_w <= 0 or doc_h <= 0:
        raise DimensionError("The document has no pixel size.")
    if sel_w <= 0 or sel_h <= 0:
        raise DimensionError("The selection has no pixel size.")
    if margin < 0:
        margin = 0

    left = max(0, sel_x - margin)
    top = max(0, sel_y - margin)
    right = min(doc_w, sel_x + sel_w + margin)
    bottom = min(doc_h, sel_y + sel_h + margin)
    if right <= left or bottom <= top:
        raise DimensionError("The selection does not cover any document pixels.")

    x, y, width, height = left, top, right - left, bottom - top
    x, y, width, height = _snap_rect_to_16(x, y, width, height, doc_w, doc_h)
    if width < 16 or height < 16:
        raise DimensionError(
            "The selection is too small to send. Select a larger area."
        )
    return x, y, width, height


def api_upload_size(width: int, height: int) -> tuple[int, int]:
    """Smallest OpenAI-legal size that keeps this crop's aspect, scaled up if needed.

    Enlarges the sketch so it fills the upload. Does not pad with empty canvas.
    """
    if width <= 0 or height <= 0:
        raise DimensionError("The crop has no pixel size.")
    w = max(16, ((width + 15) // 16) * 16)
    h = max(16, ((height + 15) // 16) * 16)
    w, h = _fix_upload_aspect(w, h)
    if _rect_meets_api_size(w, h):
        return w, h
    for scale in range(2, 241):
        uw, uh = w * scale, h * scale
        if uw > 3840 or uh > 3840:
            break
        if _rect_meets_api_size(uw, uh):
            return uw, uh
    factor = math.sqrt(655_360 / (w * h))
    uw = max(w, int(math.ceil(w * factor)))
    uh = max(h, int(math.ceil(h * factor)))
    uw = max(16, ((uw + 15) // 16) * 16)
    uh = max(16, ((uh + 15) // 16) * 16)
    uw, uh = _fix_upload_aspect(uw, uh)
    if uw > 3840 or uh > 3840:
        raise DimensionError(
            f"The selected sketch is {width}×{height}. Enlarging it to OpenAI's "
            "minimum size would exceed 3840 on an edge. Make a larger selection. "
            "The plugin will not pad the rest of the canvas."
        )
    if _rect_meets_api_size(uw, uh):
        return uw, uh
    for _ in range(64):
        if _rect_meets_api_size(uw, uh):
            return uw, uh
        problems = _api_size_problems(uw, uh)
        if "small" in problems:
            if uw <= uh and uw + 16 <= 3840:
                uw += 16
            elif uh + 16 <= 3840:
                uh += 16
            elif uw + 16 <= 3840:
                uw += 16
            else:
                break
        else:
            uw, uh = _fix_upload_aspect(uw, uh)
            if "small" not in _api_size_problems(uw, uh) and not _rect_meets_api_size(uw, uh):
                break
    if _rect_meets_api_size(uw, uh):
        return uw, uh
    raise DimensionError(
        f"The selected sketch is {width}×{height}. It cannot be enlarged to a size "
        "OpenAI accepts without padding empty canvas. Make a larger selection."
    )


def paste_crop_rgba(
    crop_rgba: bytes,
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    doc_w: int,
    doc_h: int,
) -> bytes:
    """Place a crop onto a transparent full-document RGBA buffer. No stretch."""
    expected = crop_w * crop_h * 4
    if len(crop_rgba) != expected:
        raise DimensionError(
            f"Crop has {len(crop_rgba)} bytes; expected {expected} for {crop_w}×{crop_h}."
        )
    if crop_w <= 0 or crop_h <= 0:
        raise DimensionError("The crop has no pixel size.")
    if crop_x < 0 or crop_y < 0 or crop_x + crop_w > doc_w or crop_y + crop_h > doc_h:
        raise DimensionError(
            f"Crop {crop_w}×{crop_h} at ({crop_x}, {crop_y}) does not fit on "
            f"{doc_w}×{doc_h}. The plugin will not stretch or crop it."
        )
    out = bytearray(doc_w * doc_h * 4)
    row_bytes = crop_w * 4
    for row in range(crop_h):
        src = row * row_bytes
        dest = ((crop_y + row) * doc_w + crop_x) * 4
        out[dest : dest + row_bytes] = crop_rgba[src : src + row_bytes]
    return bytes(out)


def _rect_meets_api_size(width: int, height: int) -> bool:
    try:
        api_size_string(width, height)
        return True
    except DimensionError:
        return False


def _api_size_problems(width: int, height: int) -> set[str]:
    problems: set[str] = set()
    if width <= 0 or height <= 0:
        problems.add("empty")
        return problems
    if width % 16 != 0 or height % 16 != 0:
        problems.add("align")
    if width > 3840 or height > 3840:
        problems.add("edge")
    if width / height < 1 / 3 or width / height > 3:
        problems.add("aspect")
    pixels = width * height
    if pixels < 655_360:
        problems.add("small")
    if pixels > 8_294_400:
        problems.add("large")
    return problems


def _fix_upload_aspect(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return width, height
    while height and width / height > 3 and height + 16 <= 3840:
        height += 16
    while height and width / height < 1 / 3 and width + 16 <= 3840:
        width += 16
    return width, height


def _snap_rect_to_16(
    x: int, y: int, width: int, height: int, doc_w: int, doc_h: int
) -> tuple[int, int, int, int]:
    x, width = _snap_axis_to_16(x, width, doc_w)
    y, height = _snap_axis_to_16(y, height, doc_h)
    return x, y, width, height


def _snap_axis_to_16(origin: int, size: int, doc_size: int) -> tuple[int, int]:
    leftover = size % 16
    if leftover == 0:
        return origin, size
    needed = 16 - leftover
    room_end = doc_size - (origin + size)
    room_start = origin
    take_end = min(room_end, needed)
    take_start = min(room_start, needed - take_end)
    if take_start + take_end >= needed:
        return origin - take_start, size + take_start + take_end
    aligned = (size // 16) * 16
    if aligned >= 16:
        return origin, aligned
    return origin, size


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
