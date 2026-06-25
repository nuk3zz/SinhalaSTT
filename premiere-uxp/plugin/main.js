/*
 * SinhalaSTT — Premiere Pro UXP plugin (proof of concept).
 *
 * Three tabs, matching the desktop app:
 *   Text  → Subtitles : paste a script, split it, place text blocks at the playhead
 *   Audio → Subtitles : timed blocks from a selected clip (optional script fill)
 *   AI Caption        : Gemini captions for the selected clip
 *
 * FFmpeg / Gemini / FM-DL run in the local helper server (UXP can't run FFmpeg).
 * Placing text needs a one-time .mogrt template (Premiere can't draw text from
 * nothing); the plugin remembers the one you pick.
 */

const HELPER = "http://localhost:8765"; // UXP needs a hostname, not a raw IP
const TICKS_PER_SECOND = 254016000000;

let ppro = null;
try {
  ppro = require("premierepro");
} catch (e) {
  /* logged after DOM ready */
}

const state = { templatePath: null };
const $ = (id) => document.getElementById(id);

function log(message) {
  const box = $("log");
  box.textContent += (box.textContent ? "\n" : "") + message;
  box.scrollTop = box.scrollHeight;
}

// --- Helper connection --------------------------------------------------------

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
    if (helperConnected || verbose) log("Helper offline: " + (e && e.message ? e.message : e));
    helperConnected = false;
    setHelper(false);
  }
}

// --- Text helpers -------------------------------------------------------------

function splitToLines(text, mode) {
  if (mode === "sentence") {
    return text.split(/(?<=[.!?।])\s+/).map((s) => s.trim()).filter(Boolean);
  }
  const n = parseInt(mode, 10) || 1;
  const words = text.split(/\s+/).filter(Boolean);
  const out = [];
  for (let i = 0; i < words.length; i += n) out.push(words.slice(i, i + n).join(" "));
  return out;
}

async function fmConvertLines(lines) {
  const joined = lines.join("\n");
  if (/[඀-෿]/.test(joined)) {
    try {
      const data = await callHelper("/convert", { text: joined });
      return data.fm.split("\n");
    } catch (e) {
      log("FM/DL conversion failed, using Unicode: " + (e.message || e));
    }
  }
  return lines;
}

// --- Premiere reading ---------------------------------------------------------

function ticksToSeconds(tick) {
  if (tick == null) return 0;
  if (typeof tick.seconds === "number") return tick.seconds;
  if (typeof tick.ticks === "number") return tick.ticks / TICKS_PER_SECOND;
  if (typeof tick === "number") return tick / TICKS_PER_SECOND;
  return 0;
}

async function safe(fn) {
  try {
    return await fn();
  } catch (e) {
    return null;
  }
}

async function firstSelectedAudioItem(sequence) {
  if (typeof sequence.getSelection === "function") {
    const selection = await sequence.getSelection();
    const items = selection && (await safe(() => selection.getTrackItems?.()));
    if (items && items.length) {
      for (const item of items) {
        const type = await safe(() => item.getMediaType?.());
        if (!type || String(type).toLowerCase().includes("audio")) return item;
      }
      return items[0];
    }
  }
  const trackCount = await safe(() => sequence.getAudioTrackCount?.());
  for (let t = 0; t < (trackCount || 0); t++) {
    const track = await safe(() => sequence.getAudioTrack?.(t));
    const items = track && (await safe(() => track.getTrackItems?.(1, false)));
    for (const item of items || []) {
      if (await safe(() => item.isSelected?.())) return item;
    }
  }
  return null;
}

