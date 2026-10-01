#!/usr/bin/env python3
"""workflows/head-framing.py and workflows/subject-zones.py measure her where she really is, and leave nothing
behind but their answer.

  probe       reads the DISPLAYED size. A phone filmed upright is often stored 1920x1080 with a rotation tag;
              the stored size made the face detector refuse the upright frames ffmpeg decodes.
  hair        on a source that is not 1080x1920 the hair search ran with the reframed frame's coordinates on
              the source frames, so it looked in the wrong place and fell back to the face centre. It now
              searches in source pixels beside the face it found, then converts to the 1080x1920 frame.
  scratch     every frame sample left a temp folder of PNGs behind.
  zones       a run over one graphic's window (--to, --from, --edl) overwrote the whole-reel
              subject-zones.json that the subject check and every placement read.

The detector, the frame grabs and the hair search are stood in for where a case is about the arithmetic
around them, so this runs without OpenCV; the probe and the scratch cleanup run on a real two-second clip.

Run: python3 product/tests/test_head_framing_zones.py
"""
import importlib.util, json, os, shutil, subprocess, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + str(detail)[:300]) if detail else ''}")


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ff = load("head_framing_under_test", os.path.join("workflows", "head-framing.py"))
sz = load("subject_zones_under_test", os.path.join("workflows", "subject-zones.py"))


