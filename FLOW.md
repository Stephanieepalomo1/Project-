# FLOW.md — the canonical reel-build flow (all routes, one build, no confusion)

> The single source of truth for HOW a reel is built end to end, across every option. Every engine build
> and every course lesson follows this. Locked with the creator. Pairs with
> capcut ripple needs one pass build (why the build is one pass) and kinetic caption system
> (how animated type is split into named layers).

## The organizing principle (read first)

**Everything the engine makes is built in ONE pass, BEFORE CapCut opens the draft.** CapCut is polish
only. So the flow can only be: **collect every creative choice → build once → finish.** No creative choice
can come after the build. (Why: one pass = one write cycle, so nothing can clobber her in-app edits, and
CapCut must be QUIT for every draft write. The earlier claim that layers patched on later "stay outside the
ripple graph" was disproven by a live test: engine-injected tracks ripple with the magnet as long as CapCut
was quit when they were written.)

Practical consequence: gather ALL picks up front, in one plan, then build. If a creative pick must change
after she's in CapCut → **rebuild clean to a new draft** (styling is baked in, so it's fast) — never patch.

**How the picks get gathered: a CLEAN PICK-ONE PROMPT at each gate, never prose (locked 2026-08-30).** When
a gate needs a decision before the build — the **doneness / finish route** (raw / medium / well-done /
hands-off) or the **register** (teaching / confessional) — present it as ONE structured multiple-choice
prompt with the likely default marked, not buried in a paragraph she has to dig through. Trigger cues:
"next phase", "what's next", "move on". This is format at the right moment, not asking more often (the
don't-over-ask rule still governs everywhere else). See `CLAUDE.md` rule 1 / phase gate pick one prompts.

## The four outputs — doneness × autonomy (LOCKED with the creator 2026-08-09)

The **same house treatments** (the locked per-pack looks — palettes, tone-on-tone, blocks, multicolor,
stars/doodles/borders, grain, animated type, motion graphics) run across every level. What changes is HOW
they're delivered and how much the creator still touches it. **Governing rule: any HyperFrames MP4 render
ABOVE raw uses these pack looks.** Raw (native CapCut) is the only level without rendered treatments.

| Output | Delivery | Creator still edits | Creator's creative input |
|--|--|--|--|
| **🥩 raw** | CapCut draft; treatments pushed in as far as CapCut does NATIVELY (accent/colored text, pack colors, native anims). No rendered overlays. | Everything | Full (plan → approve) |
| **🥩 medium** | Editable CapCut base + the treatments as rendered `.mov` overlays (fullscreen takeovers, multicolor text, transparent-video-over-footage). I'm a **co-pilot**: I also add SFX in CapCut + gifs/bubbles + clip scaling. | Full — she works alongside me | Full (plan → approve) |
| **🥩 well-done** | A finished baked **video** (never opens CapCut). I render the whole thing, so I can watch it and self-check before it reaches her. | Nothing (it's a finished video) | Full — she directs the creative WITH me (plan → approve → iterate) |
| **✋ Hands-Off Edit** | The **same finished baked video**, but one click. After rough-cut approval **I decide everything** — intent, stylistic calls, zoom/jump-cut variations off the script, talking-head intent — like the HyperFrames intent layer. | Nothing | **None past rough-cut approval.** Click and walk away. |

**Well-done and Hands-Off are the SAME output** — a baked video I render, neither ever opens CapCut. The ONLY
difference is who decides: on well-done she's in the driver's seat with me (plan, approve, iterate); on Hands-Off
it's one click and I make every call past the rough cut. (raw + medium are the CapCut lanes.)

Two standing rules across all levels:
- **Default to the FULL library, she SUBTRACTS.** Bring graphics, motion graphics, animated text, SFX, the
  pack treatments — applied proactively and FIT TO THE VIDEO's natural format/register (a confessional reel
  gets almost nothing; teaching earns designed moments). She tells me what to REMOVE; she never has to know a
  feature exists to get it. The creative plan reads "here's the full treatment I'm applying, tell me what to
  pull," not "here are options, pick."
- **Don't duplicate what CapCut does well.** COLOR GRADING is a CapCut-native strength — I do NOT touch it; it
  stays hers. I bring designed treatments + SFX, she grades in CapCut.

## Steps 1–3 — same for everyone

1. **Rough cut** — WhisperX transcribe → kill filler/dead air → splice. **Lock the words in Claude** (all
   beat cuts happen in the style plan here, NOT in CapCut).
2. **Style pack** — pick 1 of 3 (Editorial / Playful / Butter) or build-your-own. Chosen once,
   reused. Sets fonts/sizes/accent. (the creator's personal reels use her own hook and thought fonts — personal fonts vs ship fonts.)
   **Load ONLY the chosen pack's `product/creative-vault/design/<Pack>.design.md` for any above-raw graphics
   build (not all three) — the pack is known before graphics build.**
3. **Format** — **Yap** (talking head): a hook + thought bubbles + matched SFX reel whose graphics
   treatment is driven automatically by the video's **register** (confessional → trimmed back; teaching →
   loaded with doodles, takeovers, stat cards, b-roll). The creator doesn't pick a level; the register does.
   **Or Voiceover** (voiceover-led, no talking head) — a DIFFERENT audio-first cut engine: the VO is the
   spine, b-roll is dressed onto it, hook-burst opener. It branches from step 1 and has its own spec:
   **[`product/VO-REEL.md`](VO-REEL.md)**. **Or Animation** (footageless — no camera, no filming): built
   from designed frames + animated type + motion graphics in the style pack's look, over her own voiceover
   or music only (no AI voice). **Or B-Roll Reels** (bring-your-own filmed b-roll, no camera take and no AI
   generation): a folder of the creator's own clips gets organized, hooked, and baked with the chosen style
   pack's text into a numbered posting queue with captions. It runs through the `broll-reels` skill.
   Steps 4–7 (build/captions/music/cover/export) and the doneness routes below still apply.

> **Treatment intensity and doneness are TWO INDEPENDENT axes (locked).** Treatment (trimmed-back ↔
> loaded, register-driven) = how *loaded*. Doneness (Route C raw ↔ B medium ↔ A well-done, below) = how
> *baked / editable*. They do NOT imply each other: a **trimmed-back Yap can be raw, medium, OR well-done**,
> and so can a loaded one. The "cooked" level is never a loaded-treatment-only thing — ask both, and never
> assume a confessional Yap ⇒ raw.

## How to ask the creator — LOCKED steak-doneness format (never abstract)

The finish choice is ALWAYS put to the creator as ONE question with these three options, verbatim. NEVER
as abstract or technical framing (never "editable text vs rendered kinetic layers"). The creator is the
chef; they only ever see the three steaks. The Q1/Q2 branches below are the INTERNAL mapping.

- **🥩 raw** — editable CapCut draft: hook, thoughts, and bumper text you can retype; pack colors + native touches pushed in as far as CapCut does natively. (Route C)
- **🥩 medium** — CapCut draft with the designed look rendered on named `.mov` layers you move, resize, and toggle but don't retype; I also add your SFX + gifs in CapCut. (Route B)
- **🥩 well-done** — a fully baked video: the type is rendered in, so nothing inside it comes apart. **ASK whether she also wants it in CapCut**, and if she does, hand over a project beside the finished video: her clean cut on the main track, the rendered graphics over it, each sound cue on its own clip — hers to split and zoom. The finished MP4 is still the deliverable; the engine does not export from CapCut. (Route A · the command the bake prints: `uv run product/capcut_handoff.py <JOB> --overlay <overlay>`)

One short line each. Lead with this single concrete choice; do not stack it with other abstract questions.
(Correction from the creator 2026-08-05: abstract multi-question framing was rejected; this is the locked ask.)

**✋ Hands-Off Edit is the separate 4th lane, offered on its own** (not a steak): "approve the rough cut, then
I take it from there — I make every creative and stylistic call and hand you a finished MP4." No creative plan,
no picks, no CapCut. Offer it to the creator who wants to click one button and walk away.

### Captions ask — RAW + MEDIUM only (LOCKED, ask at the style plan)
On **raw and medium**, captions are a real choice, so ask it once at the style-plan step (well-done and
Hands-Off bake captions into the finished build — no ask):
1. **"Do you want me to build the captions, or are you running CapCut's Auto Captions?"** (Auto Captions =
   the in-app default: Bold-Text popup + keyword highlight.)
2. **If me → "styled text layers in CapCut** (editable) **or a rendered MP4/overlay in CapCut** (baked look)?"


## Q1 — CapCut draft, or animated MP4? (ask EARLY — it gates everything below)

| | **Route A — Animated MP4** | **Routes B / C — CapCut draft** |
|--|--|--|
| Opens CapCut? | Never | Once, for polish |
| Output | Flat, fully-baked video (nothing editable) | Editable, layered CapCut draft |
| Engine | HyperFrames render + ffmpeg → MP4 | VectCut build (+ HyperFrames for Route B type) |
| Who it's for | "I just want a finished video, never open CapCut" | "I want to keep tweaking in CapCut" |

Route A bakes EVERYTHING in — hook, thoughts, captions, SFX, graphics — nothing editable afterward. Want
to edit later? That's a rebuild on the CapCut route.

## Q2 (CapCut only) — Editable text, or animated text built by Claude?

| | **Route C — Editable text** | **Route B — Animated (Claude-rendered) type** |
|--|--|--|
| **Hook + thoughts** | Editable CapCut **text** (Q3 confirms you want them) | Rendered, on **named `.mov` layers** (move/resize/toggle, not retype) |
| **Captions** | **Native CapCut Auto Captions** (run in-app) | Rendered kinetic type on named `.mov` layers |
| **Footage · graphics · SFX** | Fully editable | Fully editable |
| **Look** | Clean, familiar, fully hand-editable | The custom "how'd they do that" kinetic look |
| **Engine** | `cleanyap.py` / `superyap.py` (text via `add_text`) | editable base (VectCut) + `build-hf-captions.py` → `.mov` → `build-overlay.py` named layers |

### Q3 (Route C only) — Hook + thought bubbles?
Engine builds the **hook + thought bubbles as editable CapCut text** (`cleanyap`/`superyap`). Captions =
**native CapCut Auto Captions** (in-app; real karaoke + keyword highlight). SFX + graphics ride along.

### Route B named-layer model (LOCKED — from the kinetic-caption system)
The Claude-rendered type is NOT one flat overlay. Each type ROLE is its own **dead-space-trimmed `.mov` on
its own track, named user-friendly** so she repositions/toggles/deletes each freely in CapCut (she just
can't retype it — it's rendered). Reference draft `an example draft` layers: **`Helvetica Captions` · `the pack's accent font` · `Takeover`** (+ Hook/Title). Build: `build-hf-captions.py` (HF_MODE per style) → render → transcode
to qtrle/argb → `build-overlay.py <mov> "<Layer Name>" <render_index> <spans.json>` (dead-space trimmed).
 **⚠ Build these `flag=2` overlay layers in the one-pass build**
: fewer write cycles, nothing clobbers her edits. Adding one later is
fine ONLY with CapCut quit (`build-overlay.py` enforces it); written that way, it ripples like any other track.

## Course FYI (NOT a live question — teach as a tradeoff)
On Route C she CAN ask Claude to build the captions as editable text too — but those are **one-off text
pieces**: no native CapCut caption powers (no auto-highlight / karaoke). Static-text-vs-real-captions is a
choice we teach, not a surprise. Keep it OUT of the spoken flow; mention it in the lesson.

## Then — all routes converge
SFX (on/off + light/heavy, **rotate the clicks** — never the same twice) and graphics/your-art ride along
in the SAME build. → **Approve the whole plan (one gate)** → **ONE build pass** (cut + zoom + type + graphics
+ SFX + animations together) → **finish**: Route A export the MP4 · Routes B/C open CapCut once, polish
(run native captions here on Route C), export.

## Route summary (every combination lands cleanly)

**Creator-facing names = steak doneness (the creator is the chef): A = 🥩 well-done · B = 🥩 medium · C = 🥩 raw**, plus the separate **✋ Hands-Off Edit** lane. More baked-in = more done.

| Route | Name | Finish | Type / treatments | Editable in CapCut? | Built by |
|--|--|--|--|--|--|
| **C** | 🥩 raw | CapCut draft | editable text (hook/thoughts) + pack colors/native touches; captions per the ask | everything | VectCut (`cleanyap`/`superyap`) |
| **B** | 🥩 medium | CapCut draft | designed look on named `.mov` layers + my SFX/gifs; captions per the ask | footage/graphics/SFX yes; type = move-as-block | VectCut base + HF overlays (`build-hf-captions.py`) |
| **A** | 🥩 well-done | MP4 (never opens CapCut) | animated, baked, now in the pack styles | nothing (finished video) | HyperFrames render + ffmpeg (`build-reel-type.py`) |
| **✋** | Hands-Off Edit | MP4 (never opens CapCut) | SAME output as well-done, but I decide every call autonomously | nothing (finished video) | HyperFrames render + ffmpeg (`build-reel-type.py`) |

**Well-done is UNCHANGED (2026-08-09)** — still the baked MP4 (Route A, `build-reel-type.py`), it just now
incorporates the new HyperFrames pack styles/treatments. **Hands-Off Edit is the genuinely NEW layer:** same
baked output, but after rough-cut approval I take over and make every creative call (no plan, no picks). The line
between them is AUTONOMY, not the output. (raw + medium are the CapCut lanes.)

## Cover / thumbnail (optional, PHASED — like the reel)

A reel cover = a FRAME FROM HER FOOTAGE + a title overlay. **Never pick the frame + title yourself in one
shot** — it's phased:
1. **Photo options first** — run `uv run workflows/cover-frame.py projects/<job>/outputs/<job>.final.mp4`
   (the `cover-thumbnail` skill). It scores every frame by expression (eyes open, facing camera, sharp,
   alive), throws out the blinks/blur/turned-away, and writes the top CLEAN frames (no title) to
   `thumbnails/candidates/`. Send them as numbered options. ⏸ she picks. (Eyes-open/expression are
   heuristics — the tool hands you a clean shortlist so nobody scrubs the whole reel; final pick is hers.)
2. **Then title/hook options** — short, punchy, curiosity; tie into any on-screen visual (e.g. her whiteboard). ⏸ she picks.
3. **Then build** the cover on the chosen frame + title.

**Build mechanics:** title in the pack's headline font + accent color (the creator's personal = her hook font + butter
highlight bars, marker-note style), anchored **TOP (above head) or center — NEVER bottom**, one accent word,
scrim/highlight for legibility. Frame extracted via ffmpeg → PIL title overlay (house pattern). She may name
which draft/clip to pull the frame from.

