# SinhalaSTT

![SinhalaSTT banner](assets/banner.png)

**SinhalaSTT 1.0** is a simple desktop tool for making Sinhala or English subtitle
(`.srt`) files. It runs on Windows and macOS.

It has three tools:

```text
Text  -> Subtitles : paste or open a script, pick a split, get an SRT
Audio -> Subtitles : rough timing from audio (experimental), optionally filled with your script
AI Caption         : optional online transcription with your own Gemini API key
```

When the text is **Sinhala Unicode**, SinhalaSTT automatically also saves an
**FM/DL legacy-font** version for Photoshop / Premiere workflows. English text just
makes one normal `.srt`. The Text and Audio tools work fully offline; AI Caption is
the only feature that uses the internet.

## Download

Get the latest build from the [Releases page](https://github.com/nuk3zz/SinhalaSTT/releases/latest):

- **Windows:** [`SinhalaSTT-1.0-Windows-x64.zip`](https://github.com/nuk3zz/SinhalaSTT/releases/download/v1.0/SinhalaSTT-1.0-Windows-x64.zip) — portable, no
  install needed, FFmpeg is already bundled inside. Unzip and double-click `SinhalaSTT.exe`.
- **macOS (Apple Silicon):** [`SinhalaSTT-1.0-macOS-arm64.dmg`](https://github.com/nuk3zz/SinhalaSTT/releases/download/v1.0/SinhalaSTT-1.0-macOS-arm64.dmg) — drag to
  Applications. Needs FFmpeg once via `brew install ffmpeg`.

Because the app is not code-signed, the first launch may show a warning
(Windows SmartScreen: `More info` -> `Run anyway`; macOS: right-click -> `Open`).

## The three tools

### 1. Text → Subtitles
1. Paste your script, or click **Open File** to load a `.pdf`, `.docx`, or `.txt`.
2. Choose how to split it: **Sentences / 1 word / 2 words / 3 words**.
3. Optionally set how long each line lasts (default 1 second).
4. Click **Create Subtitles**.

English text saves one Unicode `.srt`. Sinhala text saves **two** files: a Unicode
`.srt` and an FM/DL legacy-font `.srt`. Everything goes to your `Downloads` folder.

### 2. Audio → Subtitles (experimental)
1. Drag in (or import) an audio/video file.
2. Choose a split size.
3. *Optional:* paste or open your script to fill in the words.
4. Click **Create Subtitles from Audio**.

It listens for pauses to build timed blocks. With a script, your words are dropped
onto those time slots (Sinhala also gets an FM/DL file). With no script, you get
blank timed blocks to fill later. **Timing is approximate** — treat it as a starting
scaffold and fine-tune in your video editor.

### 3. AI Caption
1. Paste your Google Gemini API key (optionally remember it locally).
2. Import or drag an audio/video file.
3. Click **Generate AI Captions**.

The extracted audio is sent to Google Gemini using your key, and a draft `.srt` is
saved to `Downloads`. Always review the result — AI can make Sinhala mistakes.

## Supported inputs

```text
Audio/Video : MP3, WAV, M4A, AAC, FLAC, AIFF, MP4, MOV, M4V, MKV, AVI, WEBM
Script files: PDF, DOCX, TXT
```

## FM/DL legacy fonts

Sinhala Unicode is auto-converted to FM/DL legacy text. It may look like gibberish in
a plain editor, but displays correctly once you pick a compatible legacy Sinhala font
in Photoshop / Premiere. Example:

```text
ලංකාවේ වැඩිම දුර යන්න පුලුවන් ඹුඩ්ගෙට් EV එකද?
-> ,xldfõ jeäu ÿr hkak mq¨jka Uqâf.Ü EV tlo@
```

The offline FM/DL rules are based on the public FMAbhaya converter work by Malinthe
Samarakoon, originally created by LTRL at the University of Colombo School of Computing.

## Where files go

```text
Subtitles (.srt) : Downloads/
Temporary audio  : system Temp folder (safe to delete)
```

## Developer setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # PySide6, requests, pypdf, python-docx, ...
python scripts/ui.py
```

FFmpeg must be available (`brew install ffmpeg` on macOS). The Windows build bundles
its own FFmpeg, so end users never install anything.

## Building the apps

- **Windows:** built automatically by GitHub Actions — see
  [`packaging/windows/BUILD-WINDOWS.md`](packaging/windows/BUILD-WINDOWS.md). No Windows
  PC required. Push a `v*` tag (e.g. `v1.0`) to publish a release with the zip attached.
- **macOS:**

  ```bash
  pip install pyinstaller
  pyinstaller --noconfirm --windowed \
    --name "SinhalaSTT" \
    --icon "assets/SinhalaSTT.icns" \
    --add-data "assets:assets" \
    --paths scripts \
    scripts/ui.py
  ```

  The app is created in `dist/SinhalaSTT.app`.
