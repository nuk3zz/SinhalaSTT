#!/bin/zsh
# Double-click this file to start the SinhalaSTT helper for the Premiere plugin.
# Leave the window open while you use the plugin. Close the window (or Ctrl+C) to stop.

cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo "Python environment not found at .venv/"
  echo "Open Terminal in the project folder and run:"
  echo "  python3 -m venv .venv"
  echo "  source .venv/bin/activate"
  echo "  pip install -r requirements.txt"
  read "?Press Enter to close..."
  exit 1
fi

echo "Starting SinhalaSTT helper..."
exec ".venv/bin/python" "premiere-uxp/helper/server.py"
