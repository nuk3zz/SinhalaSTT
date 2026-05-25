#!/usr/bin/env python3
"""
Compact desktop UI for placeholder SRT generation and Sinhala line filling.
"""

from __future__ import annotations

import sys
import traceback
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSignalBlocker, QThread, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
from font_converter import unicode_to_fm
from transcriber_core import (
    DEFAULT_PLACEHOLDER_MODE,
    DESKTOP_CACHE_AUDIO_DIR,
    DOWNLOADS_OUTPUT_DIR,
    PlaceholderError,
    fill_placeholder_srt,
    find_tool,
    generate_placeholder_srt,
    get_audio_duration,
    parse_srt_blocks,
    pasted_text_to_lines,
)


MODE_LABELS = {
    "sentence": "Sentences",
    "1": "1 word",
    "2": "2 words",
    "3": "3 words",
}

APP_NAME = "SinhalaSTT"
APP_VERSION = "0.2.1 beta"
APP_TAGLINE = "Create editable Sinhala subtitle timing drafts from audio or video."
GITHUB_URL = "https://github.com/nuk3zz/SinhalaSTT"
FFMPEG_INSTALL_MESSAGE = (
    "FFmpeg setup needed: SinhalaSTT can open, but SRT creation needs FFmpeg. "
    "Install it once with Homebrew: brew install ffmpeg"
)

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".aiff", ".aif"}
SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
SUPPORTED_INPUT_SUFFIXES = SUPPORTED_AUDIO_SUFFIXES | SUPPORTED_VIDEO_SUFFIXES


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
QComboBox QAbstractItemView {
    color: #171b22;
    background: #ffffff;
    selection-background-color: #e8f0fb;
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
QPlainTextEdit#LineNumbers {
    color: #8b95a3;
    background: #f4f6f9;
    border: 1px solid #d8dee8;
    max-width: 54px;
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

        beta = QLabel("BETA")
        beta.setObjectName("BetaPill")
        beta.setMaximumWidth(56)
        beta.setAlignment(Qt.AlignCenter)

        tagline = QLabel("Turning Sinhala speech into accurate subtitles.")
        tagline.setObjectName("HeroTagline")

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(12)
        title_row.addWidget(title)
        title_row.addWidget(beta)
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


class PlaceholderWorker(QObject):
    log_message = Signal(str)
    progress_changed = Signal(int)
    finished = Signal(str, int, int, list)
    failed = Signal(str)

    def __init__(self, input_path: Path, mode: str) -> None:
        super().__init__()
        self.input_path = input_path
        self.mode = mode

    def run(self) -> None:
        try:
            result = generate_placeholder_srt(
                self.input_path,
                mode=self.mode,
                audio_dir=DESKTOP_CACHE_AUDIO_DIR,
                output_dir=DOWNLOADS_OUTPUT_DIR,
                mp3_only=False,
                log=self.log_message.emit,
                progress=self.progress_changed.emit,
            )
            self.finished.emit(
                str(result.subtitle_path),
                result.subtitle_count,
                result.speech_region_count,
                result.warnings,
            )
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
                audio_dir=DESKTOP_CACHE_AUDIO_DIR,
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
        self.selected_input: Path | None = None
        self.selected_ai_input: Path | None = None
        self.selected_srt: Path | None = None
        self.current_srt_block_count = 0
        self.settings = QSettings(APP_NAME, APP_NAME)
        self.thread: QThread | None = None
        self.worker: PlaceholderWorker | None = None
        self.ai_thread: QThread | None = None
        self.ai_worker: AiCaptionWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(620, 600)
        self.resize(760, 680)

        self.banner = HeroBanner()

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        version = QLabel(APP_VERSION)
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
        self.tabs.addTab(self.build_create_tab(), "Create")
        self.tabs.addTab(self.build_fill_tab(), "Fill")
        self.tabs.addTab(self.build_ai_tab(), "AI Captions")

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

        self.output_label.setText(FFMPEG_INSTALL_MESSAGE)
        self.append_log("First-time setup note:")
        self.append_log(FFMPEG_INSTALL_MESSAGE)
        self.append_log("The app will not install anything automatically.")

    def build_create_tab(self) -> QWidget:
        self.file_label = QLabel("No file selected")
        self.file_label.setObjectName("PathLabel")
        self.file_label.setWordWrap(True)

        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self.set_selected_input)
        self.drop_zone.rejected.connect(self.append_log)

        self.choose_audio_button = QPushButton("Import Audio")
        self.choose_audio_button.clicked.connect(self.choose_audio)

        self.choose_video_button = QPushButton("Import MP4/Video")
        self.choose_video_button.clicked.connect(self.choose_video)

        self.mode_box = QComboBox()
        for mode, label in MODE_LABELS.items():
            self.mode_box.addItem(label, mode)
        self.mode_box.setCurrentIndex(list(MODE_LABELS).index(DEFAULT_PLACEHOLDER_MODE))

        self.start_button = QPushButton("Create SRT")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_generation)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(110)
        self.log_box.setPlaceholderText("Logs...")

        self.output_label = QLabel(f"Saves to Downloads. WAV cache: {DESKTOP_CACHE_AUDIO_DIR}")
        self.output_label.setObjectName("PathLabel")
        self.output_label.setWordWrap(True)

        import_row = QHBoxLayout()
        import_row.setSpacing(8)
        import_row.addWidget(self.choose_audio_button)
        import_row.addWidget(self.choose_video_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(QLabel("Size:"))
        action_row.addWidget(self.mode_box, 1)
        action_row.addWidget(self.start_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.drop_zone)
        layout.addLayout(import_row)
        layout.addWidget(self.file_label)
        layout.addLayout(action_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_box)
        layout.addWidget(self.output_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

    def build_fill_tab(self) -> QWidget:
        self.srt_label = QLabel("No SRT selected")
        self.srt_label.setObjectName("PathLabel")
        self.srt_label.setWordWrap(True)

        self.choose_srt_button = QPushButton("Choose SRT")
        self.choose_srt_button.clicked.connect(self.choose_srt)

        self.fill_button = QPushButton("Create Unicode SRT")
        self.fill_button.setEnabled(False)
        self.fill_button.clicked.connect(self.create_unicode_filled_srt)

        self.convert_fm_button = QPushButton("Convert to FM/DL")
        self.convert_fm_button.clicked.connect(self.convert_fill_text_to_fm)

        self.copy_fm_button = QPushButton("Copy FM/DL Text")
        self.copy_fm_button.setEnabled(False)
        self.copy_fm_button.clicked.connect(self.copy_fm_text)

        self.fm_fill_button = QPushButton("Create FM/DL SRT")
        self.fm_fill_button.setEnabled(False)
        self.fm_fill_button.clicked.connect(self.create_fm_filled_srt)

        self.fill_mode_box = QComboBox()
        self.fill_mode_box.addItem("Keep pasted lines", "keep")
        for mode, label in MODE_LABELS.items():
            self.fill_mode_box.addItem(f"Split paragraph: {label}", mode)
        self.fill_mode_box.currentIndexChanged.connect(self.update_line_numbers)

        self.split_preview_button = QPushButton("Split Paragraph")
        self.split_preview_button.clicked.connect(self.apply_smart_split_to_paste)

        self.paste_box = QPlainTextEdit()
        self.paste_box.setPlaceholderText(
            "Paste Sinhala text here.\n"
            "Line-by-line text stays line-by-line. A single paragraph can be split automatically."
        )
        self.paste_box.textChanged.connect(self.update_fill_button)
        self.paste_box.textChanged.connect(self.update_line_numbers)
        self.paste_box.textChanged.connect(self.clear_fm_output)
        self.paste_box.verticalScrollBar().valueChanged.connect(self.sync_line_number_scroll)

        self.fm_box = QPlainTextEdit()
        self.fm_box.setReadOnly(True)
        self.fm_box.setPlaceholderText(
            "FM/DL converted text appears here.\n"
            "Copy it, or create an FM/DL SRT for legacy Sinhala fonts."
        )
        self.fm_box.verticalScrollBar().valueChanged.connect(self.sync_fm_scroll_to_unicode)

        self.line_numbers = QPlainTextEdit()
        self.line_numbers.setObjectName("LineNumbers")
        self.line_numbers.setReadOnly(True)
        self.line_numbers.setFocusPolicy(Qt.NoFocus)
        self.line_numbers.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.line_numbers.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.line_numbers.setPlainText("001")

        self.fill_status_label = QLabel(f"Filled SRT saves to Downloads: {DOWNLOADS_OUTPUT_DIR}")
        self.fill_status_label.setObjectName("PathLabel")
        self.fill_status_label.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addWidget(self.choose_srt_button)
        button_row.addWidget(self.fill_button)
        button_row.addWidget(self.fm_fill_button)
        button_row.addStretch(1)

        split_row = QHBoxLayout()
        split_row.setSpacing(8)
        split_row.addWidget(QLabel("Paste:"))
        split_row.addWidget(self.fill_mode_box, 1)
        split_row.addWidget(self.split_preview_button)
        split_row.addWidget(self.convert_fm_button)
        split_row.addWidget(self.copy_fm_button)

        unicode_label = QLabel("Unicode Sinhala")
        unicode_label.setObjectName("SmallNote")
        fm_label = QLabel("FM/DL Legacy Text")
        fm_label.setObjectName("SmallNote")

        label_row = QHBoxLayout()
        label_row.setSpacing(8)
        label_row.addSpacing(60)
        label_row.addWidget(unicode_label)
        label_row.addWidget(fm_label)

        paste_row = QHBoxLayout()
        paste_row.setSpacing(6)
        paste_row.addWidget(self.line_numbers)
        paste_row.addWidget(self.paste_box, 1)
        paste_row.addWidget(self.fm_box, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.srt_label)
        layout.addLayout(button_row)
        layout.addLayout(split_row)
        layout.addLayout(label_row)
        layout.addLayout(paste_row)
        layout.addWidget(self.fill_status_label)

        tab = QWidget()
        tab.setLayout(layout)
        return tab

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
            "Offline tools stay local. AI Captions sends extracted audio to Google Gemini using your API key."
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

    def choose_audio(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Audio",
            str(Path.home() / "Documents"),
            "Audio files (*.mp3 *.wav *.m4a *.aac *.flac *.aiff *.aif);;All files (*)",
        )

        if file_name:
            self.set_selected_input(Path(file_name))

    def choose_video(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Import MP4 or Video",
            str(Path.home() / "Movies"),
            "Video files (*.mp4 *.mov *.m4v *.mkv *.avi *.webm);;All files (*)",
        )

        if file_name:
            self.set_selected_input(Path(file_name))

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

    def set_selected_input(self, path: Path) -> None:
        path = path.expanduser()
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_INPUT_SUFFIXES:
            QMessageBox.warning(
                self,
                "Unsupported file",
                "Please choose MP3, WAV, M4A, AAC, FLAC, AIFF, MP4, MOV, MKV, AVI, or WEBM.",
            )
            return

        self.selected_input = path
        self.file_label.setText(str(path))
        self.drop_zone.setText(f"Selected:\n{path.name}")
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(True)
        self.log_box.clear()
        self.append_log(f"Selected: {path.name}")

    def set_ai_selected_input(self, path: Path) -> None:
        path = path.expanduser()
        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_INPUT_SUFFIXES:
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

    def choose_srt(self) -> None:
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Choose Placeholder SRT",
            str(DOWNLOADS_OUTPUT_DIR),
            "SRT subtitles (*.srt)",
        )

        if not file_name:
            return

        path = Path(file_name)
        if path.suffix.lower() != ".srt":
            QMessageBox.warning(self, "Choose SRT", "Please choose an .srt file.")
            return

        self.selected_srt = path
        self.srt_label.setText(str(path))
        self.load_srt_block_count(path)
        self.update_fill_button()

    def update_fill_button(self) -> None:
        has_text = bool(self.paste_box.toPlainText())
        has_srt = self.selected_srt is not None
        self.fill_button.setEnabled(has_srt and has_text)
        self.fm_fill_button.setEnabled(has_srt and has_text)

    def load_srt_block_count(self, path: Path) -> None:
        try:
            self.current_srt_block_count = len(parse_srt_blocks(path))
        except PlaceholderError as error:
            self.current_srt_block_count = 0
            self.append_fill_status(f"Could not read SRT blocks: {error}")
            return

        self.srt_label.setText(f"{path}\nSubtitle blocks: {self.current_srt_block_count}")
        self.update_line_numbers()

    def update_line_numbers(self) -> None:
        pasted_line_count = max(1, len(self.preview_pasted_lines()))
        count = max(self.current_srt_block_count, pasted_line_count)
        numbers = "\n".join(f"{number:03d}" for number in range(1, count + 1))

        with QSignalBlocker(self.line_numbers):
            self.line_numbers.setPlainText(numbers)
        self.sync_line_number_scroll(self.paste_box.verticalScrollBar().value())

    def sync_line_number_scroll(self, value: int) -> None:
        self.line_numbers.verticalScrollBar().setValue(value)
        self.fm_box.verticalScrollBar().setValue(value)

    def sync_fm_scroll_to_unicode(self, value: int) -> None:
        self.paste_box.verticalScrollBar().setValue(value)
        self.line_numbers.verticalScrollBar().setValue(value)

    def append_fill_status(self, message: str) -> None:
        self.fill_status_label.setText(message)

    def preview_pasted_lines(self) -> list[str]:
        mode = self.fill_mode_box.currentData() if hasattr(self, "fill_mode_box") else "keep"
        return pasted_text_to_lines(self.paste_box.toPlainText(), mode)

    def apply_smart_split_to_paste(self) -> None:
        lines = self.preview_pasted_lines()
        if not lines:
            self.append_fill_status("Paste Sinhala text first, then split the paragraph.")
            return

        with QSignalBlocker(self.paste_box):
            self.paste_box.setPlainText("\n".join(lines))
        self.update_fill_button()
        self.update_line_numbers()
        self.append_fill_status(f"Split paste into {len(lines)} lines.")

    def clear_fm_output(self) -> None:
        if not hasattr(self, "fm_box"):
            return
        with QSignalBlocker(self.fm_box):
            self.fm_box.clear()
        self.copy_fm_button.setEnabled(False)

    def convert_fill_text_to_fm(self) -> str:
        lines = self.preview_pasted_lines()
        if not lines:
            self.append_fill_status("Paste Sinhala Unicode text first.")
            return ""

        source_text = "\n".join(lines)
        result = unicode_to_fm(source_text)
        self.fm_box.setPlainText(result.text)
        self.copy_fm_button.setEnabled(bool(result.text))

        status = f"Converted {len(lines)} lines to FM/DL legacy text."
        if result.warnings:
            status += "\n" + "\n".join(f"Note: {warning}" for warning in result.warnings)
        self.append_fill_status(status)
        return result.text

    def copy_fm_text(self) -> None:
        text = self.fm_box.toPlainText()
        if not text:
            text = self.convert_fill_text_to_fm()
        if not text:
            return

        QApplication.clipboard().setText(text)
        self.append_fill_status("FM/DL text copied to clipboard.")

    def start_generation(self) -> None:
        if self.selected_input is None:
            QMessageBox.warning(self, "No file selected", "Please import or drop an audio/video file first.")
            return

        mode = self.mode_box.currentData()
        self.choose_audio_button.setEnabled(False)
        self.choose_video_button.setEnabled(False)
        self.drop_zone.setEnabled(False)
        self.mode_box.setEnabled(False)
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.append_log("Starting placeholder generation...")

        self.thread = QThread()
        self.worker = PlaceholderWorker(self.selected_input, mode)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log_message.connect(self.append_log)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.reset_worker_refs)

        self.thread.start()

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

        self.ai_choose_audio_button.setEnabled(False)
        self.ai_choose_video_button.setEnabled(False)
        self.ai_drop_zone.setEnabled(False)
        self.ai_key_input.setEnabled(False)
        self.ai_remember_check.setEnabled(False)
        self.ai_start_button.setEnabled(False)
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

    def create_unicode_filled_srt(self) -> None:
        if self.selected_srt is None:
            QMessageBox.warning(self, "No SRT selected", "Please choose a placeholder SRT first.")
            return

        try:
            result = fill_placeholder_srt(
                self.selected_srt,
                self.paste_box.toPlainText(),
                output_dir=DOWNLOADS_OUTPUT_DIR,
                paste_mode=self.fill_mode_box.currentData(),
            )
        except PlaceholderError as error:
            QMessageBox.critical(self, "Could not fill SRT", str(error))
            return

        status_lines = [
            f"Saved: {result.output_path}",
            (
                f"Blocks: {result.block_count} | Replaced: {result.replaced_count} | "
                f"Skipped blank lines: {result.skipped_count}"
            ),
        ]
        status_lines.extend(f"Note: {warning}" for warning in result.warnings)
        self.fill_status_label.setText("\n".join(status_lines))

    def create_fm_filled_srt(self) -> None:
        if self.selected_srt is None:
            QMessageBox.warning(self, "No SRT selected", "Please choose a placeholder SRT first.")
            return

        converted_text = self.fm_box.toPlainText()
        if not converted_text:
            converted_text = self.convert_fill_text_to_fm()
        if not converted_text:
            return

        try:
            result = fill_placeholder_srt(
                self.selected_srt,
                converted_text,
                output_dir=DOWNLOADS_OUTPUT_DIR,
                paste_mode="keep",
                output_suffix="_filled_fm",
            )
        except PlaceholderError as error:
            QMessageBox.critical(self, "Could not fill SRT", str(error))
            return

        status_lines = [
            f"Saved FM/DL SRT: {result.output_path}",
            (
                f"Blocks: {result.block_count} | Replaced: {result.replaced_count} | "
                f"Skipped blank lines: {result.skipped_count}"
            ),
        ]
        status_lines.extend(f"Note: {warning}" for warning in result.warnings)
        self.fill_status_label.setText("\n".join(status_lines))

    def append_log(self, message: str) -> None:
        self.log_box.appendPlainText(message)
        scrollbar = self.log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def append_ai_log(self, message: str) -> None:
        self.ai_log_box.appendPlainText(message)
        scrollbar = self.ai_log_box.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_finished(
        self,
        subtitle_path: str,
        subtitle_count: int,
        speech_region_count: int,
        warnings: list[str],
    ) -> None:
        self.progress_bar.setValue(100)
        self.append_log(f"Done: {subtitle_path}")
        self.append_log(f"Speech regions detected: {speech_region_count}")
        self.append_log(f"Subtitle blocks written: {subtitle_count}")
        self.output_label.setText(f"Saved SRT: {subtitle_path}")
        self.selected_srt = Path(subtitle_path)
        self.load_srt_block_count(self.selected_srt)
        self.tabs.setCurrentIndex(1)
        self.fill_status_label.setText(
            f"Loaded generated SRT: {subtitle_path}\nPaste Sinhala lines, then create filled SRT."
        )

        self.choose_audio_button.setEnabled(True)
        self.choose_video_button.setEnabled(True)
        self.drop_zone.setEnabled(True)
        self.mode_box.setEnabled(True)
        self.start_button.setEnabled(True)

        for warning in warnings:
            self.append_log(f"Warning: {warning}")

    def on_failed(self, message: str) -> None:
        self.append_log("Error:")
        self.append_log(message)
        self.choose_audio_button.setEnabled(True)
        self.choose_video_button.setEnabled(True)
        self.drop_zone.setEnabled(True)
        self.mode_box.setEnabled(True)
        self.start_button.setEnabled(self.selected_input is not None)
        if "FFmpeg is not installed" in message or "FFprobe is not installed" in message:
            self.output_label.setText(FFMPEG_INSTALL_MESSAGE)
            self.append_log("Install FFmpeg, then reopen SinhalaSTT and try again.")
            return
        QMessageBox.critical(self, "Placeholder generation failed", message)

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
            f"Saved AI SRT: {subtitle_path}\nDuration: {duration_seconds:.1f}s"
        )
        self.selected_srt = Path(subtitle_path)
        self.load_srt_block_count(self.selected_srt)
        self.tabs.setCurrentIndex(1)
        self.fill_status_label.setText(
            f"Loaded AI SRT: {subtitle_path}\nCorrect Sinhala lines if needed, then create filled SRT."
        )

        for warning in warnings:
            self.append_ai_log(f"Warning: {warning}")

        self.reset_ai_controls()

    def on_ai_failed(self, message: str) -> None:
        self.append_ai_log("Error:")
        self.append_ai_log(message)
        self.reset_ai_controls()
        if "FFmpeg is not installed" in message or "FFprobe is not installed" in message:
            self.ai_estimate_label.setText(FFMPEG_INSTALL_MESSAGE)
            self.append_ai_log("Install FFmpeg, then reopen SinhalaSTT and try again.")

    def reset_ai_controls(self) -> None:
        self.ai_choose_audio_button.setEnabled(True)
        self.ai_choose_video_button.setEnabled(True)
        self.ai_drop_zone.setEnabled(True)
        self.ai_key_input.setEnabled(True)
        self.ai_remember_check.setEnabled(True)
        self.ai_start_button.setEnabled(self.selected_ai_input is not None)

    def reset_worker_refs(self) -> None:
        self.thread = None
        self.worker = None

    def reset_ai_worker_refs(self) -> None:
        self.ai_thread = None
        self.ai_worker = None


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
