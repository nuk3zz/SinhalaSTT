#!/usr/bin/env python3
"""
SinhalaSTT 1.0 — a simple desktop tool for making Sinhala/English subtitles.

Three tools:
  1. Text -> Subtitles: paste or open a script, pick a split, get an SRT.
                         Sinhala text also gets an FM/DL legacy-font SRT.
  2. Audio -> Subtitles (experimental): rough timing from audio, optionally
                         filled with your script.
  3. AI Caption: optional online transcription with your own Gemini key.
"""

from __future__ import annotations

import sys
import traceback
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ai_captions_core import (
    DEFAULT_GEMINI_MODEL,
    AiCaptionError,
    estimate_gemini_cost,
    generate_ai_captions_srt,
)
from document_reader import DocumentReadError, read_text_from_file
from transcriber_core import (
    CACHE_AUDIO_DIR,
    DEFAULT_PLACEHOLDER_MODE,
    DOWNLOADS_OUTPUT_DIR,
    PlaceholderError,
    create_audio_subtitles,
    create_text_subtitles,
    ffmpeg_install_hint,
    find_tool,
    get_audio_duration,
)


MODE_LABELS = {
    "sentence": "Sentences",
    "1": "1 word",
    "2": "2 words",
    "3": "3 words",
}

APP_NAME = "SinhalaSTT"
APP_VERSION = "1.0"
APP_TAGLINE = "Make Sinhala or English subtitles from a script or from audio."
GITHUB_URL = "https://github.com/nuk3zz/SinhalaSTT"
FFMPEG_INSTALL_MESSAGE = (
    "FFmpeg setup needed: the Audio and AI tabs need FFmpeg. " + ffmpeg_install_hint()
)

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aiff", ".aif"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
SUPPORTED_INPUT_SUFFIXES = SUPPORTED_AUDIO_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES
DOCUMENT_FILTER = "Documents (*.pdf *.docx *.txt);;All files (*)"


