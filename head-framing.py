# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless"]
# ///
"""
head-framing.py — where her head is in the frame, read off the footage instead of typed in by hand.

Two different moments ask that same question, so they share one detector (workflows/subject-zones.py and
product/chin_lock.py load it too):

  MEASURE       where her face and hair sit across the whole cut, and the 9:16 crop a source that is not
                1080x1920 needs first, centred on her face (pull-reels' cut-shorts.py reads that crop from
                head-framing.json to turn a wide recording into a vertical clip).
  ZOOM ANCHORS  --windows / --range: where her face sits inside EACH shot, so a push-in closes in on her
                rather than on the middle of the room.

Finding the head. Frames are pulled at even steps through the cut and OpenCV YuNet (its model ships in
assets/models/) boxes the face in each one. That box stops at the forehead, so the real top of the hair
takes a second look: the per-pixel median of every sampled frame is the empty room, because the wall stays
put and she does not, and the first row above her face that differs from it is where her hair starts. That
still works for dark hair against a dark wall, where an edge detector finds nothing. Each figure is a
median over the frames, which soaks up the drift from one take to the next.

  measure   uv run workflows/head-framing.py projects/<job>/outputs/<job>.mp4
            -> prints the face, the hair line and any 9:16 crop, saves projects/<job>/head-framing.json
  anchors   uv run workflows/head-framing.py <base-cut.mp4> --windows @projects/<job>/caption-plan.json \\
                --out projects/<job>/face-anchors.json
            uv run workflows/head-framing.py <base-cut.mp4> --range 4.3,6.1        (one window)
  --annotate OUT.PNG on measure also saves a frame with the measurement drawn onto it.
"""
import argparse, json, os, statistics, subprocess, sys
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

# ---- the frame every number here is expressed in ---------------------------------------------------------
REEL_W, REEL_H = 1080, 1920
DRIFT_WARN = 150               # px the face centre can move between takes before it deserves a warning
CUT_FRAMES = 12                # frames sampled across a whole cut

# ---- the detector ---------------------------------------------------------------------------------------
ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YUNET = os.path.join(ENGINE, "assets", "models", "face_detection_yunet_2023mar.onnx")
YUNET_MIN_SCORE = 0.6

# ---- the hair search --------------------------------------------------------------------------------------
HAIR_SPAN_X = 300              # look this far either side of the face centre...
HAIR_SPAN_UP = 350             # ...and this far above the top of the face box
ROOM_DIFF = 14                 # mean per-channel distance from the empty-room plate that makes a pixel hers
ROW_PIXELS = 25                # a row needs more of her pixels than this to count as the top of her head
# The room comparison needs a room that holds still. Handheld, the phone moves and the room moves with it, so
# the whole search band "differs from the room" and the answer was the top of the band (a hair line 400px
# into the ceiling). Measured on real reels beside her head, above her face: tripod or propped takes change
# 0-1% of those pixels frame to frame, a handheld selfie 64%. Past this share the hair is left unread.
ROOM_MOVING_SHARE = 0.25
HANDHELD_HAIR = 0.25           # handheld: her hair starts this share of the face box's height above its top
                               # (0.22 measured by hand on a real handheld take; a little more for volume)


def probe(video):
    """(width, height, seconds) of the first video stream, as it DISPLAYS. A phone filmed upright is often
    stored 1920x1080 with a 90-degree rotation tag; ffmpeg turns every frame it decodes the right way up,
    so the stored size would describe a frame nobody ever sees (and the detector, sized from it, refuses
    the upright frames). Same reading of the tag as product/probe.py. The seconds are the stream's own,
    or the file's when the stream does not say."""
    got = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,duration:stream_side_data=rotation:stream_tags=rotate:format=duration",
         "-of", "json", video], capture_output=True, text=True, check=True)
    info = json.loads(got.stdout or "{}")
    stream = (info.get("streams") or [{}])[0]
    w, h = int(stream["width"]), int(stream["height"])
    turn = 0
    for side in stream.get("side_data_list") or []:
        if side.get("rotation") not in (None, ""):
            turn = int(round(float(side["rotation"])))
            break
    if not turn:
        turn = int(round(float((stream.get("tags") or {}).get("rotate", 0) or 0)))
    if abs(turn) % 180 == 90:
        w, h = h, w
    seconds = stream.get("duration")
    if seconds in (None, "", "N/A"):
        seconds = (info.get("format") or {}).get("duration")
    return w, h, float(seconds)


