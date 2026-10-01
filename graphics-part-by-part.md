# Incremental graphics: change one piece, never re-render the reel

The **second pass (step 4)** is where graphics get cut, swapped, moved and redone, and none of that should
cost a full render. The cost is real and it does not shrink: on a measured 30s composition, HyperFrames'
check takes about 40s and the render about 60s, and neither `-q draft` nor `--gpu` changes that, because the
time goes into capturing frames. The only speedup that exists is not repeating work: re-render the one piece
that changed, then re-stack it over everything else. The base footage (the rough cut, `outputs/<job>.mp4`)
is never re-rendered by this step, and neither is anything already locked. This applies to any HyperFrames
graphics build.

There are two ways to work, depending on where the piece sits in time and what it does to her footage.

---

## The everyday loop: `reel_render.py`, one layer at a time

This is the render path CLAUDE.md rule 9 requires. A layer is one transparent composition the length of the
reel, with each clip at its real `data-start`.

```bash
python3 product/reel_render.py render <comp_dir> -o <out.mov>
python3 product/reel_render.py composite --base <footage> --layers <a.mov> <b.mov> --audio <x> -o <final.mp4>
```

- **`render`** runs HyperFrames' native check first and REFUSES to render on errors (`--strict` refuses on
  warnings too: use it for any composition where every word must read). It caches by content hash, so a
  layer that has not changed since its last clean render is an instant no-op.
- **`composite`** is the cheap ffmpeg stack, about 15s: the base, then each transparent layer on top in
  order, plus an optional audio track. It already stacks every layer with `eof_action=pass` (the stutter
  trap below).
- **Change one layer:** re-render only that layer, then re-run `composite`. Never re-render a whole reel for
  a one-layer change.
- `product/build-reel-mp4.py` stays the plan-driven well-done finish (it bakes the punch-ins and matched SFX
  from `caption-plan.json`). `composite` is the fast re-stack for extra transparent layers and QA iteration,
  not a replacement for it.

`composite` lays every layer from the first frame of the base. A piece that has to land at its own
timestamp, or that changes the footage itself, needs the parts harness.

---

## The parts harness: pieces with their own timestamp, or that touch the footage

The harness lives with the job, in `projects/<job>/hf-graphics/`. Sort each piece by what it does to her
footage:

- **Floats over her → `overlay`.** A card, panel, caption or callout on top of the footage. Build it as a
  standalone composition and render it to a **transparent `.mov`** (`--format mov`); it composites onto the
  base at its timestamp and re-renders in isolation.
- **Moves her → `ffseg`.** A zoom, push-in or pan is pure geometry, so it is ffmpeg `zoompan` on a slice of the
  base and never enters the browser. Prefer this every time the footage move can be expressed in ffmpeg.
- **Replaces or reframes her → `segment`.** A camera-reframe takeover, a full-screen cutaway, a speed ramp.
  Build it as a standalone composition **on its own slice of the footage** and render it to an opaque `.mp4`, which
  *replaces* the base for its window. This is the browser path, and the last resort (see the brightness dip
  below).

A parts-oriented `build.py` is the single source of truth (the CSS, each graphic's markup, each graphic's
animation). It generates:

```
compositions/<id>.html   one comp per part (transparent overlay, or opaque segment w/ its base slice)
render-part.sh <id>      render ONE part → renders/parts/<id>.{mov|mp4}   (seconds)
render-all.sh            render every part, then assemble
assemble.sh              ONE ffmpeg overlay pass: base + segments + overlays → renders/final.mp4  (~5s)
parts.json               manifest (id, window, kind, comp, clip)
index.html               full monolithic comp (fallback / from-scratch render)
```

Inside its own composition, every part's GSAP timeline **begins at 0** (the build subtracts the part's start
time from every tween), and `assemble.sh` puts each clip back at its real timestamp with ffmpeg
`-itsoffset` + `overlay=enable='between(t,start,end)'`.

The loop, one part at a time:

```
edit build.py  (tweak one graphic's markup/timing)
python3 build.py                # regenerates that part's comp
./render-part.sh G4             # re-renders ONLY G4 (~30-50s)
./assemble.sh                   # recomposites the final (~5s)
# review renders/final.mp4 → lock it → next part
```

Lock the graphics one by one. Putting everything together at the end is just `./assemble.sh`; nothing gets
a full re-render unless the base cut itself changes.

