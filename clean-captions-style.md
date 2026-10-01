<!-- Starter values, not anyone's brand yet. To make them yours, fill out brand-kit.md and say
     "use my brand kit", or change the values in this file by hand. -->

# Clean Captions: hook card + line captions, burned in (pull-reels `--captions clean` and fallback)

Captions in the CapCut flow are native Auto Captions (step 5). This builder is the older burn-in behind the
clean-captions look for a full-frame talking head: one card over the hook, and after that nothing on the
footage but plain line captions. No word build, no karaoke highlight, no motion of any kind. When a reel is
burned in this way the look is locked: use it exactly. `pull-reels` burns a clip this way when asked for
`--captions clean`, and automatically for any clip whose style-pack captions (its default, in beta) cannot finish;
a single reel captions through its style pack or CapCut's Auto Captions instead.

Builder: [`presets/clean-captions/build.py`](clean-captions/build.py) · Word fixes: [`presets/caption-corrections.json`](caption-corrections.json)

## Run it (steps 3 + 5: hook card + captions)

It needs the rough cut and its transcript first: `outputs/<job>.mp4` and `outputs/<job>.transcript.json`.

1. **Preview** just the opening 30 seconds while the hook copy settles:
   `python3 presets/clean-captions/build.py projects/<job> --until 30 --hook-text "your hook"`
   That writes `<temp dir>/reels-editing-engine/<job>/clean-captions/preview.mp4` (`<temp dir>` is Python's
   `tempfile.gettempdir()`: `$TMPDIR` under `/var/folders` on macOS, not `/tmp`) and prints the caption sheet
   along with the `hook_end` it detected.
2. **Final:** drop `--until` and write the deliverable:
   `python3 presets/clean-captions/build.py projects/<job> --hook-text "your hook" --out projects/<job>/outputs/<job>.final.mp4`

The builder reads `outputs/<job>.mp4` as its clean base; the captioned file is `outputs/<job>.final.mp4`.
Never overwrite the base, or the next run captions a video that already has captions.

## The two layers (locked)

Neither layer moves. Each cuts on and off.

| | **Hook card** (top) | **Captions** (bottom) |
|---|---|---|
| Font | Inter **Bold**, from `assets/fonts/Inter-Bold.otf` | Inter **Bold** |
| Size | `64px` | `76px` |
| Color | black `#000` text on a solid white `#fff` box | a black `3px` stroke (`stroke_fill`) around white `#fff` text; **no box** |
| Shape | radius `22px`, measured to the **real ink extents** rather than the font metrics, plus `32px` horizontal and `20px` vertical padding, so it hugs the words instead of ballooning; maximum width `940px`, centered | short lines (`CAP_MAX_WORDS=4` / `CAP_MAX_CHARS=16`), broken at clause and sentence punctuation |
| Where | top of the box at `y280`, immediately below the 270px top safe band | centered horizontally, with its vertical center at `y1145`: under the face, at chest height |
| When | only while the hook is spoken | the whole reel, first word to last |
| Motion | none | none: each line cuts in and **holds until the next one starts**, so nothing flickers and no gap opens |

**Safe zones:** every key visual stays within `y270 → y1620`, with the hook card below 270 and the captions
above 1620.

**Same size, same place, every reel.** The card never moves or shrinks on its own: only when she asks. Two
things are raised for her to decide, and neither changes the render: when the job's `subject-zones.json` (cut-shorts
measures every clip) shows the card overlapping her head because she sits high in the frame, and when the hook runs
more than two lines (rewrite it shorter, or a smaller size).

**The hook card's window.** `HOOK_END_WORDS` ships empty, so by default the card ends itself at the first
sentence break, which suits fragment stacking because the first fragment IS the hook. Give it a trigger word
there if a reel wants one, or set the end outright with `--hook-end SECONDS`.

**The hook card's copy** is written, not necessarily what was said: lowercase and casual, in the brand voice.
Set it with `--hook-text "..."`.

**Captions are always on.** They run the whole video; the hook card lies over the top of them during its
window and never replaces them.

## Where the words come from

The one canonical transcript is `projects/<job>/outputs/<job>.transcript.json`. Its word timings come from
WhisperX large-v3 and are remapped through `cuts.json`, which puts them on the same clock as the audio that
ships, so lines land on the beat with nothing adjusted by hand. **Caption the render that SHIPS**, meaning the
final cut. Never re-transcribe, and never take timings from a partial transcript.

On the way to the screen, every word passes through the `auto` map in
[`caption-corrections.json`](caption-corrections.json), the place a misheard brand name, product name or bit of
casing gets put right. Display text only; the transcript itself is never altered. The builder also **drops
single-word lines under 0.2s**: at a cut those are almost always the leftover tail of a false start, not a real
caption. Add to the corrections file whenever a new mishear turns up.

## How it is drawn

PIL draws each overlay as a PNG, and ffmpeg's `overlay` composites them with enable-timing. This ffmpeg has
neither `drawtext` nor `libass`, while PIL controls the Inter weight, the stroke and the box exactly, so this
is the house pattern rather than a workaround.

## Changing it (only when asked)

| Layer | Knob | Changes |
|-------|------|---------|
| captions | `CAP_SIZE` | size |
| captions | `CAP_WEIGHT` | weight (`Semibold`, `Regular`, …) |
| captions | `LINE["edge"]` | stroke width |
| captions | `CAP_CENTER_Y` | height on the frame |
| captions | `CAP_MAX_WORDS` / `CAP_MAX_CHARS` | how long a line runs |
| captions | map `.upper()` in `render_caption` | uppercase |
| hook card | `--hook-text`, `--hook-end` | the copy and the end time, per run |
| hook card | `HOOK_SIZE` | text size |
| hook card | `CARD["air_x"]`, `CARD["air_y"]` | padding around the words |
| hook card | `CARD["corner"]` | corner radius |
| hook card | `HOOK_TOP_Y` | height of the box top |
| hook card | `HOOK_WEIGHT` | weight |
