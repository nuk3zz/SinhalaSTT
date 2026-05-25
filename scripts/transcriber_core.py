from __future__ import annotations

import math
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_AUDIO_DIR = PROJECT_ROOT / "output" / "audio"
PROJECT_SUBTITLES_DIR = PROJECT_ROOT / "subtitles"
DOCUMENTS_TRANSCRIBE_DIR = Path.home() / "Documents" / "Transcribe"
DOCUMENTS_AUDIO_DIR = DOCUMENTS_TRANSCRIBE_DIR / "audio"
DOCUMENTS_OUTPUT_DIR = DOCUMENTS_TRANSCRIBE_DIR / "output"
DESKTOP_CACHE_AUDIO_DIR = Path.home() / "Desktop" / "Cache" / "temporary wav"
DOWNLOADS_OUTPUT_DIR = Path.home() / "Downloads"

DEFAULT_PLACEHOLDER_MODE = "sentence"
SILENCE_THRESHOLD = "-25dB"
SENTENCE_SILENCE_DURATION = 0.45
WORD_SILENCE_DURATION = 0.20
MIN_REGION_MEAN_VOLUME_DB = -32.0
MIN_REGION_PEAK_VOLUME_DB = -24.0
ESTIMATED_WORD_DURATION = 0.42
MIN_SUBTITLE_DURATION = 0.25
MAX_SENTENCE_DURATION = 7.0
SUBTITLE_GAP = 0.03

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class SpeechRegion:
    start: float
    end: float


@dataclass(frozen=True)
class RegionVolume:
    mean_volume: float | None
    max_volume: float | None


@dataclass(frozen=True)
class SubtitleBlock:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class PlaceholderResult:
    audio_path: Path
    subtitle_path: Path
    subtitle_count: int
    speech_region_count: int
    mode: str
    warnings: list[str]


@dataclass(frozen=True)
class FillResult:
    input_path: Path
    output_path: Path
    block_count: int
    pasted_line_count: int
    replaced_count: int
    skipped_count: int
    extra_line_count: int
    warnings: list[str]


class PlaceholderError(Exception):
    """A user-friendly placeholder generation error."""


def default_log(message: str) -> None:
    print(message)


def default_progress(_value: int) -> None:
    return


def check_ffmpeg() -> None:
    if ffmpeg_path() is None or ffprobe_path() is None:
        raise PlaceholderError(
            "FFmpeg is not installed or not available. Install it with: brew install ffmpeg"
        )


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    for path in (
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
        Path("/usr/bin") / name,
    ):
        if path.exists():
            return str(path)

    return None


def ffmpeg_path() -> str:
    path = find_tool("ffmpeg")
    if path is None:
        raise PlaceholderError(
            "FFmpeg is not installed or not available. Install it with: brew install ffmpeg"
        )
    return path


def ffprobe_path() -> str:
    path = find_tool("ffprobe")
    if path is None:
        raise PlaceholderError(
            "FFprobe is not installed or not available. Install FFmpeg with: brew install ffmpeg"
        )
    return path


def make_safe_output_name(input_file: Path) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", input_file.stem).strip("_")
    return safe_name or "placeholders"


