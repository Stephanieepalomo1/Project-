#!/usr/bin/env bash
# check-setup.sh — can this computer run the engine yet? A read-only answer, with the fix beside each gap.
#
# It looks and it reports. It never installs, upgrades, deletes or configures anything. For every tool
# that is not on this machine yet it prints the one command that gets it, worked out for the machine that
# is actually running it: Homebrew lines on an Apple Silicon Mac, per-tool downloads on an Intel Mac,
# winget lines on Windows. Buyers paste those lines, and set-me-up hands them over exactly as printed, so
# every command below is a fixed string.
#
#   ./check-setup.sh
#
# The exit status is the verdict: 0 once every core item is in place, 1 while anything is left. On a new
# machine 1 is the expected answer, and set-me-up says so rather than calling it a failure.
#
# The speech side (WhisperX large-v3 and torch) is not checked or installed here. The rough cut builds that
# in its own venv the first time it runs.
set -uo pipefail

# The engine folder, from where this file sits. Looked up here, before anything below touches PATH, to find
# the engine's shell helpers, and again further down for every other path the checks use.
engine_dir() { cd "$(dirname "${BASH_SOURCE[0]}")" && pwd; }
SHIMS="$(engine_dir)/scripts"

# Repair PATH for THIS process before checking anything. On Windows the tools are usually installed
# but invisible to a fresh shell, and reporting an installed tool as missing sends a buyer off to
# reinstall something they already have. The shim writes nothing to the machine.
[ -f "$SHIMS/_path-shim.sh" ] && . "$SHIMS/_path-shim.sh"

# Which kind of Mac this is, from the one place that knows (scripts/_mac-arch.sh): arm64, an Apple
# Silicon Mac running translated under Rosetta, or a true Intel Mac. It decides every install line
# printed below, because Homebrew's installer now aborts on anything that is not arm64 — so on an
# Intel Mac every `brew install` hint would be a line that could not work.
MACCLASS=""
MACROUTE=""   # brew | direct | rosetta — the chip AND the macOS decide it (see mac_install_route)
if [ -f "$SHIMS/_mac-arch.sh" ]; then
  . "$SHIMS/_mac-arch.sh"
  MACCLASS="$(mac_arch_class)"
  MACROUTE="$(mac_install_route)"
fi

# What is running this: a Mac, Windows through Git Bash, or something the engine does not support.
platform() {   # platform <kernel name>  ->  OS (mac|win|other) and the OSLABEL shown in the heading
  case "$1" in
    MINGW*|MSYS*|CYGWIN*) OS=win   OSLABEL="Windows (Git Bash)" ;;
    Darwin)               OS=mac   OSLABEL="macOS" ;;
    *)                    OS=other OSLABEL="$1" ;;
  esac
}
platform "$(uname -s 2>/dev/null || echo unknown)"

# ── the install lines ──────────────────────────────────────────────────────────────────────────────
# winget's first run stops at a licence prompt and waits for a keypress. When Claude runs the line there is
# no keypress coming, so the install just sits there looking hung. These flags answer the prompt up front.
WINGET_FLAGS="-e --accept-source-agreements --accept-package-agreements --disable-interactivity"
winget_line() { echo "winget install $WINGET_FLAGS --id $1   (then open a NEW terminal)"; }

install_cmd() {   # install_cmd <ffmpeg|uv|node|python3|pillow>  ->  the line that installs it HERE
  # A Mac Homebrew cannot serve (a true Intel Mac, or an Apple-chip Mac on a macOS older than Homebrew
  # supports) gets its own routes. Those live in _mac-arch.sh, beside the installer that carries them
  # out, so the advice and the installer cannot drift apart.
  if [ "$MACROUTE" = direct ]; then mac_intel_hint "$1"; return; fi
  case "$OS" in
    mac)
      case "$1" in
        python3)               echo "brew install python" ;;
        ffmpeg|uv|node|pillow) echo "brew install $1" ;;
        *)                     echo "install $1" ;;
      esac ;;
    win)
      case "$1" in
        ffmpeg)  winget_line Gyan.FFmpeg ;;
        uv)      winget_line astral-sh.uv ;;
        node)    winget_line OpenJS.NodeJS.LTS ;;
        python3) winget_line Python.Python.3.12 ;;
        pillow)  echo "python scripts/pip-install.py pillow" ;;   # retries safely if uv manages this Python
        *)       echo "install $1" ;;
      esac ;;
    *) echo "install $1" ;;
  esac
}

