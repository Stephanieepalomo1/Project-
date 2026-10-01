# CapCut Export — the creator's finishing workflow (DEFAULT deliverable)

> **⚠️ Heads up (2026-08-02):** the everyday CapCut-draft builders are now the **generic**
> `product/cleanyap.py` (Clean Yap) and `product/superyap.py` (Super Yap). The **per-reel one-off**
> scripts described further down were **moved to `_archive/one-off-reel-builds/`** on that date, so
> nothing below is a build route to follow any more. The sections are kept for what they teach about
> the CapCut draft format itself.

**the creator finishes every video in CapCut.** The pipeline's job is to hand you an **editable CapCut
timeline** styled to her brand, then STOP. She makes the last edits herself (manual control). Do NOT
auto-finish in HyperFrames unless she asks.

Run: **intake → rough-cut → (graphics-plan if useful) → build the CapCut draft → hand off.**

## ⚡ Fast path (default — use this)

The draft is built by the engine's two generic builders, which assemble it through VectCut (the editing
engine on port 9001, SETUP.md §1b): **`product/cleanyap.py`** for a Clean Yap and **`product/superyap.py`**
for a Super Yap. They are libraries, not commands: each reel gets a short driver in its own job folder that
calls them in order (`add_cut` → `add_text` / `add_png` → `add_sfx` → `finalize`), run with the venv-capcut
interpreter and CapCut quit. [`product/CLEANYAP.md`](../../product/CLEANYAP.md) → **Run** is the recipe.

```bash
bash .claude/skills/rough-cut/scripts/word-timings.sh projects/<job>
# …Claude writes cuts.json (the creative cut) → splice → then the reel's own driver, CapCut quit:
product/engine/VectCutAPI/venv-capcut/bin/python projects/<job>/build.py        # Mac
product/engine/VectCutAPI/venv-capcut/Scripts/python.exe projects/<job>/build.py # Windows (Git Bash)
```

When all that is wanted is the rough cut on a CapCut timeline, the capcut skill lays it down straight from the
cut list: `uv run workflows/capcut-live.py replay <job>`.

## Generators

The first generators here were per-reel scripts, one styled pass and one video-only pass, with the paths,
text and timings of a single reel written into them. They were retired to `_archive/one-off-reel-builds/`
when the generic builders above replaced them. The sections below keep what they taught about CapCut's own
draft format.

---

## the creator's style profile (bake all of this in)

**Reference project:** her **`BASE FILTERS`** CapCut project. **Icon/illustration reference:** her
**`mom math`** project.

> **⚠️ THE STYLE PACK SETS THE LOOK.** Fonts and colors for the hook, thoughts and captions come from the
> creator's chosen **style pack** (Editorial, Playful, Butter, or one she built), resolved per role
> (`cleanyap.hook_font(pack)` / `thought_font(pack)`, `packbuild.role(pack, ...)`), never from a theme file
> or a personal font. Use her saved default pack (`cleanyap.default_pack()`); only when none is chosen yet,
> ask once (the style-pack skill). The `themes/` notes predate style packs. The table below is the SHARED
> structure that stays constant across packs.

