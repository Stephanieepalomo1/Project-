# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless"]
# ///
"""
subject-zones.py: the box a talking-head subject occupies in a take, and the open bands of frame around her.

In reel-layout-rules terms this is the measured subject band that Layer 1 places against. Layer 2 is
product/safe_zones.py, the platform's own UI strip: one fixed band, identical on every reel. The subject is
different on every shoot and every framing, so it has to be read off the footage. A spot is usable only when
it clears both, which is why every band below comes back already cut down to the Layer 2 band.

What it came out of: hooks landed on a creator's forehead while the top quarter of her frame was empty wall,
after she had asked more than once for that to stop. Remembering was never the problem. Placements were typed
by hand (transform_y 0.60, 0.62, 0.74 on different jobs), each carried over from the reel before. CapCut's
transform_y is (960 - y_px) / 960, which puts 0.60 at y384: clear of a subject framed low, on the forehead of
one framed high. With nothing reading where her head actually was, nothing could tell those two cases apart.

HOW IT READS HER. Frames are sampled across the whole window and each edge keeps its worst value, because a
spot that is clear on a typical frame and covered on her most animated one is not clear.

  head top     where her hair really starts, from median-background subtraction (head_framing.hair_tops):
               she moves and the room does not. YuNet's face box begins at the brow, and placing against it
               parks type in her hair. The highest value seen wins. If the hair can't be read (a hood, a hat,
               low contrast), the face-box top stands in and head_top_source says so.
               Handheld, the room moves with the phone and cannot be subtracted (head-framing.room_moves checks
               the room beside her head first): the head top is then the face box's top less a measured hair
               allowance (HANDHELD_HAIR of its height), and head_top_source says that too.
  chin bottom  the lowest the jaw reached.
  left/right   the widest the face box spanned, each side pushed out by EAR x the median box width, since the
               box ends at the cheeks and her ears sit outside it.

WHAT IT RETURNS
  subject      her box, in source px (subject_src_px) and in 1080x1920 authoring px (subject)
  zones        four open bands in authoring px, each MARGIN clear of her and inside the Layer 2 band:
                 above   safe_zones.TOP        -> head_top - MARGIN
                 below   chin_bottom + MARGIN  -> safe_zones.BOTTOM
                 left    safe_zones.LEFT       -> head_left - MARGIN
                 right   head_right + MARGIN   -> safe_zones.RIGHT
               above and below also carry center_y_norm, the CapCut transform_y of their centre, so a builder
               receives the number instead of choosing one. The side bands report x0/x1, and roomier_side
               names the wider of the two.

A band too small for one legible line comes back `usable: false` with the reason written out. That is a fact
about her framing rather than an error, and it is reported as one.

Usage:
  uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4
      prints the zones and writes projects/<job>/subject-zones.json
  uv run workflows/subject-zones.py <video> --from 4.3 --to 6.1
      reads only one graphic's time on screen, the fair window when she moves around during a reel
  uv run workflows/subject-zones.py <raw> --edl projects/<job>/transcript/cuts.json --from 12.0 --to 15.5
      takes --from/--to as timeline seconds and maps them onto the raw through cuts.json
  --json prints machine-readable output, --out FILE saves it, and --annotate OUT.PNG draws her box and the
  usable above/below bands onto the middle sampled frame
"""
import argparse, importlib.util, json, os, statistics, subprocess, sys, tempfile
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# head-framing.py has a hyphen, which is not a valid module name — load it by path rather than duplicate its
# proven sampling / detection / hair-top logic here. One correction to that file lands in both tools.
_spec = importlib.util.spec_from_file_location(
    "head_framing", os.path.join(os.path.dirname(os.path.abspath(__file__)), "head-framing.py"))
head_framing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(head_framing)

sys.path.insert(0, os.path.join(REPO, "product"))
import safe_zones                      # Layer 2, the platform UI band: one source, cut into every zone

MARGIN = 60      # authoring px kept clear between her head (hair and ears counted) and any graphic
EAR = 0.20       # share of the face-box width added on each side: YuNet's box ends before her ears do
SAMPLES = 16     # a whole take, not one beat