def resolve_input_file(input_file: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(input_file).expanduser()
    if not path.is_absolute():
        path = (base_dir or Path.cwd()) / path
    return path.resolve()


def ensure_input_file(input_file: Path, mp3_only: bool = False) -> None:
    if not input_file.exists():
        raise PlaceholderError(f"Input file not found: {input_file}")

    if not input_file.is_file():
        raise PlaceholderError(f"This is not a file: {input_file}")

    if mp3_only and input_file.suffix.lower() != ".mp3":
        raise PlaceholderError("Please choose an MP3 file. This UI accepts .mp3 only.")


def run_command(command: list[str], error_message: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise PlaceholderError(error_message + "\n\n" + result.stderr.strip())
    return result


def extract_audio(
    input_file: Path,
    output_name: str,
    audio_dir: Path,
    log: LogCallback = default_log,
) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{output_name}.wav"

    command = [
        ffmpeg_path(),
        "-y",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]

    log("Preparing audio with FFmpeg...")
    run_command(command, "FFmpeg could not read or convert the input file.")
    return audio_path


def get_audio_duration(audio_path: Path) -> float:
    command = [
        ffprobe_path(),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = run_command(command, "Could not read the audio duration.")

    try:
        return float(result.stdout.strip())
    except ValueError as error:
        raise PlaceholderError("Could not understand the audio duration.") from error


def silence_duration_for_mode(mode: str) -> float:
    if mode in {"1", "2", "3"}:
        return WORD_SILENCE_DURATION
    return SENTENCE_SILENCE_DURATION


def detect_silences(
    audio_path: Path,
    min_silence_duration: float,
    log: LogCallback = default_log,
) -> list[tuple[float, float | None]]:
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={SILENCE_THRESHOLD}:d={min_silence_duration}",
        "-f",
        "null",
        "-",
    ]

    log(f"Detecting speech and silence ({min_silence_duration:.2f}s pauses)...")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise PlaceholderError("Could not analyze speech/silence timing.\n\n" + result.stderr.strip())

    silences: list[tuple[float, float | None]] = []
    open_silence_start: float | None = None

    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            open_silence_start = float(start_match.group(1))
            continue

        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match and open_silence_start is not None:
            silences.append((open_silence_start, float(end_match.group(1))))
            open_silence_start = None

    if open_silence_start is not None:
        silences.append((open_silence_start, None))

    return silences


def build_speech_regions(duration: float, silences: list[tuple[float, float | None]]) -> list[SpeechRegion]:
    regions: list[SpeechRegion] = []
    current_start = 0.0

    for silence_start, silence_end in silences:
        speech_end = max(0.0, min(silence_start, duration))
        if speech_end - current_start >= MIN_SUBTITLE_DURATION:
            regions.append(SpeechRegion(current_start, speech_end))

        if silence_end is None:
            current_start = duration
        else:
            current_start = max(current_start, min(silence_end, duration))

    if duration - current_start >= MIN_SUBTITLE_DURATION:
        regions.append(SpeechRegion(current_start, duration))

    return regions


def measure_region_volume(audio_path: Path, region: SpeechRegion) -> RegionVolume:
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-ss",
        f"{region.start:.3f}",
        "-t",
        f"{region.end - region.start:.3f}",
        "-i",
        str(audio_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return RegionVolume(mean_volume=None, max_volume=None)

    mean_match = re.search(r"mean_volume:\s*(-?[0-9.]+)\s*dB", result.stderr)
    max_match = re.search(r"max_volume:\s*(-?[0-9.]+)\s*dB", result.stderr)

    return RegionVolume(
        mean_volume=float(mean_match.group(1)) if mean_match else None,
        max_volume=float(max_match.group(1)) if max_match else None,
    )


def filter_quiet_regions(
    audio_path: Path,
    regions: list[SpeechRegion],
    log: LogCallback = default_log,
) -> list[SpeechRegion]:
    kept_regions = []

    for region in regions:
        volume = measure_region_volume(audio_path, region)
        if volume.mean_volume is None or volume.max_volume is None:
            kept_regions.append(region)
            continue

        if (
            volume.mean_volume >= MIN_REGION_MEAN_VOLUME_DB
            or volume.max_volume >= MIN_REGION_PEAK_VOLUME_DB
        ):
            kept_regions.append(region)
        else:
            log(
                "Skipped quiet region "
                f"{format_timestamp(region.start)} -> {format_timestamp(region.end)} "
                f"(mean {volume.mean_volume:.1f} dB, peak {volume.max_volume:.1f} dB)"
            )

    return kept_regions


def split_long_region(region: SpeechRegion, max_duration: float) -> list[SpeechRegion]:
    duration = region.end - region.start
    if duration <= max_duration:
        return [region]

    count = math.ceil(duration / max_duration)
    chunk_duration = duration / count
    chunks = []
    for index in range(count):
        start = region.start + index * chunk_duration
        end = region.end if index == count - 1 else region.start + (index + 1) * chunk_duration
        chunks.append(SpeechRegion(start, end))
    return chunks


def create_sentence_blocks(regions: list[SpeechRegion]) -> list[SubtitleBlock]:
    blocks: list[SubtitleBlock] = []
    sentence_number = 1

    for region in regions:
        for chunk in split_long_region(region, MAX_SENTENCE_DURATION):
            blocks.append(
                SubtitleBlock(
                    start=chunk.start,
                    end=chunk.end,
                    text=f"[PASTE SENTENCE {sentence_number:03d}]",
                )
            )
            sentence_number += 1

    return blocks


def create_word_blocks(regions: list[SpeechRegion], words_per_block: int) -> list[SubtitleBlock]:
    blocks: list[SubtitleBlock] = []
    next_word_number = 1

    for region in regions:
        duration = region.end - region.start
        estimated_words = max(1, round(duration / ESTIMATED_WORD_DURATION))

        word_index = 0
        while word_index < estimated_words:
            block_word_count = min(words_per_block, estimated_words - word_index)
            start = region.start + (word_index / estimated_words) * duration
            end = region.start + ((word_index + block_word_count) / estimated_words) * duration
            end = max(start + MIN_SUBTITLE_DURATION, end - SUBTITLE_GAP)
            end = min(end, region.end)

            first_word = next_word_number
            last_word = next_word_number + block_word_count - 1
            if block_word_count == 1:
                text = f"[WORD {first_word:03d}]"
            else:
                text = f"[WORDS {first_word:03d}-{last_word:03d}]"

            blocks.append(SubtitleBlock(start=start, end=end, text=text))
            next_word_number += block_word_count
            word_index += block_word_count

    return blocks


def create_placeholder_blocks(regions: list[SpeechRegion], mode: str) -> list[SubtitleBlock]:
    if mode == "sentence":
        return create_sentence_blocks(regions)

    if mode in {"1", "2", "3"}:
        return create_word_blocks(regions, int(mode))

    raise PlaceholderError(f"Unknown placeholder mode: {mode}")


def format_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    millis = milliseconds % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(blocks: list[SubtitleBlock], subtitle_path: Path) -> int:
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)

    with subtitle_path.open("w", encoding="utf-8") as file:
        for index, block in enumerate(blocks, start=1):
            file.write(f"{index}\n")
            file.write(f"{format_timestamp(block.start)} --> {format_timestamp(block.end)}\n")
            file.write(f"{block.text}\n\n")

    return len(blocks)


def parse_srt_blocks(srt_path: Path) -> list[list[str]]:
    if not srt_path.exists():
        raise PlaceholderError(f"SRT file not found: {srt_path}")

    content = srt_path.read_text(encoding="utf-8-sig")
    raw_blocks = re.split(r"\n\s*\n", content.strip())
    blocks = []

    for raw_block in raw_blocks:
        lines = raw_block.splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            blocks.append(lines)

    if not blocks:
        raise PlaceholderError("No valid subtitle blocks were found in this SRT file.")

    return blocks


def write_raw_srt_blocks(blocks: list[list[str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for block in blocks:
            file.write("\n".join(block))
            file.write("\n\n")


def output_path_for_filled_srt(srt_path: Path, output_dir: Path | None = None) -> Path:
    base_dir = output_dir or srt_path.parent
    return base_dir / f"{srt_path.stem}_filled{srt_path.suffix}"


def fill_placeholder_srt(
    srt_file: str | Path,
    pasted_text: str,
    output_dir: Path | None = None,
    paste_mode: str | None = None,
) -> FillResult:
    srt_path = Path(srt_file).expanduser().resolve()
    blocks = parse_srt_blocks(srt_path)
    pasted_lines = pasted_text_to_lines(pasted_text, paste_mode)

    replaced_count = 0
    skipped_count = 0

    for index, block in enumerate(blocks):
        if index >= len(pasted_lines):
            break

        line = pasted_lines[index].strip()
        if line:
            block[2:] = [line]
            replaced_count += 1
        else:
            skipped_count += 1

    extra_line_count = max(0, len(pasted_lines) - len(blocks))
    warnings = []

    if len(pasted_lines) < len(blocks):
        warnings.append(
            f"You pasted {len(pasted_lines)} lines for {len(blocks)} subtitle blocks. "
            "Remaining placeholders were left unchanged."
        )

    if extra_line_count:
        warnings.append(
            f"You pasted {extra_line_count} extra lines. Extra lines were ignored."
        )

    output_path = output_path_for_filled_srt(srt_path, output_dir=output_dir)
    write_raw_srt_blocks(blocks, output_path)

    return FillResult(
        input_path=srt_path,
        output_path=output_path,
        block_count=len(blocks),
        pasted_line_count=len(pasted_lines),
        replaced_count=replaced_count,
        skipped_count=skipped_count,
        extra_line_count=extra_line_count,
        warnings=warnings,
    )


def pasted_text_to_lines(pasted_text: str, paste_mode: str | None = None) -> list[str]:
    if paste_mode in {None, "keep"}:
        return pasted_text.splitlines()

    if "\n" in pasted_text or "\r" in pasted_text:
        return pasted_text.splitlines()

    text = pasted_text.strip()
    if not text:
        return []

    if paste_mode == "sentence":
        return split_paragraph_sentences(text)

    if paste_mode in {"1", "2", "3"}:
        return split_paragraph_words(text, int(paste_mode))

    return pasted_text.splitlines()


def split_paragraph_words(text: str, words_per_line: int) -> list[str]:
    words = re.findall(r"\S+", text)
    return [
        " ".join(words[index : index + words_per_line])
        for index in range(0, len(words), words_per_line)
    ]


def split_paragraph_sentences(text: str) -> list[str]:
    sentence_parts = re.findall(r".+?(?:[.!?।]+|$)", text, flags=re.DOTALL)
    lines = [part.strip() for part in sentence_parts if part.strip()]
    return lines or [text]


def build_warnings(regions: list[SpeechRegion], blocks: list[SubtitleBlock]) -> list[str]:
    warnings = []

    if not regions:
        warnings.append("No clear speech regions were detected. The SRT may not be useful.")

    if len(blocks) > 500:
        warnings.append("This file produced many subtitle blocks. Sentence mode may be easier to edit.")

    return warnings


def generate_placeholder_srt(
    input_file: str | Path,
    mode: str = DEFAULT_PLACEHOLDER_MODE,
    audio_dir: Path = PROJECT_AUDIO_DIR,
    output_dir: Path = PROJECT_SUBTITLES_DIR,
    mp3_only: bool = False,
    base_dir: Path | None = None,
    log: LogCallback = default_log,
    progress: ProgressCallback = default_progress,
) -> PlaceholderResult:
    check_ffmpeg()
    progress(0)

    resolved_input = resolve_input_file(input_file, base_dir=base_dir)
    ensure_input_file(resolved_input, mp3_only=mp3_only)

    output_name = make_safe_output_name(resolved_input)
    log(f"Selected: {resolved_input.name}")
    log(f"Placeholder mode: {mode}")

    progress(20)
    audio_path = extract_audio(resolved_input, output_name, audio_dir, log=log)

    progress(45)
    duration = get_audio_duration(audio_path)
    min_silence_duration = silence_duration_for_mode(mode)
    silences = detect_silences(audio_path, min_silence_duration, log=log)
    regions = build_speech_regions(duration, silences)
    log(f"Detected possible speech regions: {len(regions)}")
    regions = filter_quiet_regions(audio_path, regions, log=log)
    log(f"Kept speech regions after quiet-area filter: {len(regions)}")

    progress(75)
    blocks = create_placeholder_blocks(regions, mode)
    subtitle_path = output_dir / f"{output_name}.srt"

    log("Writing placeholder subtitles...")
    subtitle_count = write_srt(blocks, subtitle_path)
    warnings = build_warnings(regions, blocks)

    for warning in warnings:
        log(f"Warning: {warning}")

    progress(100)
    return PlaceholderResult(
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        subtitle_count=subtitle_count,
        speech_region_count=len(regions),
        mode=mode,
        warnings=warnings,
    )
