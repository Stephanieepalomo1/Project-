#!/usr/bin/env bash
# name-final.sh — the last step of a job: leave outputs/ holding one unmistakable file to post.
#
#   scripts/name-final.sh <job>            # print the plan, change nothing
#   scripts/name-final.sh <job> --apply    # carry it out
#
# A finished job's outputs/ usually holds several .mp4 passes, and only one of them is the reel. This picks
# that one, names it <job>.final.mp4, deletes the passes it replaced and drops a copy in Downloads ready to
# upload. The clean cut (<job>.mp4), the transcript and the whole hf-graphics/ build (build.py,
# compositions/, parts.json, PROJECT.md) stay exactly where they are, because reopening the job needs them.
# Rebuildable caches (renders/, work-* scratch) are free-space.sh's job; run scripts/free-space.sh --apply straight
# after and the job is clean and shipped.

set -euo pipefail

ENGINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # this file sits in scripts/, so the root is ..

# The job is the first argument, and --apply may sit in either of the first two places. "--apply" on its
# own is a flag, never a job name.
APPLY=0
for word in "${1:-}" "${2:-}"; do
  if [[ "$word" == "--apply" ]]; then APPLY=1; fi
done
JOB="${1:-}"
if [[ "$JOB" == "--apply" ]]; then JOB=""; fi

# check-ship.sh runs this with no arguments and requires a line that starts with a lowercase "usage:".
# Change that prefix and the ship gate fails, so the release zip never builds.
if [[ -z "$JOB" ]]; then echo "usage: scripts/name-final.sh <job> [--apply]"; exit 1; fi

OUT="$ENGINE/projects/$JOB/outputs"
if [[ ! -d "$OUT" ]]; then echo "Job '$JOB' has no outputs/ folder at $OUT"; exit 1; fi

CUT="$JOB.mp4"             # the clean cut: never a candidate, never removed
REEL="$JOB.final.mp4"      # the deliverable
REEL_PATH="$OUT/$REEL"

size_of() { du -h "$1" 2>/dev/null | cut -f1; }
say()     { printf '  %-7s %s\n' "$1" "$2"; }               # say <VERB> <the rest of the line>
newer()   { [[ -z "$2" || "$1" -nt "$2" ]]; }               # newer <file> <best so far, maybe empty>
# The words that say what KIND of pass a file is (final, draft) are read from the part of its name after the
# job's name, when it has one. Otherwise a job called final-cut makes every pass look final, and one called
# draft-day or first-draft-tips makes every pass look like a draft.
ofjob()   { [[ "$(basename "$1")" == "$JOB"* ]]; }          # the file name starts with the job's
kind_of() { local b; b="$(basename "$1")"; if ofjob "$1"; then printf '%s' "${b#"$JOB"}"; else printf '%s' "$b"; fi; }
named()   { [[ "$(kind_of "$1")" == *"$2"* ]]; }             # named <path> <word>: the kind part holds it

printf '=== finalize: %s ===\n' "$JOB"

# Every .mp4 in outputs/ except the clean cut and the deliverable itself (an earlier run may already have made
# that one; it is weighed on its own below). Both are matched by their exact names, so a job name holding [ ]
# or * can never make the clean cut look like a pass. A <name>.mp4 the rough cut wrote a <name>.transcript.json
# beside is a clean cut too (a job folder renamed after its cut was made, _kajabi holding kajabi.mp4): never a
# candidate, never removed. A while-read loop, since mapfile needs bash 4 and macOS still ships 3.2.
passes=() cuts=()
[[ -f "$OUT/$CUT" ]] && cuts+=("$OUT/$CUT")
while IFS= read -r f; do
  name="$(basename "$f")"
  [[ "$name" == "$CUT" || "$name" == "$REEL" ]] && continue
  if [[ -f "$OUT/${name%.mp4}.transcript.json" ]]; then cuts+=("$f"); continue; fi
  passes+=("$f")
done < <(find "$OUT" -maxdepth 1 -type f -name '*.mp4' | sort)

# A FRAGMENT is a short partial render (a hook preview, an intro test), never the reel: anything that runs
# less than half as long as the clean cut, or, with no cut to measure, half the longest pass. Lengths come
# from ffprobe; when they cannot be read (no ffprobe, not a video), nothing counts as a fragment.
# ffprobe may sit outside this shell's PATH (Homebrew in a non-login shell, winget's folders), so the engine's
# path shim finds it. The shim runs in a subshell with -e off and hands back only the repaired PATH: sourced
# straight into this `set -e` script, one of its "is this folder there?" tests failing would end the run.
if [[ -f "$ENGINE/scripts/_path-shim.sh" ]]; then
  _shim_path="$(set +e; . "$ENGINE/scripts/_path-shim.sh" >/dev/null 2>&1; printf '%s' "$PATH")" || _shim_path=""
  if [[ -n "$_shim_path" ]]; then PATH="$_shim_path"; fi
