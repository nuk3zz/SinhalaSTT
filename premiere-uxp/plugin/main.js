/*
 * SinhalaSTT — Premiere Pro UXP plugin (proof of concept).
 *
 * Flow:
 *   1. Read the selected audio clip from the timeline (source file + in/out + start).
 *   2. Ask the local helper server for timing (or AI captions) for that audio.
 *   3. Place timed text blocks onto the sequence (Sinhala auto-converted to FM/DL).
 *
 * The heavy lifting (FFmpeg / Gemini / FM-DL rules) lives in the local helper
 * server, because UXP itself cannot run FFmpeg. Start it first:
 *     .venv/bin/python premiere-uxp/helper/server.py
 */

const HELPER = "http://127.0.0.1:8765";
const TICKS_PER_SECOND = 254016000000; // Premiere TickTime resolution

// Loaded lazily so the panel still opens if the module name differs by version.
let ppro = null;
try {
  ppro = require("premierepro");
} catch (e) {
  // logged after DOM is ready
}

// Pipeline state for the current selection.
const state = {
  filePath: null,
  clipStart: 0, // source in-point, seconds
  clipDuration: 0, // out - in, seconds
  timelineStart: 0, // where the clip sits in the sequence, seconds
  blocks: null, // [{start, end, text}]
  templatePath: null, // chosen .mogrt with an editable text field
};

const $ = (id) => document.getElementById(id);

function log(message) {
  const box = $("log");
  box.textContent += (box.textContent ? "\n" : "") + message;
  box.scrollTop = box.scrollHeight;
}

let helperConnected = false;

function setHelper(ok) {
  const pill = $("helper-status");
  pill.textContent = ok ? "Helper: connected" : "Helper: offline";
  pill.className = "pill " + (ok ? "pill-on" : "pill-off");
}

async function callHelper(path, body, method = "POST") {
  const options = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(HELPER + path, options);
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Helper request failed: " + response.status);
  }
  return data;
}

async function checkHelper(verbose) {
  try {
    const data = await callHelper("/health", undefined, "GET");
    if (!helperConnected || verbose) log(`Helper connected. FFmpeg available: ${data.ffmpeg}`);
    helperConnected = true;
    setHelper(true);
  } catch (e) {
    if (helperConnected || verbose) {
      log("Helper offline. Double-click 'start-helper.command' in the premiere-uxp folder.");
    }
    helperConnected = false;
    setHelper(false);
  }
}

// --- Premiere timeline reading ------------------------------------------------

function ticksToSeconds(tick) {
  // TickTime objects expose seconds in newer APIs; fall back to raw ticks.
  if (tick == null) return 0;
  if (typeof tick.seconds === "number") return tick.seconds;
  if (typeof tick.ticks === "number") return tick.ticks / TICKS_PER_SECOND;
  if (typeof tick === "number") return tick / TICKS_PER_SECOND;
  return 0;
}

async function firstSelectedAudioItem(sequence) {
  // Preferred: explicit selection API.
  if (typeof sequence.getSelection === "function") {
    const selection = await sequence.getSelection();
    const items = selection && (await selection.getTrackItems?.());
    if (items && items.length) {
      for (const item of items) {
        const type = await safe(() => item.getMediaType?.());
        // Accept audio items; if media type is unknown, accept anyway.
        if (!type || String(type).toLowerCase().includes("audio")) return item;
      }
      return items[0];
    }
  }

  // Fallback: scan audio tracks for a selected item.
  const trackCount = await safe(() => sequence.getAudioTrackCount?.());
  for (let t = 0; t < (trackCount || 0); t++) {
    const track = await safe(() => sequence.getAudioTrack?.(t));
    const items = track && (await safe(() => track.getTrackItems?.(1, false)));
    for (const item of items || []) {
      const selected = await safe(() => item.isSelected?.());
      if (selected) return item;
    }
  }
  return null;
}

async function safe(fn) {
  try {
    return await fn();
  } catch (e) {
    return null;
  }
}

// Lists the callable methods on an object (own + prototype). This is the fastest
// way to confirm the real API surface on a given Premiere version.
function logMethods(label, obj) {
  if (!obj) {
    log(`${label}: <null>`);
    return;
  }
  const names = new Set();
  let cur = obj;
  while (cur && cur !== Object.prototype) {
    for (const key of Object.getOwnPropertyNames(cur)) {
      if (key === "constructor") continue;
      try {
        if (typeof obj[key] === "function") names.add(key);
      } catch (e) {
        /* getters may throw */
      }
    }
    cur = Object.getPrototypeOf(cur);
  }
  log(`${label} methods: ${Array.from(names).sort().join(", ") || "(none)"}`);
}