APP_STYLE = """
QMainWindow, QWidget {
    background: #f7f8fb;
    color: #171b22;
    font-size: 13px;
}
QLabel#Title {
    color: #10141a;
    font-size: 20px;
    font-weight: 750;
}
QLabel#Version {
    color: #6b7280;
    font-size: 12px;
}
QLabel#Subtitle {
    color: #5f6773;
}
QWidget#Hero, QWidget#Banner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #eef2f7);
    border: 1px solid #dde3ec;
    border-radius: 12px;
}
QWidget#HeroHover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffffff, stop:1 #eaf2fb);
    border: 1px solid #a8bbd6;
    border-radius: 12px;
}
QLabel#HeroTitle {
    color: #111827;
    font-size: 30px;
    font-weight: 760;
}
QLabel#HeroTagline {
    color: #6b7280;
    font-size: 14px;
}
QLabel#BetaPill {
    color: #5f6773;
    background: #edf0f4;
    border: 1px solid #dbe1ea;
    border-radius: 8px;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#PathLabel {
    color: #4b5563;
    background: #ffffff;
    border: 1px solid #dfe4ec;
    border-radius: 8px;
    padding: 7px;
}
QLabel#SmallNote {
    color: #777f8c;
    font-size: 11px;
}
QLabel#DropZone {
    color: #4b5563;
    background: #fbfcfe;
    border: 1px dashed #c7d0dd;
    border-radius: 12px;
    padding: 10px;
    font-weight: 650;
}
QLabel#DropZone:hover {
    background: #ffffff;
    border: 1px dashed #7f99bd;
    color: #1f2937;
}
QLabel#DropZone[dragging="true"] {
    background: #eef6ff;
    border: 1px solid #6b94cc;
}
QPushButton {
    color: #171b22;
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 9px;
    padding: 8px 12px;
    font-weight: 650;
}
QPushButton#Primary {
    color: #ffffff;
    background: #4f7fbf;
    border: 1px solid #4574b3;
}
QPushButton#Primary:hover {
    background: #5a8ace;
}
QPushButton#Primary:disabled {
    color: #eef2f8;
    background: #aebfd8;
    border: 1px solid #aebfd8;
}
QPushButton:hover {
    background: #fbfdff;
    border: 1px solid #8aa2c6;
    color: #0f172a;
}
QPushButton:pressed {
    background: #eef4fb;
    border: 1px solid #6685b3;
}
QPushButton:disabled {
    color: #a6adba;
    border: 1px solid #e1e5ec;
    background: #f0f2f5;
}
QComboBox {
    color: #171b22;
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 9px;
    padding: 7px 34px 7px 10px;
}
QComboBox:hover {
    border: 1px solid #8aa2c6;
}
QComboBox::drop-down {
    width: 30px;
    border: 0;
    background: transparent;
}
QComboBox::down-arrow {
    image: url("__CHEVRON_PATH__");
    width: 14px;
    height: 14px;
    border: 0;
}
QComboBox::down-arrow:on {
    top: 1px;
}
QComboBox QAbstractItemView {
    color: #171b22;
    background: #ffffff;
    selection-background-color: #e8f0fb;
}
QDoubleSpinBox {
    color: #171b22;
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 9px;
    padding: 6px 8px;
}
QDoubleSpinBox:hover {
    border: 1px solid #8aa2c6;
}
QLineEdit {
    color: #171b22;
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 9px;
    padding: 8px;
}
QLineEdit:hover, QLineEdit:focus {
    border: 1px solid #8aa2c6;
}
QCheckBox {
    color: #4b5563;
}
QPlainTextEdit {
    color: #171b22;
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 10px;
    padding: 8px;
    selection-background-color: #d7e7fb;
}
QPlainTextEdit:hover, QPlainTextEdit:focus {
    border: 1px solid #8aa2c6;
}
QProgressBar {
    color: #4b5563;
    background: #edf1f6;
    border: 1px solid #e2e7ef;
    border-radius: 6px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background: #7fa2c7;
    border-radius: 5px;
}
QTabWidget::pane {
    border: 1px solid #dfe4ec;
    border-radius: 12px;
    top: -1px;
    background: #ffffff;
}
QTabBar::tab {
    color: #596273;
    background: #eef1f5;
    border: 1px solid #e2e6ee;
    padding: 7px 18px;
    border-radius: 9px;
    margin: 0 2px;
}
QTabBar::tab:hover {
    color: #111827;
    background: #ffffff;
    border: 1px solid #b9c6d8;
}
QTabBar::tab:selected {
    color: #111827;
    border-color: #d8dee8;
    background: #ffffff;
}
"""


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path


