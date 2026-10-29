# SPDX-License-Identifier: MIT

"""Side panel: local export/import plus OpenAI Image Edit Generate."""

from __future__ import annotations

import os
from datetime import datetime
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
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
    KEEP_ASPECT = Qt.AspectRatioMode.KeepAspectRatio
    SMOOTH = Qt.TransformationMode.SmoothTransformation
    ECHO_PASSWORD = QLineEdit.EchoMode.Password
    MSG_YES = QMessageBox.StandardButton.Yes
    MSG_NO = QMessageBox.StandardButton.No
    ADJUST_MIN = QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    SIZE_EXPANDING = QSizePolicy.Policy.Expanding
    SIZE_FIXED = QSizePolicy.Policy.Fixed
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
        QMessageBox,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    ALIGN_CENTER = Qt.AlignCenter
    KEEP_ASPECT = Qt.KeepAspectRatio
    SMOOTH = Qt.SmoothTransformation
    ECHO_PASSWORD = QLineEdit.Password
    MSG_YES = QMessageBox.Yes
    MSG_NO = QMessageBox.No
    ADJUST_MIN = QComboBox.AdjustToMinimumContentsLengthWithIcon
    SIZE_EXPANDING = QSizePolicy.Expanding
    SIZE_FIXED = QSizePolicy.Fixed

from krita import DockWidget, Krita

from .credentials import clear_api_key, has_api_key, load_api_key, save_api_key
from .image_pipeline import (
    CoverageError,
    DimensionError,
    api_size_string,
    api_upload_size,
    export_directory,
    new_export_path,
    png_dimensions,
    require_same_size,
    selection_crop_rect,
)
from .krita_document import (
    ExportError,
    LayerImportError,
    NoDocumentError,
    NoSelectionError,
    clip_candidate_png_to_stencil,
    crop_png_to_rect,
    default_edit_layer_name,
    default_import_layer_name,
    document_identity,
    export_selection_stencil_png,
    export_visible_png,
    import_png_as_paint_layer,
    paste_crop_png,
    scale_png,
)
from .openai_provider import OpenAIRequestError, edit_image
from .prompts import EmptyInstructionError, compose_edit_prompt
from .settings import (
    ALLOWED_QUALITIES,
    DEFAULT_MODEL,
    MODEL_CHOICES,
    append_request_log,
    load_settings,
    remember_prompt,
    save_settings,
)

try:
    from builtins import i18n
except ImportError:
    def i18n(text):
        return text

_PREVIEW_WIDTH = 240


