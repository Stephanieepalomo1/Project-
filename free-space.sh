#!/usr/bin/env bash
# free-space.sh — win back disk space from projects/ without ever touching footage or a finished reel.
#
# One rule: only something that can be made again from what stays on disk may go. Footage, everything in
# outputs/, audio, assets, broll, thumbnails and the hf-graphics build itself (build.py, compositions/, its
# .sh scripts, parts.json, PROJECT.md) are never in scope. The build is the real progress; the cache it
# produces is not. What does go, in the order it is looked for:
#   raw/archive/                     earlier copies of a source clip that has since been swapped out
#   work-*/                          frame dumps the renderer leaves behind
#   node_modules/                    packages that ended up inside a job folder
#   hf-graphics/renders/             the graphics render cache
#   hf-graphics/assets/*-base.mp4    footage slices cut for the graphics build
#   renders/*.mp4                    older passes; anything named final or graphics stays, and so does the
#                                    highest -vN
#
# It removes nothing unless told to. On its own it only adds up what it would win back.
#   scripts/free-space.sh            # how much would come back?
#   scripts/free-space.sh --apply    # remove it

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/projects"   # this file is in scripts/, so ../projects
case "${1:-}" in
  --apply) APPLY=1 ;;
  *)       APPLY=0 ;;
esac

if [[ ! -d "$ROOT" ]]; then echo "No projects folder at $ROOT"; exit 1; fi

freed_kb=0
dropped=""   # every path already counted, one per line: anything inside one of them is not counted again
kb_of() { du -sk "$1" 2>/dev/null | cut -f1; }
mb()    { echo "$1" | awk '{printf "%.0fM", $1/1024}'; }
gb()    { echo "$1" | awk '{printf "%.2f GB", $1/1024/1024}'; }

# Is <path> inside something this sweep already dropped? A dry run removes nothing, so without this the files
# inside a dropped folder (hf-graphics/renders/ first as a whole, then again in the older-renders pass) were
# counted twice and the total came out far too high.
inside_dropped() {   # inside_dropped <path>
  local d
  while IFS= read -r d; do
    [[ -n "$d" ]] || continue
    case "$1/" in "$d"/*) return 0 ;; esac
  done <<< "$dropped"
  return 1
}

# Report one item and, when asked, remove it. It always ends on `return 0`: under `set -e` a nonzero status
# from here would stop the whole sweep.
drop() {   # drop <path> <why>
  local path="$1" why="$2" kb
  inside_dropped "$path" && return 0
  # A folder du cannot read all of (a locked subfolder, say) is left exactly as it is, with a plain note,
  # and the sweep carries on. du failing used to end the whole sweep on the spot, silently, with exit 1.
  if ! kb=$(kb_of "$path"); then
    printf '  %-7s %s\n' "skipped" "${path#"$ROOT"/}  (could not read all of it, so it was left in place)"
    return 0
  fi
  kb=${kb:-0}
  : $(( freed_kb += kb ))
  dropped="$dropped$path
"
  printf '  %-7s %s\n' "$(mb "$kb")" "${path#"$ROOT"/}  ($why)"
  if (( APPLY )); then rm -rf "$path"; fi
  return 0
}

# Hand each match of a find expression to drop as find produces it, so an --apply run removes items while
# the search is still walking.
each() {   # each <why> <find expression...>
  local why="$1" hit
  shift
  while IFS= read -r hit; do drop "$hit" "$why"; done < <(find "$ROOT" "$@")
}

# One renders/ folder. Anything named final or graphics stays, and so does the highest -vN; the other
# passes go. A folder with a single render, or with nothing recognizable in it, is left exactly as it is.
thin() {   # thin <renders dir>
  local dir="$1" f name n clips=() named=0 top="" top_n=-1
  # A while-read loop rather than mapfile, which needs bash 4; macOS still ships 3.2.
  while IFS= read -r f; do clips+=("$f"); done < <(find "$dir" -maxdepth 1 -type f -name '*.mp4')
  [[ ${#clips[@]} -le 1 ]] && return 0
  for f in "${clips[@]}"; do
    name=$(basename "$f")
    case "$name" in *final*|*graphics*) named=1 ;; esac
    if [[ "$name" =~ -v([0-9]+)\.mp4$ ]]; then
      n=$((10#${BASH_REMATCH[1]}))   # base 10: -v010 is ten, and -v08 is eight rather than an error
      (( n > top_n )) && { top_n=$n; top="$f"; }
    fi
  done
  [[ $named -eq 0 && -z "$top" ]] && return 0
  for f in "${clips[@]}"; do
    case "${f##*/}" in *final*|*graphics*) continue ;; esac
    [[ "$f" == "$top" ]] && continue
    drop "$f" "older render"
  done
  return 0
}

echo "=== raw/archive — superseded clip versions ==="
each "replaced source clip" -type d -path '*/raw/archive'

echo "=== work-* scratch left by the renderer ==="
each "renderer scratch" -type d -name 'work-*' -prune

echo "=== node_modules inside job folders ==="
each "reinstalls on demand" -type d -name node_modules -prune

echo "=== hf-graphics render cache and footage slices (build.py makes them again) ==="
# Both come back from the build in the same folder (./setup-assets.sh && ./render-all.sh), as each job's
# hf-graphics/PROJECT.md explains. The small source files beside them are never in scope here.
each "render cache, rebuildable" -type d -path '*/hf-graphics/renders'
each "footage slice, rebuildable" -type f -path '*/hf-graphics/assets/*-base.mp4'

echo "=== older renders (final, graphics and the highest vN stay) ==="
while IFS= read -r dir; do thin "$dir"; done < <(find "$ROOT" -type d -name renders)

echo
total=$(gb "$freed_kb")
if (( APPLY )); then
  echo "Won back $total."
else
  echo "DRY RUN — $total would come back. Add --apply to actually delete."
fi
