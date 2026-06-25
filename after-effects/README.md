# SinhalaSTT for After Effects — Text to Subtitles

A simple After Effects panel that turns a script into **timed text layers** in your
active composition. Sinhala is automatically converted to **FM/DL legacy** text.

Fully offline — no Python, no helper, no internet. Just two script files.

## Install (one time)

1. Copy **both** files into After Effects' ScriptUI Panels folder:
   - `SinhalaSTT.jsx`
   - `fm_engine.jsx`  *(keep it next to SinhalaSTT.jsx)*

   The folder is here:
   - **macOS:** `/Applications/Adobe After Effects <version>/Scripts/ScriptUI Panels/`
   - **Windows:** `C:\Program Files\Adobe\Adobe After Effects <version>\Support Files\Scripts\ScriptUI Panels\`

2. Restart After Effects.
3. Open the panel from the **Window** menu → **SinhalaSTT.jsx**. Dock it anywhere.

**Quick alternative (no install):** `File → Scripts → Run Script File…` → pick
`SinhalaSTT.jsx`. It opens as a floating window. (`fm_engine.jsx` must be in the same
folder.)

## Use it

1. Open a composition and put the **playhead** where the subtitles should start.
2. Paste your script into the box (or **Open .txt**).
3. Choose the **Split**: Sentences / 1 word / 2 words / 3 words.
4. Set **Each** (seconds per line), and the **Font** / **Size**.
5. Click **Create text layers**.

Each line becomes a text layer, placed back-to-back from the playhead, named
`Sub 1`, `Sub 2`, … One **Undo** (Cmd/Ctrl+Z) removes them all.

## Sinhala & the FM/DL font

- When the script contains Sinhala, **Sinhala → FM/DL** auto-converts each line to
  legacy-font text (same conversion as the desktop app).
- For it to *display* correctly, install your **FM/DL legacy font** and type its exact
  name in the **Font** box (e.g. `FMAbhaya`). If the name is wrong, After Effects just
  uses a fallback font — change it and re-run.
- Uncheck **Sinhala → FM/DL** to keep normal Unicode Sinhala instead.

## Notes

- Layers are point-text, centered near the bottom of the frame, white with a thin
  black outline. Adjust styling afterwards like any AE text layer.
- `.pdf` / `.docx` scripts aren't read here (offline-only build) — paste the text or
  save it as `.txt` first.
