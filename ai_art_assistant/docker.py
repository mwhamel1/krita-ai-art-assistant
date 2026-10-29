# SPDX-License-Identifier: MIT

"""Side panel that reads the open Krita document. Export, import, and
Generate are visible in Phase 0 but not wired yet.
"""

from __future__ import annotations

import os

try:
    from PyQt6.QtWidgets import (
        QGroupBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    from PyQt5.QtWidgets import (
        QGroupBox,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

from krita import DockWidget, Krita

try:
    from builtins import i18n
except ImportError:
    def i18n(text):
        return text


class AIArtAssistantDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n("AI Art Assistant"))
        self.setObjectName("AIArtAssistantDocker")

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

        actions_box = QGroupBox(i18n("Local round trip (next step)"))
        actions_layout = QVBoxLayout(actions_box)
        self.export_visible_button = QPushButton(i18n("Export visible picture"))
        self.export_mask_button = QPushButton(i18n("Export selection stencil"))
        self.import_layer_button = QPushButton(i18n("Import as new layer"))
        for button in (
            self.export_visible_button,
            self.export_mask_button,
            self.import_layer_button,
        ):
            button.setEnabled(False)
            button.setToolTip(
                i18n("Not built yet. This will be added in the next step.")
            )
            actions_layout.addWidget(button)
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
            if document is None:
                self.document_label.setText(i18n("Document: No document open."))
                self.selection_label.setText(i18n("Selection: No selection."))
                self._set_status(
                    i18n(
                        "Open a drawing to see its name and size here. "
                        "Export and import come in the next step."
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

            selection = document.selection()
            if selection is None:
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
                    "Panel is reading the open document. "
                    "Export and import come in the next step."
                )
            )
        except Exception as exc:
            self.document_label.setText(i18n("Document: Could not read."))
            self.selection_label.setText(i18n("Selection: Could not read."))
            self._set_status(
                i18n("Could not read the document: {error}").format(error=exc)
            )

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