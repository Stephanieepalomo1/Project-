#!/usr/bin/env python3
"""clean-captions/build.py — used by pull-reels, which runs it to burn the captions and hook card onto every
clip it cuts (.claude/skills/pull-reels/scripts/cut-shorts.py). A single reel does not caption through it: those
caption through the style packs or CapCut's Auto Captions. What it draws is the Clean Captions burn-in: a hook card while the hook is being said, and
plain caption lines under the face for the whole reel. LOCKED PRESET, written up in
presets/clean-captions-style.md.

Both layers are stills that cut on and cut off. Nothing slides, fades or scales.
  hook card  a white rounded box of black Inter near the top, up only until the hook has been said
  captions   one short line at a time, white Inter with a black stroke and no box, low under the face.
             A line stays until the next one replaces it, so nothing blinks off between lines.

Every word and every time comes from outputs/<job>.transcript.json, the one transcript already remapped
through cuts.json onto the cut. This script never transcribes anything.

PIL draws each layer as a transparent PNG and ffmpeg lays the PNGs over the cut with time-gated
`overlay` filters. The split is on purpose: the ffmpeg this engine runs on has neither drawtext nor libass,
and PIL sets the weight, the stroke and the box exactly.

  a quick look while the hook copy settles (the first 30 seconds, rendered into the scratch folder):
    python3 presets/clean-captions/build.py projects/<job> --until 30 --hook-text "your hook"
  the deliverable, which drops --until and names its output:
    python3 presets/clean-captions/build.py projects/<job> --hook-text "your hook" --out projects/<job>/outputs/<job>.final.mp4

--hook-end pins the moment the card comes down. Leave out the hook copy and there is no card at all:
the captions run on their own.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "product"))
from video_encoder import pick_encoder   # the engine's one encoder choice, shared by every ffmpeg render
import safe_zones                        # where the platform draws its own UI: one source for every builder
from PIL import Image, ImageDraw, ImageFont

# ---- THE LOCKED LOOK -------------------------------------------------------------------------------
# Drawn on the 1080x1920 frame. These numbers are the preset: change one only when someone asks for it.
W, H = 1080, 1920
MID_X = W / 2                          # both layers sit centred on the frame's vertical midline
SAFE_TOP = safe_zones.TOP              # the hook card may not start above this line (checked as it is drawn)
SAFE_BOT = safe_zones.BOTTOM           # and no key visual goes below this one

_HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(_HERE, "..", "..", "assets", "fonts", "Inter-Bold.otf")   # bundled: no system font needed
FALLBACK_FONT = FONT_PATH              # the same bundled face: a second try if the first open fails
HOOK_WEIGHT = "Semibold"               # named instance to ask for; a static face keeps its own weight
CAP_WEIGHT = "Semibold"

# the hook card: one white box of black type, sized to the ink it holds
HOOK_SIZE = 64                         # px
HOOK_TOP_Y = SAFE_TOP + 10             # y of the card's top edge: just under the platform's top band
CARD = {
    "widest": 940,                     # px: the copy wraps inside this
    "air_x": 32, "air_y": 20,          # white beside and above/below the ink
    "corner": 22,                      # px of rounding
    "row_gap": 10,                     # extra px between wrapped rows
    "paper": (255, 255, 255, 255),
    "ink": (0, 0, 0, 255),
}

# the captions: white type with a black edge, low in the frame. The four knobs below keep their names:
# the style notes and the brand kit refer to them.
CAP_SIZE = 76                          # px
CAP_CENTER_Y = 1145                    # the caption block is centred on this y, below the face
CAP_MAX_CHARS = 16                     # a line closes once its text reaches this many characters,
CAP_MAX_WORDS = 4                      # or this many words, whichever comes first
LINE = {
    "widest": 960,                     # px: wider than this wraps onto a second row
    "edge": 3,                         # px of black around every letter
    "ink": (255, 255, 255, 255),
    "edge_ink": (0, 0, 0, 255),
    "row_gap": 8,                      # extra px between wrapped rows
    "linger": 0.40,                    # seconds the last line stays up after the final word
}

DEFAULT_HOOK_TEXT = ""  # each reel passes its own hook with --hook-text

# The spoken hook-end trigger: the card comes down just after the first word that starts with one of
# these, e.g. HOOK_END_WORDS = ("okay",). Empty means no trigger word, and the card ends at the first
# sentence break instead, which suits fragment stacking because the first fragment IS the hook.
# --hook-end on the command line overrides both for one run.
HOOK_END_WORDS = ()

SENTENCE_ENDERS = (".", "?", "!", "…")   # a word ending in one of these finishes its caption line


# ---- WORDS -----------------------------------------------------------------------------------------
# A transcribed word = leading marks, the word, trailing marks. Only the middle is looked up, so a fix
# keeps the punctuation around it: "claude," reads "Claude,".
_WORD_PARTS = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


def load_word_fixes(repo_root):
    """The `auto` table from presets/caption-corrections.json (mishear -> fix), or nothing when the file
    is not there. A key only matches as written, so keys belong in lowercase."""
    fixes = {}
    path = os.path.join(repo_root, "presets", "caption-corrections.json")
    if os.path.exists(path):
        fixes.update(json.load(open(path, encoding="utf-8")).get("auto", {}))
    return fixes


def shown_as(word, fixes):
    """The word as it reads on screen: a listed mishear swapped for its fix, marks kept. Anything that is
    all marks, or not in the table, or mapped to an empty fix, comes back exactly as heard."""
    lead, core, trail = _WORD_PARTS.match(word).groups()
    fix = fixes.get(core.lower()) if core else None
    return f"{lead}{fix}{trail}" if fix else word


def caption_lines(words):
    """Group the words into on-screen lines -> [{"text", "start", "end"}], in order.

    A line closes at a sentence end, at CAP_MAX_WORDS words, or once its text reaches CAP_MAX_CHARS.
    Every line then stays up until the next one starts, so the captions never blink off mid-thought, and
    the last one lingers LINE["linger"] seconds after the final word."""
    lines, group = [], []

    def close():
        if not group:
            return
        text = " ".join(member["disp"] for member in group)
        start, end = group[0]["start"], group[-1]["end"]
        span = end - start
        # One word on screen for under 0.2s is nearly always the clipped tail of a false start at a cut.
        if not (len(group) == 1 and span < 0.20):
            lines.append({"text": text, "start": start, "end": end})
        group.clear()

    for word in words:
        group.append(word)
        text = " ".join(member["disp"] for member in group)
        if (word["disp"].rstrip().endswith(SENTENCE_ENDERS) or len(group) >= CAP_MAX_WORDS
                or len(text) >= CAP_MAX_CHARS):
            close()
    close()

    for line, following in zip(lines, lines[1:]):
        line["end"] = following["start"]
    if lines:
        lines[-1]["end"] += LINE["linger"]
    return lines


def hook_end_time(words, override):
    """When the hook card comes down: --hook-end when given; else 0.1s after the first HOOK_END_WORDS
    word; else 0.1s after the first word that ends a sentence; else 5 seconds in. Matched on the words
    as heard, before any fix."""
    if override is not None:
        return override
    end = None
    if HOOK_END_WORDS:
        end = next((word["end"] + 0.10 for word in words
                    if word["text"].lower().strip(".,?!").startswith(HOOK_END_WORDS)), None)
    if end is None:
        end = next((word["end"] + 0.10 for word in words if word["text"].rstrip().endswith(SENTENCE_ENDERS)),
                   None)
    return end or 5.0


# ---- DRAWING ---------------------------------------------------------------------------------------
def open_face(size, weight):
    try:
        font = ImageFont.truetype(FONT_PATH, size)
    except OSError:
        font = ImageFont.truetype(FALLBACK_FONT, size)
    try:
        font.set_variation_by_name(weight)   # only a variable face has named weights; the bundled one is static
    except Exception:
        pass
    return font


def blank():
    """A fully transparent full-frame layer."""
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def wrap(text, font, max_w, probe):
    """Break text into rows no wider than max_w. A word that is wider on its own still gets a row of its
    own rather than being cut."""
    rows, row = [], ""
    for word in text.split():
        candidate = f"{row} {word}" if row else word
        fits = probe.textlength(candidate, font=font) <= max_w
        if fits or not row:
            row = candidate
        else:
            rows.append(row)
            row = word
    if row:
        rows.append(row)
    return rows


def trim(layer):
    """Cut a layer down to what was drawn, plus 4px of air, kept inside the frame -> (image, x, y).
    A layer with nothing on it comes back whole, at (0, 0)."""
    drawn = layer.getbbox()
    if not drawn:
        return layer, 0, 0
    left, top = max(0, drawn[0] - 4), max(0, drawn[1] - 4)
    right, bottom = min(W, drawn[2] + 4), min(H, drawn[3] + 4)
    return layer.crop((left, top, right, bottom)), left, top


def render_caption(text, font, probe):
    """One caption line as a layer -> (image, x, y): white type with a black stroke and no box, the
    block centred on CAP_CENTER_Y. Text too wide for LINE["widest"] wraps onto more rows."""
    rows = wrap(text, font, LINE["widest"], probe)
    pitch = sum(font.getmetrics()) + LINE["row_gap"]
    layer = blank()
    pen = ImageDraw.Draw(layer)
    y = CAP_CENTER_Y - pitch * len(rows) / 2
    for row in rows:
        pen.text((MID_X, y), row, font=font, fill=LINE["ink"], anchor="ma",
                 stroke_width=LINE["edge"], stroke_fill=LINE["edge_ink"])
        y += pitch
    return trim(layer)


def render_hook(copy, font, probe):
    """The hook card as a layer -> (image, x, y).

    The copy is set first on its own layer and the card is sized to the ink that actually landed, not to
    the font's ascent and descent, so the white hugs the words. Copy with no ink at all (empty, or only
    spaces) returns an empty layer: cropping to a bounding box that does not exist would hand back the
    whole frame, and the card would cover the footage."""
    rows = []
    for para in copy.split("\n"):
        rows += wrap(para, font, CARD["widest"] - 2 * CARD["air_x"], probe) or [""]   # a blank paragraph keeps its row
    pitch = sum(font.getmetrics()) + CARD["row_gap"]
    ink = blank()
    pen = ImageDraw.Draw(ink)
    y = 120                                # anywhere clear of the edges: only the size of the ink is used
    for row in rows:
        pen.text((MID_X, y), row, font=font, fill=CARD["ink"], anchor="ma")
        y += pitch
    drawn = ink.getbbox()
    if drawn is None:
        return trim(blank())
    lettering = ink.crop(drawn)
    card_w, card_h = lettering.width + 2 * CARD["air_x"], lettering.height + 2 * CARD["air_y"]
    card_x, card_y = (W - card_w) // 2, HOOK_TOP_Y
    assert card_y >= SAFE_TOP, "the hook card runs into the top safe band"
    card = blank()
    ImageDraw.Draw(card).rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h],
                                           radius=CARD["corner"], fill=CARD["paper"])
    card.alpha_composite(lettering, (card_x + CARD["air_x"], card_y + CARD["air_y"]))
    return trim(card)


def hook_notes(job_dir, top, bottom, rows):
    """Things worth raising with her about the hook card -> a list of plain lines (printed, never a failure).
    The card itself NEVER moves or shrinks on its own: same size, same place, every reel, unless she asks for
    something different (locked, owner decision). So nothing here changes the render. Two things get raised:
      * she is framed high: the card overlaps her head, per THIS job's own subject-zones.json (never a parent
        folder's, which is framed differently). Hers to decide: keep it, or place it somewhere else.
      * the hook runs long: more than two lines. Hers to decide: rewrite it shorter, or a smaller size."""
    notes = []
    path = os.path.join(job_dir, "subject-zones.json")
    if os.path.exists(path):
        try:
            zones = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            zones = {}
        head = (zones.get("subject") or {}).get("head_top")
        if isinstance(head, (int, float)) and bottom > head:
            notes.append(f"you sit high in the frame here: the hook card (y{top} to y{bottom}) overlaps your head, "
                         f"which starts at y{int(head)}. It is placed as always. Want to consider a different "
                         f"spot for the hook on this one?")
    if rows > 2:
        notes.append(f"this hook runs {rows} lines. It is placed as always, at full size. Want to rewrite it "
                     f"shorter, or use a smaller size?")
    return notes


# ---- RENDER ----------------------------------------------------------------------------------------
def scratch_dir(job):
    """This job's layers (and the default preview) go in the engine's scratch folder under the system temp
    dir. Never a literal /tmp: on native Windows that lands somewhere Git Bash cannot see."""
    return os.path.join(tempfile.gettempdir(), "reels-editing-engine", job, "clean-captions")


def media_seconds(path):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "default=nk=1:nw=1", path])
    return float(out.decode().strip())


def overlay_chain(layers):
    """The filter graph that stacks each layer over the cut for its own time window -> (graph, label of
    the finished picture).

    The layers are drawn on the W x H reel canvas, so the cut is brought to that canvas first (cover, then
    centre-crop, the same transform the other builders use). A cut straight off a 4K phone (1728x3072, say)
    would otherwise take every layer at its 1080-frame x,y: the captions small, high and left of centre."""
    links = [f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[base]"]
    below = "base"
    for n, (_png, x, y, t_on, t_off) in enumerate(layers, start=1):
        links.append(f"[{below}][{n}:v]overlay={x}:{y}:enable='between(t,{t_on:.3f},{t_off:.3f})'[v{n}]")
        below = f"v{n}"
    return ";".join(links), below


def build(job_dir, until, hook_end_at, hook_copy, out_path):
    job_dir = os.path.abspath(job_dir)
    job = os.path.basename(job_dir)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cut = os.path.join(job_dir, "outputs", f"{job}.mp4")
    transcript = os.path.join(job_dir, "outputs", f"{job}.transcript.json")
    assert os.path.exists(cut), f"missing render: {cut}"
    assert os.path.exists(transcript), f"missing transcript: {transcript}"
    cut_seconds = media_seconds(cut)

    fixes = load_word_fixes(repo_root)
    words = json.load(open(transcript, encoding="utf-8"))["words"]
    for word in words:
        word["disp"] = shown_as(word["text"], fixes)
    hook_end = hook_end_time(words, hook_end_at)

    work = scratch_dir(job)
    os.makedirs(work, exist_ok=True)
    for old_layer in glob.glob(os.path.join(work, "*.png")):
        os.remove(old_layer)   # the folder only ever holds this run's layers (os.remove, not a shell rm: Windows)

    cap_font = open_face(CAP_SIZE, CAP_WEIGHT)
    hook_font = open_face(HOOK_SIZE, HOOK_WEIGHT)
    probe = ImageDraw.Draw(blank())        # only ever measures text widths

    layers = []   # (png, x, y, on, off)
    # No copy means no card at all, not an empty white box: the captions carry on by themselves.
    if hook_copy and hook_copy.strip():
        still, x, y = render_hook(hook_copy, hook_font, probe)
        ink = still.getbbox()
        if ink:
            rows = sum(len(wrap(p, hook_font, CARD["widest"] - 2 * CARD["air_x"], probe) or [""]) for p in hook_copy.split("\n"))
            for note in hook_notes(job_dir, y + ink[1], y + ink[3], rows):
                print(f"[clean-captions] for you to decide: {note}")
        png = os.path.join(work, "hook.png")
        still.save(png)
        layers.append((png, x, y, 0.0, hook_end))

    lines = caption_lines(words)
    if until:
        lines = [line for line in lines if line["start"] < until]
    for i, line in enumerate(lines):
        still, x, y = render_caption(line["text"], cap_font, probe)
        png = os.path.join(work, f"cap_{i:03d}.png")
        still.save(png)
        layers.append((png, x, y, line["start"], min(line["end"], until) if until else line["end"]))

    graph, picture = overlay_chain(layers)
    # A looped still never ends, so the output always gets an explicit length: the preview length when
    # there is one, the whole cut otherwise. Without it the render runs on past the end of the video.
    length = min(until, cut_seconds) if until else cut_seconds
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", cut]
    for png, *_ in layers:
        cmd += ["-loop", "1", "-i", png]
    cmd += ["-filter_complex", graph, "-map", f"[{picture}]", "-map", "0:a", "-t", f"{length:.3f}"]
    # The sound is the cut's own and nothing here touches it, so it is copied. Encoding it again would
    # stack a second lossy AAC pass under the splice's 256k one.
    cmd += [*pick_encoder(vbr="10M", crf=18, preset="veryfast"), "-c:a", "copy",
            "-movflags", "+faststart", out_path]

    print(f"[clean-captions] hook_end={hook_end:.2f}s  caption_lines={len(lines)}  overlays={len(layers)}")
    print(f"[clean-captions] rendering → {out_path}")
    subprocess.run(cmd, check=True)
    print(f"[clean-captions] done: {out_path}")
    # The caption sheet, so every line can be read back before anyone commits to it.
    for line in lines:
        print(f"  {line['start']:6.2f}-{line['end']:6.2f}  {line['text']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_dir")
    ap.add_argument("--until", type=float, help="stop the preview after this many seconds")
    ap.add_argument("--hook-end", type=float, help="end the hook card at this time, in seconds")
    ap.add_argument("--hook-text", default=DEFAULT_HOOK_TEXT)
    ap.add_argument("--out")
    args = ap.parse_args()
    job = os.path.basename(os.path.abspath(args.job_dir))
    out = args.out or os.path.join(scratch_dir(job), "preview.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    build(args.job_dir, args.until, args.hook_end, args.hook_text, out)


if __name__ == "__main__":
    main()
