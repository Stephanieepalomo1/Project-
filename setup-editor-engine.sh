#!/usr/bin/env bash
# Sets up the editable-CapCut engine (VectCut) for the Reels Editing Engine.
# Safe + idempotent: it skips anything already done and never deletes your setup.
# Run it once. After that you only ever use start-editor.command.

set -euo pipefail
cd "$(dirname "$0")"   # always run from this folder

# Which machine is this, and borrow the engine's own shims so the tools resolve.
# _path-shim repairs PATH for THIS process (on Windows the tools are usually installed but invisible
# to a fresh shell); _python3-shim handles Windows' fake `python3` and gives us venv_py, which knows
# a venv keeps its interpreter in Scripts/ on Windows and bin/ everywhere else.
case "$(uname -s)" in
  Darwin)               OSK=mac;   THIS_MACHINE="Mac" ;;
  MINGW*|MSYS*|CYGWIN*) OSK=win;   THIS_MACHINE="PC" ;;
  *)                    OSK=other; THIS_MACHINE="computer" ;;
esac
_R="$(cd ../../.. && pwd)"
[ -f "$_R/scripts/_path-shim.sh" ]    && . "$_R/scripts/_path-shim.sh"
[ -f "$_R/scripts/_python3-shim.sh" ] && . "$_R/scripts/_python3-shim.sh"

echo ""
echo "Setting up your editing engine. This takes a few minutes and you only do it once."
echo ""

# 1) FFmpeg (required by the engine for anything that touches video)
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "-> The video engine (FFmpeg) is needed and was not found on your $THIS_MACHINE."
  if [ "$OSK" = win ]; then
    echo "   Install it with this, then run this again:"
    echo "       winget install -e --id Gyan.FFmpeg"
    echo "   (Close and reopen Git Bash afterwards so it can be found.)"
    exit 1
  elif command -v brew >/dev/null 2>&1; then
    echo "   Installing it with Homebrew..."
    brew install ffmpeg
  else
    echo "   Please install Homebrew first from https://brew.sh, then run this again."
    exit 1
  fi
else
  echo "-> FFmpeg is here. Good."
fi

# 2) Python workspace (create only if it does not already exist)
if [ ! -d "venv-capcut" ]; then
  echo "-> Building the engine's private workspace..."

  # The engine's code uses modern type hints (str | None) that need Python 3.10 or newer.
  # Stock macOS ships Python 3.9, which would build a workspace that crashes on import.
  # Find a good-enough Python before building the workspace. We test each candidate's ACTUAL
  # version at runtime (not its name), so 3.13 / 3.14 / any future release all qualify, and we
  # look in the real Homebrew locations even when Homebrew is installed but not yet on PATH — a
  # common fresh-Mac state where ~/.zprofile never sourced `brew shellenv`, so `python3` still
  # points at stock 3.9 and a perfectly good brew python sits unseen on disk.
  PYBIN=""
  # Pull Homebrew onto PATH for this lookup if it is installed but not resolving (does not touch
  # the user's shell files; the venv we build below is pinned to the interpreter we pick anyway).
  for brewbin in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if command -v "$brewbin" >/dev/null 2>&1 || [ -x "$brewbin" ]; then
      eval "$("$brewbin" shellenv 2>/dev/null)" 2>/dev/null || true
      break
    fi
  done
  # Candidates: whatever `python3` resolves to now, plus every versioned python3.NN in the usual
  # Homebrew / local locations (globbed, so newer releases are found without editing this list).
  # An unmatched glob stays literal and is safely skipped by the command -v + version check.
  for cand in python3 python py \
              "${LOCALAPPDATA:-}/Programs/Python/Python3"*/python.exe \
              "/c/Python3"*/python.exe \
              /opt/homebrew/bin/python3.* /opt/homebrew/opt/python@*/bin/python3.* \
              /usr/local/bin/python3.* /usr/local/opt/python@*/bin/python3.*; do
    if command -v "$cand" >/dev/null 2>&1 && \
       "$cand" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
      PYBIN="$cand"
      break
    fi
  done

  if [ -z "$PYBIN" ]; then
    echo ""
    echo "   The engine needs Python 3.10 or newer, and none was found on your $THIS_MACHINE."
    echo "   Please install it, then run this again:"
    if [ "$OSK" = win ]; then
      echo "       winget install -e --id Python.Python.3.12"
      echo "   (Then close and reopen Git Bash.)"
    else
      echo "       brew install python"
      echo "   (If you do not have Homebrew yet, get it from https://brew.sh first.)"
    fi
    exit 1
  fi

  echo "   Using $PYBIN ($("$PYBIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))."
  "$PYBIN" -m venv venv-capcut
else
  echo "-> Workspace already exists. Keeping it."
fi

# 3) Install the engine's tools (requirements.txt ONLY -- never pyproject, never pyJianYingDraft)
echo "-> Installing the engine's tools..."
# venv_py finds the interpreter wherever this OS put it (Scripts/ on Windows, bin/ elsewhere),
# and pip is invoked THROUGH it so there is no second path to get wrong.
VPY="$(venv_py "$PWD/venv-capcut")"
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet -r requirements.txt
echo "   Tools installed."

# 4) config.json pointed at your own computer (only write it if missing, never overwrite yours)
if [ ! -f "config.json" ]; then
  echo "-> Writing the local config (points the engine at your own computer)..."
  cat > config.json <<'JSON'
{
  "draft_profile": "capcut_legacy",
  "is_capcut_env": true,
  "draft_domain": "http://localhost:9001",
  "port": 9001,
  "preview_router": "/draft/downloader",
  "is_upload_draft": false
}
JSON
else
  echo "-> config.json already here. Keeping it."
fi

# 5) CapCut projects folder check (needs CapCut opened at least once)
if [ "$OSK" = win ]; then
  CAPFOLDER="$LOCALAPPDATA/CapCut/User Data/Projects/com.lveditor.draft"
else
  CAPFOLDER="$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft"
fi
if [ ! -d "$CAPFOLDER" ]; then
  echo ""
  echo "   One quick thing: open the CapCut app once so it can create its projects folder,"
  echo "   then you are all set. (You do not have to do anything in CapCut, just open it once.)"
fi

echo ""
echo "============================================"
echo " Editing engine ready."
if [ "$OSK" = win ]; then
  echo " To turn it on: double-click  start-editor.bat"
else
  echo " To turn it on: double-click  start-editor.command"
fi
echo " (or run:  \"$(venv_py "$PWD/venv-capcut")\" capcut_server.py )"
echo "============================================"
echo ""