# ── how a row looks ────────────────────────────────────────────────────────────────────────────────
# Colour only when a person is reading a terminal. Piped into a file (collect-report.sh does that), plain.
paint() {
  G="$(tput setaf 2)"; R="$(tput setaf 1)"; Y="$(tput setaf 3)"
  D="$(tput setaf 8)"; B="$(tput bold)";   N="$(tput sgr0)"
}
G= R= Y= D= B= N=
[ -t 1 ] && paint

REPO="$(engine_dir)"
missing=0          # core items still to install. The closing line and the exit status both come from it.
tally() { missing=$((missing + 1)); }

# Every row: a coloured mark, the label padded to 12, then the detail.
row()  { printf "  %s %-12s ${D}%s${N}\n" "$1" "$2" "$3"; }    # row <mark> <label> <detail>
ok()   { row "${G}✓${N}" "$1" "$2"; }
note() { row "${Y}!${N}" "$1" "$2"; }
todo() { note "$1" "$2"; tally; }                              # a note that counts toward what is left

# A tool that is not on this machine yet: the exact line that installs it, then what needs it.
#
# Ordinary gaps get a yellow dot, not a red cross. A fresh machine is a step not taken yet, not a defect,
# and a red cross on her very first minute reads as "something is broken": a tester whose laptop "kept
# telling me I needed to install stuff" tuned it out. The information is the same; only the alarm is gone.
# See CLAUDE.md, "never dress a normal state as a fault".
gap() {   # gap <mark> <label> <install key> <what needs it>
  printf "  %s %-12s ${Y}%s${N}  ${D}(needed by %s)${N}\n" "$1" "$2" "$(install_cmd "$3")" "$4"
  tally
}
need() {   # need <command> <label> <install key> <what needs it>
  if command -v "$1" >/dev/null 2>&1; then ok "$2" "$4"; else gap "${Y}•${N}" "$2" "$3" "$4"; fi
}

printf "\n${B}Reels Editing Engine — prerequisites${N}  ${D}(%s)${N}\n" "$OSLABEL"
printf "${D}  A checklist, not an error report. This installs nothing and changes nothing. A dot means\n"
printf "  that tool is not on this machine yet, with the command to get it.${N}\n\n"

if [ "$OS" = win ]; then
  printf "  ${D}Windows detected — run the engine from Git Bash (not PowerShell).${N}\n\n"
elif grep -qi microsoft /proc/version 2>/dev/null; then
  # WSL looks like Linux to uname. It is a Windows machine, and the engine runs on Windows itself.
  printf "  ${Y}This is WSL (Linux inside Windows).${N} The engine runs in ${B}Git Bash on Windows itself${N}, not inside WSL:\n"
  printf "    open ${B}Git Bash${N} from the Start menu (install it with: winget install -e --id Git.Git), go to this folder there, and run this again.\n\n"
elif [ "$OS" != mac ]; then
  printf "  ${Y}This engine supports macOS and Windows. Run it on one of those.${N}\n"
  printf "  ${Y}On Windows, open Git Bash (it comes with Git for Windows) and run this there, not in PowerShell or cmd.${N}\n\n"
fi

