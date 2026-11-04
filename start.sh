#!/usr/bin/env bash
# Starts Responsive Viewer and opens it in your browser.
# Extra options are passed along, e.g.:  ./start.sh --port 8080

set -euo pipefail
cd "$(dirname "$0")"

if [ -x .venv/bin/python ]; then
  exec .venv/bin/python app.py "$@"
elif [ -x .venv/Scripts/python.exe ]; then
  exec .venv/Scripts/python.exe app.py "$@"
else
  echo "Responsive Viewer isn't installed yet. Run:  bash install.sh" >&2
  exit 1
fi
