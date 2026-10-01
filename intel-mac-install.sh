#!/usr/bin/env bash
# intel-mac-install.sh — install the prerequisites on a Mac where Homebrew cannot serve us.
#
# Two kinds of Mac land here (scripts/_mac-arch.sh → mac_install_route = direct):
#   1. A true Intel Mac. Homebrew's installer aborts on anything that is not arm64.
#   2. An Apple-chip Mac on a macOS older than Homebrew supports (MAC_BREW_OLDEST, 15 today). Homebrew
#      has no ready-made packages there, so every `brew install` would compile for hours or fail.
# The name is historical (the Intel route came first); skills and docs point at it, so it stays.
# Each tool here comes straight from its own official build, for this Mac's chip.
#
#   ./scripts/intel-mac-install.sh ffmpeg   # ffmpeg + ffprobe, static builds for this chip, no password
#   ./scripts/intel-mac-install.sh node     # downloads Node's own .pkg and opens it
#   ./scripts/intel-mac-install.sh uv       # uv's official installer script
#   ./scripts/intel-mac-install.sh all
#
# Everything lands in ~/.local/bin, which needs NO password. /usr/local/bin would need sudo on a
# fresh Intel Mac (root-owned until Homebrew chowns it), and a password prompt is the single thing
# this whole route exists to avoid. _path-shim.sh already looks in ~/.local/bin, so the engine finds
# these without the buyer editing a PATH.
#
# Node is the one exception: it installs system-wide through Apple's own installer UI, which asks for
# her password in a normal Mac window, not blind in a terminal. That is a friendlier moment than
# Homebrew ever was, and there is no user-local Node .pkg to use instead.
set -uo pipefail

_d="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$_d/scripts/_mac-arch.sh"

BIN="$MAC_INTEL_BIN"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/intel-mac-install.XXXXXX")"

if [ -t 1 ]; then G=$(tput setaf 2); R=$(tput setaf 1); Y=$(tput setaf 3); B=$(tput bold); N=$(tput sgr0)
else G=; R=; Y=; B=; N=; fi

say()  { printf "  %s\n" "$*"; }
good() { printf "  ${G}✓${N} %s\n" "$*"; }
bad()  { printf "  ${R}✗${N} %s\n" "$*" >&2; }

# ── Recording what actually happened ────────────────────────────────────────
#
# There is no Intel Mac on this side of the engine. Every fact about how this route behaves in the
# real world has to come home from a buyer's machine, and a buyer cannot be asked to narrate a
# terminal. So each step records itself: what was attempted, where it came from, how long it took,
# whether it worked, and what version landed. `product/make-handoff.py hardware-diagnostic` reads
# this file, and SHE decides whether to send it. Nothing here is transmitted by this script.
#
# A FAILED step is the valuable one. Failures are recorded with the same care as successes.
ROUTE_LOG="$_d/_local/install-route.json"
ROUTE_STEPS=""

_route_step() {  # _route_step <tool> <source> <seconds> <exit> <version> <landed>
  # json_str (scripts/_mac-arch.sh) — NOT python3: on the fresh Intel Mac this runs on there is no Python
  # yet, and asking /usr/bin/python3 opens Apple's developer-tools dialog instead of answering.
  _esc() { json_str "${1:-}"; }
  # The report is scoped to hardware and timings. A path is useful (it says which route ran) but the
  # account name in it is not ours to collect, so $HOME always becomes "~" before anything is written.
  _rd() { printf '%s' "${1:-}" | sed "s#^$HOME#~#"; }
  set -- "$1" "$2" "$3" "$4" "$5" "$(_rd "${6:-}")"
  ROUTE_STEPS="${ROUTE_STEPS:+$ROUTE_STEPS,}{\"tool\":$(_esc "$1"),\"source\":$(_esc "$2"),\"seconds\":${3:-0},\"exit\":${4:-0},\"version\":$(_esc "$5"),\"landed\":$(_esc "$6")}"
}

_route_write() {
  mkdir -p "$(dirname "$ROUTE_LOG")" 2>/dev/null || return 0
  {
    printf '{"when":"%s","arch_class":"%s","macos":"%s","chip":"%s",' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${CLASS:-unknown}" "$(sw_vers -productVersion 2>/dev/null)" "$(mac_cpu_brand)"
    printf '"cpu_physical_cores":%s,"cpu_logical_cores":%s,' \
      "$(sysctl -n hw.physicalcpu 2>/dev/null || echo 0)" "$(sysctl -n hw.logicalcpu 2>/dev/null || echo 0)"
    printf '"bin":"%s","steps":[%s]}\n' "$(printf '%s' "$BIN" | sed "s#^$HOME#~#")" "$ROUTE_STEPS"
  } > "$ROUTE_LOG" 2>/dev/null || true
}
trap '_route_write; rm -rf "$TMP"' EXIT