fi
ms_of() {   # ms_of <video>: its length in whole milliseconds, or nothing
  command -v ffprobe >/dev/null 2>&1 || return 0
  ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null \
    | awk 'NR == 1 && $1 + 0 > 0 { printf "%d", $1 * 1000 }' || true
}
ref_ms=""
for c in ${cuts[@]+"${cuts[@]}"}; do ref_ms="$(ms_of "$c")"; [[ -n "$ref_ms" ]] && break; done
lens=()
for f in ${passes[@]+"${passes[@]}"}; do
  m="$(ms_of "$f")"; lens+=("${m:-0}")
done
if [[ -z "$ref_ms" ]]; then
  for m in ${lens[@]+"${lens[@]}"}; do (( m > ${ref_ms:-0} )) && ref_ms="$m"; done
fi
frag=()
for m in ${lens[@]+"${lens[@]}"}; do
  if [[ -n "$ref_ms" ]] && (( m > 0 && m * 2 < ref_ms )); then frag+=(1); else frag+=(0); fi
done

# Which pass is the reel. A *draft* never is, and neither is a fragment. A *graphics* pass gets no special
# standing: graphics come before captions and music, so a later pass always supersedes it, and ranking
# graphics first is exactly how a graphics-only pass once got promoted over the finished captioned reel,
# which was then deleted as a leftover. Preference, newest first within each, ties going to the earlier name
# in sorted order:
#   1. a pass actually named final
#   2. a pass whose name starts with the job's, so a later -music, -captioned or -v2 beats an earlier
#      -graphics, and a loose fragment such as hook-v5.mp4 can never win
#   3. any other pass that is not a fragment
# When only fragments and drafts are here, nothing is promoted.
# (${a[@]+"${a[@]}"} keeps an empty array from tripping `set -u` on bash 3.2.)
best_final="" best_job="" best_any=""
i=0
for f in ${passes[@]+"${passes[@]}"}; do
  if ! named "$f" draft && [[ "${frag[$i]}" == 0 ]]; then
    if named "$f" final && newer "$f" "$best_final"; then best_final="$f"; fi
    if ofjob "$f" && newer "$f" "$best_job"; then best_job="$f"; fi
    if newer "$f" "$best_any"; then best_any="$f"; fi
  fi
  i=$((i + 1))
done
chosen="${best_final:-${best_job:-$best_any}}"

# A deliverable left by an earlier run gives way only to something strictly newer. An older pick must never
# overwrite a finished reel, and the one that does give way is moved into earlier-finals/ first, never lost.
promoted="" backup=""
if [[ -n "$chosen" ]] && { [[ ! -f "$REEL_PATH" ]] || [[ "$chosen" -nt "$REEL_PATH" ]]; }; then
  promoted="$chosen"
fi
if [[ -n "$promoted" && -f "$REEL_PATH" ]]; then
  say PROMOTE "$(basename "$promoted")  ->  $REEL   (newer than the current one, $(size_of "$promoted"))"
  stamp="$(date -r "$REEL_PATH" +%Y%m%d-%H%M%S 2>/dev/null || date +%Y%m%d-%H%M%S)"
  backup="earlier-finals/$JOB.final.$stamp.mp4"; n=2
  while [[ -e "$OUT/$backup" ]]; do backup="earlier-finals/$JOB.final.$stamp-$n.mp4"; n=$((n + 1)); done
  say BACKUP "$REEL  ->  $backup   (the one it replaces, kept in case, $(size_of "$REEL_PATH"))"
elif [[ -n "$promoted" ]]; then
  say PROMOTE "$(basename "$promoted")  ->  $REEL   ($(size_of "$promoted"))"
elif [[ -f "$REEL_PATH" ]]; then
  say KEEP "$REEL   (already the one to post, $(size_of "$REEL_PATH"))"
fi
if [[ -n "$promoted" ]] && (( APPLY )); then
  if [[ -n "$backup" ]]; then mkdir -p "$OUT/earlier-finals"; mv "$REEL_PATH" "$OUT/$backup"; fi
  mv -f "$promoted" "$REEL_PATH"
fi