class HeroBanner(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Banner")
        self.setMinimumHeight(112)
        self.setMaximumHeight(140)

        icon = QLabel()
        icon.setFixedSize(92, 92)
        icon.setAlignment(Qt.AlignCenter)
        icon_pixmap = QPixmap(str(resource_path("assets/icon-source.png")))
        if not icon_pixmap.isNull():
            icon.setPixmap(
                icon_pixmap.scaled(
                    icon.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        title = QLabel(APP_NAME)
        title.setObjectName("HeroTitle")

        version_pill = QLabel(f"v{APP_VERSION}")
        version_pill.setObjectName("BetaPill")
        version_pill.setMaximumWidth(56)
        version_pill.setAlignment(Qt.AlignCenter)

        tagline = QLabel("Turning Sinhala speech into accurate subtitles.")
        tagline.setObjectName("HeroTagline")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.addWidget(title)
        title_row.addWidget(version_pill)
        title_row.addStretch(1)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        text_layout.addStretch(1)
        text_layout.addLayout(title_row)
        text_layout.addWidget(tagline)
        text_layout.addStretch(1)

        layout = QHBoxLayout()
        layout.setContentsMargins(28, 14, 28, 14)
        layout.setSpacing(24)
        layout.addWidget(icon)
        layout.addLayout(text_layout, 1)
        self.setLayout(layout)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setObjectName("HeroHover")
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setObjectName("Hero")
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


class DropZone(QLabel):
    file_dropped = Signal(Path)
    rejected = Signal(str)

    def __init__(self) -> None:
        super().__init__("Drop audio/video here\nMP3, WAV, M4A, MP4, MOV")
        self.setObjectName("DropZone")
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(66)
        self.setProperty("dragging", False)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        path = self._first_local_file(event)
        if path and path.suffix.lower() in SUPPORTED_INPUT_SUFFIXES:
            self._set_dragging(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_dragging(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._set_dragging(False)
        path = self._first_local_file(event)
        if path is None:
            self.rejected.emit("Drop did not contain a local file.")
            event.ignore()
            return

        if path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            self.rejected.emit(f"Unsupported file type: {path.suffix or 'unknown'}")
            event.ignore()
            return

        self.file_dropped.emit(path)
        event.acceptProposedAction()

    def _first_local_file(self, event) -> Path | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None

        for url in mime.urls():
            if url.isLocalFile():
                return Path(url.toLocalFile())
        return None

    def _set_dragging(self, dragging: bool) -> None:
        self.setProperty("dragging", dragging)
        self.style().unpolish(self)
        self.style().polish(self)


class AudioWorker(QObject):
    log_message = Signal(str)
    progress_changed = Signal(int)
    finished = Signal(object)  # SubtitleFilesResult
    failed = Signal(str)

    def __init__(self, input_path: Path, mode: str, script_text: str) -> None:
        super().__init__()
        self.input_path = input_path
        self.mode = mode
        self.script_text = script_text

    def run(self) -> None:
        try:
            result = create_audio_subtitles(
                self.input_path,
                mode=self.mode,
                script_text=self.script_text,
                output_dir=DOWNLOADS_OUTPUT_DIR,
                log=self.log_message.emit,
                progress=self.progress_changed.emit,
            )
            self.finished.emit(result)
        except PlaceholderError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Unexpected error:\n\n" + traceback.format_exc())


class AiCaptionWorker(QObject):
    log_message = Signal(str)
    progress_changed = Signal(int)
    finished = Signal(str, int, float, list)
    failed = Signal(str)

    def __init__(self, input_path: Path, api_key: str, model: str) -> None:
        super().__init__()
        self.input_path = input_path
        self.api_key = api_key
        self.model = model

    def run(self) -> None:
        try:
            result = generate_ai_captions_srt(
                self.input_path,
                api_key=self.api_key,
                model=self.model,
                audio_dir=CACHE_AUDIO_DIR,
                output_dir=DOWNLOADS_OUTPUT_DIR,
                log=self.log_message.emit,
                progress=self.progress_changed.emit,
            )
            self.finished.emit(
                str(result.subtitle_path),
                result.subtitle_count,
                result.duration_seconds,
                result.warnings,
            )
        except AiCaptionError as error:
            self.failed.emit(str(error))
        except PlaceholderError as error:
            self.failed.emit(str(error))
        except Exception:
            self.failed.emit("Unexpected error:\n\n" + traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.selected_audio: Path | None = None
        self.selected_ai_input: Path | None = None
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.audio_thread: QThread | None = None
        self.audio_worker: AudioWorker | None = None
        self.ai_thread: QThread | None = None
        self.ai_worker: AiCaptionWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(620, 600)
        self.resize(760, 700)

        self.banner = HeroBanner()

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("Version")
        subtitle = QLabel(APP_TAGLINE)
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        github_button = QPushButton("Check for Updates")
        github_button.setMaximumWidth(140)
        github_button.clicked.connect(self.open_github)

        header = QHBoxLayout()
        header.addWidget(title)
        header.addWidget(version)
        header.addStretch()
        header.addWidget(github_button)

        subtitle_row = QHBoxLayout()
        subtitle_row.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_text_tab(), "Text → Subtitles")
        self.tabs.addTab(self.build_audio_tab(), "Audio → Subtitles")
        self.tabs.addTab(self.build_ai_tab(), "AI Caption")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.banner)
        layout.addLayout(header)
        layout.addLayout(subtitle_row)
        layout.addWidget(self.tabs)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.show_dependency_notice()

    def open_github(self) -> None:
        webbrowser.open(GITHUB_URL)

    def show_dependency_notice(self) -> None:
        if find_tool("ffmpeg") and find_tool("ffprobe"):
            return
        self.audio_status_label.setText(FFMPEG_INSTALL_MESSAGE)
        self.append_audio_log("First-time setup note:")
        self.append_audio_log(FFMPEG_INSTALL_MESSAGE)

    # ------------------------------------------------------------------
    # Tab 1: Text -> Subtitles
    # ------------------------------------------------------------------
    def build_text_tab(self) -> QWidget:
        intro = QLabel(
            "Paste your script or open a PDF / DOCX / TXT file, pick how to split it, "
            "then create the subtitles. Sinhala text also gets an FM/DL legacy-font file."
        )
        intro.setObjectName("PathLabel")
        intro.setWordWrap(True)

        self.open_text_button = QPushButton("Open File (PDF, DOCX, TXT)")
        self.open_text_button.clicked.connect(self.open_text_document)

        self.text_mode_box = QComboBox()
        for mode, label in MODE_LABELS.items():
            self.text_mode_box.addItem(label, mode)
        self.text_mode_box.setCurrentIndex(list(MODE_LABELS).index(DEFAULT_PLACEHOLDER_MODE))

        self.text_seconds = QDoubleSpinBox()
        self.text_seconds.setRange(0.2, 60.0)
        self.text_seconds.setSingleStep(0.5)
        self.text_seconds.setValue(1.0)
        self.text_seconds.setDecimals(1)
        self.text_seconds.setSuffix(" s")
        self.text_seconds.setMaximumWidth(90)

        self.text_create_button = QPushButton("Create Subtitles")
        self.text_create_button.setObjectName("Primary")
        self.text_create_button.setEnabled(False)
        self.text_create_button.clicked.connect(self.create_text_subtitles_action)

        self.text_box = QPlainTextEdit()
        self.text_box.setPlaceholderText(
            "Paste Sinhala or English text here, or use Open File.\n"
            "Tip: choose a split (Sentences / 1 / 2 / 3 words) before creating."
        )
        self.text_box.textChanged.connect(self.update_text_button)

        self.text_status_label = QLabel("Subtitles save to your Downloads folder.")
        self.text_status_label.setObjectName("PathLabel")
        self.text_status_label.setWordWrap(True)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        controls_row.addWidget(self.open_text_button)
        controls_row.addWidget(QLabel("Split:"))
        controls_row.addWidget(self.text_mode_box, 1)
        controls_row.addWidget(QLabel("Each line:"))
        controls_row.addWidget(self.text_seconds)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(self.text_create_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(intro)
        layout.addLayout(controls_row)
        layout.addWidget(self.text_box, 1)
        layout.addLayout(action_row)
        layout.addWidget(self.text_status_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def update_text_button(self) -> None:
        self.text_create_button.setEnabled(bool(self.text_box.toPlainText().strip()))

    def open_text_document(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Open Script",
            str(Path.home() / "Documents"),
            DOCUMENT_FILTER,
        )
        if not file_name:
            return
        try:
            text = read_text_from_file(file_name)
        except DocumentReadError as error:
            QMessageBox.warning(self, "Could not read file", str(error))
            return
        self.text_box.setPlainText(text)
        self.text_status_label.setText(f"Loaded text from: {Path(file_name).name}")

    def create_text_subtitles_action(self) -> None:
        text = self.text_box.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "No text", "Paste or open some text first.")
            return

        try:
            result = create_text_subtitles(
                text,
                mode=self.text_mode_box.currentData(),
                output_dir=DOWNLOADS_OUTPUT_DIR,
                seconds_per_block=self.text_seconds.value(),
            )
        except PlaceholderError as error:
            QMessageBox.critical(self, "Could not create subtitles", str(error))
            return

        lines = [f"Saved {len(result.files)} file(s) to Downloads:"]
        lines.extend(f"  {label}: {path}" for label, path in result.files)
        lines.append(f"Subtitle blocks: {result.block_count}")
        if result.is_sinhala:
            lines.append("Detected Sinhala — an FM/DL legacy-font version was also saved.")
        lines.extend(f"Note: {warning}" for warning in result.warnings)
        self.text_status_label.setText("\n".join(lines))

    # ------------------------------------------------------------------
    # Tab 2: Audio -> Subtitles (experimental)
    # ------------------------------------------------------------------
    def build_audio_tab(self) -> QWidget:
        note = QLabel(
            "Experimental: timing is estimated from pauses in the audio, so it is "
            "approximate. Add a script below to fill in the words, or leave it empty "
            "for blank timed blocks."
        )
        note.setObjectName("SmallNote")
        note.setWordWrap(True)

        self.audio_drop = DropZone()
        self.audio_drop.file_dropped.connect(self.set_audio_input)
        self.audio_drop.rejected.connect(self.append_audio_log)

        self.audio_choose_audio_button = QPushButton("Import Audio")
        self.audio_choose_audio_button.clicked.connect(self.choose_audio)
        self.audio_choose_video_button = QPushButton("Import MP4/Video")
        self.audio_choose_video_button.clicked.connect(self.choose_video)

        self.audio_file_label = QLabel("No file selected")
        self.audio_file_label.setObjectName("PathLabel")
        self.audio_file_label.setWordWrap(True)

        self.audio_mode_box = QComboBox()
        for mode, label in MODE_LABELS.items():
            self.audio_mode_box.addItem(label, mode)
        self.audio_mode_box.setCurrentIndex(list(MODE_LABELS).index(DEFAULT_PLACEHOLDER_MODE))

        self.audio_open_script_button = QPushButton("Open Script File")
        self.audio_open_script_button.clicked.connect(self.open_audio_script_document)

        self.audio_script_box = QPlainTextEdit()
        self.audio_script_box.setMaximumHeight(120)
        self.audio_script_box.setPlaceholderText(
            "Optional: paste your script here (or use Open Script File).\n"
            "Leave empty to just get blank timed blocks."
        )

        self.audio_start_button = QPushButton("Create Subtitles from Audio")
        self.audio_start_button.setObjectName("Primary")
        self.audio_start_button.setEnabled(False)
        self.audio_start_button.clicked.connect(self.start_audio_generation)

        self.audio_progress = QProgressBar()
        self.audio_progress.setRange(0, 100)
        self.audio_progress.setValue(0)

        self.audio_log = QPlainTextEdit()
        self.audio_log.setReadOnly(True)
        self.audio_log.setMaximumHeight(100)
        self.audio_log.setPlaceholderText("Logs...")

        self.audio_status_label = QLabel("Subtitles save to your Downloads folder.")
        self.audio_status_label.setObjectName("PathLabel")
        self.audio_status_label.setWordWrap(True)

        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        import_row.addWidget(self.audio_choose_audio_button)
        import_row.addWidget(self.audio_choose_video_button)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("Split:"))
        mode_row.addWidget(self.audio_mode_box, 1)
        mode_row.addWidget(self.audio_open_script_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.audio_drop)
        layout.addLayout(import_row)
        layout.addWidget(self.audio_file_label)
        layout.addLayout(mode_row)
        layout.addWidget(QLabel("Script (optional):"))
        layout.addWidget(self.audio_script_box)
        layout.addWidget(self.audio_start_button)
        layout.addWidget(self.audio_progress)
        layout.addWidget(self.audio_log)
        layout.addWidget(note)
        layout.addWidget(self.audio_status_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def choose_audio(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Audio",
            str(Path.home() / "Documents"),
            "Audio files (*.mp3 *.wav *.m4a *.aac *.flac *.aiff *.aif);;All files (*)",
        )
        if file_name:
            self.set_audio_input(Path(file_name))

    def choose_video(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import MP4 or Video",
            str(Path.home() / "Movies"),
            "Video files (*.mp4 *.mov *.m4v *.mkv *.avi *.webm);;All files (*)",
        )
        if file_name:
            self.set_audio_input(Path(file_name))

    def set_audio_input(self, path: Path) -> None:
        path = path.expanduser()
        if path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please choose MP3, WAV, M4A, AAC, FLAC, AIFF, MP4, MOV, MKV, AVI, or WEBM.",
            )
            return
        self.selected_audio = path
        self.audio_file_label.setText(str(path))
        self.audio_drop.setText(f"Selected:\n{path.name}")
        self.audio_progress.setValue(0)
        self.audio_start_button.setEnabled(True)
        self.audio_log.clear()
        self.append_audio_log(f"Selected: {path.name}")

    def open_audio_script_document(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Open Script",
            str(Path.home() / "Documents"),
            DOCUMENT_FILTER,
        )
        if not file_name:
            return
        try:
            text = read_text_from_file(file_name)
        except DocumentReadError as error:
            QMessageBox.warning(self, "Could not read file", str(error))
            return
        self.audio_script_box.setPlainText(text)
        self.append_audio_log(f"Loaded script from: {Path(file_name).name}")

    def start_audio_generation(self) -> None:
        if self.selected_audio is None:
            QMessageBox.warning(self, "No file selected", "Please import or drop an audio/video file first.")
            return

        self.set_audio_controls_enabled(False)
        self.audio_progress.setValue(0)
        self.append_audio_log("Starting...")

        self.audio_thread = QThread()
        self.audio_worker = AudioWorker(
            self.selected_audio,
            self.audio_mode_box.currentData(),
            self.audio_script_box.toPlainText(),
        )
        self.audio_worker.moveToThread(self.audio_thread)

        self.audio_thread.started.connect(self.audio_worker.run)
        self.audio_worker.log_message.connect(self.append_audio_log)
        self.audio_worker.progress_changed.connect(self.audio_progress.setValue)
        self.audio_worker.finished.connect(self.on_audio_finished)
        self.audio_worker.failed.connect(self.on_audio_failed)
        self.audio_worker.finished.connect(self.audio_thread.quit)
        self.audio_worker.failed.connect(self.audio_thread.quit)
        self.audio_thread.finished.connect(self.audio_worker.deleteLater)
        self.audio_thread.finished.connect(self.audio_thread.deleteLater)
        self.audio_thread.finished.connect(self.reset_audio_worker_refs)

        self.audio_thread.start()

    def set_audio_controls_enabled(self, enabled: bool) -> None:
        self.audio_choose_audio_button.setEnabled(enabled)
        self.audio_choose_video_button.setEnabled(enabled)
        self.audio_drop.setEnabled(enabled)
        self.audio_mode_box.setEnabled(enabled)
        self.audio_open_script_button.setEnabled(enabled)
        self.audio_start_button.setEnabled(enabled and self.selected_audio is not None)

    def on_audio_finished(self, result) -> None:
        self.audio_progress.setValue(100)
        lines = [f"Saved {len(result.files)} file(s) to Downloads:"]
        lines.extend(f"  {label}: {path}" for label, path in result.files)
        lines.append(f"Subtitle blocks: {result.block_count}")
        if result.is_sinhala:
            lines.append("Detected Sinhala — an FM/DL legacy-font version was also saved.")
        lines.extend(f"Note: {warning}" for warning in result.warnings)
        self.audio_status_label.setText("\n".join(lines))
        for label, path in result.files:
            self.append_audio_log(f"Saved {label}: {path}")
        self.set_audio_controls_enabled(True)

    def on_audio_failed(self, message: str) -> None:
        self.append_audio_log("Error:")
        self.append_audio_log(message)
        self.set_audio_controls_enabled(True)
        if "FFmpeg" in message or "FFprobe" in message:
            self.audio_status_label.setText(FFMPEG_INSTALL_MESSAGE)
            return
        QMessageBox.critical(self, "Audio subtitles failed", message)

    def reset_audio_worker_refs(self) -> None:
        self.audio_thread = None
        self.audio_worker = None

    def append_audio_log(self, message: str) -> None:
        self.audio_log.appendPlainText(message)
        scrollbar = self.audio_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ------------------------------------------------------------------
    # Tab 3: AI Caption
    # ------------------------------------------------------------------
    def build_ai_tab(self) -> QWidget:
        saved_key = self.settings.value("gemini_api_key", "", str)

        self.ai_key_input = QLineEdit()
        self.ai_key_input.setEchoMode(QLineEdit.Password)
        self.ai_key_input.setPlaceholderText("Paste Gemini API key")
        self.ai_key_input.setText(saved_key)

        self.ai_remember_check = QCheckBox("Remember locally")
        self.ai_remember_check.setChecked(bool(saved_key))

        self.ai_model_label = QLabel(f"Model: Gemini Flash-Lite ({DEFAULT_GEMINI_MODEL})")
        self.ai_model_label.setObjectName("PathLabel")
        self.ai_model_label.setWordWrap(True)

        self.ai_note_label = QLabel(
            "Offline tools stay local. AI Caption sends extracted audio to Google Gemini "
            "using your API key."
        )
        self.ai_note_label.setObjectName("SmallNote")
        self.ai_note_label.setWordWrap(True)

        self.ai_drop_zone = DropZone()
        self.ai_drop_zone.file_dropped.connect(self.set_ai_selected_input)
        self.ai_drop_zone.rejected.connect(self.append_ai_log)

        self.ai_choose_audio_button = QPushButton("Import Audio")
        self.ai_choose_audio_button.clicked.connect(self.choose_ai_audio)
        self.ai_choose_video_button = QPushButton("Import MP4/Video")
        self.ai_choose_video_button.clicked.connect(self.choose_ai_video)

        self.ai_file_label = QLabel("No file selected")
        self.ai_file_label.setObjectName("PathLabel")
        self.ai_file_label.setWordWrap(True)

        self.ai_estimate_label = QLabel("Select a file to see an approximate Gemini cost.")
        self.ai_estimate_label.setObjectName("PathLabel")
        self.ai_estimate_label.setWordWrap(True)

        self.ai_start_button = QPushButton("Generate AI Captions")
        self.ai_start_button.setObjectName("Primary")
        self.ai_start_button.setEnabled(False)
        self.ai_start_button.clicked.connect(self.start_ai_generation)

        self.ai_progress_bar = QProgressBar()
        self.ai_progress_bar.setRange(0, 100)
        self.ai_progress_bar.setValue(0)

        self.ai_log_box = QPlainTextEdit()
        self.ai_log_box.setReadOnly(True)
        self.ai_log_box.setMaximumHeight(120)
        self.ai_log_box.setPlaceholderText("AI logs...")

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self.ai_key_input, 1)
        key_row.addWidget(self.ai_remember_check)

        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        import_row.addWidget(self.ai_choose_audio_button)
        import_row.addWidget(self.ai_choose_video_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addLayout(key_row)
        layout.addWidget(self.ai_model_label)
        layout.addWidget(self.ai_note_label)
        layout.addWidget(self.ai_drop_zone)
        layout.addLayout(import_row)
        layout.addWidget(self.ai_file_label)
        layout.addWidget(self.ai_estimate_label)
        layout.addWidget(self.ai_start_button)
        layout.addWidget(self.ai_progress_bar)
        layout.addWidget(self.ai_log_box)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def choose_ai_audio(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Audio for AI Captions",
            str(Path.home() / "Documents"),
            "Audio files (*.mp3 *.wav *.m4a *.aac *.flac *.aiff *.aif);;All files (*)",
        )
        if file_name:
            self.set_ai_selected_input(Path(file_name))

    def choose_ai_video(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Video for AI Captions",
            str(Path.home() / "Movies"),
            "Video files (*.mp4 *.mov *.m4v *.mkv *.avi *.webm);;All files (*)",
        )
        if file_name:
            self.set_ai_selected_input(Path(file_name))

    def set_ai_selected_input(self, path: Path) -> None:
        path = path.expanduser()
        if path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please choose MP3, WAV, M4A, AAC, FLAC, AIFF, MP4, MOV, MKV, AVI, or WEBM.",
            )
            return
        self.selected_ai_input = path
        self.ai_file_label.setText(str(path))
        self.ai_drop_zone.setText(f"Selected:\n{path.name}")
        self.ai_progress_bar.setValue(0)
        self.ai_start_button.setEnabled(True)
        self.ai_log_box.clear()
        self.append_ai_log(f"Selected: {path.name}")

        try:
            duration = get_audio_duration(path)
            self.ai_estimate_label.setText(
                f"Duration: {duration:.1f}s | {estimate_gemini_cost(duration)}"
            )
        except Exception:
            self.ai_estimate_label.setText(
                "Cost estimate appears after FFmpeg prepares the audio."
            )

    def start_ai_generation(self) -> None:
        if self.selected_ai_input is None:
            QMessageBox.warning(self, "No file selected", "Please import or drop an audio/video file first.")
            return

        api_key = self.ai_key_input.text().strip()
        if not api_key:
            self.append_ai_log("Paste your Gemini API key first.")
            return

        if self.ai_remember_check.isChecked():
            self.settings.setValue("gemini_api_key", api_key)
        else:
            self.settings.remove("gemini_api_key")

        self.set_ai_controls_enabled(False)
        self.ai_progress_bar.setValue(0)
        self.append_ai_log("Starting AI caption generation...")

        self.ai_thread = QThread()
        self.ai_worker = AiCaptionWorker(self.selected_ai_input, api_key, DEFAULT_GEMINI_MODEL)
        self.ai_worker.moveToThread(self.ai_thread)

        self.ai_thread.started.connect(self.ai_worker.run)
        self.ai_worker.log_message.connect(self.append_ai_log)
        self.ai_worker.progress_changed.connect(self.ai_progress_bar.setValue)
        self.ai_worker.finished.connect(self.on_ai_finished)
        self.ai_worker.failed.connect(self.on_ai_failed)
        self.ai_worker.finished.connect(self.ai_thread.quit)
        self.ai_worker.failed.connect(self.ai_thread.quit)
        self.ai_thread.finished.connect(self.ai_worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        self.ai_thread.finished.connect(self.reset_ai_worker_refs)

        self.ai_thread.start()

    def set_ai_controls_enabled(self, enabled: bool) -> None:
        self.ai_choose_audio_button.setEnabled(enabled)
        self.ai_choose_video_button.setEnabled(enabled)
        self.ai_drop_zone.setEnabled(enabled)
        self.ai_key_input.setEnabled(enabled)
        self.ai_remember_check.setEnabled(enabled)
        self.ai_start_button.setEnabled(enabled and self.selected_ai_input is not None)

    def on_ai_finished(
        self,
        subtitle_path: str,
        subtitle_count: int,
        duration_seconds: float,
        warnings: list[str],
    ) -> None:
        self.ai_progress_bar.setValue(100)
        self.append_ai_log(f"Done: {subtitle_path}")
        self.append_ai_log(f"Subtitle blocks written: {subtitle_count}")
        self.ai_estimate_label.setText(
            f"Saved AI SRT to Downloads: {subtitle_path}\nDuration: {duration_seconds:.1f}s"
        )
        for warning in warnings:
            self.append_ai_log(f"Warning: {warning}")
        self.set_ai_controls_enabled(True)

    def on_ai_failed(self, message: str) -> None:
        self.append_ai_log("Error:")
        self.append_ai_log(message)
        self.set_ai_controls_enabled(True)
        if "FFmpeg" in message or "FFprobe" in message:
            self.ai_estimate_label.setText(FFMPEG_INSTALL_MESSAGE)
            self.append_ai_log("Install FFmpeg, then reopen SinhalaSTT and try again.")

    def reset_ai_worker_refs(self) -> None:
        self.ai_thread = None
        self.ai_worker = None

    def append_ai_log(self, message: str) -> None:
        self.ai_log_box.appendPlainText(message)
        scrollbar = self.ai_log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(resource_path("assets/icon-source.png"))))
    chevron_path = str(resource_path("assets/chevron-down.svg")).replace("\\", "/")
    app.setStyleSheet(APP_STYLE.replace("__CHEVRON_PATH__", chevron_path))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