| Element | Spec |
|---|---|
| **Captions** | Run CapCut **Generate Captions** in-app (Captions → Auto captions → **Auto highlight keywords ON** → Generate) → apply **Bold Text–Popup** (save it as a CapCut preset for exact reuse) → position **under the mouth** (~−0.33). Spoken word highlights **yellow**. NEVER inject caption clips. |
| **Hook** | The pack's hook font, **WHITE**, never all caps, accent word in the pack's accent color (`packbuild.accent_color(pack)`), **above your head** in the measured open zone (clear of the top-270 reel-UI band), no tracking. Animation: Typewriter/Cheeky Bounce in, Slide out. **NEVER Bouncy Exit.** ⚠️ **What the hook SAYS is governed by "Writing the hook" below — do not skip it.** |
| **Subhead** | The quieter SECOND LINE of the hook block, in the pack's subhead font, ~0.62 scale, sitting directly under the headline. Part of the SAME text block, never a separate chip or bar. Built with `HOOK_SPLIT=1` + `hook_long`. See "Writing the hook". |
| **Ad-libs / thoughts** | **the pack's thought font** (handwritten), white + the pack's accent, **above your head** in the measured open zone. Insider-thought asides + pace changes. Animation: Chalky Scribble / Sliding Drop. |
| **Series / list** | **the pack's thought-font checklist** — numbered, builds one line per item as she speaks it. Animation: Bounce In. |
| **Emphasis / mic-drop words** | bigger + yellow. |
| **Dynamics** | alternate video clips to a punch-**IN** ~110% (scale UP only, never down/smaller; start at baseline). Aim for something changing **every 3–5s**. |
| **Animations** | ONLY on hook + thought/Ugly-Dave moments, NEVER on captions. Cheeky bounce, typing-in, directional swipes. |
| **Sound = animation + feeling** | bounce→click, pop-in→pop (pair pop with Cheeky Bounce), typing/scribble→typewriter, fly/swipe→whoosh. Sparse + soft on heartfelt beats. **Sound follows a DELIBERATE animation/landing, never a bare cut or the ambient default jump-cut punches. Confessional = near-silent (0–2 sounds, often zero); teaching = the full soundscape.** Register gates it — see the `epidemic-sound-design` skill's #0 gate. |
| **GIFs** | millennial-culture GIFs (Clueless, Legally Blonde, Devil Wears Prada, The Office…) at relevant beats — **deliver as a list w/ timestamps + Giphy links; she imports** (injection doesn't render). |
| **Illustrations / doodles** | **ABSTRACT / conceptual, hand-drawn (casual vlog-doodle vibe), NOT literal** (no chair for "pull up a chair"). Build as transparent `.mov` overlays; animate (draw-on / pop). Deliver in the project folder; she imports. |

---

## ✍️ Writing the hook (MEASURED — read before writing a single word of on-screen copy)

These rules come from performance data measured across 44 reels and 18 transcripts on a real account. This is
data, not taste. Re-read this section when in doubt.

### 🚫 The #1 mistake: mirroring the spoken line

**Never write the hook card as a transcription of what she says in the first breath.** If the card
repeats the audio, it buys nothing: the scroller gets the same information twice and no reason to
stay. The card must do a DIFFERENT job than the voice.

### The mechanic that actually won

The best-performing talking head in the reference set did not win on its spoken opener. It won on
**text that named the category on screen early**, while the spoken opener stayed a slow confessional
burn and the name did not arrive in the audio until ~60s.

> **The rule: name the unnamed thing FAST where the scroller can SEE it, and hold it.**
> When the text names it, the spoken opener is free to be a slow burn.

**That job belongs to the hook block, not to a separate bar.** A talking head gets **ONE** text block
at the top of the frame, and it has two lines:
1. **Headline** — names the tension. Opens a loop and refuses to close it.
2. **Subhead** — the quieter line under it. Says WHO it is for, or turns the knife.

**Three shapes are allowed, and nothing else. They are the same mechanic, so this is one decision,
not three:**

| Shape | How | When |
|---|---|---|
| **Hook card** | plain `hook` | one line is enough. Shortest, hardest. |
| **Eyebrow + headline** | `HOOK_SPLIT=1` + `hook_long`, `hook_emphasis: "second"` _(default)_ | small line ABOVE sets the frame, big line below lands it. |
| **Headline + subhead** | `HOOK_SPLIT=1` + `hook_long`, `hook_emphasis: "first"` | big line lands first, quiet line under it turns the knife or names WHO. |

The last two are **one shape with the sizes flipped** — `hook_emphasis` picks which half is big, and
the other half becomes the quiet line. Give `hook_halves` when the break should land on meaning
rather than on length. Both lines come from the pack's own fonts and move as ONE block.

It holds **~8s** by default (`hook_end` — the top of the frame is no longer shared, so the block
gets the room the old bar was taking), and `hook_persist: true` holds it the whole reel.

> 🔴 **NEVER build a separate persistent category chip, bar, or banner** (locked). It is not a second
> text system, it is a duplicate of the job the hook block already does, and with nothing approved to
> put in it the engine invents a line the creator never wrote and runs it for the full runtime. The
> renderer still accepts `persistent_label` for anyone who asks for one BY NAME, and nothing authors
> it otherwise. Two text systems never compete for the top of the frame.

### What a good label does: hand her a word she can repeat

The winners give the viewer **a label for an experience she has lived but never had words for**:

| Views | Line |
|---|---|
| 151,913 | "Why does nobody talk about the **a phrase from your own transcript** that hits in the middle of maternity leave?" |
| 32,305 | "I spent 10 years climbing a ladder. **Maternity leave is when I finally looked up.**" |

"Career crash out" is adoptable. She can say it to a friend. Aim for that.
**Best source for the label is her own transcript** — a phrase she already repeats in the reel.

### ⚠️ The label must name WHO, not just the feeling

A poetic phrase that doesn't say who it's for fails to capture the audience. **Every one of her
biggest reels names the audience in the TEXT:**

| Views | Text |
|---|---|
| 1,458,854 | "**Moms** at 2am: thinking… how do I re-start my career" |
| 642K | "Dear Algorithm, please introduce me to **moms born between 1985-1999**" |
| 463,878 | "**Millennial Mom** Career Crisis" |

**Formula: WHO + the condition.** That one does both in three words, so a scroller self-identifies
instantly. Put it in the hook block — as the headline, or as the quiet line under it. Never in a
separate bar.

**Important distinction:** the "never a category of person" ban applies to **SPOKEN** openers
("For women who would call themselves high-achieving" → 5.5K). In **on-screen text the opposite
holds** — naming the demographic is exactly what drives self-selection. Those spoken flops failed
for being abstract and flattering rather than a lived pain, not for naming a group.

**Don't build the label out of a word the reel argues against.** On `an example reel`, an
"Ambitious Mom…" label would contradict the entire thesis.

### Banned in the hook (each pattern is measured, not a hunch)

| Pattern | Evidence |
|---|---|
| Announcing that value is coming: "I'm about to…", "Let me show you…" | The three worst reels of 18 all do this (6.8K, 4.7K, **2.2K worst of all**) |
| Leading with her own numbers or credentials | 8.5K, 6.6K, 3.6K. Proof belongs in the MIDDLE, never the hook |
| Abstract with no concrete image; a category of person | "For women who would call themselves high-achieving" → 5.5K |
| **Em dashes** | Not in on-screen reel copy (the creator's copy rule). A writing rule only, never a building rule |
| ALL CAPS on a hook in the pack's hook font | Her explicit call, 2026-07-23 |

⚠️ **This contradicts the "Caption Formula" page** ("hook from personal results, authority not pain
point"). That is right for CAPTIONS and backwards for talking heads. Authority works in text, where
the viewer already stopped scrolling. It does not buy the stop.

### Match the hook to the reel's JOB (three-engine model)

| Engine | Format | Hook job |
|---|---|---|
| **REACH** | short text-over-b-roll | identity statement, widest net |
| **GROWTH** | **tension talking head, confessional** | **name the tension, open the loop, NEVER resolve** |
| **FUNNEL** | teaching / solution + comment-CTA | name the problem the lesson solves |

**Growth reels are the follow engine** (12–54% follow-per-like vs ~1% for a viral short). Their
contract: no lesson, no resolution, no pivot to hope. If the urge to add "here's what to do about
it" shows up in the copy, cut it. **Teaching without tension does not grow** — that is precisely
what caused her follower drop.

### Checklist before shipping a hook

1. Does the hook block name **WHO it's for** as well as the condition? (A feeling with no
   audience in it does not capture anyone.) Either line can carry the WHO.
2. Is the hook block saying something DIFFERENT from the first spoken line?
3. Does it open a loop rather than promise to close one?
4. Concrete in the first breath: a picture, a moment, a room. Not a category of person.
5. No "I'm about to" / "Let me show you" / any number about the creator / any em dash / any all-caps.
6. Confessional reel? Then no hopeful pivot anywhere in the on-screen copy either.

### Worked example — `an example reel` (confessional, 2026-07-24)

- ❌ First attempt: `"everyone keeps / calling it ambition"` — a verbatim mirror of her spoken
  opener. Named nothing and added nothing.
- ❌ Second attempt: `"The Quiet Pull"` — her own phrase and adoptable, but it names **no audience**.
  Stripped of context it could be faith, a relationship, an addiction. Poetic, poor targeting.
- ✅ **Eyebrow + headline**, one block (`hook_emphasis: "second"`):
  - eyebrow — **"moms who can't turn it off"** — WHO + the condition, taken from her own line
    ("I cannot shake it… it will not leave me alone"). Repeatable as an identity. Avoids "ambition"
    (the word the reel rejects) and "calling" (would close the loop and read preachy).
  - headline — **"there's a word for this. / ambition isn't it."** — opens the loop the whole reel
    sits inside, without repeating the audio.
  One block, two jobs, one voice. Earlier versions of this spec put the first line in a separate
  bar running the whole reel; that is the thing this page now forbids.

## Technical learnings (hard-won — don't relearn these)

- **CapCut version stores the timeline in `draft_info.json`** (on macOS; Windows uses `draft_content.json`, resolved by `product/draft_safety.py`), plaintext.
- **SDR color fix (mandatory):** cloning templates carries `hdr_settings: mode 4` (HDR, correct for her
  iPhone HDR footage). the creator's exported files are **SDR (bt709)** → mode 4 tints them **red/orange**. Set
  every video segment's `hdr_settings` to `{"mode":0,"intensity":1.0,"nits":203}`. **Screenshots can't
  verify CapCut color** (OS color-manages the capture; her wide-gamut display doesn't) — ask her.
- **Media must live inside the draft folder, in a form CapCut imports.** Its sandbox can't read arbitrary
  absolute home paths, so every clip is copied into the draft. Opaque footage goes in as an H.264/HEVC MP4;
  ProRes only as a TRANSPARENT overlay (ProRes 4444 with alpha). An opaque ProRes is what "couldn't import
  some of the files" was, so `capcut_media.ensure_shippable` (run by every `finalize`) copies each clip in and
  refuses an opaque ProRes. Color stays right through the SDR fix above.
- **Text renders ONLY from the proven templates** `tpl_textmat.json` + `tpl_tseg.json` (from June
  Finances). Cloning BASE FILTERS' text materials/segments rendered as empty carets.
- **`clip.transform.y` is INVERTED (y-up):** +y = toward TOP, −y = toward BOTTOM; ~1.0 = half canvas
  height. Hook-above-head ≈ **+0.72**, caption-under-mouth ≈ **−0.22** show the direction only: a real
  placement is MEASURED off her footage (`uv run workflows/subject-zones.py …`, then
  `subject_place.y_for(...)`), never typed or copied from another reel.
- **Captions:** don't inject individual word clips. A real captions track uses CapCut's proprietary
  `text_template_subtitle` format (fragile). Hand her the timeline WITHOUT captions → she runs
  **Captions → Auto Captions** (transcribes the clean cut audio) → applies her highlight preset.
- **GIF/media overlays don't render when injected** (CapCut needs to import/process media). Deliver GIFs
  as a suggestion list; she imports via CapCut's GIPHY panel.
- **Animations + SFX DO inject** — clone the `material_animations` (Cheeky Bounce, Chalky Scribble,
  Bounce In, Sliding Drop…); sounds come from the engine's own library (`python3 product/capcut_sfx.py
  --list`), copied into the draft. Never a path into CapCut's cache: it exists only on the machine it was
  made on.
- Quit CapCut before writing the draft; it rewrites `root_meta_info.json` on launch. Relaunch to see the
  project. Back up `root_meta_info.json` first.

## ⚠️ NON-DESTRUCTIVE + FREEZE (critical)

- The generator must **never `rmtree` the project folder** — the creator imports her own media (GIFs, doodles) into it. Only (re)write the files the generator owns; leave everything else. (Fixed 2026-07-23.)
- **Once the creator starts editing in CapCut — especially after you run Generate Captions — STOP regenerating.** Rewriting `draft_info.json` overwrites your caption track, imported media, and manual edits. After the automated styling pass + caption generation, the project is yours. Future automated changes should be **surgical patches** to the existing `draft_info.json` (read → modify the specific thing → write, preserving your tracks/materials), NOT a full rebuild.
- Captions: trigger CapCut's **Generate Captions** (Captions tab → Auto captions → turn ON "Auto highlight keywords" → Generate). That makes the real caption track with her yellow keyword highlight. Do this in-app; don't inject text clips.

## 🏁 FINAL STEP — the Handoff Brief (closes the editing workflow)

The editing portion of the pipeline ENDS with a **handoff brief** delivered to the creator — a shift-change
briefing so she can finish in CapCut without re-reading the whole session. Always produce one.

**Storage: everything for a job goes in ONE durable folder, the repo's `projects/<job>/`.**
That holds the working source (rough cut, ProRes master, transcript) AND the handoff assets
(doodles/, gifs/, HANDOFF.md, post-caption.txt). One folder, whole content piece, every stage.

NEVER `~/Downloads` (it gets cleaned out). NEVER a cloud-synced folder either, such as Documents or
Desktop on a Mac with iCloud Drive syncing them. The OS can evict large media files to the cloud to
save space. The file still looks present in Finder, but ffmpeg and WhisperX will stall or fail on it
mid-job.

Handoff structure (see the an example reel folder for the worked example):
1. **Drop schedule** — chronological list of every doodle/GIF + its drop timestamp (markers don't inject; this is the substitute).
2. **Already on the timeline** — what's done, in her style.
3. **Doodles table** — asset · timestamp · moment · suggested SFX (sound-matches-animation).
4. **GIFs table** — gif · timestamp · moment · **direct Giphy link**.
5. **Font note (only if a pack font fell back) — ALWAYS check this.** Run
   `python3 -c "import sys; sys.path.insert(0,'product'); import stylepack; print(stylepack.delivery_font_note('<pack>') or '')"`
   with the pack she chose. If it returns anything, say it warmly in the handoff, verbatim in spirit: the
   pack's real font is not on her setup so a replacement was used, she can add the real font in CapCut
   (free for Bloop/Ugly Dave, CapCut Pro for Prosecco/Soup Du Jour) or just tell you another font to swap
   in. If it returns nothing, her fonts all resolved — say nothing about fonts. Never call a free font
   "Pro" (Bloop is free). The helper already words it correctly per font.
6. **Things to be aware of** — style pack used, captions recipe, sound=animation rule, "don't rebuild (frozen)", export = real backup, cleanup items, notification-hook activation.
7. **Where everything lives** — the project folder, rough cut/master, the reusable system.

After the brief, the editing workflow is COMPLETE. What happens to the exported file (posting,
scheduling) is out of scope for this repo.

## ⚠️ Timeline markers don't inject either (learned 2026-07-23)
Writing `time_marks` into `draft_info.json` does NOT stick — CapCut overwrites it with its own marker state on open (same class as GIF/media injection: CapCut only renders markers created in its UI). Deliver drop-points via the HANDOFF brief timestamps instead; if she wants literal CapCut markers she adds them (park playhead → marker button) using the brief as the guide.
