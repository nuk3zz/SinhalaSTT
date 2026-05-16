#!/usr/bin/env python3
"""
Compact desktop UI for placeholder SRT generation and Sinhala line filling.
"""

from __future__ import annotations

import sys
import traceback
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QSignalBlocker, QThread, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from transcriber_core import (
    DEFAULT_PLACEHOLDER_MODE,
    DESKTOP_CACHE_AUDIO_DIR,
    DOWNLOADS_OUTPUT_DIR,
    PlaceholderError,
    fill_placeholder_srt,
    find_tool,
    generate_placeholder_srt,
    parse_srt_blocks,
)


MODE_LABELS = {
    "sentence": "Sentences",
    "1": "1 word",
    "2": "2 words",
    "3": "3 words",
}

APP_NAME = "SinhalaSTT"
APP_VERSION = "0.1.0 beta"
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
    background: #111111;
    color: #e8e8e8;
    font-size: 12px;
}
QLabel#Title {
    color: #f2f2f2;
    font-size: 18px;
    font-weight: 750;
}
QLabel#Version {
    color: #9a9a9a;
    font-size: 11px;
}
QLabel#Subtitle {
    color: #9a9a9a;
}
QLabel#Banner {
    background: #0b0b0b;
    border: 1px solid #242424;
    border-radius: 7px;
}
QLabel#PathLabel {
    color: #cfcfcf;
    background: #171717;
    border: 1px solid #2b2b2b;
    border-radius: 5px;
    padding: 5px;
}
QLabel#DropZone {
    color: #d8d8d8;
    background: #151515;
    border: 1px dashed #555555;
    border-radius: 7px;
    padding: 10px;
    font-weight: 650;
}
QLabel#DropZone[dragging="true"] {
    background: #1d2426;
    border: 1px solid #7aa7b2;
}
QPushButton {
    color: #e8e8e8;
    background: #202020;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 7px 10px;
    font-weight: 650;
}
QPushButton:hover {
    background: #2a2a2a;
    border: 1px solid #5a5a5a;
}
QPushButton:disabled {
    color: #666666;
    border: 1px solid #2a2a2a;
    background: #181818;
}
QComboBox {
    color: #e8e8e8;
    background: #171717;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 6px;
}
QComboBox QAbstractItemView {
    color: #e8e8e8;
    background: #171717;
    selection-background-color: #2f3f43;
}
QPlainTextEdit {
    color: #efefef;
    background: #171717;
    border: 1px solid #333333;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #35535a;
}
QPlainTextEdit#LineNumbers {
    color: #777777;
    border: 1px solid #2b2b2b;
    max-width: 54px;
}
QProgressBar {
    color: #cfcfcf;
    background: #171717;
    border: 1px solid #2b2b2b;
    border-radius: 5px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background: #7aa7b2;
    border-radius: 4px;
}
QTabWidget::pane {
    border: 1px solid #2b2b2b;
    border-radius: 7px;
    top: -1px;
}
QTabBar::tab {
    color: #9a9a9a;
    background: #151515;
    border: 1px solid #2b2b2b;
    padding: 6px 10px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabBar::tab:selected {
    color: #f2f2f2;
    border-color: #4a4a4a;
    background: #202020;
}
"""


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path


class BannerLabel(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Banner")
        self.setMinimumHeight(104)
        self.setMaximumHeight(130)
        self.setAlignment(Qt.AlignCenter)
        self._pixmap = QPixmap(str(resource_path("assets/banner.png")))
        self.update_pixmap()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update_pixmap()

    def update_pixmap(self) -> None:
        if self._pixmap.isNull():
            self.setText(APP_NAME)
            return

        self.setPixmap(
            self._pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.selected_input: Path | None = None
        self.selected_srt: Path | None = None
        self.current_srt_block_count = 0
        self.thread: QThread | None = None
        self.worker: PlaceholderWorker | None = None

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(540, 520)
        self.resize(620, 560)

        self.banner = BannerLabel()

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

        self.fill_button = QPushButton("Create Filled SRT")
        self.fill_button.setEnabled(False)
        self.fill_button.clicked.connect(self.create_filled_srt)

        self.paste_box = QPlainTextEdit()
        self.paste_box.setPlaceholderText(
            "Paste Sinhala text here, one line per subtitle block.\n"
            "Blank lines skip matching placeholders."
        )
        self.paste_box.textChanged.connect(self.update_fill_button)
        self.paste_box.textChanged.connect(self.update_line_numbers)
        self.paste_box.verticalScrollBar().valueChanged.connect(self.sync_line_number_scroll)

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
        button_row.addStretch(1)

        paste_row = QHBoxLayout()
        paste_row.setSpacing(6)
        paste_row.addWidget(self.line_numbers)
        paste_row.addWidget(self.paste_box)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.srt_label)
        layout.addLayout(button_row)
        layout.addLayout(paste_row)
        layout.addWidget(self.fill_status_label)

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
        self.fill_button.setEnabled(
            self.selected_srt is not None and bool(self.paste_box.toPlainText())
        )

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
        pasted_line_count = max(1, len(self.paste_box.toPlainText().splitlines()))
        count = max(self.current_srt_block_count, pasted_line_count)
        numbers = "\n".join(f"{number:03d}" for number in range(1, count + 1))

        with QSignalBlocker(self.line_numbers):
            self.line_numbers.setPlainText(numbers)
        self.sync_line_number_scroll(self.paste_box.verticalScrollBar().value())

    def sync_line_number_scroll(self, value: int) -> None:
        self.line_numbers.verticalScrollBar().setValue(value)

    def append_fill_status(self, message: str) -> None:
        self.fill_status_label.setText(message)

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

    def create_filled_srt(self) -> None:
        if self.selected_srt is None:
            QMessageBox.warning(self, "No SRT selected", "Please choose a placeholder SRT first.")
            return

        try:
            result = fill_placeholder_srt(
                self.selected_srt,
                self.paste_box.toPlainText(),
                output_dir=DOWNLOADS_OUTPUT_DIR,
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

    def append_log(self, message: str) -> None:
        self.log_box.appendPlainText(message)
        scrollbar = self.log_box.verticalScrollBar()
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

    def reset_worker_refs(self) -> None:
        self.thread = None
        self.worker = None


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(resource_path("assets/icon-source.png"))))
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
