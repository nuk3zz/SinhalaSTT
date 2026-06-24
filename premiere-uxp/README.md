# SinhalaSTT for Premiere Pro (UXP) — proof of concept

A native Premiere Pro panel that reads the **selected audio clip** from your
timeline and places **timed text blocks** straight onto the sequence — Sinhala is
auto-converted to FM/DL legacy text. No SRT files to manage.

## Why there are two parts

UXP plugins **cannot run FFmpeg** (Adobe blocks running external programs). So the
work is split:

```
Premiere panel (this UXP plugin)         Local helper (Python, reuses ../scripts)
  • reads the selected clip       ──►      • FFmpeg: trims + silence timing
    (file path + in/out + start)           • Gemini: AI captions
  • places text on the timeline   ◄──      • FM/DL Sinhala conversion
        (talks over http://127.0.0.1:8765)
```

The helper is just the existing SinhalaSTT engine wrapped in a tiny local web
server. Nothing leaves your machine except the optional AI Caption call.

## How to run it

### 1. Start the helper
From the project root, with the virtual environment that has the dependencies:

```bash
.venv/bin/python premiere-uxp/helper/server.py
```

Leave that window open. It listens on `http://127.0.0.1:8765` (local only).
FFmpeg must be available (`brew install ffmpeg` on macOS).

### 2. Load the plugin
1. Open the **Adobe UXP Developer Tool**.
2. **Add Plugin** → choose `premiere-uxp/plugin/manifest.json`.
3. Click **Load** (with Premiere Pro open).
4. The **SinhalaSTT** panel appears under `Window → Extensions` (or the plugin menu).

### 3. Use it
1. The panel shows **Helper: connected** when the server is running.
2. Click an **audio clip** in your timeline, then **Read selected clip**.
3. **Get timing from audio** (or tick *Use AI Caption* with a Gemini key).
4. Optionally paste your script.
5. **Add text blocks to timeline**.

The **Sinhala → FM/DL** tool at the bottom works on its own (just needs the helper).

## Status (what's proven vs. what needs your machine)

| Part | Status |
|------|--------|
| Helper server: timing, FM/DL, AI endpoints | ✅ built and tested on macOS |
| Panel UI + helper connection + FM/DL convert | ✅ ready (testable as soon as you load it) |
| Read selected clip (file + in/out) | ⏳ uses the current `premierepro` API — confirm on your Premiere version |
| Insert text blocks on the timeline | ⏳ best-effort; the exact graphics API varies by version and is the main thing to wire up together |

When you load it, tell me your **Premiere version** and paste anything the panel's
log shows — that's how we lock down the clip-read and timeline-insert calls.

## Files
- `helper/server.py` — local server reusing `../../scripts` (the SinhalaSTT engine).
- `plugin/manifest.json` — UXP manifest (Premiere host, localhost network permission).
- `plugin/index.html`, `plugin/styles.css`, `plugin/main.js` — the panel.
