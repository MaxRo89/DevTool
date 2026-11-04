#!/usr/bin/env bash
# Responsive Viewer installer for macOS, Linux and Windows (Git Bash).
# Usage:  bash install.sh
# Windows users without Git Bash can double-click install.bat instead.

set -euo pipefail

cd "$(dirname "$0")"

bold=$'\033[1m'; red=$'\033[31m'; green=$'\033[32m'; reset=$'\033[0m'
step() { printf '\n%s==> %s%s\n' "$bold" "$1" "$reset"; }
fail() { printf '\n%sError:%s %s\n\n' "$red" "$reset" "$1" >&2; exit 1; }

# ---------- Detect the operating system ----------
case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  MINGW*|MSYS*|CYGWIN*) OS=windows ;;
  *) OS=unknown ;;
esac

# ---------- Find Python 3.9 or newer ----------
step "Looking for Python 3.9 or newer"

PYTHON=""
for candidate in python3 python "py -3"; do
  # "py -3" is the Python launcher on Windows. The python.exe that ships
  # with Windows only opens the Microsoft Store, so we check it really runs.
  if $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  case "$OS" in
    mac)
      fail "Python 3.9+ was not found.
  Install it from https://www.python.org/downloads/macos/
  (or, with Homebrew: brew install python), then run this script again." ;;
    linux)
      fail "Python 3.9+ was not found. Install it with your package manager:
  Ubuntu / Debian:  sudo apt install python3 python3-venv
  Fedora:           sudo dnf install python3
  Arch:             sudo pacman -S python
  Then run this script again." ;;
    windows)
      fail "Python 3.9+ was not found.
  Install it from https://www.python.org/downloads/windows/
  and check \"Add python.exe to PATH\" during setup.
  Or run: winget install Python.Python.3.12
  Then open a new terminal and run this script again." ;;
    *)
      fail "Python 3.9+ was not found. Install it from https://www.python.org/downloads/" ;;
  esac
fi

echo "Using $($PYTHON --version 2>&1) ($PYTHON)"

# ---------- Virtual environment ----------
step "Creating a private environment in .venv"

if [ "$OS" = windows ]; then
  VENV_PY=".venv/Scripts/python.exe"
else
  VENV_PY=".venv/bin/python"
fi

if [ ! -x "$VENV_PY" ]; then
  if ! $PYTHON -m venv .venv; then
    rm -rf .venv
    if [ "$OS" = linux ]; then
      fail "Couldn't create the environment. On Ubuntu / Debian install the venv module:
  sudo apt install python3-venv
  Then run this script again."
    fi
    fail "Couldn't create the environment with '$PYTHON -m venv'."
  fi
else
  echo "Already exists, reusing it."
fi

# ---------- Dependencies ----------
step "Installing dependencies (Flask, requests)"
"$VENV_PY" -m pip install --disable-pip-version-check --quiet -r requirements.txt \
  || fail "Couldn't install the dependencies. Check your internet connection and try again."

chmod +x start.sh 2>/dev/null || true

# ---------- Done ----------
if [ "$OS" = windows ]; then
  START_CMD="start.bat   (or double-click it)"
else
  START_CMD="./start.sh"
fi

printf '\n%sResponsive Viewer is installed.%s\n\n' "$green" "$reset"
echo "To open it later, run:  $START_CMD"
echo

if [ -t 0 ]; then
  read -r -p "Open it now? [Y/n] " answer
  case "${answer:-y}" in
    [Nn]*) ;;
    *) exec "$VENV_PY" app.py ;;
  esac
fi