def sample_frames(video, dur, n=CUT_FRAMES, t0=None, t1=None):
    """n decoded frames, one from the middle of each of n equal slices of [t0, t1] (the whole clip when no
    window is given). A window that is empty or backwards means the whole clip rather than no frames at
    all, and a timestamp ffmpeg cannot decode is skipped, so fewer than n can come back. The stills are
    read into memory and their scratch folder is removed before this returns."""
    import cv2, shutil, tempfile
    lo = 0.0 if t0 is None else max(0.0, float(t0))
    hi = dur if t1 is None else min(dur, float(t1))
    if not hi > lo:
        lo, hi = 0.0, dur
    scratch = tempfile.mkdtemp()
    times = [lo + (hi - lo) * (i + 0.5) / n for i in range(n)]
    frames = []
    try:
        for i, at in enumerate(times):
            png = os.path.join(scratch, f"f{i}.png")
            subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", video, "-frames:v", "1", "-y", png],
                           capture_output=True)
            frame = cv2.imread(png)
            if frame is not None:
                frames.append(frame)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return frames


def detect_faces(imgs, w, h):
    """The biggest face YuNet finds in each frame, as float (x, y, w, h). A frame with no face adds nothing."""
    import cv2
    yunet = cv2.FaceDetectorYN_create(YUNET, "", (w, h), score_threshold=YUNET_MIN_SCORE)
    faces = []
    for frame in imgs:
        found = yunet.detect(frame)[1]
        if found is None or not len(found):
            continue
        d = max(found, key=lambda d: d[2] * d[3])      # the largest box; on a tie the first one found wins
        faces.append((float(d[0]), float(d[1]), float(d[2]), float(d[3])))
    return faces


def hair_tops(imgs, face_cx, face_top, y_floor=0):
    """Per frame, the highest row of the band above her face where she stands out from the room.

    The room is the per-pixel median of all the frames: wall and furniture agree from frame to frame and
    she does not. Only a band is searched (HAIR_SPAN_X either side of the face centre, from HAIR_SPAN_UP
    above the face box down to its top, never above y_floor), which keeps a hand or a moving object in the
    background out of the answer. A frame where nothing in the band stands out adds nothing."""
    import cv2, numpy as np
    room = np.median(np.stack([f.astype(np.float32) for f in imgs]), axis=0)
    left, right = max(0, int(face_cx - HAIR_SPAN_X)), min(imgs[0].shape[1], int(face_cx + HAIR_SPAN_X))
    top, bottom = max(y_floor, int(face_top - HAIR_SPAN_UP)), int(face_top)
    if _room_moves(imgs, room, left, right, top, bottom):
        return []                  # handheld: there is no still room to tell her from (see ROOM_MOVING_SHARE)
    speck = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tops = []
    for f in imgs:
        hers = (np.abs(f.astype(np.float32) - room).mean(axis=2) > ROOM_DIFF).astype(np.uint8)
        hers = cv2.morphologyEx(hers, cv2.MORPH_OPEN, speck)     # lone noisy pixels are not hair
        rows = np.flatnonzero(np.count_nonzero(hers[top:bottom, left:right], axis=1) > ROW_PIXELS)
        if rows.size:
            tops.append(top + int(rows[0]))
    return tops


def _room_moves(imgs, room, left, right, top, bottom):
    """True when the room itself changes from frame to frame (a handheld phone), judged on the strips beside
    the search band, where only the room is. With no strip to judge by, the room is taken as still."""
    import numpy as np
    if bottom <= top or (left <= 0 and right >= imgs[0].shape[1]):
        return False
    shares = []
    for f in imgs:
        moved = np.abs(f.astype(np.float32) - room).mean(axis=2) > ROOM_DIFF
        strip = np.concatenate([moved[top:bottom, :left].ravel(), moved[top:bottom, right:].ravel()])
        if strip.size:
            shares.append(float(strip.mean()))
    return bool(shares) and statistics.median(shares) > ROOM_MOVING_SHARE


def room_moves(imgs, face_cx, face_top, y_floor=0):
    """The same test hair_tops() applies, for a caller that needs to say WHY the hair went unread."""
    import numpy as np
    room = np.median(np.stack([f.astype(np.float32) for f in imgs]), axis=0)
    left, right = max(0, int(face_cx - HAIR_SPAN_X)), min(imgs[0].shape[1], int(face_cx + HAIR_SPAN_X))
    return _room_moves(imgs, room, left, right, max(y_floor, int(face_top - HAIR_SPAN_UP)), int(face_top))


