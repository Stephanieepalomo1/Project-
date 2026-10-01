"""hdr.py — tell HDR phone footage apart from SDR, and the one filter that brings it back to SDR.

iPhone b-roll is shot BT.2020 + HLG (or PQ from a Dolby Vision export), 10-bit. Treated as SDR it renders
washed out and flat, and anything drawn on top (white hook text) lands at the HDR peak or goes grey. Detect
it from the stream's real color tags and convert BT.2020 -> BT.709 SDR before any scale, zoom or overlay.

The `colorspace` filter is the conversion because this toolchain has no zscale/libplacebo. It is driven by
the stream's own metadata, so it holds for any buyer's HDR footage, unlike a hand-tuned eq/saturation boost.
HLG converts correctly; PQ only approximately (no true tone map here), which the callers say out loud.

    from hdr import HDR2SDR, hdr_kind
    pre = f"{HDR2SDR}," if hdr_kind(src) else ""      # prepend to the clip's -vf chain

Shared by the voiceover builder (product/vo-build.py) and the b-roll hook baker
(.claude/skills/broll-reels/tools/bake-hook.py), so both convert the same footage the same way.
"""
import subprocess

HDR2SDR = ("colorspace=ispace=bt2020nc:itrc=bt2020-10:iprimaries=bt2020:"
           "space=bt709:trc=bt709:primaries=bt709")


def hdr_kind(src):
    """'hlg' (iPhone default) | 'pq' (Dolby Vision export) | 'bt2020' | None, from the stream's color tags."""
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer,color_primaries",
             "-of", "default=nw=1:nk=1", src], text=True).lower()
    except Exception:
        return None
    if "arib-std-b67" in out: return "hlg"
    if "smpte2084" in out: return "pq"
    if "bt2020" in out: return "bt2020"
    return None
