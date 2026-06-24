#!/usr/bin/env python3
"""
SinhalaSTT Premiere helper server.

The Premiere UXP plugin cannot run FFmpeg or AI itself, so it talks to this tiny
local server over http://localhost. This server reuses the existing SinhalaSTT
engine (scripts/) — FFmpeg silence timing, the Gemini AI captions, and the FM/DL
font conversion.

Run it with the project's virtual environment:

    .venv/bin/python premiere-uxp/helper/server.py

It listens on http://127.0.0.1:8765 and only accepts local connections.

Endpoints (all JSON):
    GET  /health   -> { ok, ffmpeg }
    POST /convert  -> { text }                                  -> { fm, isSinhala, warnings }
    POST /timing   -> { filePath, mode, clipStart?, clipDuration? } -> { blocks: [{start,end,text}] }
    POST /ai       -> { filePath, apiKey, mode?, clipStart?, clipDuration? } -> { blocks: [...] }
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Make the existing engine importable.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from ai_captions_core import AiCaptionError, generate_ai_caption_blocks  # noqa: E402
from font_converter import contains_sinhala, unicode_to_fm  # noqa: E402
from transcriber_core import (  # noqa: E402
    PlaceholderError,
    analyze_audio_to_blocks,
    find_tool,
)


HOST = "127.0.0.1"
PORT = 8765


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Allow the UXP panel to call us.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, *args) -> None:  # quiet console
        return

    def do_OPTIONS(self) -> None:  # noqa: N802 - CORS preflight
        self._send(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            ffmpeg_ok = bool(find_tool("ffmpeg") and find_tool("ffprobe"))
            self._send(200, {"ok": True, "ffmpeg": ffmpeg_ok, "service": "SinhalaSTT helper"})
            return
        self._send(404, {"ok": False, "error": "Unknown endpoint"})

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.rstrip("/")
        try:
            if route == "/convert":
                self._handle_convert()
            elif route == "/timing":
                self._handle_timing()
            elif route == "/ai":
                self._handle_ai()
            else:
                self._send(404, {"ok": False, "error": "Unknown endpoint"})
        except (PlaceholderError, AiCaptionError) as error:
            self._send(400, {"ok": False, "error": str(error)})
        except Exception:
            self._send(500, {"ok": False, "error": "Unexpected error:\n" + traceback.format_exc()})

    # -- endpoint handlers -------------------------------------------------
    def _handle_convert(self) -> None:
        data = self._read_json()
        text = str(data.get("text", ""))
        result = unicode_to_fm(text)
        self._send(
            200,
            {
                "ok": True,
                "fm": result.text,
                "isSinhala": contains_sinhala(text),
                "warnings": result.warnings,
            },
        )

    def _handle_timing(self) -> None:
        data = self._read_json()
        file_path = str(data.get("filePath", "")).strip()
        if not file_path:
            self._send(400, {"ok": False, "error": "filePath is required."})
            return
        blocks = analyze_audio_to_blocks(
            file_path,
            mode=str(data.get("mode", "sentence")),
            clip_start=_float_or_none(data.get("clipStart")),
            clip_duration=_float_or_none(data.get("clipDuration")),
        )
        self._send(200, {"ok": True, "blocks": blocks})

    def _handle_ai(self) -> None:
        data = self._read_json()
        file_path = str(data.get("filePath", "")).strip()
        api_key = str(data.get("apiKey", "")).strip()
        if not file_path:
            self._send(400, {"ok": False, "error": "filePath is required."})
            return
        if not api_key:
            self._send(400, {"ok": False, "error": "apiKey is required."})
            return
        blocks = generate_ai_caption_blocks(
            file_path,
            api_key=api_key,
            clip_start=_float_or_none(data.get("clipStart")),
            clip_duration=_float_or_none(data.get("clipDuration")),
        )
        self._send(200, {"ok": True, "blocks": blocks})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SinhalaSTT helper running at http://{HOST}:{PORT}")
    print("Leave this window open while using the Premiere plugin. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping helper.")
        server.shutdown()


if __name__ == "__main__":
    main()