async function readSelectedClip(infoEl) {
  if (!ppro) throw new Error("premierepro module unavailable (check Premiere version).");
  const project = await ppro.Project.getActiveProject();
  const sequence = await project.getActiveSequence();
  if (!sequence) throw new Error("No active sequence. Open a sequence first.");

  const item = await firstSelectedAudioItem(sequence);
  if (!item) throw new Error("No audio clip selected. Click an audio clip in the timeline.");

  const projectItem = await item.getProjectItem();
  const filePath = await safe(() => projectItem.getMediaFilePath?.());
  if (!filePath) throw new Error("Could not read the clip's media file path.");

  const inPoint = ticksToSeconds(await safe(() => item.getInPoint?.()));
  const outPoint = ticksToSeconds(await safe(() => item.getOutPoint?.()));
  const startTime = ticksToSeconds(await safe(() => item.getStartTime?.()));

  if (infoEl) {
    infoEl.textContent =
      `File: ${filePath}\nClip: ${inPoint.toFixed(2)}–${outPoint.toFixed(2)}s, on timeline at ${startTime.toFixed(2)}s`;
  }
  return { filePath, clipStart: inPoint, clipDuration: Math.max(0, outPoint - inPoint), timelineStart: startTime };
}

async function currentPlayhead() {
  try {
    const project = await ppro.Project.getActiveProject();
    const sequence = await project.getActiveSequence();
    return ticksToSeconds(await safe(() => sequence.getPlayerPosition?.())) || 0;
  } catch (e) {
    return 0;
  }
}

// --- Placing text blocks ------------------------------------------------------

async function placeBlocks(items, statusEl) {
  if (!state.templatePath) {
    const m = "Pick a text template first — the 'Text template…' button at the bottom (one time).";
    statusEl.textContent = m;
    log(m);
    return;
  }
  log(`Placing ${items.length} text block(s)…`);
  let placed = 0;
  for (let i = 0; i < items.length; i++) {
    try {
      await placeTextGraphic(items[i].text, items[i].start, items[i].end, 0);
      placed++;
      if (i === 0) {
        log("First block placed. MOGRT params: " + lastParamInfo);
        safe(() => callHelper("/diag", { text: "MOGRT params: " + lastParamInfo }));
      }
    } catch (e) {
      log(`Block ${i + 1} failed: ${e.message || e}`);
      safe(() => callHelper("/diag", { text: "INSERT ERROR: " + (e.message || e) }));
      break;
    }
  }
  statusEl.textContent = `Placed ${placed}/${items.length} block(s).`;
  if (placed === 0) {
    log("Insertion needs the template + the API method names — click 'Log API methods' and send me the log.");
  }
}

let lastParamInfo = ""; // structure of the last inserted MOGRT, for debugging

async function placeTextGraphic(text, startSeconds, endSeconds, videoTrackIndex) {
  if (!ppro) throw new Error("premierepro module unavailable");
  if (!state.templatePath) throw new Error("Choose a .mogrt text template first.");

  const project = await ppro.Project.getActiveProject();
  const sequence = await project.getActiveSequence();
  const editor = await ppro.SequenceEditor.getEditor(sequence);
  const tick = secondsToTick(startSeconds);

  // 1) Insert the .mogrt onto the timeline. Returns the created track items.
  let items = null;
  const doInsert = () => {
    items = editor.insertMogrtFromPath(state.templatePath, tick, videoTrackIndex, 0);
  };
  try {
    await project.lockedAccess(doInsert);
  } catch (e) {
    doInsert(); // fallback: call directly if a lock isn't required
  }
  if (!items || !items.length) throw new Error("insertMogrtFromPath returned no track items");

  // 2) Find the editable text parameter and set its value via a transaction.
  const found = await findTextParam(items[0]);
  lastParamInfo = found.info.join(", ");
  if (!found.param) throw new Error("inserted, but no text parameter found. params: " + lastParamInfo);

  const keyframe = found.param.createKeyframe(text);
  const action = found.param.createSetValueAction(keyframe, true);
  const ok = await project.executeTransaction((compoundAction) => {
    compoundAction.addAction(action);
  }, "SinhalaSTT subtitle");
  if (ok === false) throw new Error("executeTransaction failed to set the text");
}