def edl_map(path):
    """A function taking a time on the cut's timeline to the same moment in the raw (cuts.json spans are raw times)."""
    doc = json.load(open(path, encoding="utf-8"))
    kept = doc.get("segments") if isinstance(doc, dict) else doc
    pieces, clock = [], 0.0          # (where it starts on the cut, where it ends there, where it starts in the raw)
    for piece in kept:
        raw_in = float(piece["start"])
        length = float(piece["end"]) - raw_in
        pieces.append((clock, clock + length, raw_in))
        clock += length

    def to_raw(at):
        hit = next((p for p in pieces if p[0] <= at < p[1]), None)
        return None if hit is None else hit[2] + (at - hit[0])
    return to_raw


def _edl_duration(path):
    """Total TIMELINE length of a cut = the kept durations summed."""
    c = json.load(open(path, encoding="utf-8"))
    segs = c.get("segments") if isinstance(c, dict) else c
    return sum(float(sg["end"]) - float(sg["start"]) for sg in segs)


def _sample_through_edl(video, t0, t1, edl, n):
    """Sample n frames evenly across a TIMELINE window, each mapped onto the raw through the cut. The stills
    are read into memory and their scratch folder is removed before this returns."""
    import cv2, shutil
    to_src = edl_map(edl)
    td = tempfile.mkdtemp()
    imgs = []
    try:
        for i in range(n):
            tl = t0 + (t1 - t0) * (i + 0.5) / n
            st = to_src(tl)
            if st is None:
                continue
            f = os.path.join(td, f"f{i}.png")
            subprocess.run(["ffmpeg", "-v", "error", "-ss", str(st), "-i", video,
                            "-frames:v", "1", "-y", f], capture_output=True)
            img = cv2.imread(f)
            if img is not None:
                imgs.append(img)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return imgs


# A zone is only "usable" if TEXT could legibly go in it. Any positive number would technically be a gap,
# but reporting a 40px band as usable hands a caller a centre line and lets a legible line spill straight
# back onto her — the defect this tool exists to prevent, arrived at politely.
MIN_TALL = safe_zones.MIN_PX["caption"]   # one legible line (58px at 1080x1920)
MIN_WIDE = MIN_TALL * 3                   # a side zone narrower than a few characters cannot hold copy


def _zone(name, top, bottom, h, need=None, axis="y"):
    """One open band, honestly reported. `need` = px required before it counts as usable."""
    need = need if need is not None else (MIN_TALL if axis == "y" else MIN_WIDE)
    room = int(round(bottom - top))
    z = {"top": int(round(top)), "bottom": int(round(bottom)), "room_px": room,
         "center_px": int(round((top + bottom) / 2))}
    z["center_y_norm"] = round((h / 2 - z["center_px"]) / (h / 2), 4)
    z["usable"] = room >= need
    if not z["usable"]:
        dim = "tall" if axis == "y" else "wide"
        z["why"] = (f"only {max(room, 0)}px {dim} — her framing leaves no usable room {name} her once the "
                    f"{MARGIN}px head margin and the platform band are both honoured "
                    f"(needs {need}px for legible text)")
    return z