async function logApiDiagnostics() {
  if (!ppro) {
    log("premierepro module not available.");
    return;
  }
  log("--- API diagnostics ---");
  log("premierepro top-level: " + Object.keys(ppro).sort().join(", "));
  const project = await safe(() => ppro.Project.getActiveProject());
  const sequence = project && (await safe(() => project.getActiveSequence()));
  logMethods("project", project);
  logMethods("sequence", sequence);
  if (sequence) {
    const item = await firstSelectedAudioItem(sequence);
    logMethods("trackItem", item);
    if (item) logMethods("projectItem", await safe(() => item.getProjectItem()));
  }
  log("--- end diagnostics ---");
}

async function readSelectedClip() {
  if (!ppro) {
    log("Premiere API (premierepro) not available in this version. Check the host/minVersion.");
    return;
  }
  try {
    const project = await ppro.Project.getActiveProject();
    const sequence = await project.getActiveSequence();
    if (!sequence) {
      log("No active sequence. Open a sequence with an audio clip.");
      return;
    }

    const item = await firstSelectedAudioItem(sequence);
    if (!item) {
      log("No selected audio clip found. Click an audio clip in the timeline first.");
      return;
    }

    const projectItem = await item.getProjectItem();
    const filePath = await safe(() => projectItem.getMediaFilePath?.());
    const inPoint = ticksToSeconds(await safe(() => item.getInPoint?.()));
    const outPoint = ticksToSeconds(await safe(() => item.getOutPoint?.()));
    const startTime = ticksToSeconds(await safe(() => item.getStartTime?.()));

    if (!filePath) {
      log("Could not read the clip's media file path from the API.");
      return;
    }

    state.filePath = filePath;
    state.clipStart = inPoint;
    state.clipDuration = Math.max(0, outPoint - inPoint);
    state.timelineStart = startTime;
    state.blocks = null;

    $("clip-info").textContent =
      `File: ${filePath}\n` +
      `Clip region: ${inPoint.toFixed(2)}s → ${outPoint.toFixed(2)}s (${state.clipDuration.toFixed(2)}s)\n` +
      `Timeline start: ${startTime.toFixed(2)}s`;
    $("get-timing").disabled = false;
    $("add-blocks").disabled = true;
    log("Clip read successfully.");
  } catch (e) {
    log("Error reading clip: " + (e.message || e));
  }
}

// --- Timing / AI --------------------------------------------------------------

async function getTiming() {
  if (!state.filePath) {
    log("Read a clip first.");
    return;
  }
  const useAi = $("use-ai").checked;
  try {
    log(useAi ? "Requesting AI captions from helper…" : "Requesting timing from helper…");
    let data;
    if (useAi) {
      data = await callHelper("/ai", {
        filePath: state.filePath,
        apiKey: $("api-key").value.trim(),
        clipStart: state.clipStart,
        clipDuration: state.clipDuration,
      });
    } else {
      data = await callHelper("/timing", {
        filePath: state.filePath,
        mode: $("mode").value,
        clipStart: state.clipStart,
        clipDuration: state.clipDuration,
      });
    }
    state.blocks = data.blocks || [];
    log(`Got ${state.blocks.length} block(s).`);
    $("add-blocks").disabled = state.blocks.length === 0;
  } catch (e) {
    log("Timing error: " + (e.message || e));
  }
}

// --- Fill text and place blocks ----------------------------------------------

async function blockTexts() {
  // Decide the text for each block: AI text already present, otherwise the
  // user's script split per line, otherwise a numbered placeholder.
  const script = $("script").value.trim();
  const texts = state.blocks.map((b, i) => b.text || `Block ${i + 1}`);

  if (script) {
    // Split the script into one line per block using the helper's same rules
    // would be ideal; for the POC we split on lines/spaces by the chosen mode.
    const mode = $("mode").value;
    let lines;
    if (mode === "sentence") {
      lines = script.split(/(?<=[.!?।])\s+/).map((s) => s.trim()).filter(Boolean);
    } else {
      const n = parseInt(mode, 10) || 1;
      const words = script.split(/\s+/).filter(Boolean);
      lines = [];
      for (let i = 0; i < words.length; i += n) lines.push(words.slice(i, i + n).join(" "));
    }
    for (let i = 0; i < texts.length; i++) texts[i] = lines[i] || "";
  }

  // Auto-convert Sinhala to FM/DL via the helper (offline rules).
  const joined = texts.join("\n");
  if (/[඀-෿]/.test(joined)) {
    try {
      const data = await callHelper("/convert", { text: joined });
      return data.fm.split("\n");
    } catch (e) {
      log("FM/DL conversion failed, using Unicode: " + (e.message || e));
    }
  }
  return texts;
}

