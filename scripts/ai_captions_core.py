from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from transcriber_core import (
    DOWNLOADS_OUTPUT_DIR,
    LogCallback,
    PlaceholderError,
    ProgressCallback,
    SubtitleBlock,
    default_log,
    default_progress,
    extract_audio,
    get_audio_duration,
    make_safe_output_name,
    resolve_input_file,
    write_srt,
)


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
AUDIO_INPUT_TOKENS_PER_SECOND = 25
ESTIMATED_AUDIO_INPUT_PRICE_PER_MILLION = 0.50
ESTIMATED_TEXT_OUTPUT_PRICE_PER_MILLION = 1.50
GEMINI_REQUEST_TIMEOUT_MS = 120_000
INLINE_AUDIO_LIMIT_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class AiCaptionResult:
    audio_path: Path
    subtitle_path: Path
    subtitle_count: int
    duration_seconds: float
    model: str
    warnings: list[str]


class AiCaptionError(Exception):
    """A user-friendly AI caption generation error."""


def estimate_gemini_cost(duration_seconds: float) -> str:
    input_tokens = duration_seconds * AUDIO_INPUT_TOKENS_PER_SECOND
    input_cost = (input_tokens / 1_000_000) * ESTIMATED_AUDIO_INPUT_PRICE_PER_MILLION

    # Output text size varies a lot, so show a practical small range.
    low_output_cost = (1_000 / 1_000_000) * ESTIMATED_TEXT_OUTPUT_PRICE_PER_MILLION
    high_output_cost = (4_000 / 1_000_000) * ESTIMATED_TEXT_OUTPUT_PRICE_PER_MILLION
    low_total = input_cost + low_output_cost
    high_total = input_cost + high_output_cost
    return f"Approx Gemini cost: ${low_total:.4f} - ${high_total:.4f} USD"


def _caption_prompt(duration_seconds: float) -> str:
    return (
        "Transcribe the provided audio into subtitle segments.\n"
        "Keep Sinhala as Sinhala and English as English. Do not translate. "
        "Do not summarize or clean up meaning. Preserve spoken wording as much as possible.\n"
        "Return subtitle segments for the full audio duration. "
        f"The audio is about {duration_seconds:.1f} seconds long.\n"
        "Use seconds for start and end times. Keep segments short enough for subtitles."
    )


def _caption_schema() -> dict[str, Any]:
    return {
        "type": "OBJECT",
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "required": ["start", "end", "text"],
                    "properties": {
                        "start": {"type": "NUMBER"},
                        "end": {"type": "NUMBER"},
                        "text": {"type": "STRING"},
                    },
                },
            }
        },
    }


def _response_to_json(response: Any) -> dict[str, Any]:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, dict):
        return parsed

    text = getattr(response, "text", "") or ""
    text = text.strip()
    if not text:
        raise AiCaptionError("Gemini returned an empty response.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        raise AiCaptionError("Gemini returned text that could not be converted into subtitles.") from error


def _blocks_from_response(data: dict[str, Any], duration_seconds: float) -> tuple[list[SubtitleBlock], list[str]]:
    raw_segments = data.get("segments")
    if not isinstance(raw_segments, list):
        raise AiCaptionError("Gemini response did not contain subtitle segments.")

    blocks: list[SubtitleBlock] = []
    warnings: list[str] = []
    previous_end = 0.0

    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            continue

        text = str(raw_segment.get("text", "")).strip()
        if not text:
            continue

        try:
            start = float(raw_segment.get("start", 0.0))
            end = float(raw_segment.get("end", 0.0))
        except (TypeError, ValueError):
            continue

        start = max(0.0, min(start, duration_seconds))
        end = max(0.0, min(end, duration_seconds))

        if end <= start:
            end = min(duration_seconds, start + 1.5)

        if start < previous_end:
            start = previous_end
            if end <= start:
                end = min(duration_seconds, start + 1.0)

        if end <= start:
            continue

        blocks.append(SubtitleBlock(start=start, end=end, text=text))
        previous_end = end

    if not blocks:
        raise AiCaptionError("Gemini did not return any usable subtitle text.")

    if len(blocks) < 3 and duration_seconds > 30:
        warnings.append("Gemini returned very few subtitle blocks. Check the SRT carefully.")

    return blocks, warnings


def generate_ai_captions_srt(
    input_file: str | Path,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    audio_dir: Path | None = None,
    output_dir: Path = DOWNLOADS_OUTPUT_DIR,
    log: LogCallback = default_log,
    progress: ProgressCallback = default_progress,
) -> AiCaptionResult:
    api_key = api_key.strip()
    if not api_key:
        raise AiCaptionError("Paste your Gemini API key first.")

    resolved_input = resolve_input_file(input_file)
    if not resolved_input.exists() or not resolved_input.is_file():
        raise AiCaptionError(f"Input file not found: {resolved_input}")

    output_name = make_safe_output_name(resolved_input)
    audio_output_dir = audio_dir or (Path.home() / "Desktop" / "Cache" / "temporary wav")

    progress(10)
    log("Preparing audio with FFmpeg...")
    audio_path = extract_audio(resolved_input, f"{output_name}_ai", audio_output_dir, log=log)
    duration_seconds = get_audio_duration(audio_path)
    log(f"Audio duration: {duration_seconds:.1f}s")
    log(estimate_gemini_cost(duration_seconds))

    progress(35)
    log(f"Sending extracted audio to Gemini: {model}")
    log("This should usually finish within 1-2 minutes for short clips.")
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS),
    )
    uploaded_file = None

    try:
        audio_size = audio_path.stat().st_size
        if audio_size <= INLINE_AUDIO_LIMIT_BYTES:
            log("Sending audio directly...")
            audio_part = types.Part.from_bytes(
                data=audio_path.read_bytes(),
                mime_type="audio/wav",
            )
        else:
            log("Uploading larger audio file...")
            uploaded_file = client.files.upload(file=str(audio_path))
            audio_part = uploaded_file

        progress(55)
        log("Waiting for Gemini transcript...")
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_caption_schema(),
            temperature=0.1,
        )
        response = client.models.generate_content(
            model=model,
            contents=[
                _caption_prompt(duration_seconds),
                audio_part,
            ],
            config=config,
        )
    except Exception as error:
        error_text = str(error)
        error_text_lower = error_text.lower()
        if "429" in error_text or "toomanyrequests" in error_text_lower or "rate limit" in error_text_lower:
            raise AiCaptionError(
                "Gemini rate limit hit: Google returned 429 TooManyRequests. "
                "Wait a few minutes and try again, or test with a shorter clip. "
                "Free tier/Tier 1 limits can be strict."
            ) from error
        if "timed out" in error_text_lower or "timeout" in error_text_lower:
            raise AiCaptionError(
                "Gemini did not respond within 2 minutes. Try again, or test with a shorter clip. "
                "Free tier can be slow or rate-limited."
            ) from error
        raise AiCaptionError(f"Gemini caption generation failed: {error}") from error
    finally:
        if uploaded_file is not None:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
        try:
            client.close()
        except Exception:
            pass

    progress(75)
    data = _response_to_json(response)
    blocks, warnings = _blocks_from_response(data, duration_seconds)

    output_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = output_dir / f"{output_name}_ai.srt"
    log("Writing AI subtitle draft...")
    subtitle_count = write_srt(blocks, subtitle_path)

    progress(100)
    return AiCaptionResult(
        audio_path=audio_path,
        subtitle_path=subtitle_path,
        subtitle_count=subtitle_count,
        duration_seconds=duration_seconds,
        model=model,
        warnings=warnings,
    )
