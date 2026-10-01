#!/usr/bin/env python3
"""video_encoder.py — SHARED cross-platform video encoder choice for every ffmpeg render in this
engine. One correction lands everywhere, instead of four separate copies drifting apart.

Mac: Apple's videotoolbox (hardware, always available, no GPU check needed — it's the integrated
media engine on every Mac this ships to).

Windows/Linux: an NVIDIA GPU gets h264_nvenc (hardware) — checked for real, not assumed: an
NVIDIA GPU present (nvidia-smi) AND this machine's actual ffmpeg build actually has nvenc
compiled in (`ffmpeg -encoders`), because a GPU alone doesn't guarantee the ffmpeg binary a
buyer installed was built with NVENC support. No NVIDIA GPU (or the check fails for any reason)
→ libx264 software, which every ffmpeg build ships and needs no GPU — today's already-working,
never-removed floor. VENC/VBR env vars still override on any platform, same as before.

Was 4 near-identical copies (stitch-cut.sh, cut-shorts.py, build-reel-mp4.py, clean-captions/build.py)
before this module — the Mac-vs-everyone-else split existed everywhere, but Windows/Linux never
had a hardware path at all, only ever libx264. This is additive: nothing that worked before stops
working, it just now has a faster path when the hardware is actually there.
"""
import os
import sys
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
import platform
import subprocess

_nvenc_cache = None

# Every delivery render in this engine is SDR h264 in a .mp4. If the OUTPUT stream carries no
# color tags, a player has to guess — and the guess goes wrong on footage shot by a phone, which
# often tags itself full-range (pc). Chrome's decoder in particular then renders EVERY FRAME PURE
# BLACK while the audio plays normally: no ffmpeg error, no nonzero exit, nothing in any log. The
# file looks fine to ffprobe and plays fine in VLC, so the failure only shows up when a buyer (or
# a preview pane) opens it in a browser.
#
# Stamping the standard bt709/limited set on every render removes the guess. This is a TAG on the
# output stream, so callers whose filter chain ingests raw phone footage should also normalize the
# actual pixels to limited range before this point (stitch-cut.sh does, via its per-segment
# scale=out_range=tv + setparams) — tag and data then agree instead of merely being declared.
#
# Not Windows-specific, and not GPU-specific: it reproduces anywhere the source is full-range.
COLOR_FLAGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
               "-color_trc", "bt709", "-color_range", "tv"]


def _nvenc_available():
    """True only if an NVIDIA GPU is present AND this ffmpeg build actually has nvenc compiled
    in. Cached per-process — this gets called once per render, cheap enough either way, but no
    reason to shell out twice in a script that calls pick_encoder() more than once."""
    global _nvenc_cache
    if _nvenc_cache is not None:
        return _nvenc_cache
    try:
        gpu = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
        if gpu.returncode != 0 or not gpu.stdout.strip():
            _nvenc_cache = False
            return False
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                              capture_output=True, text=True, timeout=10)
        _nvenc_cache = ("h264_nvenc" in enc.stdout)
    except Exception:
        _nvenc_cache = False
    return _nvenc_cache


def pick_encoder(vbr="16M", crf=17, preset="veryfast", hw_on_mac=True):
    """Returns ffmpeg -c:v ... args for the calling script's cmd list. `vbr` is the hardware-path
    bitrate target (videotoolbox/nvenc); `crf`/`preset` are the software-path (libx264) quality
    knobs — each caller passes its own already-tuned values, this only decides WHICH encoder.
    `hw_on_mac=False` keeps libx264 on a Mac for a path whose look was tuned on it (the cinematic
    Voiceover finish, the composite re-stack): NVENC still kicks in on a Windows GPU box, where the
    speed matters most, and nothing changes on the machine the look was locked on."""
    venc = os.environ.get("VENC")
    if venc:
        return ["-c:v", venc, "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    if platform.system() == "Darwin":
        if not hw_on_mac:
            return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"] + COLOR_FLAGS
        return ["-c:v", "h264_videotoolbox", "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    if _nvenc_available():
        return ["-c:v", "h264_nvenc", "-b:v", os.environ.get("VBR", vbr)] + COLOR_FLAGS
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"] + COLOR_FLAGS


if __name__ == "__main__":
    print("encoder:", " ".join(pick_encoder()))
    print("nvenc available:", _nvenc_available())
