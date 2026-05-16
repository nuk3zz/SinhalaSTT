#!/bin/zsh

cd "$(dirname "$0")"

APP="/Applications/SinhalaSTT.app"

if [ ! -d "$APP" ]; then
  APP="$HOME/Applications/SinhalaSTT.app"
fi

if [ -d "$APP" ]; then
  open "$APP"
  (
    sleep 0.4
    osascript -e 'tell application "Terminal" to close front window' >/dev/null 2>&1
  ) &
  exit 0
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "Python environment not found."
  echo "Please open Terminal in this folder and run:"
  echo "python3 -m venv .venv"
  echo "source .venv/bin/activate"
  echo "pip install -r requirements.txt"
  read "?Press Enter to close..."
  exit 1
fi

".venv/bin/python" "scripts/ui.py"