async function findTextParam(item) {
  const out = { param: null, info: [] };
  const chain = await safe(() => item.getComponentChain?.());
  if (!chain) {
    out.info.push("no component chain");
    return out;
  }
  const compCount = (await safe(() => chain.getComponentCount?.())) || 0;
  for (let c = 0; c < compCount; c++) {
    const comp = await safe(() => chain.getComponentAtIndex?.(c));
    if (!comp) continue;
    const cname = (await safe(() => comp.getDisplayName?.())) || "comp" + c;
    const pCount = (await safe(() => comp.getParamCount?.())) || 0;
    for (let p = 0; p < pCount; p++) {
      const param = await safe(() => comp.getParam?.(p));
      if (!param) continue;
      const val = await safe(() => param.getStartValue?.());
      out.info.push(`${cname}[${p}]:${typeof val}`);
      if (!out.param && typeof val === "string") out.param = param;
    }
  }
  return out;
}

function secondsToTick(seconds) {
  if (ppro && ppro.TickTime && typeof ppro.TickTime.createWithSeconds === "function") {
    return ppro.TickTime.createWithSeconds(seconds);
  }
  return Math.round(seconds * TICKS_PER_SECOND);
}

// --- Tab actions --------------------------------------------------------------

async function createFromScript() {
  const status = $("text-status");
  const text = $("script-text").value.trim();
  if (!text) {
    status.textContent = "Paste a script first.";
    return;
  }
  let lines = splitToLines(text, $("script-mode").value).filter((s) => s.trim());
  if (!lines.length) {
    status.textContent = "Nothing to add.";
    return;
  }
  lines = await fmConvertLines(lines);
  const secs = parseFloat($("script-seconds").value) || 1;
  const start0 = await currentPlayhead();
  await placeBlocks(
    lines.map((t, i) => ({ start: start0 + i * secs, end: start0 + (i + 1) * secs, text: t })),
    status
  );
}

async function audioCreate() {
  const status = $("audio-status");
  try {
    status.textContent = "Reading selected clip…";
    const clip = await readSelectedClip($("clip-info"));
    status.textContent = "Getting timing from audio…";
    const data = await callHelper("/timing", {
      filePath: clip.filePath,
      mode: $("audio-mode").value,
      clipStart: clip.clipStart,
      clipDuration: clip.clipDuration,
    });
    const blocks = data.blocks || [];
    if (!blocks.length) {
      status.textContent = "No speech blocks detected.";
      return;
    }
    const script = $("audio-script").value.trim();
    let texts = blocks.map((b) => b.text);
    if (script) texts = await fmConvertLines(splitToLines(script, $("audio-mode").value));
    await placeBlocks(
      blocks.map((b, i) => ({
        start: clip.timelineStart + b.start,
        end: clip.timelineStart + b.end,
        text: texts[i] || "",
      })),
      status
    );
  } catch (e) {
    status.textContent = "Error: " + (e.message || e);
    log("Audio error: " + (e.message || e));
  }
}

async function aiCreate() {
  const status = $("ai-status");
  try {
    const key = $("api-key").value.trim();
    if (!key) {
      status.textContent = "Paste your Gemini API key first.";
      return;
    }
    status.textContent = "Reading selected clip…";
    const clip = await readSelectedClip($("ai-clip-info"));
    status.textContent = "Asking Gemini (can take a minute)…";
    const data = await callHelper("/ai", {
      filePath: clip.filePath,
      apiKey: key,
      clipStart: clip.clipStart,
      clipDuration: clip.clipDuration,
    });
    const blocks = data.blocks || [];
    if (!blocks.length) {
      status.textContent = "No captions returned.";
      return;
    }
    const texts = await fmConvertLines(blocks.map((b) => b.text));
    await placeBlocks(
      blocks.map((b, i) => ({
        start: clip.timelineStart + b.start,
        end: clip.timelineStart + b.end,
        text: texts[i] || "",
      })),
      status
    );
  } catch (e) {
    status.textContent = "Error: " + (e.message || e);
    log("AI error: " + (e.message || e));
  }
}

// --- Template (remembered) ----------------------------------------------------

