# Conversion Playbook (platforms the engine does not ship support for)

This is the reference an assistant uses to help a creator try to run the engine on a platform it does NOT
ship support for, e.g. Linux. **Windows is a supported platform and does not use this doc** — it installs
natively through the `set-me-up` skill. It is loaded by the `pc-conversion` skill. It is a preparedness
doc, not a promise. Read it fully before touching a creator's machine.

## THE GOLDEN RULE (read first, never break)
This path is **purely additive and experimental**. It must NEVER change how the engine works on a supported
platform.
- Do not edit the shipped pipeline code to "make it cross-platform" as a blanket change. Every port tweak is
  applied **live, on the creator's own copy, on their machine**, logged, and reversible. The Mac product ships
  and behaves exactly as before.
- Mac and Windows are the **Supported** tier. Everything else is the **Experimental** tier. There is no
  in-between where a creator on a supported platform silently gets experimental behavior.

## The three tiers (say the tier out loud, in plain words)
Borrowed from how Rust, Homebrew, and Steam Deck label platforms honestly:
- **Supported (Mac and Windows):** it works, we stand behind it.
- **Experimental (anything else):** opt-in only. On some machines it works, on some it works after a couple
  of steps, on some it is not there yet. We try it together on your machine and we are honest the whole way.
- **Not yet (Waitlist / refund):** for machines we already know cannot run it today, so nobody wastes money.

A sales page or checkout MAY say the engine runs on Mac and Windows, because it does: both install natively
and both are supported. What must never be claimed is a platform outside that list. For anything else,
**"experimental"** is still the only honest word a creator should see. Decide based on what it is today, not
what it might become.

## The safety pipeline (EVERY change to the creator's machine goes through this)
`preview -> consent -> backup -> change -> log -> offer undo`
- **Preview / dry-run first.** Tell them exactly what you will install or edit and where. "Nothing has changed
  yet." This is the single most trust-building step for a nervous non-technical creator.
- **Consent per action class,** not one blanket yes. Ask again before anything that needs admin, installs a
  tool, or edits an existing file.
- **Back up before you touch anything.** Copy any file to `<name>.bak` before editing it. Where reasonable,
  make a Windows System Restore point before the first install.
- **Log every change** to a manifest file in the creator's folder (`_pc-conversion/change-log.md`): what, where,
  timestamp, how to undo.
- **Idempotent:** re-running setup must be safe. Detect what is already done and skip it, never double-install.
- **Least privilege:** elevate only for the one step that needs it. Install into the tool's own folders, do not
  scatter files across their system.
- **Fail safe, not silent:** on any error, stop, restore from the backup you took, and report plainly. Never
  retry destructively.
- **Never write to the Mac product's files or config.** The PC work lives in the creator's copy only.

## STEP 0 - Preflight (read-only, before you promise anything)
Run these checks and give the creator the verdict BEFORE they invest time. Nothing is installed yet.
- **Windows edition + build** (`winver` / `systeminfo`). Windows 10 1809+ or Windows 11 is the floor.
- **CPU virtualization on?** (Task Manager > Performance > CPU > "Virtualization: Enabled"). Off in BIOS is a
  known cliff (only matters if you ever fall back to WSL2, but check anyway).
- **Admin rights available?** Installs need them.
- **RAM / free disk** (WhisperX large-v3 model is ~3 GB; leave headroom).
- **GPU:** is there an **NVIDIA** GPU? (`dxdiag` or Device Manager). NVIDIA = optional big speedup for
  transcription. AMD/Intel/none = CPU baseline (works, just slower). Assume CPU baseline for most creators.
- **CapCut installed, and which build?** You need the **standalone desktop CapCut** from capcut.com, NOT the
  Microsoft Store version (the Store version hides drafts under a `Packages\...\LocalCache` path and is a
  support trap). Confirm CapCut has been opened once (that creates the drafts folder).
Route the verdict to one of: **proceed** / **proceed with caveats** / **known cliff -> waitlist or refund**
(see the cliffs table). Catch a dead machine here, not 40 minutes in.

## The route: native Windows, NOT WSL2 (this is the important call)
Research verdict, weighted by the one step that cannot break (handing CapCut a draft it can open):
- **Use native Windows** for everything: Python + `uv`, ffmpeg, WhisperX, and the `.sh` scripts under
  **Git Bash** (from Git for Windows). CapCut is a native Windows app that reads its draft by absolute Windows
  path, so producing the draft on the Windows filesystem makes the handoff zero-copy and zero-translation.
