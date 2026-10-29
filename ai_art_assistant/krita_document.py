# SPDX-License-Identifier: MIT

"""Read the visible Krita document and insert a paint layer. UI-thread only."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

try:
    from PyQt6.QtGui import QImage
except Exception:
    from PyQt5.QtGui import QImage

from krita import InfoObject

from .image_pipeline import (
    DimensionError,
    openai_mask_rgba_from_coverage,
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
    return QImage.Format.Format_ARGB32


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