# Wall-clock seconds, integer, portable (no `date +%s%N` on macOS).
_now() { date +%s; }

# ── Reading the two download indexes without Python ─────────────────────────
#
# Both lookups run BEFORE Python is on the machine: ffmpeg is the first step of `all`, and `node` can be
# asked for on its own. On a fresh Intel Mac the only python3 is Apple's placeholder, which opens the
# "install the developer tools?" dialog and answers nothing, so reading these through `python3 -c` made
# both installs fail at their first line. Both documents are small and regular, so tr + sed + grep read
# them, and print nothing at all for anything they do not recognise.

# evermeet.cx's /ffmpeg/info/<tool>/release -> the zip's download URL. JSON may write "/" as "\/"; that is
# turned back into a plain "/" here, so the URL works either way.
_evermeet_zip_url() {
  tr -d '\n\r' \
    | sed -n 's/.*"zip"[[:space:]]*:[[:space:]]*{[^}]*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | sed 's#\\/#/#g'
}

# nodejs.org's dist/index.json -> the newest LTS release that ships a macOS .pkg (v22.21.1, say). The file is
# a list of releases, newest first, each one a flat object whose "lts" is false or the release's codename;
# splitting at every "}" puts one release on each line however the file happens to be wrapped.
_node_lts_pkg_version() {
  tr -d '\n\r' | tr '}' '\n' \
    | grep -E '"lts"[[:space:]]*:[[:space:]]*("[^"]|true)' | grep '"osx-x64-pkg"' | head -1 \
    | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

# Same index, newest release of ONE major line (22, say) that ships a macOS .pkg. Needed because the
# newest LTS is not always one this Mac can run: Node 24 needs macOS 13.5 (see mac_node_line), and
# installing it on 13.4 or older leaves a node that refuses to start. The "version" field is the only
# thing matched, so an "lts" of false (a Current release in that line) never sneaks in either: only
# even-numbered majors are LTS, and those are the only lines mac_node_line ever asks for.
_node_line_pkg_version() {  # _node_line_pkg_version <major>
  tr -d '\n\r' | tr '}' '\n' \
    | grep -E "\"version\"[[:space:]]*:[[:space:]]*\"v$1\\." | grep '"osx-x64-pkg"' | head -1 \
    | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'
}

# Refuse to run on the wrong machine. On an Apple-chip Mac that Homebrew still supports, the normal
# Homebrew path is right and much better; on a Rosetta'd terminal the fix is a checkbox, not this script.
CLASS="$(mac_arch_class)"
case "$CLASS" in
  arm64)
    if [ "$(mac_install_route)" != direct ]; then
      bad "This is an Apple Silicon Mac on a macOS Homebrew supports. Use the normal setup (Homebrew)."
      exit 2
    fi ;;
  rosetta)
    bad "This is an Apple Silicon Mac, but this terminal is running under Rosetta."
    say "Fix it once instead of installing Intel tools: quit Terminal, find it in Applications > Utilities,"
    say "File > Get Info, UNTICK \"Open using Rosetta\", reopen it, and run setup again."
    exit 2 ;;
  "")
    bad "Not a Mac. This script is only for Intel Macs."
    exit 2 ;;
esac

if ! mac_intel_supported; then
  bad "macOS $(sw_vers -productVersion) is older than this route supports (macOS 11 Big Sur is the floor)."
  say "Below Big Sur the speech tools would all have to be pinned back several years at once, and that"
  say "combination has never been tested here. Say so plainly rather than shipping a second dead end."
  exit 2
fi

mkdir -p "$BIN"