def _hair_line(frames, face_cx, face_top, y_floor=0):
    """The median hair top, or None when fewer than half the frames showed one."""
    tops = hair_tops(frames, face_cx, face_top, y_floor)
    return statistics.median(tops) if len(tops) >= len(frames) / 2 else None


def _median_face(boxes):
    """One face box standing in for all of them: centre x, centre y, width, height, top, each its own median."""
    mid = statistics.median
    return (mid(x + bw / 2 for x, y, bw, bh in boxes), mid(y + bh / 2 for x, y, bw, bh in boxes),
            mid(bw for x, y, bw, bh in boxes), mid(bh for x, y, bw, bh in boxes),
            mid(y for x, y, bw, bh in boxes))


def _even(v):
    return round(v / 2) * 2


def _to_nine_sixteen(w, h, face_x):
    """The crop a source that is not 1080x1920 needs first: full height, 9:16 wide (kept even), centred on
    her face and slid back inside the frame when that would run past an edge."""
    cw = _even(h * 9 / 16)
    x = max(0, min(w - cw, round(face_x - cw / 2)))
    return {"crop_w": cw, "crop_h": h, "crop_x": x, "ffmpeg": f"crop={cw}:{h}:{x}:0,scale={REEL_W}:{REEL_H}"}


def _header(video, w, h):
    """The two fields every JSON written here opens with."""
    return {"video": os.path.abspath(video), "source": {"w": w, "h": h}}


def _say_source(w, h, dur, extra=""):
    print(f"source: {w}x{h}  {dur:.1f}s{extra}")


def _fail(msg):
    print(msg)
    sys.exit(1)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
    print(f"wrote {path}")


def _save_frame(img, path):
    import cv2
    cv2.imwrite(path, img)
    print(f"annotated frame → {path}")


# ---------------------------------------------------------------------------------------------------------
# MEASURE

def measure(video, annotate=None):
    """Where her face and hair sit across this cut, plus the 9:16 crop a source that is not 1080x1920 needs
    first. Kept next to the job (head-framing.json) when the cut is a job's."""
    w, h, dur = probe(video)
    _say_source(w, h, dur)
    frames = sample_frames(video, dur)
    boxes = detect_faces(frames, w, h)
    if len(boxes) < len(frames) / 2:
        _fail(f"✗ a face showed up in just {len(boxes)} of {len(frames)} frames — "
              f"so no crop is being written. Set the framing by eye instead.")
    cx, cy, fw, fh, ftop = _median_face(boxes)
    centres_y = [y + bh / 2 for _x, y, _bw, bh in boxes]
    drift = max(centres_y) - min(centres_y)
    print(f"face: center=({cx:.0f},{cy:.0f})  box={fw:.0f}x{fh:.0f}  moves {drift:.0f}px between takes")
    if drift > DRIFT_WARN:
        print(f"⚠ the framing moves {drift:.0f}px between takes (past {DRIFT_WARN}) — "
              f"one median crop may not suit them all, so look over the draft carefully.")

    record = _header(video, w, h)
    record["face"] = {"cx": round(cx), "cy": round(cy), "w": round(fw), "h": round(fh),
                      "spread_y": round(drift), "frames": len(boxes)}

    # The hair is searched for on the frames as they were decoded, so in source pixels, beside the face
    # that was found there.
    hair = hair_src = _hair_line(frames, cx, ftop)
    if (w, h) != (REEL_W, REEL_H):
        crop = record["reframe"] = _to_nine_sixteen(w, h, cx)
        print(f'crop to 9:16 first: ffmpeg -vf "{crop["ffmpeg"]}"')
        # From here on everything is described in the reframed 1080x1920 frame. The crop keeps the full
        # height and the scale stretches it to 1920, so a height in the source maps across by that ratio.
        if hair is not None:
            hair = hair * REEL_H / h

    if hair is not None:
        record["hair_top"] = round(hair)
        print(f"hair top: y{hair:.0f}")
    else:
        print("hair line: not readable on this cut (a hood, a hat, or a handheld take), so only the face box is kept")

    folder = os.path.dirname(os.path.abspath(video))
    if os.path.basename(folder) == "outputs":        # a job's base cut: the answer lives with the job
        _write_json(os.path.join(os.path.dirname(folder), "head-framing.json"), record)

    _draw_measurement(frames, record, annotate, hair_src)
    return record


