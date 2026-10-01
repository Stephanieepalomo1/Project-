#!/usr/bin/env python3
"""test_render_fallbacks.py — the two SILENT render failures from the second PC tester (v1.0.67).

Both shipped. Both dead-ended a buyer with no way around them. Neither can be reproduced on a Mac by
running the engine, because both need an NVIDIA GPU with an out-of-date driver — which is exactly why
they survived a whole earlier test round on a machine that had no NVIDIA GPU at all.

  1. THE FALLBACK THAT COULD NOT BE REACHED. stitch-cut.sh has a software-encoder fallback for when the
     hardware encoder misbehaves. It was written for ONE failure mode: the encoder exits 0 having
     written a short or corrupt file. A stock OEM NVIDIA driver lagging the buyer's ffmpeg build
     produces the OTHER mode — "Driver does not support the required nvenc API version. Required:
     13.1 Found: 13.0", exit non-zero, no output file at all. The code propagated that exit one line
     ABOVE the fallback, so the working software encoder was never tried. Dead render, no output.

  2. THE VIDEO THAT PLAYED BLACK. Phone footage frequently tags itself full-range (pc). Nothing
     normalized it and nothing tagged the output, so the render inherited an incoherent colour
     description. ffprobe is happy, VLC is happy, and Chrome decodes EVERY FRAME PURE BLACK while the
     audio plays normally. There is no error anywhere — the tester found it by looking at the picture.

Run:  python3 product/tests/test_render_fallbacks.py
"""
import ast
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SPLICE = os.path.join(ROOT, ".claude", "skills", "rough-cut", "scripts", "stitch-cut.sh")
fails = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(label)


def embedded_python(path):
    """The python heredoc stitch-cut.sh pipes to the interpreter."""
    src = open(path, encoding="utf-8").read()
    # the heredoc line carries trailing shell ( `<<'PY' || render_rc=$?` ), so don't anchor on \n
    m = re.search(r"<<\s*'?PY'?[^\n]*\n(.*?)\n^PY$", src, re.S | re.M)
    return m.group(1) if m else ""


# ------------------------------------------------------------------ 1. the fallback is reachable
print("\na hardware encoder that FAILS OUTRIGHT still falls back to software")
block = embedded_python(SPLICE)
check("stitch-cut.sh's python block was located", bool(block))

if block:
    tree = ast.parse(block)

    def calls_sys_exit(node):
        """ast.dump() never renders `sys.exit` as that literal string — it is an Attribute on a
        Name — so this has to be matched structurally or the check silently never fires."""
        for c in ast.walk(node):
            if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                    and c.func.attr == "exit" and isinstance(c.func.value, ast.Name)
                    and c.func.value.id == "sys"):
                return True
        return False

    def mentions_rc_nonzero(node):
        for c in ast.walk(node):
            if isinstance(c, ast.Compare) and isinstance(c.left, ast.Name) and c.left.id == "rc" \
               and any(isinstance(o, ast.NotEq) for o in c.ops):
                return True
        return False

    bare_exit, fallback_covers_rc = None, False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not mentions_rc_nonzero(node.test):
            continue
        if any(calls_sys_exit(st) for st in node.body):
            # An early exit on a non-zero return is only correct once we know the SOFTWARE encoder
            # ran — on a hardware encoder it has to fall through to the retry instead. A bare
            # `if rc != 0:` (no second condition) is precisely the bug: it cannot tell the two apart.
            if not isinstance(node.test, ast.BoolOp):
                bare_exit = node.lineno
        if isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.Or):
            if any("_whole" in ast.dump(v) for v in node.test.values):
                fallback_covers_rc = True

    check("no unconditional exit on a non-zero encoder return before the fallback",
          bare_exit is None,
          f"bare `if rc != 0: sys.exit(rc)` still at line {bare_exit} of the python block")
    check("the software-encoder retry triggers on a non-zero return as well as a corrupt file",
          fallback_covers_rc)

    # The retry must not quietly drop the colour contract that check 2 below enforces.
    m = re.search(r'sw = \[([^\]]*)\](.*)', block)
    check("the software-encoder retry still carries the colour flags",
          bool(m) and "COLOR_FLAGS" in (m.group(2)[:40] if m else ""),
          "the libx264 retry rebuilds -c:v without COLOR_FLAGS")


# ------------------------------------------------------------------ 2. every encoder path is tagged
print("\nevery encoder pick_encoder() can return stamps a complete colour description")
sys.path.insert(0, os.path.join(ROOT, "product"))
import video_encoder as ve   # noqa: E402

REQUIRED = {"-colorspace", "-color_primaries", "-color_trc", "-color_range"}
cases = [("default", {}), ("software-on-mac", {"hw_on_mac": False})]
for label, kw in cases:
    got = ve.pick_encoder(**kw)
    check(f"{label} path carries every colour flag", REQUIRED.issubset(set(got)), f"got {got}")

os.environ["VENC"] = "h264_nvenc"
check("an explicit VENC override is tagged too", REQUIRED.issubset(set(ve.pick_encoder())))
os.environ.pop("VENC", None)


# ------------------------------------------------------------------ 3. the picture is not black
print("\nfull-range phone footage survives the pipeline with a coherent colour description")
if subprocess.run(["bash", "-c", "command -v ffmpeg"], capture_output=True).returncode != 0:
    print("  ..   ffmpeg not on PATH — skipping the render leg")
else:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "phone.mp4")
        out = os.path.join(tmp, "out.mp4")
        # A source that lies exactly the way phone footage does: full-range, odd primaries.
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=360x640:rate=30:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-color_range", "pc",
                        "-colorspace", "bt470bg", "-y", src], check=True)

        vnorm = re.search(r'VNORM = \((.*?)\)\n', block, re.S)
        check("stitch-cut.sh defines the per-segment colour normalisation", bool(vnorm))
        filt = "".join(re.findall(r'"([^"]*)"', vnorm.group(1))) if vnorm else ""
        check("the normalisation converts range and re-tags",
              "out_range=tv" in filt and "setparams=" in filt, f"got {filt!r}")

        subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-filter_complex",
                        f"[0:v]trim=0:1,setpts=PTS-STARTPTS,{filt}[v0]", "-map", "[v0]",
                        *[a for a in ve.pick_encoder(crf=18, preset="veryfast", hw_on_mac=False)],
                        "-y", out], check=True)

        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=color_range,color_space,color_primaries,color_transfer",
                                "-of", "default=nw=1", out], capture_output=True, text=True).stdout
        tags = dict(l.split("=", 1) for l in probe.strip().splitlines() if "=" in l)
        check("the output is tagged bt709 limited, not the source's full-range guess",
              tags.get("color_range") == "tv" and tags.get("color_space") == "bt709"
              and tags.get("color_primaries") == "bt709" and tags.get("color_transfer") == "bt709",
              f"got {tags}")

        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vframes", "1",
                              "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        mean = sum(raw) / len(raw) if raw else 0
        check("the picture is not black", mean > 16, f"mean luma {mean:.1f}")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "render fallbacks hold"))
sys.exit(1 if fails else 0)