**Keep the source durable.** The small source (`build.py`, `render-part.sh`, `assemble.sh`, `parts.json`,
`compositions/`) lives under `projects/<job>/hf-graphics/`, never only in `/tmp`: macOS clears `/tmp` on its
own schedule, and a whole build's source has been lost that way, leaving only the video that had already
been copied to `outputs/`. Only the heavy regenerables (`renders/`, `assets/*-base.mp4` slices, font copies)
belong in `/tmp`.

---

## Traps, by where they bite

### While authoring the composition

- ⭐ **No raw emoji glyphs in a graphic: they HANG the headless render, and it looks stuck without being
  stuck.** A real emoji (`💤`, `😴`, any Apple Color Emoji codepoint) sends HyperFrames' headless Chrome into
  a ~100% CPU spin trying to load the system color-emoji font, which isn't available or decodable in
  low-memory render mode. It never errors and never times out; it just runs forever. A part that renders in
  seconds without the glyph burns minutes of CPU with it (5+ min on a 5s part that should take ~7s), so it is
  not a performance wall, and it stays invisible until you watch CPU time pile up on a tiny clip. **Fix:**
  keep emoji codepoints out of the markup. Fake the look with the embedded brand font instead (a sparkle
  becomes a small cluster of asterisks in the pack's display face), which renders instantly and stays on
  brand. If you genuinely need a pictographic glyph, bake it to a pre-rendered PNG/SVG and overlay that,
  never live text the browser has to font-resolve: [`emoji-to-png.py`](emoji-to-png.py)
  (`python3 workflows/emoji-to-png.py rocket=🚀 check=✅ --out projects/<job>/hf-graphics/assets/emoji`)
  renders the emoji to a PNG through PIL, then trims and pads it to a clean transparent PNG. **Smell test:** if
  a part is still rendering at ~3× what its siblings of the SAME length took, stop it and look through it for
  an emoji or other exotic glyph before assuming a real hang.
- ⭐ **An exit or transition tween must finish INSIDE its clip's `data-duration`, plus a hard-kill at the next
  clip's start.** HyperFrames hard-hides a clip the instant its window ends, so an exit fade still mid-dissolve
  at that boundary POPS off screen. Extend the clip's duration to contain the exit, and add
  `tl.set("#id",{opacity:0}, <next-clip-start>)` as the hard-kill. Lint flags a missing hard-kill
  (`gsap_exit_missing_hard_kill`), but a duration that is simply too short sails through lint and still pops
  in the finished video.
- ⭐ **Anything GSAP tweens gets no CSS `transform` for its starting position.** A stylesheet
  `transform:translateX(-115%)` gets absorbed into GSAP's transform cache, so a later `xPercent`/`x` tween nets
  the wrong end position. Let GSAP own position entirely: set the initial pose with `tl.set(...)` or
  from-values, and keep `transform` out of the CSS for anything the timeline touches.
- **Glass and panels must be opaque-bright.** A transparent overlay render has nothing behind it, so a
  `backdrop-filter` blur of the footage does NOT happen in isolation. Design panels to read on their own fill
  (frosted-bright) rather than on live backdrop blur, and the overlay composites identically to a same-pass
  render.
- ⭐ **Never GSAP-`transform` a `<video>` element: it silently drops out of the render.** Put a
  `transform`/`scale`/`x`/`y` on a `<video>` and HyperFrames' headless render quietly composites it away. The
  face just **vanishes** where the move should be, with no error and no lint. (The vendored
  faceless-explainer/pr-to-video pipelines hit the same wall: their hoisted `<video>` *"cannot follow in-scene
  GSAP transforms"*, so its slot must hold STILL.) A browser segment reframes through **layout, not
  transform**: the `<video id="head">` (`width:100%;height:100%;object-fit:cover`) sits inside a
  `<div id="headwrap">` with `overflow:hidden`, and GSAP animates the WRAPPER's `left/top/width/height`
  (+ `borderRadius`/`boxShadow`) from the full frame down to the card. The parent shrinks and slides and crops
  the still-untransformed video. So full-screen cutaways and face-reframe takeovers work as browser segments
  **only** through wrapper-box layout animation. **Better still, don't need it:** a pure scale, move or
  push-in PiP is cleaner as an `ffseg` (ffmpeg `zoompan`: no browser round-trip, no brightness dip) or as a
  move on a transparent overlay. Reach for the browser segment only when the reframe needs live graphics
  revealing *behind* the moving face.
- **Lint noise that is benign; don't "fix" it:** `duplicate_media_discovery_risk` (two synced video layers, a
  reused logo) is a **warning**; `missing_local_asset: <id>-base.mp4` clears once `render-part.sh` cuts the
  slice; `timeline_track_too_dense` is a **warning only** (it suggests sub-comps; fine to ship as-is);
  `missing_three_script` is a **false positive** for `+esm` module imports (WebGL still renders).

### At render time

- **Every render script names its HyperFrames version.** An unpinned `npx hyperframes` floats to whatever
  shipped last, and a contract change can land mid-job that way. Any render script a job's `build.py` emits
  must call `npx hyperframes@<tested version>` (currently `0.8.43`). Bump the pin deliberately: edit it,
  re-render one part, review, then adopt. (`reel_render.py` already reads the pin for you.)
- **Same frame rate as the footage.** Render every part at the base's frame rate (`--fps 24000/1001` for 23.976
  footage) so overlays and segments stay frame-aligned through ffmpeg. Mixed fps drifts.
