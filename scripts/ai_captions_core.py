from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from transcriber_core import (
    CACHE_AUDIO_DIR,
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
GEMINI_API_VERSION = "v1beta"


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


def _gemini_generate_content(
    api_key: str,
    model: str,
    audio_path: Path,
    duration_seconds: float,
    log: LogCallback,
) -> dict[str, Any]:
    audio_size = audio_path.stat().st_size
    log(f"Prepared WAV size: {audio_size / (1024 * 1024):.2f} MB")
    if audio_size > INLINE_AUDIO_LIMIT_BYTES:
        raise AiCaptionError(
            "This audio is too large for the current AI Captions beta. "
            "Try a shorter clip first."
        )

    log("Encoding audio for Gemini...")
    audio_base64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    url = (
        f"https://generativelanguage.googleapis.com/{GEMINI_API_VERSION}/"
        f"models/{model}:generateContent"
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _caption_prompt(duration_seconds)},
                    {
                        "inlineData": {
                            "mimeType": "audio/wav",
                            "data": audio_base64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": _caption_schema(),
        },
    }

    log("Contacting Gemini API...")
    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=body,
            timeout=(10, GEMINI_REQUEST_TIMEOUT_MS / 1000),
        )
    except requests.Timeout as error:
        log("Gemini request timed out.")
        raise AiCaptionError(
            "Gemini did not respond within 2 minutes. Try again later, or test with a shorter clip. "
            "Free tier can be slow or rate-limited."
        ) from error
    except requests.RequestException as error:
        log("Network request failed before Gemini returned a response.")
        raise AiCaptionError(f"Could not reach Gemini: {error}") from error

    log(f"Gemini HTTP status: {response.status_code}")

    if response.status_code == 429:
        log("Google says: 429 TooManyRequests.")
        raise AiCaptionError(
            "Gemini rate limit hit: Google returned 429 TooManyRequests. "
            "Wait 10-15 minutes and try one short clip again. "
            "Free tier/Tier 1 limits can be strict for audio."
        )

    if response.status_code == 400:
        log("Google rejected the request.")
        raise AiCaptionError(
            "Gemini rejected the request. Check that your API key is valid for Gemini API "
            "and try a shorter audio clip."
        )

    if response.status_code >= 400:
        try:
            error_data = response.json().get("error", {})
            message = error_data.get("message") or response.text[:300]
        except ValueError:
            message = response.text[:300]
        log(f"Gemini error message: {message}")
        raise AiCaptionError(f"Gemini request failed ({response.status_code}): {message}")

    try:
        data = response.json()
    except ValueError as error:
        log("Gemini returned non-JSON HTTP content.")
        raise AiCaptionError("Gemini returned a response that was not valid JSON.") from error

    log("Gemini response received. Parsing subtitles...")
    return data


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


def _rest_response_to_json(response_data: dict[str, Any]) -> dict[str, Any]:
    try:
        parts = response_data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as error:
        raise AiCaptionError("Gemini did not return subtitle content.") from error

    text_parts = [
        str(part.get("text", "")).strip()
        for part in parts
        if isinstance(part, dict) and part.get("text")
    ]
    text = "\n".join(text_parts).strip()
    if not text:
        raise AiCaptionError("Gemini returned an empty transcript.")

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
    audio_output_dir = audio_dir or CACHE_AUDIO_DIR

    progress(10)
    log("Preparing audio with FFmpeg...")
    audio_path = extract_audio(resolved_input, f"{output_name}_ai", audio_output_dir, log=log)
    duration_seconds = get_audio_duration(audio_path)
    log(f"Audio duration: {duration_seconds:.1f}s")
    log(estimate_gemini_cost(duration_seconds))

    progress(35)
    log(f"Sending extracted audio to Gemini: {model}")
    log("This should usually finish within 1-2 minutes for short clips.")

    progress(55)
    log("Waiting for Gemini transcript...")
    response_data = _gemini_generate_content(api_key, model, audio_path, duration_seconds, log=log)

    progress(75)
    data = _rest_response_to_json(response_data)
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
