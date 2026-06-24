# PyInstaller spec for the Windows build of SinhalaSTT.
#
# This produces a self-contained "onedir" application folder:
#   dist/SinhalaSTT/SinhalaSTT.exe   (plus a _internal folder with everything else)
#
# FFmpeg and FFprobe are bundled, so the end user does NOT need to install
# Python, FFmpeg, or anything else. The whole dist/SinhalaSTT folder is zipped
# and shipped as the portable Windows app.
#
# Build (on Windows):
#   pyinstaller --noconfirm packaging/windows/SinhalaSTT.spec
#
# The GitHub Actions workflow downloads FFmpeg into vendor/ffmpeg/ and creates
# the .ico icon before running this spec.

from pathlib import Path

# SPECPATH is injected by PyInstaller and points to this file's folder.
PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ASSETS_DIR = PROJECT_ROOT / "assets"
FFMPEG_DIR = PROJECT_ROOT / "vendor" / "ffmpeg"
ICON_PATH = ASSETS_DIR / "SinhalaSTT.ico"

# Bundle the assets folder (fonts rules, icons, chevron, etc.).
datas = [(str(ASSETS_DIR), "assets")]

# Bundle FFmpeg / FFprobe into an "ffmpeg" subfolder that find_tool() searches.
missing_ffmpeg = []
for exe_name in ("ffmpeg.exe", "ffprobe.exe"):
    exe_path = FFMPEG_DIR / exe_name
    if exe_path.exists():
        datas.append((str(exe_path), "ffmpeg"))
    else:
        missing_ffmpeg.append(exe_name)

if missing_ffmpeg:
    # Don't fail silently: a build without FFmpeg would defeat the whole point.
    raise SystemExit(
        "Missing bundled FFmpeg binaries: "
        + ", ".join(missing_ffmpeg)
        + f"\nExpected them in: {FFMPEG_DIR}\n"
        "The GitHub Actions workflow downloads these automatically."
    )


a = Analysis(
    [str(SCRIPTS_DIR / "ui.py")],
    pathex=[str(SCRIPTS_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=["requests", "pypdf", "docx"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SinhalaSTT",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI app, no terminal window
    disable_windowed_traceback=False,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SinhalaSTT",
)