- **Render parts at `-q standard`,** so `renders/final.mp4` is already final quality: the assemble is the
  deliverable, with no separate "final render" step.

### Footage pieces (segments and ffseg)

- **A segment carries its own base slice.** Cut the footage window once (`ffmpeg -ss A -to B`) into
  `assets/<id>-base.mp4`; the segment comp uses THAT as its `#head`/`#head2`, so its first and last frames
  match the base at the seam and the overlay is seamless.
- **Slice the footage where the segment is PLACED, not where it was built (the stutter/desync trap).** When the
  base gets spliced again and the graphics move by a `PLACE_SHIFT` (say, a lead-in added downstream), a
  segment's slice must be cut at `build_time + shift`, the spot where it is actually overlaid, NOT at the raw
  build time. Cut it at the build time and the segment's footage **jumps** at the seam (a visible stutter) and
  runs **out of sync** with the base audio for its whole duration, because it plays footage from the wrong
  moment. Overlays simply move with the shift (no footage, no problem); only segments carry footage, so after
  the base is spliced again, **cut a fresh slice at the placed time AND render the segment again**. To check:
  frame 0 of the slice should have the same luma as `ffmpeg -ss <placed_start> -i base` (same frame →
  aligned).
- **The segment brightness dip: fix it at the ROOT, not afterward.** A browser segment round-trips its
  footage through the HyperFrames headless browser (decode→RGB→re-encode), which **darkens the face ~3%**
  (YAVG ~2.8 on a 16–235 scale) against the passthrough base, so the face visibly dims at every segment seam.
  Overlays never show it (translucent graphics, no adjacent base to seam against); only footage segments do.
  Two root causes stack. Address them in this order:
  1. **Do footage motion in ffmpeg, not the browser: the `ffseg` kind.** A zoom, push-in or pan is pure YUV
     geometry. Render it with ffmpeg `zoompan` on the base slice and it NEVER enters the browser → **zero
     shift** (measured 92.42 vs base 92.38). The associated graphic (a chip or callout) stays a separate
     transparent overlay composited on top. This is the real fix; prefer it whenever the footage move is
     expressible in ffmpeg. `zoompan` gotchas: the width and height of `crop` cannot be animated, only x and y
     change per frame (`t` is undefined when w/h are configured, and it errors `-22`); scale the slice up 2×
     first (`scale=3840:2160` on a 1920×1080 base, `scale=2160:3840` on a 1080×1920 reel), or the zoom
     jitters from quantization; drive the easing from output time `on/fps` with a cosine, so the zoom is
     exactly 1.0 at both seams; and match `fps=` to the base, or frames drift.
  2. **When nothing but a browser segment will do** (a complex animated reframe, a rounded card with a border
     and graphics revealing behind, that ffmpeg can't sanely do): **extract the source frames as PNG.** Add
     `--video-frame-format png` to the segment's render. HyperFrames' default `auto` extracts to lossy JPG,
     which is most of the dip, so that alone roughly halves it (~2.8→~1.2). Whatever is left, close with a
     small **gamma** correction, a lutyuv applied to that one segment inside assemble (no re-render):
     `lutyuv=y='clip(pow(clip((val-16)/219,0,1),1/G)*219+16,16,235)'`. Gamma (not a flat gain) pins black and
     white, so highlights don't clip. After PNG, **G≈1.03** landed a takeover within 0.03 luma of the base.
     Re-derive G by comparing frame 0 (scale-1.0, same crop) of the segment render against its
     `<id>-base.mp4` slice via `signalstats` `YAVG`, tuning until they match.
- ⭐ **An `ffseg` zoom on a slice that doesn't start at t=0 needs `trim`+`setpts` to reset zoompan's `on`, or
  the zoom is CONSTANT (it reads as a cut, not a ramp).** `zoompan`'s frame counter `on` counts from where its
  filtergraph input begins. Slice with `-ss <S>` placed AFTER `-i` and ffmpeg still feeds zoompan frames
  counted from the **video start**, so for a mid-video part (`S>0`) `on` is already huge at frame 0 and an
  `on`-based ramp (`1+amp/(1+exp((c-on)/w))`, `1+amp*(1-on/N)^2`, a cosine, …) sits pinned at its end value
  for the entire clip: the zoom never moves, and on screen it looks like a hard cut. It is invisible when the
  part starts at 0, so an opening zoom works by luck. **Fix:** build the slice with
  `trim=start=S:end=E,setpts=PTS-STARTPTS,<zoompan…>` in the filtergraph (NOT `-ss S -t DUR`), so zoompan
  receives only the windowed frames and `on` starts at 0, and have the harness's ffseg branch always build it
  that way. Verify by eye: the slice's frame 0 must match the base at `S` (scale 1.0), and later frames are
  visibly zoomed.
- **Footage moves follow the cut as MEASURED in the render, never its nominal time.** A rendered base can
  drift from the nominal cut timeline (`cuts.json`/`segments.tsv`), by ~0.4s by the end of a reel, and the
  transcript shares that drift. A NOSHIFT `ffseg` zoom placed at the nominal cut therefore lands early and
  creeps onto the previous clip's tail. Take the real cut from the *rendered* base:
  `ffmpeg -i video.mp4 -vf "scdet=threshold=0,metadata=print:file=-" -an -f null -`, then take the peak
  `scd.score` in the gap (same-framing jump cuts score low, so use `threshold=0` and pick the max rather than
  a fixed threshold). Cut the slice with `-ss <time>` **after** `-i` (decode-accurate; `-ss` before `-i` is
  keyframe-only and can be off by ~0.5s). A `PLACE_SHIFT` applied to overlays is an approximate correction
  for this same drift, but footage `ffseg` parts are NOSHIFT, so anchor them to the measured cut explicitly.

### In the composite (ffmpeg)

- ⭐ **Give every overlay `:eof_action=pass` (the one held push-in excepted); without it ffmpeg quietly
  repeats roughly every fourth output frame (the stutter trap).** `overlay` defaults an ended input to
  `eof_action=repeat`. Chain ~9 short overlays over the long base, each defaulting to repeat, and the frame
  scheduler, juggling several ended-but-still-repeating inputs, starts duplicating OUTPUT frames on a
  periodic cadence (measured **exactly 1 in 4**). What makes it vicious: the output is dead-even CFR (23.976), so ffprobe, frame counts and PTS all
  read **perfectly fine**, while the content only changes ~18×/sec inside a 24fps costume: visible judder,
  worst on smooth motion like a zoom. And every *input* (the zoom clip, the slice, the base) measures clean in
  isolation; the duplicates exist ONLY in the assembled output, so you keep "fixing" a zoom that was never
  broken. **Fix:** set `:eof_action=pass` on every `overlay=` ("when this input ends, pass the base through
  untouched": no repeat, no dup). Only a frame held on purpose (the push-in below) gets `repeat`. Have
  `build.py` emit `pass` on every part and `repeat` only on the held one, so a hand-edit of `assemble.sh`
  can't silently drop it. **Detect:**
  `ffmpeg -i out.mp4 -vf "signalstats,metadata=print:key=lavfi.signalstats.YDIF:file=-" -f null -` and tally
  the `YDIF=0` lines (exact duplicates): clean is ~0–3%, the bug ~25%. `assemble.sh` runs this automatically
  after every composite and **exits 1 if dups ≥ 8%**. That smoothness guardrail is the real "never again"; do
  not remove it. **Do NOT** mask stutter by forcing CFR (`-r`/`fps=`): the output is already CFR, so that only
  re-times the duplicates and buries the cause.
- **To hold a footage zoom to the end (a push-in that doesn't zoom back out), use the overlay's
  `eof_action=repeat`, NOT `tpad`.** `tpad=stop_mode=clone` chained after `zoompan` (with videotoolbox) RUNS
  AWAY: it never EOFs, and it ballooned a ~4s clip past 1GB before it was killed (the same no-EOF family as the
  `-loop 1` PNG-overlay trap). Instead, let the zoompan clip end naturally (it trims ~2 frames off the tail)
  and set `eof_action=repeat` on that part's `overlay=` in `assemble.sh`; it holds the last zoomed frame
  through to the end of the base, with no pop-out.