async function chooseTemplate() {
  try {
    const fs = require("uxp").storage.localFileSystem;
    const file = await fs.getFileForOpening({ types: ["mogrt"] });
    if (!file) return;
    state.templatePath = file.nativePath;
    try {
      localStorage.setItem("sttTemplate", file.nativePath);
    } catch (e) {
      /* ignore */
    }
    $("template-info").textContent = "Template: " + file.nativePath;
    log("Template chosen and remembered.");
  } catch (e) {
    log("Could not choose template: " + (e.message || e));
  }
}

function loadTemplate() {
  try {
    const saved = localStorage.getItem("sttTemplate");
    if (saved) {
      state.templatePath = saved;
      $("template-info").textContent = "Template: " + saved;
    }
  } catch (e) {
    /* ignore */
  }
}

// --- Diagnostics --------------------------------------------------------------

function methodNames(obj) {
  if (!obj) return null;
  const names = new Set();
  let cur = obj;
  while (cur && cur !== Object.prototype && cur !== Function.prototype) {
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
  return Array.from(names).sort();
}

function methodsLine(label, obj) {
  const names = methodNames(obj);
  return `${label}: ${names ? names.join(", ") || "(none)" : "<null>"}`;
}

async function logApiDiagnostics() {
  const lines = [];
  const D = (m) => {
    lines.push(m);
    log(m);
  };

  if (!ppro) {
    D("premierepro module not available.");
    return;
  }
  D("=== SinhalaSTT API diagnostics (Premiere) ===");
  D("premierepro: " + Object.keys(ppro).sort().join(", "));

  // Static factories/utilities most likely to hold the insert-MOGRT call.
  for (const cls of ["SequenceEditor", "ComponentFactory", "SequenceUtils", "ProjectUtils", "Utils"]) {
    if (ppro[cls]) D(methodsLine(cls + " (static)", ppro[cls]));
  }

  const project = await safe(() => ppro.Project.getActiveProject());
  const sequence = project && (await safe(() => project.getActiveSequence()));
  D(methodsLine("project", project));
  D(methodsLine("sequence", sequence));

  // Try to obtain a SequenceEditor (the editing entry point in v26 UXP).
  let editor =
    (await safe(() => ppro.SequenceEditor.getEditor?.(sequence))) ||
    (await safe(() => ppro.SequenceEditor.createSequenceEditor?.(sequence))) ||
    (await safe(() => sequence && sequence.getEditor?.()));
  D(methodsLine("sequenceEditor", editor));

  if (sequence) {
    const item = await firstSelectedAudioItem(sequence);
    D(methodsLine("trackItem", item));
    if (item) D(methodsLine("projectItem", await safe(() => item.getProjectItem())));
  }
  D("=== end diagnostics ===");

  // Send to the helper, which writes them to a file the assistant can read.
  try {
    await callHelper("/diag", { text: lines.join("\n") });
    log("(Diagnostics sent to the helper — saved to premiere-uxp/helper/last_diagnostics.txt)");
  } catch (e) {
    log("(Could not send diagnostics to helper: " + (e.message || e) + ")");
  }
  // Also try the clipboard as a fallback.
  try {
    await navigator.clipboard.setContent({ "text/plain": lines.join("\n") });
  } catch (e) {
    /* ignore */
  }
}

// --- Wire up ------------------------------------------------------------------

function showTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpanel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + name));
}

function init() {
  if (!ppro) log("Note: premierepro module not loaded — Premiere may be too old, or this is outside Premiere.");
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));

  $("create-from-script").addEventListener("click", createFromScript);
  $("audio-create").addEventListener("click", audioCreate);
  $("ai-create").addEventListener("click", aiCreate);
  $("choose-template").addEventListener("click", chooseTemplate);
  $("diagnostics").addEventListener("click", logApiDiagnostics);
  $("helper-status").addEventListener("click", () => checkHelper(true));

  loadTemplate();
  checkHelper(true);
  setInterval(() => checkHelper(false), 4000);
}

document.addEventListener("DOMContentLoaded", init);
