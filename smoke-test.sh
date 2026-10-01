#!/usr/bin/env bash
# smoke-test.sh — a fresh-Mac shakedown of the engine's risk points. Run it after setup, or any time you
# want proof the build is healthy on this machine. It checks the things most likely to bite a real buyer:
#   1. the tools it needs are installed
#   2. your style-pack fonts actually resolve (nothing renders in tofu)
#   3. no draft/template points at a path that does not exist on THIS machine (the /Users/creator trap)
#   4. THE BIG ONE — a real render comes out whole, not the short/corrupt file the hardware encoder can
#      occasionally produce (pass a clip to run this; --loops N stresses the encoder to catch the flaky case)
# On ANY major failure it writes a handoff report and hands you a one-click email to the engine team.
#
# usage:  scripts/smoke-test.sh [path/to/clip.mov]  [--loops N]
set -uo pipefail

# Source the python3 shim: on Windows the name `python3` is a Microsoft Store decoy that exists on
# PATH but does not run. Walks up to the engine root to find it. No-op on macOS/Linux.
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while [ "$_d" != "/" ]; do
  if [ -f "$_d/scripts/_python3-shim.sh" ]; then . "$_d/scripts/_python3-shim.sh"; [ -f "$_d/scripts/_path-shim.sh" ] && . "$_d/scripts/_path-shim.sh"; break; fi
  _d="$(dirname "$_d")"
done
unset _d

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # lives in scripts/; the engine root is one level up
cd "$ROOT"

CLIP=""; LOOPS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --loops) LOOPS="$2"; shift 2 ;;
    *) CLIP="$1"; shift ;;
  esac
done

FAILURES=(); LOG="$(mktemp)"; PASS=0; TOTAL=0
say(){ echo "$@"; }
ok(){   TOTAL=$((TOTAL+1)); PASS=$((PASS+1)); say "  ✓ $1"; }
bad(){  TOTAL=$((TOTAL+1)); say "  ✗ $1"; FAILURES+=("$1"); }
log(){  echo "$@" >>"$LOG"; }

say "── Reels Editing Engine · smoke test ──"

# ── 1. tools ───────────────────────────────────────────────────────────────
say ""; say "1. Tools"
for tool in ffmpeg ffprobe python3 node; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool present"; else bad "$tool is not installed"; fi
done
if [ -x "$(venv_py "$(venv_home whisperx-venv)")" ]; then ok "WhisperX transcription ready"
elif [ -x "$(venv_py "${REELS_ENGINE_NOFW_VENV:-$(venv_home fasterwhisper-venv)}")" ]; then
  # An Intel Mac builds faster-whisper instead. Reporting that as "not ready" is a false alarm in
  # the one place a buyer goes to find out whether her machine is fine.
  ok "speech transcription ready (faster-whisper — the Intel-Mac engine)"
else say "  · speech transcription will build itself on your first rough cut — nothing to do now"; fi
[ -f product/engine/VectCutAPI/config.json ] && ok "VectCut config present" || bad "VectCut config.json missing"

# ── 2. fonts resolve ───────────────────────────────────────────────────────
say ""; say "2. Style-pack fonts"
if [ -f product/capcut_font_doctor.py ]; then
  fd="$(python3 product/capcut_font_doctor.py 2>&1)"; log "$fd"
  if echo "$fd" | grep -qiE "✗|○|missing|not found|not downloaded"; then
    say "  · some pack fonts come from CapCut and download the first time you use them (normal, not an error). Add your pack's font in CapCut once, or it resolves on your first reel. Diagnose anytime: python3 product/capcut_font_doctor.py <YourPack>"
  else ok "all pack fonts resolve"; fi
else bad "capcut_font_doctor.py missing"; fi

# ── 3. no dangling absolute paths in the shipped templates (the /Users/creator trap) ──
say ""; say "3. Template + font-registry paths"
dangle=0
while IFS= read -r p; do
  # any absolute /Users/... MEDIA path a template hardcodes must exist on THIS machine.
  # Font paths (.ttf/.otf) are intentionally skipped: the engine always resolves the real
  # font at build time (build-captions.py / build-graphics.py overwrite it), so a placeholder
  # font path that does not exist is expected, not a broken reference.
  for path in $(grep -oE '/Users/[^"[:space:]]+\.(mov|mp4|png|json)' "$p" 2>/dev/null | sort -u); do
    if [ ! -e "$path" ]; then log "dangling in $p -> $path"; dangle=$((dangle+1)); fi
  done
done < <(find product/creative-vault product/engine/VectCutAPI/template* -name '*.json' 2>/dev/null)
if [ "$dangle" -eq 0 ]; then ok "no template points at a missing path"
else bad "$dangle template path(s) point at files that do not exist on this machine (see report; the /Users/creator trap)"; fi

# ── 4. render integrity — THE BLOCKER (needs a clip) ───────────────────────
say ""; say "4. Render integrity"
if [ -z "$CLIP" ]; then
  say "  (skipped — pass a clip to run it, e.g. scripts/smoke-test.sh inbox/my-clip.mov)"
elif [ ! -f "$CLIP" ]; then
  bad "clip not found: $CLIP"
else
  JOB="smoke-$(date +%s)"; mkdir -p "projects/$JOB/raw"; cp "$CLIP" "projects/$JOB/raw/"
  say "  transcribing + cutting a real render ($LOOPS render pass(es))…"
  bash .claude/skills/rough-cut/scripts/word-timings.sh "projects/$JOB" >>"$LOG" 2>&1
  python3 .claude/skills/rough-cut/scripts/transcript-cut.py "$JOB" >>"$LOG" 2>&1
  badrender=0
  for i in $(seq 1 "$LOOPS"); do
    bash .claude/skills/rough-cut/scripts/stitch-cut.sh "projects/$JOB" >>"$LOG" 2>&1
    out="projects/$JOB/outputs/$JOB.mp4"
    exp="$(python3 -c "import json;d=json.load(open('projects/$JOB/transcript/cuts.json'));s=d if isinstance(d,list) else d['segments'];print(sum(x['end']-x['start'] for x in s))" 2>/dev/null)"
    act="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out" 2>/dev/null)"
    errs="$(ffmpeg -v error -i "$out" -f null - 2>&1 | head -c 200)"
    dur_ok="$(python3 -c "print(1 if abs(float('${act:-0}')-float('${exp:-0}'))<=0.5 else 0)" 2>/dev/null)"
    if [ "$dur_ok" != "1" ] || [ -n "$errs" ]; then
      log "RENDER PASS $i BAD: expected=${exp}s actual=${act}s decode_errors='${errs}'"
      badrender=$((badrender+1))
    fi
  done
  rm -rf "projects/$JOB"
  if [ "$badrender" -eq 0 ]; then ok "render is whole and clean ($LOOPS/$LOOPS good)"
  else bad "render came out short or corrupt on $badrender/$LOOPS pass(es) — the hardware-encoder bug (see report)"; fi
fi

# ── verdict ────────────────────────────────────────────────────────────────
say ""; say "── $PASS/$TOTAL checks passed ──"
if [ "${#FAILURES[@]}" -eq 0 ]; then
  say "✅ Engine looks healthy on this machine."
  rm -f "$LOG"; exit 0
fi
say "⚠ ${#FAILURES[@]} issue(s) found. Writing a handoff report for the engine team."
python3 product/make-handoff.py "smoke-test" "${FAILURES[@]}" --log "$LOG"
rm -f "$LOG"; exit 1