- **Avoid WSL2 as the primary environment.** WSL2 is the nicer place to run WhisperX, but a WSL2 (Linux)
  process must write the draft + media to `/mnt/c/...` for the Windows CapCut app to see it, which is slow
  (the 9P filesystem boundary) and forces Linux paths that CapCut cannot resolve. That fights the single most
  fragile, creator-facing step. Only consider WSL2 if the `.sh` layer proves impractical under Git Bash, and
  even then stage the final draft + media onto a real Windows path and rewrite media paths to `C:\...`.

## Install recipes (native Windows, hide the machinery, run them FOR the creator)
Each is one command. After any install that changes PATH, **open a fresh terminal** before verifying.
- **ffmpeg:** `winget install -e --id Gyan.FFmpeg` then (new shell) `ffmpeg -version`.
- **uv:** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (or
  `winget install --id=astral-sh.uv -e`). `uv run`, `uv sync`, lockfiles all behave like macOS.
- **Python:** let `uv` install and pin **Python 3.12**. Do NOT use 3.13 (CTranslate2, which WhisperX depends
  on, has no 3.13 wheels). 3.11 also fine.
- **Git Bash:** install **Git for Windows** (`winget install -e --id Git.Git`); it provides the bash the
  `.sh` scripts need. Save scripts LF-only (a CRLF `.sh` fails with `bad interpreter: /bin/bash^M`). If an
  ffmpeg path arg gets mangled by Git Bash path translation, prefix with `MSYS_NO_PATHCONV=1`.

## WhisperX (the fragile part - ship a pinned set, do NOT free-resolve)
The instability is the PyTorch <-> CTranslate2 <-> cuDNN version triangle, not Windows itself. Remove the
freedom to resolve and reliability mostly returns.
- **Python 3.11 or 3.12 only** (3.13 blocked, above).
- **CPU baseline** (no NVIDIA): install the CPU PyTorch wheel, then WhisperX. large-v3 runs, just slow. Fine
  for short reels.
- **NVIDIA GPU:** install the **CUDA** torch wheel explicitly FIRST (e.g. the `cu121`/`cu124` index), THEN
  WhisperX, or a plain `pip install whisperx` silently pulls CPU torch and you get no GPU.
- **The classic failure** is `Could not load library cudnn_ops...dll`: a CTranslate2/cuDNN mismatch. Pin a
  known-good trio rather than mixing latest:
  - CUDA 12 + cuDNN 9 -> CTranslate2 >= 4.5, torch 2.5+.
  - CUDA 12 + cuDNN 8 -> pin `ctranslate2==4.4.0`, torch < 2.4.
  - CUDA 11 + cuDNN 8 -> pin `ctranslate2==3.24.0`.
- **Best practice:** ship a `uv.lock` with the exact tested torch + ctranslate2 + whisperx versions so the
  creator gets the combination that was proven, not a fresh resolve. Treat that lockfile as the deliverable.

## THE CRUX: the CapCut draft handoff (this is what actually makes or breaks a port)
The pipeline's final act is a CapCut draft the creator opens. On Windows:
- **Windows draft folder:** `%LocalAppData%\CapCut\User Data\Projects\com.lveditor.draft`
  (i.e. `C:\Users\<user>\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft`). The
  `com.lveditor.draft` name is the same as Mac. Quick open for the creator: `Win+R`, paste
  `%LocalAppData%\CapCut\User Data`, Enter.
- **#1 breakage - absolute media paths.** CapCut does NOT embed media; the draft JSON references each clip by
  **absolute path**. A Mac path (`/Users/...`) does not exist on Windows, so a Mac-built draft opens as
  **"media offline."** Every media path in the draft must be the Windows location (`C:\Users\...`). Either
  build the draft on the Windows machine so paths are written native, or run a **relink pass** over the JSON
  before the creator opens CapCut. This is mandatory, not optional.
- **`com.lemon.lvoverseas` is Mac-only.** That container path (fonts, caches, sometimes the draft root) does
  not exist on Windows; the Windows data root is simply `%LocalAppData%\CapCut`. Remap any such path.