# ── ffmpeg / ffprobe ────────────────────────────────────────────────────────
# Intel: evermeet.cx publishes the long-standing static Intel macOS builds of ffmpeg and ffprobe, as
# single self-contained binaries in a zip. Its JSON endpoint reports the current release.
# Apple chip: evermeet is Intel-only (it would run, slowly, through Rosetta). ffmpeg.martin-riedl.de
# publishes static arm64 builds with a stable "latest release" redirect, one binary per zip. VETTED
# 2026-09-30 on 9.0.2: native arm64, LC_BUILD_VERSION minos 12.0, links only /System and /usr/lib,
# Developer ID signed (Team KU3N25YGLU), and carries every encoder and filter the engine calls
# (libx264, libx265, h264_videotoolbox, aac, libmp3lame, flac, prores_ks, qtrle, png, libvpx; plus
# drawtext and subtitles, which the Homebrew build lacks). Neither source hardcodes a version.
install_ffmpeg() {
  for tool in ffmpeg ffprobe; do
    _t="$(_now)"
    if [ "$CLASS" = arm64 ]; then
      _src="ffmpeg.martin-riedl.de"; _want=arm64
      say "fetching $tool (Apple chip build)…"
      url="https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/$tool.zip"
    else
      _src="evermeet.cx"; _want=x86_64
      say "fetching $tool (Intel build)…"
      url="$(curl -fsSL -m 60 "https://evermeet.cx/ffmpeg/info/$tool/release" | _evermeet_zip_url)"
    fi
    if [ -z "$url" ]; then _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: could not read the $tool download URL from $_src"; bad "could not read the $tool download URL from $_src"; return 1; fi
    if ! curl -fsSL -m 600 -o "$TMP/$tool.zip" "$url"; then _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: download failed: $url"; bad "download failed: $url"; return 1; fi
    if ! unzip -qo "$TMP/$tool.zip" -d "$TMP"; then _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: could not unzip $tool"; bad "could not unzip $tool"; return 1; fi
    [ -f "$TMP/$tool" ] || { _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: not in zip"; bad "$tool not found inside the zip"; return 1; }

    # Verify it is built for THIS chip before putting it on her PATH. A wrong-arch binary here would
    # fail later with "bad CPU type" (or run crawling under Rosetta), mid-edit, which reads as a broken engine.
    if ! file "$TMP/$tool" | grep -q "$_want"; then
      _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: wrong architecture"
      bad "$tool downloaded but is not an $_want binary: $(file -b "$TMP/$tool")"; return 1
    fi
    chmod +x "$TMP/$tool"
    # macOS quarantines anything downloaded and refuses to run it until it is cleared. Without this
    # the very first ffmpeg call dies with a Gatekeeper dialog instead of transcoding.
    xattr -d com.apple.quarantine "$TMP/$tool" 2>/dev/null || true
    mv -f "$TMP/$tool" "$BIN/$tool"
    _v="$("$BIN/$tool" -version 2>/dev/null | head -1 | cut -c1-40)"
    # It has to RUN here, not just download: a binary built for a newer macOS than this one dies on its
    # first call. Caught now, it is a clear message; caught at the first reel, it is a broken engine.
    if [ -z "$_v" ]; then
      _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 1 "" "FAILED: installed but does not run on macOS $(sw_vers -productVersion 2>/dev/null)"
      bad "$tool installed but will not run on this Mac"; return 1
    fi
    _route_step "$tool" "$_src" "$(( $(_now) - _t ))" 0 "$_v" "$BIN/$tool"
    good "$tool → $BIN/$tool  ($_v)"
  done
}

# ── node ────────────────────────────────────────────────────────────────────
# nodejs.org's macOS .pkg is universal (arm64 + x64), so one download serves both chips.
# This downloads it and opens it; Apple's installer UI does the rest and asks for her password there.
# The LINE is picked for this macOS (mac_node_line): the newest LTS, or Node 22 below macOS 13.5.
install_node() {
  _t="$(_now)"
  _line="$(mac_node_line)"
  if [ "$_line" = lts ]; then
    say "finding the current Node LTS…"
    ver="$(curl -fsSL -m 60 https://nodejs.org/dist/index.json | _node_lts_pkg_version)"
  else
    say "finding Node $_line (the newest Node that runs on macOS $(sw_vers -productVersion 2>/dev/null))…"
    ver="$(curl -fsSL -m 60 https://nodejs.org/dist/index.json | _node_line_pkg_version "$_line")"
  fi
  url=""; [ -n "$ver" ] && url="https://nodejs.org/dist/$ver/node-$ver.pkg"
  if [ -z "${url:-}" ]; then
    _route_step node nodejs.org "$(( $(_now) - _t ))" 1 "" "FAILED: no LTS with a macOS installer"
    bad "could not find a Node LTS with a macOS installer"; return 1
  fi
  say "downloading Node $ver…"
  if ! curl -fsSL -m 900 -o "$TMP/node.pkg" "$url"; then
    _route_step node nodejs.org "$(( $(_now) - _t ))" 1 "" "FAILED: download"
    bad "download failed: $url"; return 1
  fi
  # Keep it somewhere she can find it again if she closes the installer.
  mkdir -p "$HOME/Downloads"
  mv -f "$TMP/node.pkg" "$HOME/Downloads/node-$ver.pkg"
  _route_step node nodejs.org "$(( $(_now) - _t ))" 0 "$ver" "~/Downloads/node-$ver.pkg (installer opened, not yet run)"
  good "downloaded → ~/Downloads/node-$ver.pkg"
  say "${B}Opening it now.${N} Click through the installer and enter your Mac password when it asks."
  say "That password box is a normal Mac window — this is the only password in the whole setup."
  open "$HOME/Downloads/node-$ver.pkg" 2>/dev/null || say "Open it yourself from your Downloads folder."
}

# ── uv ──────────────────────────────────────────────────────────────────────
# uv's own installer ships x86_64 and aarch64 macOS builds and installs to ~/.local/bin without sudo.
# uv then provides Python too (`uv python install 3.11`), which is what replaces `brew install python`.
install_uv() {
  _t="$(_now)"
  say "installing uv (the transcriber helper)…"
  if curl -LsSf -m 600 https://astral.sh/uv/install.sh | sh; then
    _route_step uv astral.sh "$(( $(_now) - _t ))" 0 "$("$BIN/uv" --version 2>/dev/null)" "$BIN/uv"
    good "uv installed → $BIN/uv"
    say "Reopen the terminal before using it, or run: export PATH=\"\$HOME/.local/bin:\$PATH\""
  else
    _route_step uv astral.sh "$(( $(_now) - _t ))" 1 "" "FAILED: installer script"
    bad "uv install failed"; return 1
  fi
}

# ── python 3.11 + Pillow ────────────────────────────────────────────────────
#
# `brew install python` has no Intel equivalent, and it does not need one: uv already manages
# interpreters, and python-build-standalone publishes an x86_64-apple-darwin CPython 3.11. That is
# the same interpreter the transcriber venv is built against, so the buyer ends up on one Python
# instead of two. Pillow then comes from its own Intel wheel — check-setup.sh tests `import PIL`,
# not a command, so it has to land in the Python that actually runs.
install_python() {
  _t="$(_now)"
  UV="$(command -v uv || echo "$BIN/uv")"
  if [ ! -x "$UV" ]; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: uv missing, install uv first"
    bad "uv is not installed yet — run this script with 'uv' first."; return 1
  fi
  say "installing Python 3.11 (managed by uv, no Homebrew)…"
  # --default also writes plain `python3` / `python` shims next to uv, which is what check-setup.sh
  # and every script in the engine actually look for. Without it uv installs `python3.11` only, and
  # `python3` stays missing on a Mac that has no Homebrew Python — setup would report success and
  # then fail on the first caption.
  if ! "$UV" python install 3.11 --default >&2; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: uv python install 3.11 --default"
    bad "could not install Python 3.11"; return 1
  fi
  _py="$("$UV" python find 3.11 2>/dev/null)"
  if [ -z "$_py" ] || [ ! -x "$_py" ]; then
    _route_step python3 uv "$(( $(_now) - _t ))" 1 "" "FAILED: installed but could not be located"
    bad "Python 3.11 installed but could not be found afterwards"; return 1
  fi
  _route_step python3 "uv-managed" "$(( $(_now) - _t ))" 0 "$("$_py" -V 2>&1)" "uv python 3.11 (+ python3 shim)"
  good "Python 3.11 ready ($("$_py" -V 2>&1))"

  _t="$(_now)"
  say "installing Pillow (the caption renderer)…"
  # NOT `uv pip install --python <interpreter>`: uv refuses to install into a bare managed
  # interpreter ("Consider creating a virtual environment"), and the engine needs Pillow in the
  # interpreter itself, because check-setup.sh tests `import PIL` through whichever python3 runs.
  # scripts/pip-install.py already exists for exactly this — it installs into the interpreter that
  # runs it and handles uv's externally-managed refusal. (Caught on a real run; the obvious uv
  # command looks right and fails.)
  if "$_py" "$_d/scripts/pip-install.py" pillow >&2; then
    _route_step pillow pypi "$(( $(_now) - _t ))" 0 "$("$_py" -c 'import PIL;print(PIL.__version__)' 2>/dev/null)" "uv python 3.11"
    good "Pillow ready"
  else
    _route_step pillow pypi "$(( $(_now) - _t ))" 1 "" "FAILED: pip-install.py pillow"
    bad "Pillow did not install"; return 1
  fi
}

rc=0
case "${1:-all}" in
  ffmpeg|ffprobe)   install_ffmpeg || rc=1 ;;
  node)             install_node   || rc=1 ;;
  uv)               install_uv     || rc=1 ;;
  python|python3)   install_python || rc=1 ;;
  pillow)           install_python || rc=1 ;;
  all)              install_ffmpeg || rc=1
                    install_uv     || rc=1
                    install_python || rc=1
                    install_node   || rc=1 ;;   # last: it hands the screen to Apple's installer UI
  *) bad "unknown tool: $1 (want: ffmpeg | node | uv | python | all)"; exit 2 ;;
esac

printf "\n"
if [ "$rc" -eq 0 ]; then
  say "${G}${B}Done.${N} Reopen the terminal, then run ./check-setup.sh to confirm."
else
  say "${Y}Something above did not finish.${N} Re-run this — it is safe to run twice — and if it still"
  say "fails, the full route is written down in product/INTEL-MAC-ROUTE.md."
fi
exit "$rc"