def measure(video, t0=0.0, t1=None, edl=None, samples=SAMPLES, annotate=None, out=None):
    # Only a measurement of the WHOLE cut may stand as the job's subject-zones.json, which subject_guard and
    # every placement read as "where she is across the reel". One graphic's window (--from/--to) or a raw
    # mapped through --edl answers a narrower question and must never overwrite it.
    whole_reel = not edl and float(t0) == 0.0 and t1 is None
    w, h, dur = head_framing.probe(video)
    # ASPECT GUARD, FIRST — before any sampling or detection. ONE scale factor maps source px onto the
    # 1080x1920 authoring frame only when the source shares that aspect. A 16:9 raw does not: it gets
    # reframed/cropped to 9:16 later, so no fixed scale maps a y in the raw onto a y in the finished reel,
    # and a number derived by scaling width would be confidently wrong. It runs here rather than after the
    # measurement so the answer is the real reason, delivered in a second instead of after a 30s sweep that
    # would then fail on "no face" and send someone hunting the wrong problem.
    if abs(safe_zones.W / w - safe_zones.H / h) > 1e-3:
        sys.exit(f"✗ {w}x{h} is not the 9:16 authoring aspect, so its pixels cannot be mapped onto the "
                 f"1080x1920 frame the graphics are built in (a reframe/crop happens between the two).\n"
                 f"  Measure the finished cut instead: projects/<job>/outputs/<job>.mp4")
    if t1 is None:
        # With --edl the window is in TIMELINE seconds, and the timeline is shorter than the raw it was cut
        # from, so the raw's duration is the wrong ceiling — it would sample past the end of the cut and map
        # those times to nothing. Take the timeline's own length from the EDL.
        t1 = _edl_duration(edl) if edl else dur
    else:
        t1 = float(t1) if edl else min(float(t1), dur)
    window = [float(t0), float(t1)]

    imgs = (_sample_through_edl(video, t0, t1, edl, samples) if edl
            else head_framing.sample_frames(video, dur, n=samples, t0=t0, t1=t1))
    if not imgs:
        sys.exit("could not decode any frame in that window — check the path and the times")
    boxes = head_framing.detect_faces(imgs, w, h)
    if len(boxes) < max(2, len(imgs) / 2):
        sys.exit(f"✗ face found in only {len(boxes)}/{len(imgs)} sampled frames — not writing zones from "
                 f"that. Place this one by eye, or re-run over a window where she is actually on camera.")

    # ---- the subject box, WORST CASE over the window ------------------------------------------------
    face_top = min(y for x, y, bw, bh in boxes)                    # highest the forehead ever got
    chin_bottom = max(y + bh for x, y, bw, bh in boxes)            # lowest the jaw ever got
    ear = round(EAR * statistics.median(bw for x, y, bw, bh in boxes))
    head_left = min(x for x, y, bw, bh in boxes) - ear
    head_right = max(x + bw for x, y, bw, bh in boxes) + ear
    face_cx = statistics.median(x + bw / 2 for x, y, bw, bh in boxes)

    # The TRUE hair top, not the forehead. YuNet's box starts at the brow, so placing to it puts type in
    # her hair and reads exactly like the defect this tool exists to stop.
    hair_src = "hair (median-background subtraction)"
    handheld = False
    try:
        tops = head_framing.hair_tops(imgs, face_cx, face_top)
        head_top = min(tops) if tops else None
        handheld = not tops and head_framing.room_moves(imgs, face_cx, face_top)
    except Exception:
        head_top = None
    if head_top is None and handheld:
        # The room moves with the phone, so it cannot be subtracted: her hair starts a measured share of the
        # face box above its top, worst case over the take like every other edge here.
        head_top = min(y - head_framing.HANDHELD_HAIR * bh for x, y, bw, bh in boxes)
        hair_src = "face box + hair allowance (handheld: the room moves with the phone)"
    elif head_top is None:
        head_top, hair_src = face_top, "face box (hair unmeasurable: hood, hat, or low contrast)"

    k = safe_zones.W / w
    def A(v): return int(round(v * k))

    zones = {
        "above": _zone("above", safe_zones.TOP,          A(head_top) - MARGIN,    safe_zones.H),
        "below": _zone("below", A(chin_bottom) + MARGIN, safe_zones.BOTTOM,       safe_zones.H),
    }
    # The side zones constrain X, so they carry x-shaped keys. Reusing `top`/`bottom` for horizontal bounds
    # reads fine in a print and lies to every consumer that reads the JSON.
    lz = _zone("left of",  safe_zones.LEFT, A(head_left) - MARGIN, safe_zones.H, axis="x")
    rz = _zone("right of", A(head_right) + MARGIN, safe_zones.RIGHT, safe_zones.H, axis="x")
    for z in (lz, rz):
        z["x0"], z["x1"] = z.pop("top"), z.pop("bottom")
        z["center_x_px"] = z.pop("center_px")
        z.pop("center_y_norm")
    zones["left"], zones["right"] = lz, rz
    roomier = "left" if lz["room_px"] >= rz["room_px"] else "right"

    result = {
        "video": os.path.abspath(video), "frame": [w, h], "window": window, "timeline": bool(edl),
        "frames_sampled": len(boxes), "misses": len(imgs) - len(boxes),
        "margin_px": MARGIN, "ear_px": ear, "head_top_source": hair_src,
        "subject_src_px": {"head_top": int(round(head_top)), "chin_bottom": int(round(chin_bottom)),
                           "left": int(round(head_left)), "right": int(round(head_right)),
                           "face_top": int(round(face_top))},
        "subject": {"head_top": A(head_top), "chin_bottom": A(chin_bottom),
                    "left": A(head_left), "right": A(head_right)},
        "zones": zones, "roomier_side": roomier,
    }

    _report(result)
    if annotate:
        _annotate(imgs[len(imgs) // 2], result, k, annotate)

    if out is None:
        vdir = os.path.dirname(os.path.abspath(video))
        if os.path.basename(vdir) == "outputs" and whole_reel:
            out = os.path.join(os.path.dirname(vdir), "subject-zones.json")
    if out:
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(result, fp, indent=2)
        print(f"  json: {out}")
    return result


def _report(r):
    s, z = r["subject"], r["zones"]
    print(f"source {r['frame'][0]}x{r['frame'][1]}  ·  {r['frames_sampled']} frames with a face "
          f"(+{r['misses']} without)  ·  measured in 1080x1920 authoring px")
    print(f"SHE OCCUPIES  y{s['head_top']}–{s['chin_bottom']}  x{s['left']}–{s['right']}  "
          f"(head top from the {r['head_top_source']}, ears +{r['ear_px']}px, worst case)")
    print(f"\nopen zones, {r['margin_px']}px off her and already inside the platform safe band:")
    for name in ("above", "below"):
        b = z[name]
        if b["usable"]:
            print(f"  {name:<6} y{b['top']}–{b['bottom']}  ({b['room_px']}px tall)  "
                  f"center y{b['center_px']}  →  CapCut transform_y {b['center_y_norm']}")
        else:
            print(f"  {name:<6} {b['why']}")
    for name in ("left", "right"):
        b = z[name]
        print(f"  {name:<6} x{b['x0']}–{b['x1']}  ({b['room_px']}px wide)"
              if b["usable"] else f"  {name:<6} {b['why']}")
    if any(z[n]["usable"] for n in ("left", "right")):
        print(f"  → more side room on the {r['roomier_side'].upper()}")
    if not any(z[n]["usable"] for n in ("above", "below", "left", "right")):
        print("  → nothing around her is usable on this framing. That is the framing, not a failure: "
              "a graphic here has to go over her on purpose, or the shot needs re-framing.")


def _annotate(img, r, k, out):
    import cv2
    s = r["subject_src_px"]
    cv2.rectangle(img, (s["left"], s["head_top"]), (s["right"], s["chin_bottom"]), (0, 200, 255), 3)
    cv2.putText(img, "her", (s["left"], max(30, s["head_top"] - 14)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 255), 3)
    for name in ("above", "below"):
        b = r["zones"][name]
        if not b["usable"]:
            continue
        y0, y1 = int(b["top"] / k), int(b["bottom"] / k)
        cv2.rectangle(img, (int(safe_zones.LEFT / k), y0), (int(safe_zones.RIGHT / k), y1), (0, 255, 0), 3)
        cv2.putText(img, name, (int(safe_zones.LEFT / k) + 12, y0 + 44),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
    cv2.imwrite(out, img)
    print(f"  annotated frame: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--edl", metavar="CUTS.JSON",
                    help="--from/--to are TIMELINE seconds; map them onto the video through this cut")
    ap.add_argument("--samples", type=int, default=SAMPLES)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", metavar="FILE")
    ap.add_argument("--annotate", metavar="OUT.PNG")
    a = ap.parse_args()
    if a.json:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = measure(a.video, a.t0, a.t1, a.edl, a.samples, a.annotate, a.out)
        print(json.dumps(r, indent=2))
    else:
        measure(a.video, a.t0, a.t1, a.edl, a.samples, a.annotate, a.out)
