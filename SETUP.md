# 🎬 The Reels Editing Engine — getting it running

**You film it. The engine edits it. You decide how done it comes back:** an editable CapCut draft you
finish yourself, or a finished video ready to post. It runs inside
[Claude Code](https://claude.com/claude-code) and makes vertical short-form reels in three formats:

- **Yap**: you on camera, talking. A hook, thought bubbles and matched sound effects, with how much
  graphics treatment it gets decided automatically by the video's register.
- **Voiceover**: your voiceover over your own b-roll, with no talking head.
- **Animation**: footageless, no camera and no filming. Designed frames, animated type and motion
  graphics, over your voiceover or music.

Every one of them comes out in your look and your voice. _(The Reels Editing Engine is short-form only:
Yap · Voiceover · Animation.)_ **Runs on macOS and on Windows** (on a PC it runs in Git Bash, which "set me
up" checks for first).

**You don't have to do any of this by hand.** Once it's unzipped, open the folder in Claude Code and just
say **"set me up."** Claude reads this page and walks you through everything on it, doing the technical
parts for you. The rest of this page is that same setup written out, for when you want to see what's
happening or do a step yourself.

---

## 0. Where this folder lives

Pick a spot that is NOT synced to iCloud. On a Mac, `Documents`
and `Desktop` are often synced, and when your drive gets full the Mac quietly moves big video files up
to the cloud to free up room. The file still shows up in Finder, but the engine can't actually read it
and your edit stops halfway. A plain `Projects` folder alongside Documents and Downloads is perfect: on a Mac that is
`/Users/your-name/Projects`, on Windows `C:\Users\your-name\Projects`. Your footage and your finished
reels all live inside this folder, so this one choice keeps everything safe.

> **On Windows, do not use the "Home" item in File Explorer.** It looks like the right place and is not.
> It is a virtual view of pinned and recent files, and Windows will not let you make a folder there.
> Instead click the address bar at the top, clear it, type `%USERPROFILE%` and press Enter. That lands
> you in your real user folder, where **New folder** works. Skip Documents and Desktop on Windows too:
> both are redirected into OneDrive by default.

*Not sure if yours is synced?* Open **System Settings**, click your name at the top, then **iCloud**,
then **iCloud Drive**, and see whether **"Desktop & Documents Folders"** is switched on. If it is,
don't unzip into either of those.

(Unzipped it somewhere synced already? "Set me up" checks this before it installs anything, and offers to
move the folder for you.)

---

## 1. What "set me up" installs, named by the job each piece does

Everything starts from the included checker. It only reports: it works out which machine you are on,
tells you exactly what's missing, and prints the exact install command for that machine. Run it, then do
what it tells you.

```bash
./check-setup.sh
```

### The core tools every reel needs

On a Mac they come to this (on Windows, the checker prints the matching `winget` lines instead):

```bash
# 1) Homebrew, the Mac's installer for everything below. Already have it? Skip this line.
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install ffmpeg          # the video engine: every audio/video pass (cutting, captions, music, rendering)
brew install uv              # the transcriber helper: it builds WhisperX the first time it runs
brew install node            # the graphics engine (it runs npx hyperframes)
brew install python          # the caption + text helper
brew install pillow          # the helper's drawing kit (PIL); this ffmpeg cannot draw text itself
```

### The render browser, once

```bash
npx hyperframes@0.8.43 browser ensure   # fetches the headless browser the graphics engine draws with (~150 MB, one time)
npx hyperframes@0.8.43 doctor           # a report on Node, CPU, memory and disk; it downloads nothing
```

> Why `@0.8.43` and not the newest: every caption and graphics preset in the engine
> was built and tested on that release. Asking for that same version here means it downloads once, and every render after
> that reuses the copy already on your disk.

### Your first reel is the slow one (only the first)

Before it can cut anything, the rough-cut step downloads WhisperX's `large-v3` speech model (around 3 to
5 GB) and sets up its environment: expect several minutes, and you'll need internet, but it happens once.
Every job after it goes straight to the work. It is also why the first-reel script is short. (The same
thing on a much smaller scale: the first time `workflows/head-framing.py` runs, it pulls its own OpenCV
through `uv`, about 50 MB.)

### Fonts that come in the box

Two faces ship in `assets/fonts/`, so there is nothing to install:

- **Inter** (free, Open Font License) is the display face for type-and-look and the reel graphics, and
  it is already the default. Would you rather have Apple's SF Pro? It is optional. Apple's free "San
  Francisco Pro" pack is at <https://developer.apple.com/fonts>: install it, then name it in
  `brand-kit.md`. Until you do, overlays stay on the bundled Inter.
- **Coolvetica** ships for the Butter style pack. Nothing for you to do.

---

## 1b. The editing engine (VectCut) — required for editable CapCut drafts

The Yap reel builds (`cleanyap.py` / `superyap.py`) assemble your **editable CapCut draft** through **VectCut**, a small local server at `product/engine/VectCutAPI/`. "Set me up" does this part for you. By hand it is one script, run once, on a Mac or in Git Bash on Windows:

```bash
bash product/engine/VectCutAPI/setup-editor-engine.sh
```

It builds the engine's own workspace (`venv-capcut/`) on a Python new enough for it (3.10 or newer; it
looks past the Mac's built-in 3.9 on its own), installs `requirements.txt` into it (never `pyproject.toml`,
and never `pip install pyJianYingDraft`: that ships inside the folder), and makes sure `config.json` points
the engine at your own computer (`http://localhost:9001`). The package already carries that `config.json`;
the script writes it only if it is missing and never overwrites yours. Anything already done is skipped, so
it is safe to run again.

