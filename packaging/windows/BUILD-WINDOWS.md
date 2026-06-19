# Building the Windows version of SinhalaSTT

You do **not** need a Windows computer. GitHub builds the app for you on its own
Windows servers, for free.

## The easy way (GitHub Actions — recommended)

1. Push your changes to the `main` branch on GitHub (or just edit a file on the
   GitHub website and commit).
2. Go to your repository on GitHub and click the **Actions** tab.
3. Open the latest **Build Windows App** run and wait for the green check (it
   takes a few minutes).
4. Scroll down to **Artifacts** and download `SinhalaSTT-Windows-x64`.
5. Inside is the portable app zip. Send that zip to your users — they unzip it
   and double-click `SinhalaSTT.exe`.

You can also start a build by hand: **Actions → Build Windows App → Run workflow**.

### Making an official release
Push a version tag and the zip is attached to a GitHub Release automatically:

```bash
git tag v0.2.3
git push origin v0.2.3
```

## What the workflow does for you
- Installs Python and the app's dependencies.
- Downloads `ffmpeg.exe` and `ffprobe.exe` (a stable GPL build from gyan.dev)
  into `vendor/ffmpeg/`.
- Creates the Windows `.ico` icon from `assets/icon-source.png`.
- Runs PyInstaller with `packaging/windows/SinhalaSTT.spec`.
- Zips the finished `dist/SinhalaSTT/` folder, including the FFmpeg license.

## Building manually on a real Windows PC (optional)
If you ever want to build on a Windows machine yourself:

```powershell
python -m pip install -r requirements.txt
python -m pip install pillow

# Put ffmpeg.exe and ffprobe.exe in vendor\ffmpeg\
#   download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

# Make the icon
python -c "from PIL import Image; Image.open('assets/icon-source.png').convert('RGBA').save('assets/SinhalaSTT.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

pyinstaller --noconfirm packaging\windows\SinhalaSTT.spec
```

The app appears in `dist\SinhalaSTT\`.

## How FFmpeg is found at runtime
`scripts/transcriber_core.py` (`find_tool`) looks for FFmpeg in this order:
1. The bundled copy shipped inside the app (`ffmpeg/` next to the resources).
2. Anything already on the system `PATH`.
3. The usual macOS/Linux install folders.

So the Windows build uses its own bundled FFmpeg and never needs the user to
install anything.
