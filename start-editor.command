#!/usr/bin/env bash
# Double-click this to turn on your editing engine.
# Keep the window it opens open while you edit. Close it when you are done.

cd "$(dirname "$0")"

# Pull in the engine's shared shims (PATH repair + the macOS pyexpat/libexpat fix) so the double-click
# launcher starts the server the SAME way every other entry point does. Without this, setup can succeed
# and then the very first server start dies on the identical pyexpat ImportError setup just fixed.
_R="$(cd ../../.. && pwd)"
[ -f "$_R/scripts/_path-shim.sh" ]    && . "$_R/scripts/_path-shim.sh"
[ -f "$_R/scripts/_python3-shim.sh" ] && . "$_R/scripts/_python3-shim.sh"

# Already running? Don't start a second one. But only say "you're good" when the one running is
# THIS copy: a second copy of the engine (an old download still on) can hold the same port, and
# every build would quietly go through it.
if lsof -iTCP:9001 -sTCP:LISTEN >/dev/null 2>&1; then
  HERE="$(pwd -P)"
  THERE="$(curl -s --max-time 3 http://127.0.0.1:9001/engine_home 2>/dev/null || true)"
  case "$THERE" in /*) ;; *) THERE="" ;; esac   # a 404 page from an older engine is not a path
  if [ "$THERE" = "$HERE" ]; then
    echo "Your editing engine is already on (localhost:9001). You are good to go."
    echo "You can close this window."
    exit 0
  fi
  echo "Another editing engine is already running, so this one can't start."
  if [ -n "$THERE" ]; then
    echo "The one that's on is from a different folder:"
    echo "    $THERE"
  else
    echo "It's an older engine, from before your latest update or from another copy of the engine."
  fi
  echo ""
  echo "To fix it: close the engine window that is already open (or restart your computer), then double-click this again."
  exit 1
fi

if [ ! -x "venv-capcut/bin/python" ]; then
  echo "It looks like the engine is not set up yet."
  echo "Run setup-editor-engine.sh first (or just tell Claude 'set me up')."
  exit 1
fi

echo "Starting your editing engine..."
echo "Keep this window open while you edit. You'll see 'Running on ... 9001' when it's ready."
echo ""
exec ./venv-capcut/bin/python capcut_server.py
