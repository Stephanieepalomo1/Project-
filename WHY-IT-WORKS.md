# Preset Engineering Notes: why each lock holds

> The reasoning behind the locked presets, kept out of the always-loaded `CLAUDE.md` because it is
> reference material, not a per-turn rule. Read the stage you are about to touch before you extend it, so a
> gotcha that was already solved stays solved. Stages follow the pipeline in `CLAUDE.md`; each note gives the
> lock, why it is there, and where it lives. The table at the end maps every lock to the file that owns it.

---

## STAGE 2 · ROUGH CUT

**One transcription per video.**
- **The lock:** WhisperX large-v3 is the single transcription for the whole pipeline. It is the most
  accurate, so it is the source of truth. `rough-cut` persists it to `projects/<job>/transcript/words.json`
  and reuses it forever (`--force` to redo). The WhisperX venv builds once and is reused across jobs.
- **Nothing downstream re-transcribes.** Finishing and captions never do: `stitch-cut.sh` derives
  `outputs/<job>.transcript.json` by remapping the kept words through `cuts.json`, which is pure arithmetic.
- **Spelling and brand fixes happen right there.** As it writes that canonical transcript,
  `kept-words.py` runs `presets/caption-corrections.json` over it, so the fix reaches graphics-plan and
  both caption formats, while the raw `words.json` stays untouched. The locked caption builders (step 5) read
  the already-corrected `outputs/<job>.transcript.json` directly.

**The splice: three audio artifacts fixed at the root in `stitch-cut.sh`, plus a self-check. Do not simplify any
of these away.**
1. **Cuts snap to the video frame grid.** Unsnapped, fractional cuts give each segment a video duration up to
   ±1 frame off its audio, and ffmpeg's `concat` pads the difference with digital-silence gaps at the joints:
   audible room-tone dropouts, plus a timeline that stretches progressively until captions and graphics
   desync. Snapped, the rendered timeline equals `transcript/cuts.json` exactly, so everything downstream
   anchors to EDL times directly.
2. **Joints are J-cut crossfades.** Each one is an equal-power crossfade over real, continuing room tone
   (each segment's audio runs 15 ms past its video cut). Never a butt-splice, which clicks on any non-zero
   crossing, and never a fade to zero, which punches an audible ambience hole. Timing stays exact by
   construction. A per-joint `"xfade": <seconds>` override in `cuts.json` widens the ramp into a segment whose
   cut-in clips an in-progress word attack (acoustic onsets often start tens of ms before the word timestamp).
3. **The limiter runs with `latency=1`.** Its lookahead otherwise delays the audio ~5 ms against the video.

**The self-check.** After every splice, **`sound-check.py`** verifies the joints, ambience continuity, timeline
integrity and limiter pressure. A limiter-pressure warning means the footage is peakier than the default gain
assumes: re-run with `VOICE_GAIN_DB=8` and compare by ear.

---

## STAGE 3 · GRAPHICS

**Plan first, place by measurement.** `graphics-plan` decides which beats get a graphic; each graphic is built in
the creator's style pack and placed in the open space around her, read from `workflows/subject-zones.py`, never
over her face and always inside `product/safe_zones.py`'s band.

---

## STAGE 4 · SECOND PASS

**Render part by part and composite with ffmpeg; never re-render the whole video per change.** Full doc:
[`workflows/graphics-part-by-part.md`](../workflows/graphics-part-by-part.md).
- A parts-oriented `build.py` emits one composition PER graphic, plus `render-part.sh <id>` and `assemble.sh`.
- **Two part kinds.** An **overlay** floats over the footage, so it renders standalone as a transparent `.mov`
  via `--format mov`. A **segment** modifies the footage itself, so it renders as an opaque `.mp4` that
  carries its own base slice.
- `assemble.sh` is ONE ffmpeg pass chaining the base and each part with `-itsoffset` +
  `overlay=enable='between(...)'`.
- **The loop:** edit `build.py` → render only the changed part (~30–50s) → assemble (~5s) → review. The base
  rough cut NEVER gets rendered a second time.
- Render every part at the base fps (e.g. `--fps 24000/1001` for 23.976) or frames drift through ffmpeg.
- The win is modest on a short reel and compounds the longer the video runs.

**Render cut drift.** A rendered base can drift ~0.4s from the nominal cut timeline, so footage zooms and
cuts anchor to MEASURED scene-cut times (ffmpeg `scdet`), not to the nominal `cuts.json` times.

---

## STAGE 5 · CAPTIONS

A single reel captions through the creator's style pack or CapCut's Auto Captions. `pull-reels` captions its
clips through the style pack too (beta); the Clean Captions burn-in below is its `--captions clean` option and
the automatic fallback for any clip the pack route cannot finish.

**Clean Captions.**
- **Files:** hook card + line captions live in
  [`presets/clean-captions-style.md`](../presets/clean-captions-style.md) + builder
  [`presets/clean-captions/build.py`](../presets/clean-captions/build.py).
- **Hook card:** Inter Bold 64px, black on a white box sized to the ink extents (not the font metrics), pinned
  top (y280), and shown only over the spoken hook. It auto-ends on a configured trigger word or `--hook-end`.
- **Captions:** Inter Bold 76px white + 3px black stroke, no box, no animation, line by line, under the
  face at chest height (y1145). **Captions are ALWAYS ON** for the whole video; the hook card overlays on top of them and never
  replaces them.
- **Engine:** PIL PNG overlays + ffmpeg `overlay` enable-timing. This ffmpeg has no freetype/libass, so PIL is
  the house pattern.
- **Output:** the deliverable is `outputs/<job>.final.mp4`. `outputs/<job>.mp4` stays the untouched base the
  builder reads; don't overwrite it, or you'll caption an already-captioned video.
- **Gotcha:** the `-loop 1` PNG overlay inputs never EOF, so the output MUST be bounded with `-t` (the source
  duration). The builder always passes it.

---

## STAGE 7 · EXPORT AND HOUSEKEEPING

**`scripts/free-space.sh` reclaims space in `projects/`.** It deletes only regenerable dead weight: HyperFrames
`work-*` render scratch, stray `node_modules`, and intermediate renders, while keeping `*final*`/`*graphics*` +
the highest `-vN`. It never touches the source `raw/*.mp4` or `outputs/`. Dry-run by default; `--apply` to
delete. The space hogs are raw footage and leftover render scratch.

---

## WHERE EACH LOCK LIVES

| Lock | Owned by |
|---|---|
| One transcription, corrections applied once | the `rough-cut` skill (`stitch-cut.sh`, `kept-words.py`) + `presets/caption-corrections.json` |
| Frame-snapped, crossfaded, latency-compensated splice | the `rough-cut` skill's `stitch-cut.sh`, checked by its `sound-check.py` |
| Part-by-part second pass | `workflows/graphics-part-by-part.md` |
| Pull-reels clip captions, style pack (beta) | `build-reel-type.py` → `reel_render.py` → `build-reel-mp4.py`, run per clip by `cut-shorts.py` |
| Clean Captions (pull-reels `--captions clean` and fallback) | `presets/clean-captions/build.py` |
| Disk space | `scripts/free-space.sh` |