def _narrow_combo(combo: QComboBox) -> None:
    combo.setSizeAdjustPolicy(ADJUST_MIN)
    combo.setMinimumContentsLength(8)
    combo.setSizePolicy(SIZE_EXPANDING, SIZE_FIXED)


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
        self._job_stencil_path = ""
        self._job_scope = "whole-canvas"
        self._job_quality = "medium"
        self._job_document_name = ""
        self._job_width = 0
        self._job_height = 0
        self._job_crop = None
        self._job_running = False
        self._cancel_requested = False
        self._session_generates = 0
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
        generate_help = QLabel(
            i18n(
                "Generate uploads the visible canvas, or the selected sketch "
                "(enlarged if OpenAI needs a bigger image)."
            )
        )
        generate_help.setWordWrap(True)
        generate_layout.addWidget(generate_help)
        generate_layout.addWidget(QLabel(i18n("Instruction")))
        self.history_combo = QComboBox()
        self.history_combo.setToolTip(
            i18n("Recent instructions saved on this PC. Pictures are not stored.")
        )
        _narrow_combo(self.history_combo)
        self.history_combo.currentIndexChanged.connect(self._reuse_history)
        generate_layout.addWidget(self.history_combo)
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
        _narrow_combo(self.quality_combo)
        for value in ALLOWED_QUALITIES:
            self.quality_combo.addItem(value)
        quality = self._settings.get("quality", "medium")
        index = max(0, self.quality_combo.findText(quality))
        self.quality_combo.setCurrentIndex(index)
        quality_row.addWidget(self.quality_combo)
        generate_layout.addLayout(quality_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(i18n("Model")))
        self.model_combo = QComboBox()
        _narrow_combo(self.model_combo)
        self.model_combo.setToolTip(
            i18n(
                "Flare is faster. Sunburst is more precise and usually costs more. "
                "One image per Generate click. This is the Image Edit API, not ChatGPT."
            )
        )
        for model_id, label in MODEL_CHOICES:
            self.model_combo.addItem(i18n(label), model_id)
        saved_model = self._settings.get("model", DEFAULT_MODEL)
        model_index = self.model_combo.findData(saved_model)
        self.model_combo.setCurrentIndex(model_index if model_index >= 0 else 0)
        model_row.addWidget(self.model_combo)
        generate_layout.addLayout(model_row)

        self.generate_button = QPushButton(i18n("Generate"))
        self.generate_button.clicked.connect(self._generate)
        self.cancel_button = QPushButton(i18n("Cancel"))
        self.cancel_button.setToolTip(
            i18n(
                "Ignore the result when it returns. If OpenAI already started, "
                "that click may still be billed."
            )
        )
        self.cancel_button.clicked.connect(self._cancel_generate)
        self.cancel_button.setEnabled(False)
        generate_layout.addWidget(self.generate_button)
        generate_layout.addWidget(self.cancel_button)

        self.apply_button = QPushButton(i18n("Apply as new layer"))
        self.apply_button.clicked.connect(self._apply_candidate)
        self.discard_button = QPushButton(i18n("Discard"))
        self.discard_button.clicked.connect(self._discard_candidate)
        self.retry_button = QPushButton(i18n("Retry"))
        self.retry_button.setToolTip(i18n("Sends another paid request."))
        self.retry_button.clicked.connect(self._generate)
        generate_layout.addWidget(self.apply_button)
        generate_layout.addWidget(self.discard_button)
        generate_layout.addWidget(self.retry_button)
        layout.addWidget(generate_box)

        self.preview_label = QLabel(i18n("No preview yet."))
        self.preview_label.setAlignment(ALIGN_CENTER)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        settings_box = QGroupBox(i18n("Settings"))
        settings_layout = QVBoxLayout(settings_box)
        key_help = QLabel(i18n("OpenAI API key (not ChatGPT Plus)"))
        key_help.setWordWrap(True)
        settings_layout.addWidget(key_help)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(ECHO_PASSWORD)
        self.api_key_edit.setPlaceholderText(i18n("sk-..."))
        settings_layout.addWidget(self.api_key_edit)
        self.key_status_label = QLabel()
        self.key_status_label.setWordWrap(True)
        settings_layout.addWidget(self.key_status_label)
        save_key_button = QPushButton(i18n("Save on this PC"))
        save_key_button.clicked.connect(self._save_key_persistent)
        session_key_button = QPushButton(i18n("This session only"))
        session_key_button.clicked.connect(self._save_key_session)
        clear_key_button = QPushButton(i18n("Clear key"))
        clear_key_button.clicked.connect(self._clear_key)
        settings_layout.addWidget(save_key_button)
        settings_layout.addWidget(session_key_button)
        settings_layout.addWidget(clear_key_button)
        save_prefs_button = QPushButton(i18n("Save prompt, model, and quality"))
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
        self._refresh_history_combo()
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
                        "Generate sends the visible canvas, or the selected sketch, "
                        "to OpenAI (one paid request). A small selection is enlarged "
                        "so the doodle fills the upload, then clipped back to the box."
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
        self.cancel_button.setEnabled(self._job_running)
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
            has_selection = document.selection() is not None
            prompt = compose_edit_prompt(
                self.base_prompt_edit.toPlainText(),
                self.prompt_edit.toPlainText(),
                has_selection,
            )
            upload_w = document.width()
            upload_h = document.height()
            crop_rect = None
            if has_selection:
                selection = document.selection()
                crop_rect = selection_crop_rect(
                    selection.x(),
                    selection.y(),
                    selection.width(),
                    selection.height(),
                    document.width(),
                    document.height(),
                )
                upload_w, upload_h = api_upload_size(crop_rect[2], crop_rect[3])
            size = api_size_string(upload_w, upload_h)
            if not self._confirm_session_spend():
                self._set_status(i18n("Generate cancelled. Nothing was sent."))
                return
            image_path = new_export_path("visible")
            export_visible_png(document, image_path)
            mask_path = ""
            self._job_stencil_path = ""
            self._job_crop = crop_rect
            self._job_scope = "selection" if has_selection else "whole-canvas"
            if has_selection:
                stencil_file = new_export_path("stencil")
                export_selection_stencil_png(document, stencil_file)
                self._job_stencil_path = str(stencil_file)
                crop_x, crop_y, crop_w, crop_h = crop_rect
                image_path = crop_png_to_rect(
                    image_path,
                    new_export_path("visible-crop"),
                    crop_x,
                    crop_y,
                    crop_w,
                    crop_h,
                )
                if (upload_w, upload_h) != (crop_w, crop_h):
                    image_path = scale_png(
                        image_path,
                        new_export_path("visible-upload"),
                        upload_w,
                        upload_h,
                        nearest=True,
                    )
            instruction = self.prompt_edit.toPlainText()
            self._settings["prompt_history"] = remember_prompt(
                self._settings.get("prompt_history") or [], instruction
            )
            self._persist_prefs_quietly()
            self._refresh_history_combo()
            self._job_snapshot = document_identity(document)
            self._job_quality = self.quality_combo.currentText() or "medium"
            self._job_document_name = _document_display_name(document)
            self._job_width = document.width()
            self._job_height = document.height()
            self._job_running = True
            self._cancel_requested = False
            self._candidate_path = ""
            self._set_candidate_buttons(False)
            self._update_generate_enabled(True)
            if has_selection:
                self._set_status(
                    i18n(
                        "Uploading the selected sketch to OpenAI. "
                        "If the box is small, the doodle is enlarged so it fills the "
                        "request, then scaled back. This spends API credits. "
                        "Cancel ignores the result; it does not stop a request that already started."
                    )
                )
            else:
                self._set_status(
                    i18n(
                        "Uploading the visible canvas to OpenAI. This spends API credits. "
                        "One click is one image. Krita should stay usable. Cancel ignores "
                        "the result; it does not stop a request that already started."
                    )
                )
            worker = GenerateWorker(
                api_key=api_key,
                image_path=str(image_path),
                mask_path=mask_path,
                prompt=prompt,
                model=self._current_model(),
                quality=self._job_quality,
                size=size,
                width=upload_w,
                height=upload_h,
            )
            worker.succeeded.connect(self._on_generate_ok)
            worker.failed.connect(self._on_generate_error)
            self._worker = worker
            self._session_generates += 1
            worker.start()
        except (
            EmptyInstructionError,
            DimensionError,
            NoDocumentError,
            NoSelectionError,
            ExportError,
            LayerImportError,
            CoverageError,
        ) as exc:
            self._job_running = False
            self._cancel_requested = False
            self._set_status(str(exc))
            self._update_generate_enabled(document is not None)
        except Exception as exc:
            self._job_running = False
            self._cancel_requested = False
            self._set_status(i18n("Could not start Generate: {error}").format(error=exc))
            self._update_generate_enabled(document is not None)

    def _on_generate_ok(self, path: str):
        self._job_running = False
        self._update_generate_enabled(_active_document() is not None)
        if self._cancel_requested:
            self._cancel_requested = False
            self._candidate_path = ""
            self._set_candidate_buttons(False)
            self.preview_label.setText(
                i18n("No preview. The cancelled result was ignored.")
            )
            self._log_request("cancelled")
            self._set_status(
                i18n(
                    "Generate cancelled. The result was ignored. "
                    "If OpenAI already started, that click may still have been billed."
                )
            )
            return
        apply_path = path
        try:
            if self._job_crop is not None:
                crop_x, crop_y, crop_w, crop_h = self._job_crop
                crop_result = path
                got_w, got_h = png_dimensions(path)
                if (got_w, got_h) != (crop_w, crop_h):
                    scaled_back = new_export_path("scaled-back")
                    scale_png(path, scaled_back, crop_w, crop_h, nearest=False)
                    crop_result = str(scaled_back)
                pasted = new_export_path("pasted")
                paste_crop_png(
                    crop_result,
                    pasted,
                    crop_x,
                    crop_y,
                    crop_w,
                    crop_h,
                    self._job_width,
                    self._job_height,
                )
                apply_path = str(pasted)
            if self._job_stencil_path:
                overlay = new_export_path("overlay")
                clip_candidate_png_to_stencil(
                    apply_path,
                    self._job_stencil_path,
                    overlay,
                    self._job_width,
                    self._job_height,
                )
                apply_path = str(overlay)
        except Exception as exc:
            self._candidate_path = ""
            self._set_candidate_buttons(False)
            self._log_request("error")
            self._set_status(
                i18n(
                    "The AI image returned, but placing it on the canvas failed: {error}"
                ).format(error=exc)
            )
            return
        self._candidate_path = apply_path
        self._show_preview(Path(apply_path))
        self._set_candidate_buttons(True)
        extra = ""
        if self._job_stencil_path:
            extra = i18n(
                " The upload was the selected sketch (enlarged if needed). "
                "Preview and Apply are clipped to the selection from Generate. "
                "Outside that box the new layer stays empty."
            )
        self._log_request("ok")
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
        if self._cancel_requested:
            self._cancel_requested = False
            self._log_request("cancelled")
            self._set_status(
                i18n(
                    "Generate cancelled. If OpenAI already started, that click may "
                    "still have been billed. {error}"
                ).format(error=message)
            )
            return
        self._log_request("error")
        self._set_status(message)

    def _cancel_generate(self):
        if not self._job_running:
            return
        self._cancel_requested = True
        self._set_status(
            i18n(
                "Cancel requested. Krita stays usable. If OpenAI already started, "
                "that click may still be billed. The result will be ignored."
            )
        )

    def _confirm_session_spend(self) -> bool:
        warn_after = int(self._settings.get("generate_warn_after", 5))
        if self._session_generates < warn_after:
            return True
        answer = QMessageBox.question(
            self,
            i18n("Spend another credit?"),
            i18n(
                "You have already sent {n} Generate requests this Krita session. "
                "This spends another API credit. Continue?"
            ).format(n=self._session_generates),
            MSG_YES | MSG_NO,
            MSG_NO,
        )
        return answer == MSG_YES

    def _log_request(self, outcome: str):
        try:
            append_request_log(
                {
                    "time": datetime.now().isoformat(timespec="seconds"),
                    "document": self._job_document_name,
                    "quality": self._job_quality,
                    "scope": self._job_scope,
                    "outcome": outcome,
                }
            )
        except OSError:
            pass

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
            self._clear_candidate_state()
        except (NoDocumentError, LayerImportError, DimensionError) as exc:
            self._set_status(str(exc))
        except Exception as exc:
            self._set_status(i18n("Apply failed: {error}").format(error=exc))

    def _discard_candidate(self):
        self._clear_candidate_state()
        self.preview_label.setText(i18n("Candidate discarded. Originals were not changed."))
        self._set_status(i18n("Candidate discarded."))

    def _clear_candidate_state(self):
        self._candidate_path = ""
        self._job_snapshot = None
        self._set_candidate_buttons(False)

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
        self._set_status(i18n("Prompt, model, and quality saved on this PC (not the API key)."))

    def _persist_prefs_quietly(self):
        self._settings["base_prompt"] = self.base_prompt_edit.toPlainText()
        self._settings["quality"] = self.quality_combo.currentText() or "medium"
        self._settings["model"] = self._current_model()
        save_settings(self._settings)

    def _current_model(self) -> str:
        value = self.model_combo.currentData()
        if value in (choice[0] for choice in MODEL_CHOICES):
            return str(value)
        return DEFAULT_MODEL

    def _refresh_history_combo(self):
        self.history_combo.blockSignals(True)
        self.history_combo.clear()
        self.history_combo.addItem(i18n("Reuse a recent instruction\u2026"))
        for item in self._settings.get("prompt_history") or []:
            self.history_combo.addItem(item)
        self.history_combo.setCurrentIndex(0)
        self.history_combo.blockSignals(False)

    def _reuse_history(self, index: int):
        if index <= 0:
            return
        self.prompt_edit.setPlainText(self.history_combo.itemText(index))

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