async function addBlocksToTimeline() {
  if (!state.blocks || !state.blocks.length) {
    log("Get timing first.");
    return;
  }
  if (!state.templatePath) {
    log("Choose a .mogrt text template first (see README for how to make one).");
    return;
  }
  const texts = await blockTexts();
  const videoTrackIndex = 0; // place graphics on the first video track for now

  log("Placing " + state.blocks.length + " text block(s) on the timeline…");
  let placed = 0;
  for (let i = 0; i < state.blocks.length; i++) {
    const block = state.blocks[i];
    const start = state.timelineStart + block.start;
    const end = state.timelineStart + block.end;
    const text = texts[i] || "";
    try {
      await placeTextGraphic(text, start, end, videoTrackIndex);
      placed++;
    } catch (e) {
      log(`Block ${i + 1} insert failed: ${e.message || e}`);
      // Stop after the first failure; click "Log API methods" and send me the
      // output so we can match the exact import/parameter calls for your version.
      break;
    }
  }
  log(`Placed ${placed}/${state.blocks.length} block(s).`);
}

async function placeTextGraphic(text, startSeconds, endSeconds, videoTrackIndex) {
  // Premiere UXP cannot create a text graphic from nothing — the supported path
  // is: import a .mogrt that exposes an editable text field, then set that field.
  if (!ppro) throw new Error("premierepro module unavailable");
  if (!state.templatePath) throw new Error("Choose a .mogrt text template first.");

  const project = await ppro.Project.getActiveProject();
  const sequence = await project.getActiveSequence();
  const tick = secondsToTick(startSeconds);

  // Import the template to the timeline. Method names vary by version, so try the
  // known candidates and let diagnostics reveal the right one if none match.
  let trackItem = null;
  const importArgsCandidates = [
    () => sequence.importMGT(state.templatePath, tick, videoTrackIndex, 0),
    () => sequence.importMGTFromLibrary(state.templatePath, tick, videoTrackIndex, 0),
    () => project.importMGT(sequence, state.templatePath, tick, videoTrackIndex),
  ];
  for (const attempt of importArgsCandidates) {
    trackItem = await safe(attempt);
    if (trackItem) break;
  }
  if (!trackItem) throw new Error("could not import .mogrt (importMGT API not found — see diagnostics)");

  // Set the exposed text parameter on the imported graphic.
  const component = await safe(() => trackItem.getComponent?.(0)) || trackItem;
  const param =
    (await safe(() => component.getParamForDisplayName?.("Text"))) ||
    (await safe(() => component.getParam?.(0)));
  if (param) {
    if (typeof param.setValue === "function") await param.setValue(text);
    else if (typeof param.setText === "function") await param.setText(text);
    else throw new Error("text parameter has no setValue/setText");
  } else {
    throw new Error("no editable text parameter found on the template");
  }
}

async function chooseTemplate() {
  try {
    const fs = require("uxp").storage.localFileSystem;
    const file = await fs.getFileForOpening({ types: ["mogrt"] });
    if (!file) return;
    state.templatePath = file.nativePath;
    $("template-info").textContent = "Template: " + file.nativePath;
    log("Template chosen.");
  } catch (e) {
    log("Could not choose template: " + (e.message || e));
  }
}

function secondsToTick(seconds) {
  if (ppro && ppro.TickTime && typeof ppro.TickTime.createWithSeconds === "function") {
    return ppro.TickTime.createWithSeconds(seconds);
  }
  return Math.round(seconds * TICKS_PER_SECOND);
}

// --- Offline FM/DL tool -------------------------------------------------------

async function convertFm() {
  const text = $("fm-in").value;
  if (!text.trim()) {
    log("Paste Sinhala text to convert.");
    return;
  }
  try {
    const data = await callHelper("/convert", { text });
    $("fm-out").value = data.fm;
    $("copy-fm").disabled = !data.fm;
    log(`Converted to FM/DL (${data.isSinhala ? "Sinhala detected" : "no Sinhala found"}).`);
  } catch (e) {
    log("Convert error: " + (e.message || e));
  }
}

// --- Wire up ------------------------------------------------------------------

function init() {
  if (!ppro) log("Note: premierepro module not loaded. The FM/DL tool still works via the helper.");
  $("read-clip").addEventListener("click", readSelectedClip);
  $("get-timing").addEventListener("click", getTiming);
  $("add-blocks").addEventListener("click", addBlocksToTimeline);
  $("choose-template").addEventListener("click", chooseTemplate);
  $("diagnostics").addEventListener("click", logApiDiagnostics);
  $("convert-fm").addEventListener("click", convertFm);
  $("copy-fm").addEventListener("click", () => {
    navigator.clipboard.setContent ? navigator.clipboard.setContent({ "text/plain": $("fm-out").value }) : null;
    log("Copied FM/DL text.");
  });
  // Click the status pill to re-check on demand.
  $("helper-status").addEventListener("click", () => checkHelper(true));
  // Auto-connect: keep checking until the helper is up, then stop spamming.
  checkHelper(true);
  setInterval(() => checkHelper(false), 4000);
}

document.addEventListener("DOMContentLoaded", init);