# ── Windows-only: two settings that fail silently and look like unrelated bugs later ──
if [ "$OS" = win ]; then
  # winget is how every install below happens. Windows 10 PCs from 2016-2019 can be missing it (it ships
  # with "App Installer" from the Store), and then every install line dies "command not found".
  if command -v winget >/dev/null 2>&1; then
    ok "winget" "Windows' built-in installer is here — the tools below install with it, no admin account needed"
    printf "    ${D}After each install, open a NEW Git Bash window (and restart Claude Code once) so the new tool is found.${N}\n"
  else
    printf "  ${R}✗${N} %-12s ${Y}%s${N}\n" "winget" "missing. Open the Microsoft Store, search \"App Installer\", install it, then close and reopen Git Bash."
    printf "    ${D}(direct link: ms-windows-store://pdp/?productid=9NBLGGH4NNS1). Nothing else below can install until this is in.${N}\n"
    tally
  fi
  if [ "${PYTHONUTF8:-}" = "1" ]; then
    ok "UTF-8 mode" "Python reads/writes UTF-8 — accents, curly quotes and emoji are safe"
  else
    note "UTF-8 mode" "NOT set. Run: setx PYTHONUTF8 1  and  setx PYTHONIOENCODING utf-8  then reopen this terminal."
    printf "    ${D}Without it, any caption, hook or brand-kit line with a curly quote, accent or emoji\n"
    printf "    crashes the step that reads it, and status symbols crash the step that prints them.${N}\n"
  fi
  # MSYS_NO_PATHCONV: Git Bash rewrites arguments that look like POSIX paths ("/v") into Windows paths
  # before a native .exe sees them, which turns the switch into garbage and makes this read as OFF on every PC.
  # reg prints a blank line and the key's name before the value line ("LongPathsEnabled REG_DWORD 0x1"), so
  # only the line carrying the value is kept; reading every line made this row fail on a PC that was set.
  LP="$(MSYS_NO_PATHCONV=1 reg query 'HKLM\SYSTEM\CurrentControlSet\Control\FileSystem' /v LongPathsEnabled 2>/dev/null | tr -d ' \r' | sed -n 's/.*0x//p')"
  if [ "$LP" = "1" ]; then
    ok "long paths" "Windows 260-character path limit lifted"
  else
    note "long paths" "Windows still caps paths at 260 characters. CapCut draft folders nest deep; a long user name or a deep project folder can fail mid-build with a confusing error."
  fi
  # Controlled Folder Access (Defender's ransomware guard) silently blocks Git Bash/node/python from
  # writing inside Documents/Desktop/Pictures/Videos/Music/OneDrive, and the error it throws looks
  # like a missing-file bug ("No such file or directory"), not a permissions one. Read the ACTUAL
  # state (not just a guess) and cross-check it against where this folder actually sits, so a work
  # or managed machine with CFA extended further isn't left guessing what a strange write failure
  # actually is. `Get-MpPreference` needs no admin rights; empty output just means it couldn't be
  # read (no Defender, or PowerShell blocked) — that's not itself a problem, just an unknown.
  CFA="$(powershell.exe -NoProfile -NonInteractive -Command '(Get-MpPreference).EnableControlledFolderAccess' 2>/dev/null | tr -d '[:space:]')"
  case "$REPO" in
    */Documents/*|*/Desktop/*|*/Pictures/*|*/Videos/*|*/Music/*|*/OneDrive/*|*/OneDrive\ -\ */*) CFA_RISK=1 ;;
    *) CFA_RISK=0 ;;
  esac
  # Backstop: `Get-MpPreference` can itself fail to answer — blocked execution policy, a managed/
  # corporate machine, third-party antivirus replacing Defender. An ACTUAL write-probe catches the real
  # symptom regardless of cause (CFA, a synced-folder lock, plain permissions) and turns a guess into an
  # observed fact when it fails.
  CFA_PROBE="$REPO/.ve-write-probe-$$"
  if { : > "$CFA_PROBE"; } 2>/dev/null; then
    rm -f "$CFA_PROBE"
    CFA_WRITABLE=1
  else
    CFA_WRITABLE=0
  fi
  if [ "$CFA_WRITABLE" -eq 0 ]; then
    printf "  ${R}✗${N} %-12s ${Y}%s${N}\n" "folder guard" "this folder is NOT writable right now — confirmed by an actual write test, not a guess."
    printf "    ${D}Very likely Windows Controlled Folder Access (Settings > Privacy & security > Windows Security > Virus\n"
    printf "    & threat protection > Manage ransomware protection), whether or not its exact state could be read above.\n"
    printf "    Move this folder to C:\\Users\\<you>\\Projects, or allow-list bash.exe/git.exe/node.exe/python.exe there.${N}\n"
    tally
  elif [ "$CFA" = "1" ] && [ "$CFA_RISK" -eq 1 ]; then
    note "folder guard" "Controlled Folder Access is ON and this folder sits somewhere it protects. Git Bash can reach this file (so bash.exe is allow-listed), but node and python are SEPARATE entries — a render or an edit can still fail later with \"No such file or directory\". Move the folder to C:\\Users\\<you>\\Projects, or allow-list bash.exe/git.exe/node.exe/python.exe: Windows Security > Virus & threat protection > Ransomware protection > Allow an app through Controlled folder access."
  elif [ "$CFA" = "1" ]; then
    ok "folder guard" "Controlled Folder Access is on, but this folder is outside the locations it protects"
  else
    note "folder guard" "a basic write test from this shell just passed, and Windows' own Controlled Folder Access state couldn't be read (no Defender, or PowerShell blocked — not itself a problem). If node or python still fail here later with a vague \"no such file or directory\" for a file that plainly exists, that is very likely CFA blocking THOSE programs specifically even though this shell writes fine. Keeping this folder in C:\\Users\\<you>\\Projects (never Documents/Desktop/Pictures/Videos/Music/OneDrive) avoids it either way."
  fi
fi

# ── Where the engine folder lives. A synced folder quietly evicts big video files. ──
# This used to be checked ONLY inside "set me up". Anyone who set up before that check existed was never
# told, and nothing ever looked again: a tester built her whole first reel from OneDrive\Desktop and her
# setup reported the location as fine, because she set up one version before the check was added. It runs
# here too now, so every run of this script re-checks, including for people who installed long ago.
# Same rules as set-me-up, kept in step with it.
ENGINE_HERE="$(cd "$(dirname "$0")" && pwd -P)"
SYNC=""
if [ "$OS" = win ]; then
  case "$ENGINE_HERE" in
    */OneDrive/*|*/OneDrive\ -\ */*) SYNC=onedrive ;;
    *) for _od in "${OneDrive:-}" "${OneDriveCommercial:-}"; do
         [ -n "$_od" ] || continue
         _odp="$(cygpath -u "$_od" 2>/dev/null)"
         case "$ENGINE_HERE" in "$_odp"/*) SYNC=onedrive ;; esac
       done ;;
  esac
elif [ "$OS" = mac ]; then
  case "$ENGINE_HERE" in
    "$HOME"/Documents/*|"$HOME"/Desktop/*)
      [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Documents" ] && SYNC=icloud ;;
  esac
fi
if [ "$SYNC" = onedrive ]; then
  note "folder" "This engine is inside OneDrive, which syncs it. When your drive fills up, OneDrive moves big video files off your computer and leaves a placeholder that looks real, and an edit stops partway through. Say \"move my engine\" and it moves the whole folder to C:\\Users\\<you>\\Projects. Your settings and brand kit go with it."
elif [ "$SYNC" = icloud ]; then
  note "folder" "This engine is in Desktop or Documents, which iCloud syncs. When your drive fills up, iCloud moves big video files off your Mac and leaves a placeholder, and an edit stops partway through. Say \"move my engine\" and it moves the whole folder to your home folder. Your settings and brand kit go with it."
elif [ "$OS" = win ] || [ "$OS" = mac ]; then
  ok "folder" "not in a synced folder, so your video files stay put"
fi

# ── Before any install line: can Homebrew even run on this Mac? ────────────────────────────────────
# The chip is settled first and admin rights second. Where Homebrew cannot run at all, asking whether the
# account is an administrator is the wrong question, and it sends her into System Settings to fix
# something that was never the problem.
rosetta_terminal() {
  printf "  ${Y}This Mac has an Apple Silicon chip, but this terminal runs under Rosetta${N} (Intel translation).\n"
  printf "    Everything below would install the slow Intel versions. One checkbox fixes it for good:\n"
  printf "    ${B}quit Terminal${N}, open ${B}Applications > Utilities${N}, click ${B}Terminal${N} once, ${B}File > Get Info${N},\n"
  printf "    UNTICK ${B}\"Open using Rosetta\"${N}, then reopen Terminal and run this again.\n"
  printf "    ${D}Worth doing now: on the right side of that checkbox is the full-speed, fully supported setup.${N}\n\n"
}
# No Homebrew line on this machine, ever. Homebrew's installer aborts before it even asks for a password
# ("Homebrew on macOS is only supported on Apple Silicon processors!"), so what people report is a password
# prompt that never came, not an error message.
intel_route() {
  if [ "$MACCLASS" = arm64 ]; then
    # An Apple-chip Mac below MAC_BREW_OLDEST. Homebrew's installer would warn, then sit on Apple's
    # Command Line Tools download, and every tool after it would compile for hours. Same no-Homebrew
    # route as an Intel Mac, with Apple-chip builds. Nothing about the engine itself is reduced.
    printf "  ${B}This Mac has an Apple chip and runs macOS %s${N}, so the setup skips Homebrew.\n" "$(sw_vers -productVersion 2>/dev/null)"
    printf "    Homebrew only supports macOS %s and newer now, so on this Mac its installer stalls. That is not a\n" "$MAC_BREW_OLDEST"
    printf "    broken install and it is not your machine. Everything installs from each tool's own download:\n"
    printf "    ${B}bash scripts/intel-mac-install.sh all${N}\n"
    printf "    ${D}No password except the Node installer, which asks in a normal Mac window. Every feature works.${N}\n"
    printf "    ${D}Optional, and the smoothest route: update macOS first (System Settings > General > Software Update,${N}\n"
    printf "    ${D}free on every Apple-chip Mac), then run setup again for the standard path.${N}\n\n"
  elif ! mac_intel_supported; then
    printf "  ${R}This Mac is an Intel Mac running macOS %s${N}, which is older than the engine can set up.\n" "$(sw_vers -productVersion 2>/dev/null)"
    printf "    ${Y}macOS 11 (Big Sur) is the floor.${N} Below it the speech tools would all need pinning back several\n"
    printf "    years at once, and that combination has never been tested. Updating macOS, if this Mac can take\n"
    printf "    a newer one, is the honest fix. Nothing below will work until then.\n\n"
  else
    printf "  ${B}This is an Intel Mac${N} (%s), so the setup takes a different route.\n" "$(mac_cpu_brand)"
    printf "    Homebrew stopped supporting Intel Macs, and its installer now quits ${B}before${N} it asks for your\n"
    printf "    password. That is not a broken install and it is not your machine. Everything still installs,\n"
    printf "    just from each tool's own download instead:\n"
    printf "    ${B}bash scripts/intel-mac-install.sh all${N}\n"
    printf "    ${D}No password except the Node installer, which asks in a normal Mac window. Full route:${N}\n"
    printf "    ${D}product/INTEL-MAC-ROUTE.md${N}\n\n"
  fi
}
# Homebrew's own installer, pasted once by her: it asks for the Mac password, so it cannot be run for her.
BREW_INSTALLER='/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
homebrew_first() {
  # Homebrew's installer needs sudo, which a Standard (non-admin) macOS account cannot run.
  # Catch that here so the buyer sees a clear fix instead of a raw "user may not run sudo" wall.
  if ! id -Gn 2>/dev/null | tr ' ' '\n' | grep -qx admin; then
    printf "  ${Y}This Mac account is NOT an administrator${N} — Homebrew (and the tools below) need admin rights to install, so setup cannot run on a Standard account. This is not broken and not your fault.\n"
    printf "    ${B}Fix (about a minute):${N} on this Mac open ${B}System Settings > Users & Groups${N}, and for this account turn ON \"Allow this user to administer this computer\" (whoever first set up this Mac can do it). Then fully quit and reopen Claude Code and run setup again.\n"
    printf "    ${B}Or:${N} log in to the Mac's administrator account and run setup there instead.\n\n"
  elif [ -x /opt/homebrew/bin/brew ] || [ -x /usr/local/bin/brew ]; then
    # Installed but not on PATH in this terminal: the classic "brew: command not found" right after a fresh
    # install, on both Apple Silicon (/opt/homebrew) and Intel (/usr/local). Not a broken install.
    _brewbin=/opt/homebrew/bin/brew; [ -x "$_brewbin" ] || _brewbin=/usr/local/bin/brew
    printf "  ${Y}Homebrew is installed but this terminal can't see it yet${N} (normal right after installing it). Paste this once, then reopen the terminal:\n"
    printf "    ${B}echo 'eval \"\$(%s shellenv)\"' >> ~/.zprofile && eval \"\$(%s shellenv)\"${N}\n\n" "$_brewbin" "$_brewbin"
  else
    printf "  ${Y}Homebrew not found${N} — it's the delivery truck the installs below ride on, and Claude walks you through it during \"set me up.\" The one line it'll have you paste:\n"
    printf "    ${B}%s${N}\n\n" "$BREW_INSTALLER"
  fi
}
case "$OS" in
  mac) if [ "$MACROUTE" = direct ]; then intel_route
       elif ! command -v brew >/dev/null 2>&1; then
         case "$MACCLASS" in rosetta) rosetta_terminal ;; *) homebrew_first ;; esac
       fi ;;
esac

printf "${B}Core${N} (every job needs these, from raw footage through to the export):\n"
need ffmpeg  ffmpeg  ffmpeg "used by every audio and video pass: the cut, the captions, the music"
need ffprobe ffprobe ffmpeg "reads each clip's length and format"
need uv      uv      uv     "the rough cut — sets up the WhisperX transcriber (and provides uvx)"
need node    node    node   "the graphics renderer (npx hyperframes)"
need npx     npx     node   "launches the hyperframes command line"

# python3 is judged by whether it RUNS. Existing proves nothing on two fronts:
#   Windows puts a Microsoft Store alias called python3 on PATH. `command -v` finds it; running it only
#     prints an install-me message.
#   A Mac without Apple's Command Line Tools has /usr/bin/python3 as a placeholder, and RUNNING that one
#     opens the "install the developer tools?" dialog over her screen (measured on a tester's fresh Intel
#     Mac, 2026-09-18). So on a Mac the placeholder is recognised by path and never run; the shim below,
#     which knows the same rule, does the looking instead.
_cs_apple_stub=0
if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && [ "$(command -v python3 2>/dev/null)" = "/usr/bin/python3" ] \
   && ! xcode-select -p >/dev/null 2>&1; then
  _cs_apple_stub=1
fi
runs()    { "$1" -c '' >/dev/null 2>&1; }             # runs <interpreter>: does it actually execute?
imports() { "$1" -c "import $2" >/dev/null 2>&1; }   # imports <interpreter> <module>
PYBIN=""
if [ "$_cs_apple_stub" -eq 0 ] && runs python3; then
  PYBIN=python3
  ok "python3" "caption and text overlays"
elif command -v python >/dev/null 2>&1 && runs python; then
  PYBIN=python
  note "python3" "found 'python' but not 'python3' — the engine handles this automatically (scripts/_python3-shim.sh)"
else
  # Neither name ran. Before calling Python missing, ask the same shim every other engine script uses:
  # it also knows the `py -3` launcher and real interpreters sitting on disk under neither name, including
  # the uv-managed Python this engine's own Windows setup installs into AppData/Roaming/uv/python/.
  #
  # A checker that disagrees with the engine is worse than none. On a tester's PC every engine script ran
  # Python fine while this reported it missing, and sent her off to reinstall what she already had.
  # (PC test, 2026-09-18.)
  if [ -f "$SHIMS/_python3-shim.sh" ]; then
    . "$SHIMS/_python3-shim.sh" 2>/dev/null || true
  fi
  # The shim's own verdict, read instead of trying `python3` again: on a fresh Mac that retry is exactly
  # the call that opens Apple's dialog (see _cs_apple_stub above).
  if [ "${_P3_OK:-0}" -eq 1 ]; then
    PYBIN=python3
    note "python3" "reached through scripts/_python3-shim.sh — the engine finds it automatically, nothing to install"
  else
    gap "${R}✗${N}" python3 python3 "caption and text overlays"
  fi
fi

# HyperFrames runs on Node 22 or newer. An older Node still passes `command -v`, so it is asked its version.
node_major()   { node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0; }
node_upgrade() {
  if [ "$OS" = win ]; then echo "winget upgrade $WINGET_FLAGS --id OpenJS.NodeJS.LTS, then reopen Git Bash"
  elif [ "$MACROUTE" = direct ]; then echo "bash scripts/intel-mac-install.sh node"
  else echo "brew upgrade node"; fi
}
node_too_old() { local major; major="$(node_major)"; [ "${major:-0}" -lt 22 ]; }
if command -v node >/dev/null 2>&1 && node_too_old; then
  node_seen="$(node -v | tr -d v)"
  todo "node version" "found v$node_seen; HyperFrames needs node 22 or newer ($(node_upgrade))"
fi

# Caption and text images are drawn with Pillow: the engine's ffmpeg has no drawtext
# and no libass to do it.
# The import is tried with the interpreter that actually ran above, never `python3` by name: on Windows
# that name is usually the Store alias, which cannot import anything, and every PC used to be told
# Pillow was missing.
if [ -z "$PYBIN" ]; then
  :   # no Python ran at all; its row above already carries the fix
elif imports "$PYBIN" PIL; then
  ok "Pillow (PIL)" "caption and text overlays"
else
  todo "Pillow (PIL)" "missing — run: $(install_cmd pillow)   (caption and text overlays)"
fi

# Something that ships inside the engine folder. Absent means an incomplete download, and that counts.
bundled() {   # bundled <path inside the engine> <label> <when present> <when absent>
  if [ -f "$REPO/$1" ]; then ok "$2" "$3"; else todo "$2" "$4"; fi
}

printf "\n${B}Fonts${N}  ${D}(bundled with the engine — nothing to install)${N}:\n"
bundled assets/fonts/Coolvetica-Rg.otf Coolvetica \
  "ships in assets/fonts/, for the Butter style pack" \
  "not in assets/fonts/. The Butter style pack uses Coolvetica-Rg.otf"
bundled assets/fonts/Inter-Regular.otf Inter \
  "bundled in assets/fonts/ — the fallback headline font and reel graphics" \
  "not in assets/fonts/. This is the graphics display font; get it again from https://rsms.me/inter"
# SF Pro is Apple's, installed or not, and never required: bundled Inter is the default look everywhere.
sf_pro_here() { [ -f /System/Library/Fonts/SFNS.ttf ] || ls /Library/Fonts/SF-Pro-Display-*.otf >/dev/null 2>&1; }
case "$OS" in
  mac) if sf_pro_here; then
         ok "SF Pro (system)" "installed — optional; bundled Inter is the default look"
       else
         note "SF Pro (system)" "optional and not installed — bundled Inter is the default. Want SF Pro instead? https://developer.apple.com/fonts"
       fi ;;
esac

# Bundled assets a job reaches for mid-run: a missing one fails in the middle of a build, not at setup.
printf "\n${B}Bundled assets${N}  ${D}(ship with the engine — nothing to install)${N}:\n"
bundled assets/models/face_detection_yunet_2023mar.onnx "face model" \
  "bundled in assets/models/ — cover frame + face framing" \
  "missing: assets/models/face_detection_yunet_2023mar.onnx (cover frame + face framing) — re-download the engine zip"
# The index is what every build reads the library through, and it always ships (sfx/approved/ is the
# owner's own CapCut sounds and never does, so checking for it failed every buyer's setup).
bundled product/creative-vault/sfx/sfx-index.json "sound library" \
  "bundled in product/creative-vault/sfx/ — matched SFX" \
  "missing: product/creative-vault/sfx/sfx-index.json (matched SFX) — re-download the engine zip"

printf "\n${B}Speed${N} (informational — doesn't block anything):\n"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
  ok "GPU" "NVIDIA ${GPU_NAME:-detected} — rough-cut transcription uses it automatically, much faster than CPU"
elif [ "$OS" != mac ]; then
  note "GPU" "no NVIDIA GPU detected — transcription runs on CPU. Normal and it works; the engine automatically uses a lighter, faster model on CPU-only Windows machines to keep this to minutes, not hours."
elif [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" != "1" ]; then
  # Intel Mac: same weak, non-accelerated CPU class as a Windows laptop — word-timings.sh already
  # downgrades the model automatically here. Saying "already-fast Mac default" on every Mac
  # regardless of chip was itself the bug: it told an Intel buyer she was on the fast path right
  # before her first transcription quietly loaded a lighter model than that implied.
  note "GPU" "Intel Mac — no Apple Silicon acceleration on this chip. Normal and it works; the engine automatically uses a lighter, faster model to keep this to minutes, not hours."
elif [ "$(uname -m)" = "arm64" ]; then
  ok "GPU" "Apple Silicon CPU path — this is the normal, already-fast Mac default"
else
  # Real Apple Silicon hardware, but this shell is running under Rosetta (uname -m says x86_64 while
  # the hardware says arm64). Tools installed from here inherit the translation, so the transcriber
  # would quietly pick a lighter model on a machine that can run the fast path natively. This is a
  # SETUP fix, not a hardware limit — say so, because "Intel Mac" here would be a misreport.
  note "GPU" "Apple Silicon chip, but this terminal runs under Rosetta (Intel translation) — usually an Intel-era Terminal setting or Homebrew carried over from an older Mac. It works, but tools installed from here run slower than this machine can. Fix once: open Terminal natively (Get Info > untick 'Open using Rosetta') and reinstall the tools, and transcription gets the full-speed path."
fi

printf "\n${B}Optional${N} (only matters if you use that feature):\n"
# The rough cut flags suspect words against a system wordlist. macOS ships one; Windows has none.
wordlist=""
for _wl in /usr/share/dict/words /usr/share/dict/web2 /usr/share/dict/american-english; do
  [ -f "$_wl" ] && { wordlist="$_wl"; break; }
done
if [ -n "$wordlist" ]; then
  ok "wordlist" "here, and the rough cut uses it to flag suspect words"
elif [ "$OS" = win ]; then
  ok "wordlist" "Windows has none, so the rough cut skips its suspect-word scan (advisory only; everything else works)"
fi

printf "\n"
case "$missing" in
  0) printf "${G}${B}Everything core is here.${N} You can start editing.\n" ;;
  *) if [ "$missing" -eq 1 ]; then _it="1 tool"; else _it="$missing tools"; fi
     printf "${B}%s left to install.${N} Nothing is wrong, this is a new machine. Run the command shown beside each one, then run this again.\n" "$_it" ;;
esac

# One item that happens on first use: its mark, its name in bold, then the rest of the line.
once() { printf "  %s ${B}%s${N} — %s\n" "$1" "$2" "$3"; }   # once <mark> <name> <text>

printf "\n${B}On first use${N} (not installed here — each happens once, on its own or with one command):\n"
if [ "$MACCLASS" = intel ]; then
  # Different engine, and a very different download. Quoting 3-5 GB at an Intel-Mac buyer would be
  # both wrong and discouraging, on the machine least able to afford either.
  once "${D}•${N}" "Speech transcription" "the first edit sets up the rough cut's venv (~175 MB), then downloads the speech model. It needs a network connection and a few minutes, once."
  printf "    ${D}On an Intel Mac this uses faster-whisper instead of WhisperX, automatically — WhisperX needs a piece of software that has no Intel build.${N}\n"
else
  once "${D}•${N}" "WhisperX transcription" "the first edit sets up the rough cut's venv and downloads large-v3 (~3–5 GB). It needs a network connection and a few minutes, once."
fi
# On Windows, a bare `npx` pasted into PowerShell runs npx.ps1, which PowerShell refuses by default
# ("running scripts is disabled on this system"). npx.cmd ships with every Windows Node install and is not
# subject to that policy, so it works as pasted, with no security setting changed.
NPX_CMD="npx"; [ "$OS" = win ] && NPX_CMD="npx.cmd"
if [ -f "$REPO/_local/hf-browser-0.8.43.ok" ]; then
  once "${G}✓${N}" "Render engine" "ready (hyperframes@0.8.43, the version the locked presets are pinned to)."
else
  once "${D}•${N}" "Render engine bootstrap" "run this once in the engine folder:  ${B}${NPX_CMD} hyperframes@0.8.43 browser ensure${N}  (fetches the ~150 MB headless browser that draws the graphics, at the version the locked presets are pinned to). ${D}\`doctor\` only reports; it downloads nothing.${N}"
fi
once "${D}•${N}" "Brand kit" "fill in ${B}brand-kit.md${N} before your first job (see SETUP.md)."
printf "\n"

# The verdict: 0 when nothing core is left, 1 otherwise.
(( missing == 0 ))
