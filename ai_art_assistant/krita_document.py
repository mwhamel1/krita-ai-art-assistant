# SPDX-License-Identifier: MIT

"""Read the visible Krita document and insert a paint layer. UI-thread only."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage

    IGNORE_ASPECT = Qt.AspectRatioMode.IgnoreAspectRatio
    FAST_SCALE = Qt.TransformationMode.FastTransformation
    SMOOTH_SCALE = Qt.TransformationMode.SmoothTransformation
except Exception:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QImage

    IGNORE_ASPECT = Qt.IgnoreAspectRatio
    FAST_SCALE = Qt.FastTransformation
    SMOOTH_SCALE = Qt.SmoothTransformation

from krita import InfoObject

from .image_pipeline import (
    DimensionError,
    clip_candidate_rgba_to_coverage,
    openai_mask_rgba_from_coverage,
    paste_crop_rgba,
    png_dimensions,
    require_coverage_size,
    require_same_size,
    write_png_gray,
    write_png_rgba,
)


class NoDocumentError(RuntimeError):
    pass


class NoSelectionError(RuntimeError):
    pass


class ExportError(RuntimeError):
    pass


class LayerImportError(RuntimeError):
    pass


def _qimage_format_argb32():
    try:
        return QImage.Format.Format_ARGB32
    except AttributeError:
        return QImage.Format_ARGB32


def _qimage_format_rgba8888():
    try:
        return QImage.Format.Format_RGBA8888
    except AttributeError:
        return QImage.Format_RGBA8888


def _qimage_format_gray8():
    try:
        return QImage.Format.Format_Grayscale8
    except AttributeError:
        return QImage.Format_Grayscale8


def _as_bytes(data) -> bytes:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    try:
        return bytes(data)
    except Exception as exc:
        raise ExportError(f"Could not read pixel bytes: {exc}") from exc


def _qimage_raw_bytes(image: QImage) -> bytes:
    nbytes = image.sizeInBytes() if hasattr(image, "sizeInBytes") else image.byteCount()
    bits = image.constBits()
    if bits is None:
        raise LayerImportError("Could not read image bytes.")
    try:
        bits.setsize(nbytes)
    except Exception:
        pass
    if hasattr(bits, "asstring"):
        return bits.asstring(nbytes)
    return bytes(bits)


def _packed_bgra(image: QImage) -> bytes:
    converted = image.convertToFormat(_qimage_format_argb32())
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    src = _qimage_raw_bytes(converted)
    row = width * 4
    if bytes_per_line == row:
        return src[: row * height]
    packed = bytearray(row * height)
    for y in range(height):
        start = y * bytes_per_line
        packed[y * row : (y + 1) * row] = src[start : start + row]
    return bytes(packed)


def _bgra_to_qimage(data: bytes, width: int, height: int) -> QImage:
    expected = width * height * 4
    if len(data) != expected:
        raise ExportError(
            f"Visible canvas data was {len(data)} bytes; expected {expected} for "
            f"{width}×{height} 8-bit RGBA."
        )
    image = QImage(data, width, height, width * 4, _qimage_format_argb32())
    return image.copy()


def export_visible_png(document, path: str | Path) -> str:
    """Save the visible projection. Does not flatten or save the .kra file."""
    if document is None:
        raise NoDocumentError("Open a drawing first.")
    width = document.width()
    height = document.height()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    model = document.colorModel()
    depth = document.colorDepth()
    warning = ""
    if model == "RGBA" and depth == "U8":
        data = _as_bytes(document.pixelData(0, 0, width, height))
        image = _bgra_to_qimage(data, width, height)
        if not image.save(str(path), "PNG"):
            raise ExportError(f"Could not save PNG to {path}")
        exported_w, exported_h = png_dimensions(path)
        require_same_size(exported_w, exported_h, width, height)
    else:
        info = InfoObject()
        info.setProperty("alpha", True)
        info.setProperty("compression", 6)
        info.setProperty("forceSRGB", True)
        if not document.exportImage(str(path), info):
            raise ExportError(f"Could not export the visible canvas to {path}")
        warning = (
            f"Document is {model}/{depth}, not 8-bit RGBA. "
            "Exported a converted PNG; the original document was not changed."
        )
        exported_w, exported_h = png_dimensions(path)
        require_same_size(exported_w, exported_h, width, height)
    return warning


def export_selection_stencil_png(document, path: str | Path) -> None:
    if document is None:
        raise NoDocumentError("Open a drawing first.")
    selection = document.selection()
    if selection is None:
        raise NoSelectionError(
            "There is no selection. Select an area first. "
            "The plugin will not treat 'nothing selected' as 'edit everything'."
        )
    width = document.width()
    height = document.height()
    coverage = _as_bytes(selection.pixelData(0, 0, width, height))
    require_coverage_size(coverage, width, height)
    write_png_gray(path, coverage, width, height)


def import_png_as_paint_layer(document, path: str | Path, layer_name: str | None = None) -> str:
    if document is None:
        raise NoDocumentError("Open a drawing first.")
    path = Path(path)
    if not path.is_file():
        raise LayerImportError(f"File not found: {path}")

    image = QImage(str(path))
    if image.isNull():
        raise LayerImportError(f"Could not read PNG: {path}")

    width = document.width()
    height = document.height()
    require_same_size(image.width(), image.height(), width, height)

    warning = ""
    model = document.colorModel()
    depth = document.colorDepth()
    layer = document.createNode(
        layer_name or default_import_layer_name(), "paintlayer"
    )
    if layer is None:
        raise LayerImportError("Krita did not create a paint layer.")

    if model != "RGBA" or depth != "U8":
        try:
            layer.setColorSpace("RGBA", "U8", document.colorProfile())
        except Exception:
            pass
        warning = (
            f"Document is {model}/{depth}. Imported an 8-bit RGBA overlay layer. "
            "Original layers were not converted."
        )

    pixel_bytes = _packed_bgra(image)
    if not layer.setPixelData(pixel_bytes, 0, 0, width, height):
        raise LayerImportError("Krita refused to write pixels onto the new layer.")

    parent = document.rootNode()
    if not parent.addChildNode(layer, None):
        raise LayerImportError("Could not add the new layer to the document.")

    document.refreshProjection()
    if hasattr(document, "waitForDone"):
        document.waitForDone()
    return warning


def default_import_layer_name(when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
    return f"AI Import {stamp}"


def default_edit_layer_name(when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime("%Y-%m-%d %H:%M")
    return f"AI Edit {stamp}"


def document_identity(document) -> tuple:
    if document is None:
        return ("", 0, 0)
    path = document.fileName() or ""
    if path:
        name = os.path.basename(path)
    else:
        name = ""
        if hasattr(document, "name"):
            try:
                name = document.name() or ""
            except Exception:
                name = ""
        name = name or "Untitled"
    return (name, document.width(), document.height())


def crop_png_to_rect(
    source_path: str | Path,
    dest_path: str | Path,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Path:
    """Cut a rectangle from a full-size PNG. Does not stretch."""
    source_path = Path(source_path)
    dest_path = Path(dest_path)
    image = QImage(str(source_path))
    if image.isNull():
        raise LayerImportError(f"Could not read PNG: {source_path}")
    if x < 0 or y < 0 or x + width > image.width() or y + height > image.height():
        raise DimensionError(
            f"Crop {width}×{height} at ({x}, {y}) does not fit on "
            f"{image.width()}×{image.height()}. The plugin will not stretch or crop it."
        )
    cropped = image.copy(x, y, width, height)
    if cropped.isNull() or cropped.width() != width or cropped.height() != height:
        raise LayerImportError(f"Could not crop PNG to {width}×{height}.")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not cropped.save(str(dest_path), "PNG"):
        raise ExportError(f"Could not save cropped PNG to {dest_path}")
    got_w, got_h = png_dimensions(dest_path)
    require_same_size(got_w, got_h, width, height)
    return dest_path


def scale_png(
    source_path: str | Path,
    dest_path: str | Path,
    width: int,
    height: int,
    nearest: bool,
) -> Path:
    """Scale a PNG to an exact size. Nearest-neighbor keeps sketch lines chunky."""
    source_path = Path(source_path)
    dest_path = Path(dest_path)
    image = QImage(str(source_path))
    if image.isNull():
        raise LayerImportError(f"Could not read PNG: {source_path}")
    mode = FAST_SCALE if nearest else SMOOTH_SCALE
    scaled = image.scaled(width, height, IGNORE_ASPECT, mode)
    if scaled.isNull() or scaled.width() != width or scaled.height() != height:
        raise LayerImportError(f"Could not scale PNG to {width}×{height}.")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not scaled.save(str(dest_path), "PNG"):
        raise ExportError(f"Could not save scaled PNG to {dest_path}")
    got_w, got_h = png_dimensions(dest_path)
    require_same_size(got_w, got_h, width, height)
    return dest_path


def paste_crop_png(
    crop_path: str | Path,
    dest_path: str | Path,
    x: int,
    y: int,
    crop_w: int,
    crop_h: int,
    doc_w: int,
    doc_h: int,
) -> Path:
    """Paste a crop onto a transparent full-document PNG."""
    crop_path = Path(crop_path)
    dest_path = Path(dest_path)
    crop = QImage(str(crop_path))
    if crop.isNull():
        raise LayerImportError(f"Could not read AI crop: {crop_path}")
    require_same_size(crop.width(), crop.height(), crop_w, crop_h)
    rgba = _packed_rgba(crop)
    full = paste_crop_rgba(rgba, x, y, crop_w, crop_h, doc_w, doc_h)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    write_png_rgba(dest_path, full, doc_w, doc_h)
    return dest_path


def clip_candidate_png_to_stencil(
    candidate_path: str | Path,
    stencil_path: str | Path,
    dest_path: str | Path,
    width: int,
    height: int,
) -> Path:
    """Write an overlay PNG: AI RGB, alpha from the Generate-time stencil."""
    candidate_path = Path(candidate_path)
    stencil_path = Path(stencil_path)
    dest_path = Path(dest_path)
    candidate = QImage(str(candidate_path))
    if candidate.isNull():
        raise LayerImportError(f"Could not read AI result: {candidate_path}")
    require_same_size(candidate.width(), candidate.height(), width, height)
    stencil = QImage(str(stencil_path))
    if stencil.isNull():
        raise LayerImportError(f"Could not read selection stencil: {stencil_path}")
    require_same_size(stencil.width(), stencil.height(), width, height)
    rgba = _packed_rgba(candidate)
    coverage = _packed_gray(stencil)
    clipped = clip_candidate_rgba_to_coverage(rgba, coverage, width, height)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    write_png_rgba(dest_path, clipped, width, height)
    return dest_path


def _packed_rgba(image: QImage) -> bytes:
    converted = image.convertToFormat(_qimage_format_rgba8888())
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    src = _qimage_raw_bytes(converted)
    row = width * 4
    if bytes_per_line == row:
        return src[: row * height]
    packed = bytearray(row * height)
    for y in range(height):
        start = y * bytes_per_line
        packed[y * row : (y + 1) * row] = src[start : start + row]
    return bytes(packed)


def _packed_gray(image: QImage) -> bytes:
    converted = image.convertToFormat(_qimage_format_gray8())
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    src = _qimage_raw_bytes(converted)
    if bytes_per_line == width:
        return src[: width * height]
    packed = bytearray(width * height)
    for y in range(height):
        start = y * bytes_per_line
        packed[y * width : (y + 1) * width] = src[start : start + width]
    return bytes(packed)


def export_openai_mask_png(document, path: str | Path) -> None:
    if document is None:
        raise NoDocumentError("Open a drawing first.")
    selection = document.selection()
    if selection is None:
        raise NoSelectionError(
            "There is no selection. Select an area first. "
            "The plugin will not treat 'nothing selected' as 'edit everything'."
        )
    width = document.width()
    height = document.height()
    coverage = _as_bytes(selection.pixelData(0, 0, width, height))
    rgba = openai_mask_rgba_from_coverage(coverage, width, height)
    write_png_rgba(path, rgba, width, height)

