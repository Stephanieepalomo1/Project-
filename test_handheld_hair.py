#!/usr/bin/env python3
"""A handheld take is measured where she really is, not 400px up in the ceiling.

The hair search compares each frame with the room (the per-pixel median of the take), which only works while
the room holds still. Handheld, the phone moves and the room moves with it, so the whole search band read as
"her" and the hair top came back as the top of the band: on a real handheld selfie, y150 for hair that starts
near y566, and every placement around her was judged against that. Now the room is checked first, on the
strips beside the band where only the room is. When it moves, the hair is left unread, and subject-zones
falls back to the face box plus a measured hair allowance, saying so. A still room is read exactly as before.

Needs numpy (the engine's measuring tools run with it); the face detector and the frame grabs are stood in.

Run: python3 product/tests/test_handheld_hair.py   (Windows: python)
"""
import contextlib, importlib.util, io, json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  ({str(detail)[:200]})"))
    if not cond:
        fails.append(name)


try:
    import numpy as np
except ImportError:
    print("test_handheld_hair: skipped (numpy is not installed for this Python)")
    sys.exit(0)


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hf = load("head_framing_under_test", os.path.join("workflows", "head-framing.py"))
sz = load("subject_zones_under_test", os.path.join("workflows", "subject-zones.py"))

H, W = 960, 1080                                   # a reel's width: the room shows beside her head
rng = np.random.default_rng(7)
wall = rng.integers(0, 255, size=(H + 200, W + 200, 3)).astype(np.uint8)   # a busy room, bigger than the frame


def take(handheld):
    """16 frames: a still figure in the middle, and a room that is either still or shifted frame to frame."""
    frames = []
    for i in range(16):
        dx, dy = ((i * 37) % 180, (i * 23) % 180) if handheld else (100, 100)
        f = wall[dy:dy + H, dx:dx + W].copy()
        f[300:960, 440:640] = (90, 120, 200)          # her: head and shoulders, the same in every frame
        frames.append(f)
    return frames


print("1. is the room still?")
face_cx, face_top = 540, 420
still, moving = take(False), take(True)
check("a tripod take's room holds still", hf.room_moves(still, face_cx, face_top) is False)
check("a handheld take's room moves", hf.room_moves(moving, face_cx, face_top) is True)

print("\n2. subject-zones on a handheld take")
tmp = tempfile.mkdtemp(prefix="handheld-hair-")
try:
    out = os.path.join(tmp, "job", "outputs")
    os.makedirs(out)
    video = os.path.join(out, "job.mp4")
    fz = sz.head_framing
    boxes = [(400.0, 500.0 + 20 * (i % 3), 280.0, 480.0) for i in range(16)]
    real = (fz.probe, fz.sample_frames, fz.detect_faces, fz.hair_tops, fz.room_moves)
    fz.probe = lambda v: (1080, 1920, 10.0)
    fz.sample_frames = lambda v, d, **k: ["frame"] * 16
    fz.detect_faces = lambda imgs, w, h: boxes
    try:
        for label, moves, want_src, want_top in (
                ("handheld", True, "handheld", min(y - hf.HANDHELD_HAIR * bh for x, y, bw, bh in boxes)),
                ("hair unreadable on a still take", False, "hair unmeasurable", min(y for x, y, bw, bh in boxes))):
            fz.hair_tops = lambda imgs, cx, top: []
            fz.room_moves = lambda imgs, cx, top, y_floor=0, _m=moves: _m
            with contextlib.redirect_stdout(io.StringIO()):
                rec = sz.measure(video)
            check(f"{label}: head top = {want_top:.0f}", rec["subject"]["head_top"] == round(want_top), rec["subject"])
            check(f"{label}: the reason is written down", want_src in rec["head_top_source"], rec["head_top_source"])
        fz.hair_tops = lambda imgs, cx, top: [300] * 16
        fz.room_moves = lambda *a, **k: False
        with contextlib.redirect_stdout(io.StringIO()):
            rec = sz.measure(video)
        check("a still take whose hair reads keeps the hair line", rec["subject"]["head_top"] == 300
              and "median-background" in rec["head_top_source"], rec["subject"])
        with open(os.path.join(tmp, "job", "subject-zones.json"), encoding="utf-8") as fh:
            check("the whole-reel measurement is written", json.load(fh)["subject"]["head_top"] == 300)
    finally:
        fz.probe, fz.sample_frames, fz.detect_faces, fz.hair_tops, fz.room_moves = real
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "a handheld take is measured where she is"))
sys.exit(1 if fails else 0)