def quiet(fn, *a, **k):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def main():
    tmp = tempfile.mkdtemp(prefix="head-framing-zones-")
    try:
        # ---- probe: displayed size, on real files ----------------------------------------------------------
        upright = os.path.join(tmp, "upright.mp4")
        stored = os.path.join(tmp, "stored-sideways.mp4")
        tagged = os.path.join(tmp, "tagged.mp4")
        ok = all(subprocess.run(a, capture_output=True).returncode == 0 for a in (
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=108x192:rate=10", "-t", "2",
             "-pix_fmt", "yuv420p", upright],
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", upright, "-vf", "transpose=1", "-pix_fmt", "yuv420p", stored],
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-display_rotation", "90", "-i", stored, "-c", "copy", tagged]))
        if ok:
            w, h, dur = ff.probe(upright)
            check("probe: an upright clip reads as stored", (w, h) == (108, 192) and abs(dur - 2.0) < 0.2, (w, h, dur))
            w, h, _d = ff.probe(tagged)
            check("probe: a rotation-tagged clip reads at its displayed size", (w, h) == (108, 192), (w, h))
            # ---- scratch: the sampled stills never stay behind ---------------------------------------------
            scratch = os.path.join(tmp, "scratch")
            os.makedirs(scratch)
            fake_cv2 = types.ModuleType("cv2")
            fake_cv2.imread = lambda p: ("frame", os.path.getsize(p)) if os.path.exists(p) else None
            real_tmp, real_cv2 = tempfile.tempdir, sys.modules.get("cv2")
            tempfile.tempdir, sys.modules["cv2"] = scratch, fake_cv2
            try:
                frames = ff.sample_frames(upright, 2.0, n=3)
            finally:
                tempfile.tempdir = real_tmp
                if real_cv2 is not None:
                    sys.modules["cv2"] = real_cv2
                else:
                    sys.modules.pop("cv2", None)
            check("sample_frames still returns the frames", len(frames) == 3, frames)
            check("sample_frames leaves no scratch folder behind", os.listdir(scratch) == [], os.listdir(scratch))
        else:
            check("ffmpeg could build the test clips", False, "ffmpeg missing or failed")

        # ---- hair: searched in source pixels, reported in the 1080x1920 frame ----------------------------
        seen = {}
        def fake_tops(imgs, face_cx, face_top, y_floor=0):
            seen["args"] = (face_cx, face_top)
            return [1250] * len(imgs)
        for (w, h) in ((2160, 3840), (1080, 1920)):
            real = (ff.probe, ff.sample_frames, ff.detect_faces, ff.hair_tops)
            ff.probe = lambda v, w=w, h=h: (w, h, 10.0)
            ff.sample_frames = lambda v, d, **k: ["frame"] * 12
            ff.detect_faces = lambda imgs, w_, h_: [(900.0, 1400.0, 400.0, 400.0)] * len(imgs)
            ff.hair_tops = fake_tops
            try:
                rec = quiet(ff.measure, os.path.join(tmp, "not-a-job.mp4"))
            finally:
                ff.probe, ff.sample_frames, ff.detect_faces, ff.hair_tops = real
            k = 1920 / h
            check(f"{w}x{h}: the hair is searched beside the face found in the source",
                  seen.get("args") == (1100.0, 1400.0), seen.get("args"))
            check(f"{w}x{h}: hair_top is reported in the 1080x1920 frame", rec.get("hair_top") == round(1250 * k), rec)
            # The 9:16 crop pull-reels reads from head-framing.json: only a source that is not 1080x1920 needs one,
            # and it is centred on the face found in the source (slid back inside the frame at an edge).
            crop = (rec.get("reframe") or {}).get("ffmpeg")
            if (w, h) == (1080, 1920):
                check(f"{w}x{h}: an already-vertical cut gets no crop", crop is None, rec.get("reframe"))
            else:
                cw = round(h * 9 / 16 / 2) * 2
                x = max(0, min(w - cw, round(1100.0 - cw / 2)))
                check(f"{w}x{h}: the 9:16 crop is centred on her face", crop == f"crop={cw}:{h}:{x}:0,scale=1080:1920",
                      crop)

        # ---- zones: only a whole-reel measurement writes the job's subject-zones.json --------------------
        out = os.path.join(tmp, "job", "outputs")
        os.makedirs(out)
        video = os.path.join(out, "job.mp4")
        zones = os.path.join(tmp, "job", "subject-zones.json")
        edl = os.path.join(tmp, "cuts.json")
        with open(edl, "w", encoding="utf-8") as fh:
            json.dump({"segments": [{"start": 0.0, "end": 10.0}]}, fh)
        fz = sz.head_framing
        real = (fz.probe, fz.sample_frames, fz.detect_faces, fz.hair_tops, sz._sample_through_edl)
        fz.probe = lambda v: (1080, 1920, 10.0)
        fz.sample_frames = lambda v, d, **k: ["frame"] * 16
        fz.detect_faces = lambda imgs, w, h: [(400.0, 500.0, 280.0, 300.0)] * len(imgs)
        fz.hair_tops = lambda imgs, cx, top: [420] * len(imgs)
        sz._sample_through_edl = lambda v, a, b, e, n: ["frame"] * n
        try:
            for label, kw, writes in (("whole reel", {}, True), ("--to only", {"t1": 5.0}, False),
                                      ("--from only", {"t0": 2.0}, False), ("--from/--to", {"t0": 1.0, "t1": 3.0}, False),
                                      ("--edl", {"edl": edl, "t0": 0.0, "t1": 4.0}, False)):
                if os.path.exists(zones):
                    os.remove(zones)
                quiet(sz.measure, video, **kw)
                check(f"subject-zones.json {'written' if writes else 'left alone'} for {label}",
                      os.path.exists(zones) == writes)
            quiet(sz.measure, video)
            with open(zones, encoding="utf-8") as fh:
                whole = fh.read()
            quiet(sz.measure, video, t0=0.0, t1=5.0)
            with open(zones, encoding="utf-8") as fh:
                check("a window run leaves the whole-reel file exactly as it was", fh.read() == whole)
        finally:
            fz.probe, fz.sample_frames, fz.detect_faces, fz.hair_tops, sz._sample_through_edl = real
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"test_head_framing_zones: FAILED {len(fails)}/{total}: " + " | ".join(fails))
        return 1
    print(f"test_head_framing_zones: all {total} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