# The file that stands for "the reel" when deciding whether a leftover is newer than it: after --apply the
# pick already sits at the deliverable's path, while in a dry run it has not moved yet.
ruler=""
if [[ -e "$REEL_PATH" ]]; then
  ruler="$REEL_PATH"
elif [[ -n "$promoted" && -e "$promoted" ]]; then
  ruler="$promoted"
fi

# Clear out the other passes, except the kinds that always stay:
#   - the pass that just became the reel
#   - anything else named final, which is odd enough that a person should look at it
#   - anything newer than the reel, which may be the real one if this picked wrong
#   - a fragment, when there is no reel at all: nothing has replaced it
i=0
for f in ${passes[@]+"${passes[@]}"}; do
  isfrag="${frag[$i]}"; i=$((i + 1))
  [[ "$f" == "$promoted" ]] && continue
  [[ -e "$f" ]] || continue
  name=$(basename "$f")
  if named "$f" final; then
    say KEEP "$name   (this one also looks final, so it stays; delete it yourself if it is dead)"
  elif [[ -n "$ruler" && "$f" -nt "$ruler" ]]; then
    say KEEP "$name   (newer than the reel, so it stays; promote it yourself if it is the real one)"
  elif [[ -z "$ruler" && "$isfrag" == 1 ]] && ! named "$f" draft; then
    say KEEP "$name   (a short preview, not the whole reel, so it stays)"
  else
    if named "$f" draft; then why="draft"; else why="replaced by a later render"; fi
    say DELETE "$name   ($why, $(size_of "$f"))"
    if (( APPLY )); then rm -f "$f"; fi
  fi
done

# Name what survived, so it is plain the job can still be reopened.
for c in ${cuts[@]+"${cuts[@]}"}; do say KEEP "$(basename "$c")   (clean cut, for re-editing, $(size_of "$c"))"; done
if [[ -f "$OUT/$JOB.transcript.json" ]]; then say KEEP "$JOB.transcript.json"; fi
for c in ${cuts[@]+"${cuts[@]}"}; do
  t="$(basename "$c" .mp4).transcript.json"
  [[ "$t" != "$JOB.transcript.json" && -f "$OUT/$t" ]] && say KEEP "$t"
done
if [[ -d "$ENGINE/projects/$JOB/hf-graphics" ]]; then
  say KEEP "hf-graphics/ build (build.py + compositions, so this can be reopened)"
fi

if [[ -z "$chosen" && ! -f "$REEL_PATH" ]]; then
  # name the clean cut that is actually here (a renamed job keeps its cut under the old name)
  note_cut="$CUT"
  if [[ ! -f "$OUT/$CUT" ]] && (( ${#cuts[@]} > 0 )); then note_cut="$(basename "${cuts[0]}")"; fi
  echo
  echo "  ⚠ There is no render here to promote. If $note_cut is itself the finished reel (a plain cut with no"
  echo "    graphics), copy it across: cp \"$OUT/$note_cut\" \"$OUT/$REEL\""
fi

# Where the ready-to-upload copy goes. REELS_EXPORT_DIR decides when it is set. Otherwise ~/Downloads, except
# under WSL2, where the Linux home's Downloads cannot be seen from Windows Explorer: there the Windows
# user's own Downloads is used whenever it can be found.
DEST="${REELS_EXPORT_DIR:-}"
if [[ -z "$DEST" ]]; then
  DEST="$HOME/Downloads"
  if grep -qi microsoft /proc/version 2>/dev/null; then
    win_home="$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')" 2>/dev/null || true)"
    if [[ -n "$win_home" && -d "$win_home/Downloads" ]]; then DEST="$win_home/Downloads"; fi
  fi
fi
COPIED=0
if [[ -f "$REEL_PATH" || -n "$promoted" ]]; then
  if (( ! APPLY )); then
    say EXPORT "$REEL  ->  $DEST/$REEL   (copy ready to upload)"
  elif [[ -d "$DEST" ]]; then
    if cp -f "$REEL_PATH" "$DEST/$REEL"; then
      COPIED=1
      say EXPORT "$REEL  ->  $DEST/$REEL   ($(size_of "$REEL_PATH"))"
    fi
  else
    echo "  · no Downloads folder on this machine, so nothing was copied there. Your reel is in outputs/."
  fi
fi

echo
if (( ! APPLY )); then
  echo "DRY RUN — nothing was touched. Add --apply to go ahead."
else
  echo "Done. The one to post: projects/$JOB/outputs/$REEL"
  if (( COPIED )); then echo "      Copy to upload: $DEST/$REEL"; fi
  echo "Next, win back the space the caches use:  scripts/free-space.sh --apply"
fi