def _draw_measurement(frames, record, path, hair_src=None):
    """Red: the median face box. Yellow: the hair line. Drawn on the middle frame so a number can be
    checked by eye. Both are drawn where they sit on that source frame (the face box and the hair line
    as measured there), which is the record's own hair_top whenever the source is already 1080x1920.
    Nothing happens without a path."""
    if not path:
        return
    import cv2
    img, f = frames[len(frames) // 2], record["face"]
    x0, y0 = f["cx"] - f["w"] // 2, f["cy"] - f["h"] // 2
    cv2.rectangle(img, (x0, y0), (x0 + f["w"], y0 + f["h"]), (0, 0, 255), 6)
    if "hair_top" in record and hair_src is not None:
        y = round(hair_src)
        cv2.line(img, (0, y), (img.shape[1], y), (0, 255, 255), 3)
    _save_frame(img, path)


# ---------------------------------------------------------------------------------------------------------
# PER-SHOT ZOOM ANCHORS
#
# A zoom scales about the FRAME CENTER. When the creator does not sit dead center, a centre-anchored
# push-in enlarges the middle of the room and slides her toward the edge — the "it zoomed off to the
# side" bug. The motion planners therefore need the face position IN THE SHOT BEING ZOOMED, not one
# median for the whole cut: a creator re-frames between takes (measured on the first PC test reel:
# the face moved 0.14 of the frame width, x=0.508 on one take and x=0.652 on another), so a single
# anchor for the whole reel is wrong for every shot but one.
#
# Coordinates come back NORMALISED (0..1 of the source frame, origin top-left) so each consumer can
# convert into its own units: pixels for the ffmpeg bake, half-canvas units for a CapCut draft.
WINDOW_FRAMES = 5              # frames per window; a window is short, and 5 is enough for a median
WINDOW_MIN_FACES = 2           # below this a "median" is one lucky frame: fall back rather than trust it
STILL = 0.04                   # face wanders less than this within the window: trust the median fully
ROAMING = 0.15                 # ... and beyond this, a single anchor means nothing, so do not correct


def _normalised(cx, cy, w, h, found, of):
    return {"x": round(cx / w, 4), "y": round(cy / h, 4), "frames": found, "of": of}


def _confidence(boxes, w):
    """How much this window's median is worth trusting, 0..1, from how far the face WANDERS inside
    it. A static anchor can only hold a subject who stays put: if she moves during the shot, the
    median is stale by the time the zoom lands and the correction pushes the wrong way — verified on
    a real clip where a full correction pushed the subject past centre the other way.

    Spread is measured ROBUSTLY (median absolute deviation), not max-minus-min. Traced frame by
    frame, a real shot sat at x=0.666 for 1.4s and then jumped once: max-minus-min called that 0.138
    of wandering and would have switched the fix off, while the MAD was 0.006 — the face is in one
    place and one sample is not. Worst-case spread is the wrong question; "is she mostly in one
    place?" is the right one, and a handful of samples makes the worst case almost meaningless."""
    xs = sorted((x + bw / 2) / w for x, _y, bw, _bh in boxes)
    if len(xs) < 2:
        return 1.0, 0.0
    med = statistics.median(xs)
    spread = 2.0 * statistics.median([abs(v - med) for v in xs])   # a robust stand-in for the face's range
    if spread <= STILL:
        conf = 1.0
    elif spread >= ROAMING:
        conf = 0.0
    else:
        conf = (ROAMING - spread) / (ROAMING - STILL)
    return round(conf, 3), round(spread, 4)


def window_anchor(video, dur, t0, t1, w, h, n=WINDOW_FRAMES):
    """Median face centre within [t0,t1], normalised. None when this window has too few detections
    to be worth trusting. One hit out of five is not a median — it is a single frame, and a false
    positive there aims the zoom at the wrong part of the room. Measured on real footage: a window
    detecting 1/5 returned x=0.21 while every solid window on the same clip sat at 0.54-0.64. Below
    WINDOW_MIN_FACES the caller falls back to the whole-cut median, which is at least a real one."""
    frames = sample_frames(video, dur, n=n, t0=t0, t1=t1)
    if not frames:
        return None
    boxes = detect_faces(frames, w, h)
    if len(boxes) < WINDOW_MIN_FACES:
        return None
    cx, cy, _fw, _fh, _top = _median_face(boxes)
    got = _normalised(cx, cy, w, h, len(boxes), len(frames))
    got["confidence"], got["spread_x"] = _confidence(boxes, w)
    return got


def anchors(video, windows, out=None):
    """One anchor per window, with an honest fallback chain: the window's own face, else the
    whole-cut median, else frame centre. Every row says which it used, so a build can never
    silently pass off a centre zoom as an anchored one."""
    w, h, dur = probe(video)
    _say_source(w, h, dur, f"   windows: {len(windows)}")

    frames = sample_frames(video, dur)
    boxes = detect_faces(frames, w, h)
    whole = None
    if boxes:
        cx, cy, _fw, _fh, _top = _median_face(boxes)
        whole = _normalised(cx, cy, w, h, len(boxes), len(frames))
        whole["confidence"], whole["spread_x"] = _confidence(boxes, w)
        whole["confidence"] = round(whole["confidence"] * 0.5, 3)   # a whole-cut median is a guess for any one shot
        print(f"whole-cut median face: ({whole['x']:.3f}, {whole['y']:.3f})  "
              f"from {whole['frames']}/{whole['of']} frames")
    else:
        print("⚠ no face anywhere in the cut - every window falls back to frame centre")

    rows = []
    for a, b in windows:
        got, src = window_anchor(video, dur, a, b, w, h), "window"
        if got is None and whole is not None:
            got, src = dict(whole), "whole-cut"
        if got is None:
            got, src = {"x": 0.5, "y": 0.5, "frames": 0, "of": 0,
                        "confidence": 0.0, "spread_x": 0.0}, "frame-centre"
        rows.append({"start": round(float(a), 3), "end": round(float(b), 3),
                     "anchor": [got["x"], got["y"]], "source": src,
                     "confidence": got.get("confidence", 0.0),
                     "spread_x": got.get("spread_x", 0.0),
                     "frames": got["frames"], "of": got["of"]})
        note = ""
        if src != "window":
            note = f"  (too few detections; using the {src})"
        elif got["confidence"] < 0.99:
            note = (f"  (she moves {got['spread_x']:.2f} of the frame inside this window - "
                    f"correcting at {got['confidence'] * 100:.0f}%)")
        print(f"  {a:7.2f}-{b:7.2f}s  anchor=({got['x']:.3f}, {got['y']:.3f})  "
              f"[{src} {got['frames']}/{got['of']}]{note}")

    xs = [r["anchor"][0] for r in rows]
    spread = round(max(xs) - min(xs), 4) if len(xs) > 1 else 0.0
    if len(xs) > 1:
        print(f"face moves {spread:.3f} of the frame width across these windows - "
              f"{'per-shot anchors matter on this footage' if spread >= 0.05 else 'fairly still'}")

    doc = dict(_header(video, w, h), whole_cut=whole, x_spread=spread, windows=rows)
    if out:
        _write_json(out, doc)
    else:
        print(json.dumps(doc, indent=2))
    return doc


def parse_windows(spec):
    """--windows takes inline JSON or @file. The file can be a bare [[a,b],...] list, a caption-plan.json
    (its punch.windows), or this tool's own output (windows[].start/end)."""
    if spec.startswith("@"):
        with open(spec[1:], encoding="utf-8") as fp:
            data = json.load(fp)
    else:
        data = json.loads(spec)
    if isinstance(data, dict):
        data = (data.get("punch") or {}).get("windows") or data.get("windows") or []
    return [(float(row["start"]), float(row["end"])) if isinstance(row, dict)
            else (float(row[0]), float(row[1])) for row in data]


def _range_window(spec):
    """--range 4.3,6.1 (or 4.3:6.1) as one window."""
    return tuple(float(v) for v in spec.replace(":", ",").split(",")[:2])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--annotate", metavar="OUT_PNG")
    ap.add_argument("--windows", metavar="JSON",
                    help="per-shot zoom anchors: [[start,end],...] inline, or @plan.json")
    ap.add_argument("--range", metavar="A,B", help="a single window, in seconds")
    ap.add_argument("--out", metavar="OUT_JSON", help="write the anchors here instead of stdout")
    args = ap.parse_args()
    if args.windows or args.range:
        if not args.video:
            ap.error("give the video to measure alongside --windows/--range")
        wins = parse_windows(args.windows) if args.windows else [_range_window(args.range)]
        anchors(args.video, wins, out=args.out)
    elif args.video:
        measure(args.video, args.annotate)
    else:
        ap.error("point it at a base cut to measure")


if __name__ == "__main__":
    main()
