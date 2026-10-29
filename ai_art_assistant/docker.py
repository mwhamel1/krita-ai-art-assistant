# SPDX-License-Identifier: MIT

"""Side panel: local export/import plus OpenAI Image Edit Generate."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
    from PyQt6.QtGui import QDesktopServices, QPixmap
    from PyQt6.QtWidgets import (
        QComboBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    KEEP_ASPECT = Qt.AspectRatioMode.KeepAspectRatio
    SMOOTH = Qt.TransformationMode.SmoothTransformation
    ECHO_PASSWORD = QLineEdit.EchoMode.Password
except Exception:
    from PyQt5.QtCore import Qt, QThread, QUrl, pyqtSignal
    from PyQt5.QtGui import QDesktopServices, QPixmap
    from PyQt5.QtWidgets import (
        QComboBox,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QScrollArea,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignCenter
    KEEP_ASPECT = Qt.KeepAspectRatio
    SMOOTH = Qt.SmoothTransformation
    ECHO_PASSWORD = QLineEdit.Password

from krita import DockWidget, Krita

from .credentials import clear_api_key, has_api_key, load_api_key, save_api_key
from .image_pipeline import (
    CoverageError,
    DimensionError,
    api_size_string,
    export_directory,
    new_export_path,
    png_dimensions,
    require_same_size,
)
from .krita_document import (
    ExportError,
    LayerImportError,
    NoDocumentError,
    NoSelectionError,
    default_edit_layer_name,
    default_import_layer_name,
    document_identity,
    export_openai_mask_png,
    export_selection_stencil_png,
    export_visible_png,
    import_png_as_paint_layer,
)
from .openai_provider import OpenAIRequestError, edit_image
from .prompts import EmptyInstructionError, compose_edit_prompt
from .settings import ALLOWED_QUALITIES, load_settings, save_settings

try:
    from builtins import i18n
except ImportError:
    def i18n(text):
        return text

_PREVIEW_WIDTH = 240


class GenerateWorker(QThread):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        image_path: str,
        mask_path: str,
        prompt: str,
        model: str,
        quality: str,
        size: str,
        width: int,
        height: int,
    ):
        super().__init__()
        self._api_key = api_key
        self._image_path = image_path
        self._mask_path = mask_path
        self._prompt = prompt
        self._model = model
        self._quality = quality
        self._size = size
        self._width = width
        self._height = height

    def run(self):
        try:
            image_png = Path(self._image_path).read_bytes()
            mask_png = None
            if self._mask_path:
                mask_png = Path(self._mask_path).read_bytes()
            result = edit_image(
                api_key=self._api_key,
                image_png=image_png,
                mask_png=mask_png,
                prompt=self._prompt,
                model=self._model,
                quality=self._quality,
                size=self._size,
            )
            dest = new_export_path("candidate")
            dest.write_bytes(result)
            got_w, got_h = png_dimensions(dest)
            require_same_size(got_w, got_h, self._width, self._height)
            self.succeeded.emit(str(dest))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._api_key = ""


class AIArtAssistantDocker(DockWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n("AI Art Assistant"))
        self.setObjectName("AIArtAssistantDocker")
        self._last_export_path = ""
        self._last_stencil_path = ""
        self._candidate_path = ""
        self._job_snapshot = None
        self._job_running = False
        self._worker = None
        self._settings = load_settings()

        root = QWidget()
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
        self.export_visible_button.clicked.connect(self._export_visible)
        self.export_mask_button = QPushButton(i18n("Export selection stencil"))
        self.export_mask_button.clicked.connect(self._export_stencil)
        self.import_layer_button = QPushButton(i18n("Import as new layer"))
        self.import_layer_button.clicked.connect(self._import_layer)
        self.show_files_button = QPushButton(i18n("Show exported files"))
        self.show_files_button.clicked.connect(self._show_exported_files)
        for button in (
            self.export_visible_button,
            self.export_mask_button,
            self.import_layer_button,
            self.show_files_button,
        ):
            actions_layout.addWidget(button)
        layout.addWidget(actions_box)

        generate_box = QGroupBox(i18n("AI edit"))
        generate_layout = QVBoxLayout(generate_box)
        generate_layout.addWidget(
            QLabel(i18n("Generate uploads the visible canvas (and mask) to OpenAI."))
        )
        generate_layout.addWidget(QLabel(i18n("Instruction")))
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText(
            i18n("Example: Turn the selected armor into ancient leather.")
        )
        self.prompt_edit.setMaximumHeight(80)
        generate_layout.addWidget(self.prompt_edit)

        self.base_prompt_box = QGroupBox(i18n("Base prompt (project art direction)"))
        self.base_prompt_box.setCheckable(True)
        self.base_prompt_box.setChecked(False)
        base_layout = QVBoxLayout(self.base_prompt_box)
        self.base_prompt_edit = QTextEdit()
        self.base_prompt_edit.setPlainText(self._settings.get("base_prompt", ""))
        self.base_prompt_edit.setMaximumHeight(70)
        base_layout.addWidget(self.base_prompt_edit)
        generate_layout.addWidget(self.base_prompt_box)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel(i18n("Quality")))
        self.quality_combo = QComboBox()
        for value in ALLOWED_QUALITIES:
            self.quality_combo.addItem(value)
        quality = self._settings.get("quality", "medium")
        index = max(0, self.quality_combo.findText(quality))
        self.quality_combo.setCurrentIndex(index)
        quality_row.addWidget(self.quality_combo)
        generate_layout.addLayout(quality_row)
        generate_layout.addWidget(
            QLabel(i18n("Model: gpt-image-2.5-flare (one image per Generate click)"))
        )

        self.generate_button = QPushButton(i18n("Generate"))
        self.generate_button.clicked.connect(self._generate)
        generate_layout.addWidget(self.generate_button)

        candidate_row = QHBoxLayout()
        self.apply_button = QPushButton(i18n("Apply as new layer"))
        self.apply_button.clicked.connect(self._apply_candidate)
        self.discard_button = QPushButton(i18n("Discard"))
        self.discard_button.clicked.connect(self._discard_candidate)
        self.retry_button = QPushButton(i18n("Retry"))
        self.retry_button.setToolTip(i18n("Sends another paid request."))
        self.retry_button.clicked.connect(self._generate)
        candidate_row.addWidget(self.apply_button)
        candidate_row.addWidget(self.discard_button)
        candidate_row.addWidget(self.retry_button)
        generate_layout.addLayout(candidate_row)
        layout.addWidget(generate_box)

        self.preview_label = QLabel(i18n("No preview yet."))
        self.preview_label.setAlignment(ALIGN_CENTER)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        settings_box = QGroupBox(i18n("Settings"))
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addWidget(QLabel(i18n("OpenAI API key (not ChatGPT Plus)")))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(ECHO_PASSWORD)
        self.api_key_edit.setPlaceholderText(i18n("sk-..."))
        settings_layout.addWidget(self.api_key_edit)
        self.key_status_label = QLabel()
        self.key_status_label.setWordWrap(True)
        settings_layout.addWidget(self.key_status_label)
        key_row = QHBoxLayout()
        save_key_button = QPushButton(i18n("Save on this PC"))
        save_key_button.clicked.connect(self._save_key_persistent)
        session_key_button = QPushButton(i18n("This session only"))
        session_key_button.clicked.connect(self._save_key_session)
        clear_key_button = QPushButton(i18n("Clear key"))
        clear_key_button.clicked.connect(self._clear_key)
        key_row.addWidget(save_key_button)
        key_row.addWidget(session_key_button)
        key_row.addWidget(clear_key_button)
        settings_layout.addLayout(key_row)
        save_prefs_button = QPushButton(i18n("Save prompt and quality"))
        save_prefs_button.clicked.connect(self._save_prefs)
        settings_layout.addWidget(save_prefs_button)
        layout.addWidget(settings_box)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("AIArtAssistantStatus")
        layout.addWidget(self.status_label)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root)
        self.setWidget(scroll)

        self._refresh_key_status()
        self._set_candidate_buttons(False)
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
            self._update_generate_enabled(has_document)

            if not has_document:
                self.document_label.setText(i18n("Document: No document open."))
                self.selection_label.setText(i18n("Selection: No selection."))
                if not self._job_running and not self._candidate_path:
                    self._set_status(
                        i18n(
                            "Open a drawing (File → New, or New Image on the Start screen)."
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
            if not self._job_running and not self._candidate_path:
                self._set_status(
                    i18n(
                        "Generate sends the visible canvas to OpenAI (one paid request). "
                        "A selection is guidance only in this version; clipping comes later."
                    )
                )
        except Exception as exc:
            self.export_visible_button.setEnabled(False)
            self.export_mask_button.setEnabled(False)
            self.import_layer_button.setEnabled(False)
            self.generate_button.setEnabled(False)
            self._set_status(
                i18n("Could not read the document: {error}").format(error=exc)
            )

    def _update_generate_enabled(self, has_document: bool):
        ok = (
            has_document
            and has_api_key()
            and not self._job_running
        )
        self.generate_button.setEnabled(ok)
        if not has_document:
            self.generate_button.setToolTip(i18n("Open a drawing first."))
        elif not has_api_key():
            self.generate_button.setToolTip(
                i18n("Save an OpenAI API key in Settings first.")
            )
        elif self._job_running:
            self.generate_button.setToolTip(i18n("A request is already running."))
        else:
            self.generate_button.setToolTip(
                i18n("Send one Image Edit request. This uses API credits.")
            )

    def _set_candidate_buttons(self, enabled: bool):
        self.apply_button.setEnabled(enabled)
        self.discard_button.setEnabled(enabled)
        self.retry_button.setEnabled(enabled and not self._job_running)

    def _generate(self):
        if self._job_running:
            self._set_status(i18n("A request is already running."))
            return
        document = _active_document()
        if document is None:
            self._set_status(i18n("Open a drawing first."))
            return
        api_key = load_api_key()
        if not api_key:
            self._set_status(
                i18n(
                    "Save an OpenAI API key in Settings first. "
                    "ChatGPT Plus is not an API key."
                )
            )
            self._update_generate_enabled(True)
            return
        try:
            prompt = compose_edit_prompt(
                self.base_prompt_edit.toPlainText(),
                self.prompt_edit.toPlainText(),
                document.selection() is not None,
            )
            size = api_size_string(document.width(), document.height())
            image_path = new_export_path("visible")
            export_visible_png(document, image_path)
            mask_path = ""
            if document.selection() is not None:
                mask_file = new_export_path("openai-mask")
                export_openai_mask_png(document, mask_file)
                mask_path = str(mask_file)
            self._persist_prefs_quietly()
            self._job_snapshot = document_identity(document)
            self._job_running = True
            self._candidate_path = ""
            self._set_candidate_buttons(False)
            self._update_generate_enabled(True)
            self._set_status(
                i18n(
                    "Uploading the visible canvas to OpenAI. This spends API credits. "
                    "One click is one image. Krita should stay usable."
                )
            )
            worker = GenerateWorker(
                api_key=api_key,
                image_path=str(image_path),
                mask_path=mask_path,
                prompt=prompt,
                model=self._settings.get("model", "gpt-image-2.5-flare"),
                quality=self.quality_combo.currentText() or "medium",
                size=size,
                width=document.width(),
                height=document.height(),
            )
            worker.succeeded.connect(self._on_generate_ok)
            worker.failed.connect(self._on_generate_error)
            self._worker = worker
            worker.start()
        except (
            EmptyInstructionError,
            DimensionError,
            NoDocumentError,
            NoSelectionError,
            ExportError,
            CoverageError,
        ) as exc:
            self._job_running = False
            self._set_status(str(exc))
            self._update_generate_enabled(document is not None)
        except Exception as exc:
            self._job_running = False
            self._set_status(i18n("Could not start Generate: {error}").format(error=exc))
            self._update_generate_enabled(document is not None)

    def _on_generate_ok(self, path: str):
        self._job_running = False
        self._candidate_path = path
        self._show_preview(Path(path))
        self._set_candidate_buttons(True)
        self._update_generate_enabled(_active_document() is not None)
        extra = ""
        if _active_document() is not None and _active_document().selection() is not None:
            extra = i18n(
                " A selection was sent as guidance; the result may still change "
                "pixels outside the box until a later version clips it."
            )
        self._set_status(
            i18n("Candidate ready. Apply as a new layer, Discard, or Retry (Retry costs again).{extra}").format(
                extra=extra
            )
        )

    def _on_generate_error(self, message: str):
        self._job_running = False
        self._candidate_path = ""
        self._set_candidate_buttons(False)
        self._update_generate_enabled(_active_document() is not None)
        self._set_status(message)

    def _apply_candidate(self):
        try:
            document = _active_document()
            if document is None:
                raise NoDocumentError("Open the original drawing before applying.")
            if not self._candidate_path:
                self._set_status(i18n("There is no candidate to apply."))
                return
            current = document_identity(document)
            if self._job_snapshot and current != self._job_snapshot:
                self._set_status(
                    i18n(
                        "This result belongs to a different document. "
                        "The plugin will not apply it here."
                    )
                )
                return
            warning = import_png_as_paint_layer(
                document, self._candidate_path, default_edit_layer_name()
            )
            extra = f" {warning}" if warning else ""
            self._set_status(
                i18n(
                    "Applied as a new layer.{extra} Undo will remove it. "
                    "Original layers were not overwritten."
                ).format(extra=extra)
            )
            self._candidate_path = ""
            self._job_snapshot = None
            self._set_candidate_buttons(False)
        except (NoDocumentError, LayerImportError, DimensionError) as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(i18n("Apply failed: {error}").format(error=exc))

    def _discard_candidate(self):
        self._candidate_path = ""
        self._job_snapshot = None
        self._set_candidate_buttons(False)
        self.preview_label.setText(i18n("Candidate discarded. Originals were not changed."))
        self._set_status(i18n("Candidate discarded."))

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
            self._set_status(i18n("Export failed: {error}").format(error=exc))

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
            self._set_status(i18n("Stencil export failed: {error}").format(error=exc))

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
            self._set_status(i18n("Import failed: {error}").format(error=exc))

    def _show_exported_files(self):
        folder = export_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self._set_status(i18n("Opened export folder: {path}").format(path=folder))

    def _show_preview(self, path: Path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.preview_label.setText(i18n("Saved, but preview could not load."))
            return
        scaled = pixmap.scaled(_PREVIEW_WIDTH, _PREVIEW_WIDTH, KEEP_ASPECT, SMOOTH)
        self.preview_label.setPixmap(scaled)

    def _save_key_persistent(self):
        try:
            where = save_api_key(self.api_key_edit.text(), persist=True)
            self.api_key_edit.clear()
            if where == "credential_manager":
                self._set_status(i18n("API key saved in Windows Credential Manager."))
            else:
                self._set_status(
                    i18n(
                        "Could not use Credential Manager. The key will last only "
                        "until you close Krita."
                    )
                )
            self._refresh_key_status()
            self._update_generate_enabled(_active_document() is not None)
        except ValueError as exc:
            self._set_status(str(exc))

    def _save_key_session(self):
        try:
            save_api_key(self.api_key_edit.text(), persist=False)
            self.api_key_edit.clear()
            self._set_status(i18n("API key kept for this Krita session only."))
            self._refresh_key_status()
            self._update_generate_enabled(_active_document() is not None)
        except ValueError as exc:
            self._set_status(str(exc))

    def _clear_key(self):
        clear_api_key()
        self.api_key_edit.clear()
        self._set_status(i18n("Saved API key cleared."))
        self._refresh_key_status()
        self._update_generate_enabled(_active_document() is not None)

    def _save_prefs(self):
        self._persist_prefs_quietly()
        self._set_status(i18n("Prompt and quality saved on this PC (not the API key)."))

    def _persist_prefs_quietly(self):
        self._settings["base_prompt"] = self.base_prompt_edit.toPlainText()
        self._settings["quality"] = self.quality_combo.currentText() or "medium"
        save_settings(self._settings)

    def _refresh_key_status(self):
        if has_api_key():
            self.key_status_label.setText(i18n("A key is stored on this PC or in this session."))
            self.api_key_edit.setPlaceholderText(i18n("Key saved — paste a new one to replace it"))
        else:
            self.key_status_label.setText(i18n("No API key stored."))
            self.api_key_edit.setPlaceholderText(i18n("sk-..."))

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
