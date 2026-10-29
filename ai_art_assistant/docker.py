# SPDX-License-Identifier: MIT

"""Side panel for local canvas export/import. Generate is not wired yet."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QDesktopServices, QPixmap
    from PyQt6.QtWidgets import (
        QFileDialog,
        QGroupBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    KEEP_ASPECT = Qt.AspectRatioMode.KeepAspectRatio
    SMOOTH = Qt.TransformationMode.SmoothTransformation
except Exception:
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtGui import QDesktopServices, QPixmap
    from PyQt5.QtWidgets import (
        QFileDialog,
        QGroupBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignCenter
    KEEP_ASPECT = Qt.KeepAspectRatio
    SMOOTH = Qt.SmoothTransformation

from krita import DockWidget, Krita

from .image_pipeline import (
    CoverageError,
    DimensionError,
    export_directory,
    new_export_path,
)
from .krita_document import (
    ExportError,
    LayerImportError,
    NoDocumentError,
    NoSelectionError,
    default_import_layer_name,
    export_selection_stencil_png,
    export_visible_png,
    import_png_as_paint_layer,
)

try:
    from builtins import i18n
except ImportError:
    def i18n(text):
        return text

_PREVIEW_WIDTH = 240


class AIArtAssistantDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n("AI Art Assistant"))
        self.setObjectName("AIArtAssistantDocker")
        self._last_export_path = ""
        self._last_stencil_path = ""

        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.document_label = QLabel()
        self.document_label.setWordWrap(True)
        self.selection_label = QLabel()
        self.selection_label.setWordWrap(True)

        info_box = QGroupBox(i18n("Current document"))
        info_layout = QVBoxLayout(info_box)
        info_layout.addWidget(self.document_label)
        info_layout.addWidget(self.selection_label)
        self.refresh_button = QPushButton(i18n("Refresh"))
        self.refresh_button.setToolTip(
            i18n("Update document size and selection status from Krita.")
        )
        self.refresh_button.clicked.connect(self.refresh_document_info)
        info_layout.addWidget(self.refresh_button)
        layout.addWidget(info_box)

        actions_box = QGroupBox(i18n("Local round trip"))
        actions_layout = QVBoxLayout(actions_box)
        self.export_visible_button = QPushButton(i18n("Export visible picture"))
        self.export_visible_button.setToolTip(
            i18n("Save what the canvas currently looks like as a PNG.")
        )
        self.export_visible_button.clicked.connect(self._export_visible)
        self.export_mask_button = QPushButton(i18n("Export selection stencil"))
        self.export_mask_button.setToolTip(
            i18n("Save the current selection as a same-size stencil PNG.")
        )
        self.export_mask_button.clicked.connect(self._export_stencil)
        self.import_layer_button = QPushButton(i18n("Import as new layer"))
        self.import_layer_button.setToolTip(
            i18n("Choose a PNG and add it as a new layer. Originals are kept.")
        )
        self.import_layer_button.clicked.connect(self._import_layer)
        self.show_files_button = QPushButton(i18n("Show exported files"))
        self.show_files_button.setToolTip(
            i18n("Open the folder where exported PNGs are saved.")
        )
        self.show_files_button.clicked.connect(self._show_exported_files)
        for button in (
            self.export_visible_button,
            self.export_mask_button,
            self.import_layer_button,
            self.show_files_button,
        ):
            actions_layout.addWidget(button)

        self.preview_label = QLabel(i18n("No export yet."))
        self.preview_label.setAlignment(ALIGN_CENTER)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setWordWrap(True)
        actions_layout.addWidget(self.preview_label)
        layout.addWidget(actions_box)

        generate_box = QGroupBox(i18n("AI edit"))
        generate_layout = QVBoxLayout(generate_box)
        self.generate_button = QPushButton(i18n("Generate (not built yet)"))
        self.generate_button.setEnabled(False)
        self.generate_button.setToolTip(
            i18n("Cloud image edit is not in this version.")
        )
        generate_layout.addWidget(self.generate_button)
        layout.addWidget(generate_box)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("AIArtAssistantStatus")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        self.setWidget(root)
        self.refresh_document_info()

    def canvasChanged(self, canvas):
        self.refresh_document_info()

    def refresh_document_info(self):
        try:
            document = _active_document()
            has_document = document is not None
            selection = document.selection() if has_document else None
            has_selection = selection is not None

            self.export_visible_button.setEnabled(has_document)
            self.export_mask_button.setEnabled(has_document and has_selection)
            self.import_layer_button.setEnabled(has_document)
            self.show_files_button.setEnabled(True)

            if not has_document:
                self.document_label.setText(i18n("Document: No document open."))
                self.selection_label.setText(i18n("Selection: No selection."))
                self._set_status(
                    i18n(
                        "Open a drawing (File → New, or New Image on the Start screen). "
                        "Export needs a canvas."
                    )
                )
                return

            width = document.width()
            height = document.height()
            name = _document_display_name(document)
            self.document_label.setText(
                i18n("Document: {name} \u2014 {width} \u00d7 {height}").format(
                    name=name, width=width, height=height
                )
            )

            if not has_selection:
                self.selection_label.setText(i18n("Selection: No selection."))
            else:
                self.selection_label.setText(
                    i18n(
                        "Selection: Yes \u2014 {width} \u00d7 {height} at ({x}, {y})"
                    ).format(
                        width=selection.width(),
                        height=selection.height(),
                        x=selection.x(),
                        y=selection.y(),
                    )
                )

            self._set_status(
                i18n(
                    "Export the visible picture, optionally export a selection stencil, "
                    "then import a PNG as a new layer. Generate is not built yet."
                )
            )
        except Exception as exc:
            self.document_label.setText(i18n("Document: Could not read."))
            self.selection_label.setText(i18n("Selection: Could not read."))
            self.export_visible_button.setEnabled(False)
            self.export_mask_button.setEnabled(False)
            self.import_layer_button.setEnabled(False)
            self._set_status(
                i18n("Could not read the document: {error}").format(error=exc)
            )

    def _export_visible(self):
        try:
            document = _active_document()
            path = new_export_path("visible")
            warning = export_visible_png(document, path)
            self._last_export_path = str(path)
            self._show_preview(path)
            extra = f" {warning}" if warning else ""
            self._set_status(
                i18n("Saved visible picture to {path}.{extra}").format(
                    path=path.name, extra=extra
                )
            )
        except (NoDocumentError, ExportError, DimensionError) as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(
                i18n("Export failed: {error}").format(error=exc)
            )

    def _export_stencil(self):
        try:
            document = _active_document()
            path = new_export_path("stencil")
            export_selection_stencil_png(document, path)
            self._last_stencil_path = str(path)
            self._show_preview(path)
            self._set_status(
                i18n("Saved selection stencil to {path}.").format(path=path.name)
            )
        except (NoDocumentError, NoSelectionError, ExportError, CoverageError) as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(
                i18n("Stencil export failed: {error}").format(error=exc)
            )

    def _import_layer(self):
        try:
            document = _active_document()
            if document is None:
                raise NoDocumentError("Open a drawing first.")
            start = self._last_export_path or str(export_directory())
            chosen, _filter = QFileDialog.getOpenFileName(
                self,
                i18n("Import PNG as new layer"),
                start,
                i18n("PNG images (*.png)"),
            )
            if not chosen:
                self._set_status(i18n("Import cancelled."))
                return
            warning = import_png_as_paint_layer(
                document, chosen, default_import_layer_name()
            )
            extra = f" {warning}" if warning else ""
            self._set_status(
                i18n("Added a new layer from {name}.{extra} Undo will remove it.").format(
                    name=Path(chosen).name, extra=extra
                )
            )
        except (NoDocumentError, LayerImportError, DimensionError) as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(
                i18n("Import failed: {error}").format(error=exc)
            )

    def _show_exported_files(self):
        folder = export_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self._set_status(
            i18n("Opened export folder: {path}").format(path=folder)
        )

    def _show_preview(self, path: Path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText(i18n("Saved, but preview could not load."))
            return
        scaled = pixmap.scaled(_PREVIEW_WIDTH, _PREVIEW_WIDTH, KEEP_ASPECT, SMOOTH)
        self.preview_label.setPixmap(scaled)

    def _set_status(self, text):
        self.status_label.setText(i18n("Status: {text}").format(text=text))


def _active_document():
    app = Krita.instance()
    if app is None:
        return None
    return app.activeDocument()


def _document_display_name(document):
    path = document.fileName() or ""
    if path:
        return os.path.basename(path)
    name = ""
    if hasattr(document, "name"):
        try:
            name = document.name() or ""
        except Exception:
            name = ""
    return name or i18n("Untitled")
