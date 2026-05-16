#!/usr/bin/env python3
"""
Terminal version of the placeholder subtitle generator.

For normal use, open SinhalaSTT.app or double-click Run SinhalaSTT.command.
"""

from __future__ import annotations

import argparse
import sys

from transcriber_core import (
    DEFAULT_PLACEHOLDER_MODE,
    PROJECT_AUDIO_DIR,
    PROJECT_SUBTITLES_DIR,
    PlaceholderError,
    generate_placeholder_srt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create editable placeholder SRT timestamps from a local audio or video file."
    )
    parser.add_argument(
        "input_file",
        help="Path to the audio/video file, for example: input/example.mp3 or input/example.mp4",
    )
    parser.add_argument(
        "--mode",
        default=DEFAULT_PLACEHOLDER_MODE,
        choices=["sentence", "1", "2", "3"],
        help="Placeholder mode: sentence, 1, 2, or 3 words per subtitle block.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        result = generate_placeholder_srt(
            args.input_file,
            mode=args.mode,
            audio_dir=PROJECT_AUDIO_DIR,
            output_dir=PROJECT_SUBTITLES_DIR,
        )
    except PlaceholderError as error:
        print(f"Error: {error}")
        sys.exit(1)

    print("Done.")
    print(f"Audio file: {result.audio_path}")
    print(f"Subtitle file: {result.subtitle_path}")
    print(f"Speech regions detected: {result.speech_region_count}")
    print(f"Subtitle blocks written: {result.subtitle_count}")

    for warning in result.warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