## Non-negotiables (apply to every route)
- **🥩 raw gets NO rendered "vibe"/flourish overlay** (no HyperFrames-rendered underline/circle/stars/
  kinetic doodle passes). Raw = clean, editable CapCut elements + native captions only. Vibe / kinetic
  flourishes belong to 🥩 medium (rendered `.mov` layers), or skip them. Never bake a speculative rendered
  flourish you can't see the result of onto a raw edit. (2026-08-11: a vibe overlay on raw "looked stupid.")
- **ONE route per project — never switch a reel between levels in place.** Each level uses different builders + outputs (C/raw = `cleanyap`/`superyap` → editable CapCut text · B/medium = `build-hf-captions.py` → CapCut `.mov` layers + SFX/gifs · A/well-done = `build-reel-type.py` → baked MP4, she directs · ✋ Hands-Off = `build-reel-type.py` → baked MP4, autonomous after rough cut). Flipping the same project between them conflicts its state and multiplies errors. If the creator changes their level, do NOT convert in place: **duplicate the footage into a NEW, renamed project and build fresh** at the new level.
- One build pass; CapCut is polish only. Never patch FX/type/overlays onto an already-edited draft — rebuild clean.
- Beat cuts happen in the Claude style plan, not CapCut.
- **Captions YIELD under any full-screen takeover OR breakaway, on BOTH sides (LOCKED 2026-08-09, all takeovers + breakaways).** When a takeover or a motion-graphic breakaway owns the screen, no caption may overlap it: captions clear before it starts and wait out its full held tail, then resume. A breakaway also DISSOLVES in and out, so its guard is widened by the fade on both sides — a caption never reveals word-by-word through the translucent card (that read as a glitch). Two effects never fight for the same pixels on a beat. Lives in the core caption logic (`build-reel-type.py` `_yield` + `_BK_GUARD`).
- **The motion-graphic BREAKAWAY is a standard capability on EVERY above-raw output mode** (medium · well-done · Hands-Off · ultra-vibe), not an ultra-vibe-only trick — it's ungated in the shared engine (`build-reel-type.py`, `CP["breakaways"]`). It cuts from her footage to a full-screen designed PACK card (locked palette ground/ink/accent, pack display font) and back. The card ANIMATES like a real HyperFrames card, never a flat fade: it pushes in (scale 1.06→1) the whole hold, an accent bar wipes in, each line lands with a staggered `back.out` overshoot + scale, and the emphasis word gets a late accent pop. This is the animation LEVEL expected on anything above raw (2026-08-09: "this is the level of animations/treatment i expect"). Raw stays native CapCut (no rendered breakaway).
- **Default to the FULL toolkit, fit to the video's vibe; the creator subtracts.** Bring animations, motion graphics, designed effects proactively in EVERY format wherever they fit the register (confessional stays bare, teaching/energetic loads up). Never strip effects "to be safe" — leaning out is the failure mode.
- Every added layer is individually editable/named — never baked-together or grouped (except Route A, which is a full render by definition).
- Base guardrails run in every finalize: magnet all tracks, text safety + 9:16 wrap.
