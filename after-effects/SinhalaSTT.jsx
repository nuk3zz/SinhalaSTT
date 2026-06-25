// SinhalaSTT for After Effects - Text to Subtitles
// A dockable panel that turns a pasted/loaded script into timed text layers in
// the active composition. Sinhala is auto-converted to FM/DL legacy text.
// Pure ExtendScript, fully offline. Keep fm_engine.jsx next to this file.

(function (thisObj) {
  // --- Load the FM/DL + splitting engine (fm_engine.jsx, same folder) --------
  function loadEngine() {
    try {
      var here = File($.fileName).parent;
      var engineFile = File(here.fsName + "/fm_engine.jsx");
      if (!engineFile.exists) {
        return "fm_engine.jsx was not found next to SinhalaSTT.jsx. Keep both files together.";
      }
      $.evalFile(engineFile);
      if (typeof unicodeToFM !== "function" || typeof splitToLines !== "function") {
        return "fm_engine.jsx loaded but its functions are missing.";
      }
      return null;
    } catch (e) {
      return "Could not load fm_engine.jsx: " + e.toString();
    }
  }

  var engineError = loadEngine();

  // --- Create the text layers ------------------------------------------------
  function createSubtitleLayers(rawText, opts) {
    var comp = app.project.activeItem;
    if (!comp || !(comp instanceof CompItem)) {
      return "Open a composition first (double-click one so it's active), then try again.";
    }

    var lines = splitToLines(rawText, opts.mode);
    if (!lines || lines.length === 0) return "No text to add.";

    var isSinhala = containsSinhala(rawText);
    var useFm = opts.toFm && isSinhala;

    app.beginUndoGroup("SinhalaSTT subtitles");
    try {
      var start = comp.time; // begin at the current-time indicator
      for (var i = 0; i < lines.length; i++) {
        var display = useFm ? unicodeToFM(lines[i]) : lines[i];
        var t0 = start + i * opts.seconds;
        var t1 = t0 + opts.seconds;

        var layer = comp.layers.addText(display);
        var srcProp = layer.property("ADBE Text Properties").property("ADBE Text Document");
        var td = srcProp.value;
        td.resetCharStyle();
        td.text = display;
        if (opts.font && opts.font.length) {
          try { td.font = opts.font; } catch (eFont) {}
        }
        td.fontSize = opts.fontSize;
        td.fillColor = [1, 1, 1];
        td.applyFill = true;
        td.strokeColor = [0, 0, 0];
        td.strokeWidth = Math.max(1, opts.fontSize * 0.06);
        td.applyStroke = true;
        td.justification = ParagraphJustification.CENTER_JUSTIFY;
        srcProp.setValue(td);

        // Position near the bottom-center of the frame.
        layer.property("ADBE Transform Group").property("ADBE Position")
          .setValue([comp.width / 2, comp.height * 0.86]);
        layer.name = "Sub " + (i + 1);

        // Timing: set out point first so in > current-out never happens.
        layer.outPoint = t1;
        layer.inPoint = t0;
      }
    } catch (e) {
      app.endUndoGroup();
      return "Error creating layers: " + e.toString();
    }
    app.endUndoGroup();

    var msg = "Created " + lines.length + " text layer(s)";
    msg += useFm ? " (FM/DL legacy)." : (isSinhala ? " (Unicode)." : ".");
    msg += " Undo with Cmd/Ctrl+Z.";
    return msg;
  }

  // --- UI --------------------------------------------------------------------
  var MODE_VALUES = ["sentence", "1", "2", "3"];

  function buildUI(thisObj) {
    var win = (thisObj instanceof Panel)
      ? thisObj
      : new Window("palette", "SinhalaSTT", undefined, { resizeable: true });
    win.alignChildren = ["fill", "top"];
    win.spacing = 8;
    win.margins = 12;

    var title = win.add("statictext", undefined, "SinhalaSTT - Text to Subtitles");
    try { title.graphics.font = ScriptUI.newFont(title.graphics.font.name, "Bold", 15); } catch (e) {}

    var info = win.add("statictext", undefined,
      "Paste a script or open a .txt, choose the split, then add timed text layers to the active comp. Sinhala auto-converts to FM/DL.",
      { multiline: true });
    info.preferredSize.height = 42;

    var scriptBox = win.add("edittext", undefined, "", { multiline: true, scrollable: true });
    scriptBox.preferredSize = [320, 130];

    var fileRow = win.add("group");
    fileRow.alignment = ["left", "top"];
    var openBtn = fileRow.add("button", undefined, "Open .txt");

    var optRow = win.add("group");
    optRow.add("statictext", undefined, "Split:");
    var modeDd = optRow.add("dropdownlist", undefined, ["Sentences", "1 word", "2 words", "3 words"]);
    modeDd.selection = 0;
    optRow.add("statictext", undefined, "Each:");
    var secsBox = optRow.add("edittext", undefined, "1");
    secsBox.preferredSize.width = 44;
    optRow.add("statictext", undefined, "sec");

    var fontRow = win.add("group");
    var fmCheck = fontRow.add("checkbox", undefined, "Sinhala -> FM/DL");
    fmCheck.value = true;
    fontRow.add("statictext", undefined, "Font:");
    var fontBox = fontRow.add("edittext", undefined, "FMAbhaya");
    fontBox.preferredSize.width = 100;
    fontRow.add("statictext", undefined, "Size:");
    var sizeBox = fontRow.add("edittext", undefined, "60");
    sizeBox.preferredSize.width = 44;

    var createBtn = win.add("button", undefined, "Create text layers");

    var status = win.add("statictext", undefined,
      engineError ? ("Engine error: " + engineError) : "Layers start at the current-time indicator.",
      { multiline: true });
    status.preferredSize.height = 44;

    openBtn.onClick = function () {
      var f = File.openDialog("Choose a .txt script");
      if (f && f.open("r")) {
        f.encoding = "UTF-8";
        scriptBox.text = f.read();
        f.close();
        status.text = "Loaded " + f.name;
      }
    };

    createBtn.onClick = function () {
      if (engineError) { status.text = "Engine error: " + engineError; return; }
      var raw = scriptBox.text;
      if (!raw || !/\S/.test(raw)) { status.text = "Paste or open a script first."; return; }
      var seconds = parseFloat(secsBox.text);
      if (!(seconds > 0)) seconds = 1;
      var fontSize = parseFloat(sizeBox.text);
      if (!(fontSize > 0)) fontSize = 60;
      status.text = createSubtitleLayers(raw, {
        mode: MODE_VALUES[modeDd.selection.index],
        seconds: seconds,
        toFm: fmCheck.value,
        font: fontBox.text,
        fontSize: fontSize
      });
    };

    win.layout.layout(true);
    win.onResizing = win.onResize = function () { this.layout.resize(); };
    return win;
  }

  var ui = buildUI(thisObj);
  if (ui instanceof Window) { ui.center(); ui.show(); }
})(this);