Also needs **ffmpeg** (installed in the Core step above) and **CapCut 9.1.0+ opened once**, which creates
its projects folder (`~/Movies/CapCut/User Data/Projects/com.lveditor.draft/` on a Mac,
`%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` on Windows).

**Start it before you edit, and leave it running.** In `product/engine/VectCutAPI/`, double-click
**`start-editor.command`** on a Mac or **`start-editor.bat`** on Windows. It opens its own window: keep that
window open while you edit, and close it when you are done.

Confirm it's up: `curl -s http://localhost:9001/get_mask_types` should return JSON with `"success":true`.

> Full step-by-step + every gotcha: see the **VectCut Clean Install Guide + Holes Audit** (in the course docs). Note: the finished-MP4 render path (HyperFrames + ffmpeg) needs **neither** VectCut nor CapCut — that's the "watch it without CapCut" option.

## 1c. Your Homebase: make it sound and look like you

The engine ships with placeholder branding, and `brand-kit.md` is where yours goes: who you are, your
niche and handles, how you sound, your fonts and hook style, and the brand words the transcriber tends to
mishear. Your colors come from the style pack you pick. Every caption's sound and look is driven by this
one file, and you only fill it in once.

You don't have to type it yourself: say **"build my homebase"** and Claude interviews you one question at
a time and fills it in. (Built a Homebase in another product already? Say **"sync my homebase"**.) Part A
of the file is the form itself; **Part B** lists the exact file and token each value lands in, for when
you would rather do it yourself or check the work. After changing it by hand, say
**"use my brand kit"** and those values get written into the presets and into `CLAUDE.md` for you.
(Claude brings all of this up on its own the first time you open the project; see the onboarding gate
near the top of `CLAUDE.md`.)

---

## 2. Your first reel

1. **Film the first-reel script,** [`product/FIRST-REEL-SCRIPT.md`](product/FIRST-REEL-SCRIPT.md). It is
   about 40 seconds on purpose, and every line in it names an effect, so the finished reel shows you the
   whole effects menu on your own face. Any short clip you already have works too.
2. **Drop the clip into `inbox/`** and say **"edit this reel."** It takes the newest clip there. A clip
   somewhere else works too: **"edit this video: ~/Downloads/first-try.mov"**.
3. **It makes a job folder for the reel** and copies the clip into `projects/<job>/raw/`, leaving your
   original where it was. Then it runs the rough cut, shows you the style plan, plans the graphics and
   walks you through the rest. What it can't work out for itself comes as a quick tap-to-pick question:
   is this reel teaching or confessional, and how done do you want it (raw, medium, well-done, or
   hands-off)?
4. **Where it lands:** your cut is `projects/<job>/outputs/<job>.mp4`, and the finished video you post is
   `projects/<job>/outputs/<job>.final.mp4`. On raw and medium your finish is the CapCut draft: you polish
   it there and export from CapCut.

That's everything. `CLAUDE.md` covers how the edit itself runs, phase by phase.

---

## Where your stuff lives

Every effect, and the words to ask for it: say **"library"**, or open
[`product/BUILD-VOCABULARY.md`](product/BUILD-VOCABULARY.md). The folders:

| When you want to… | Look in |
|---|---|
| drop in a new clip | `inbox/` |
| find everything for one reel | `projects/`: one folder per video, made for you |
| change how the engine sounds and looks for you | `brand-kit.md`, the one file you fill in |
| check which tools are installed | `check-setup.sh`: it looks for what you need and only reports back |
| free up disk space from old render scratch | `scripts/free-space.sh` (a dry run by default) |
| see how the editor thinks: the phases, the rules, the formats | `CLAUDE.md` |
| look at the editing skills and the HyperFrames render toolkit | `.claude/skills/` |
| look at the locked looks: signature style, captions, the clean-captions hook card | `presets/` |
| look up per-format layout and safe zones | `workflows/` |
| find the bundled fonts, or add your logos | `assets/`: the fonts ship with it, the logos are yours to supply |