- **Fonts:** confirm the draft references fonts by **name / font-id** (so CapCut resolves them from the
  creator's own CapCut, per the ship model), NOT by a Mac absolute font path. A baked Mac font path is dead on
  Windows.
- **Possible encryption (version-dependent).** Some newer CapCut builds obfuscate/encrypt `draft_content.json`
  so it is not plain JSON. If the creator's version does this, direct-JSON rewrite tools need a fallback. **Test
  against the creator's exact CapCut version; do not assume plaintext.**

### The drafts folder is already per-platform (do not hand-patch anything)
The engine finds CapCut's drafts folder on each platform by itself: `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
on Windows, `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` on a Mac (`product/draft_safety.py` and
`workflows/capcut-live.py` both branch on the platform), and it names the draft's timeline file the way
each platform's CapCut expects. So never patch a draft path into her copy: the Windows branch is already
there. If a draft still opens "media offline", run a relink pass over its media paths instead. CapCut has no
Linux app, so on Linux there is no drafts folder to find at all; the finished-video route (HyperFrames +
ffmpeg) is the one to try there.

## Known cliffs (STOP and offer waitlist/refund, do not flail)
- Virtualization off in BIOS and the creator cannot/will not enable it (only blocks a WSL2 fallback, but note it).
- Windows Home edge cases or a corporate-locked / no-admin machine.
- An **ARM** Windows PC (Surface Pro X and similar): the tool stack is not proven there.
- **Microsoft Store CapCut** with the hidden `Packages\...\LocalCache` path: ask them to install the
  standalone desktop CapCut instead; if they cannot, treat as a cliff.
- The creator's CapCut version writes **encrypted** drafts and the relink cannot read them: cliff until tested.
When a cliff is hit, stop, be warm, and route to the graceful exit (refund or "first in line" waitlist).

## What to capture (this is why we do this: the compatibility flywheel)
Every attempt, success OR failure, produces a **handoff report**. The report is what lets the creator build a
real PC release later, so treat data quality as the point. Auto-fill everything a machine can see; ask the
human only for the verdict and one comment. Fields (keep outcomes as a CLOSED vocabulary so they can be
counted):
1. **Config fingerprint (auto):** Windows edition + build, CPU, GPU (NVIDIA?), RAM, virtualization on/off,
   admin available, CapCut version + install type (standalone/Store), free disk, and this engine's version.
2. **Outcome (pick one):** Worked / Worked-after-steps / Failed-at-setup / Failed-at-render / Bad-output.
3. **Break point (pick one + verbatim error):** which step or command, and the exact error text.
4. **The tweak that fixed it (if any):** "worked after I did X." This is the seed of the next automated fix.
5. **Timestamp + engine version + CapCut version** (so fixed issues age out of the matrix).
6. **One free-text comment box, last, optional.**

## Handoff report template (write to `_pc-conversion/PC-REPORT-<date>.md`)
```
# PC Conversion Report
Engine version: <x> | Date: <ISO> | CapCut version: <x> (standalone/Store)

## Config
Windows: <edition + build> | CPU: <> | GPU: <NVIDIA? model> | RAM: <> GB
Virtualization: <on/off> | Admin: <yes/no> | Free disk: <> GB

## Outcome
[ ] Worked   [ ] Worked after steps   [ ] Failed at setup   [ ] Failed at render   [ ] Bad output

## Where it broke (if it did)
Step/command: <>
Verbatim error: <>

## What fixed it (the tweak)
<>

## Anything else (optional)
<>
```
Then ask the creator to **email this file to the creator's support address** (the address on their purchase
receipt or the creator's website). Frame it warmly: they are a "PC Pioneer," their report is exactly what
builds the real PC version, and redundant reports still help (they quantify impact). If it succeeded, say so
with extra thanks; success cases are the most valuable rows of all.

## Confidence + what MUST be tested before promising anything
- HIGH: the install one-liners, the Windows draft path, the WhisperX dependency pitfalls, native-Windows route.
- MEDIUM (version-dependent, TEST on a real Windows machine with the creator's CapCut version first): whether the
  draft JSON is plaintext or encrypted, and exactly how the engine writes media/font paths into the draft.
Do not tell a creator "this will work." Tell them "let's try it together and see, and either way what we learn
helps." That honesty is the product.

## Set UTF-8 permanently (required, one command)

```
setx PYTHONUTF8 1
setx PYTHONIOENCODING utf-8
```
Reopen the terminal afterwards.

Windows runs Python under a legacy codepage (cp1252), not UTF-8. That causes two failures that look like
unrelated bugs: printing a status symbol raises `UnicodeEncodeError` mid-step, and `open()` without an
explicit `encoding=` raises `UnicodeDecodeError` on any file containing a curly quote, an accent or an
emoji (a caption, a hook, the brand kit, a draft JSON). Roughly 129 engine files can trip one of these.
The shell scripts export it themselves, but anything Claude runs directly does not inherit that, so it has
to be set on the machine. It stays invisible until the creator's first piece of non-plain text.
