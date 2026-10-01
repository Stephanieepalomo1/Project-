#!/usr/bin/env python3
"""video_grade.py — OPTIONAL color grade for the footage on the rendered routes.

Never applied by default. A grade is something the creator asks for by name (locked: "optional and
available, not built in"). It goes on the FOOTAGE only; graphics are composited on top, untouched, so
the pack's colors never shift. The editable-CapCut route never gets one from here — that look stays the
creator's to set in CapCut.

Five looks, built only from filters every ffmpeg has shipped for a decade (eq, colorbalance, curves,
hue) — so an older Mac's Homebrew ffmpeg or a minimal Windows build cannot lack them, and there is no
LUT file to bundle, stage, or lose:

  cinematic  richer contrast, teal shadows and amber highlights
  warm       sunlit, nostalgic warmth
  cool       calm, moody cool cast
  film       soft contrast, lifted blacks, a little less saturation
  mono       black and white with a touch more contrast

Used by: product/build-reel-mp4.py (GRADE=<look> in the env) and product/reel_render.py composite
(--grade <look>). Unknown names fail loud — a misspelled look must never silently ship the reel ungraded
when a grade was asked for.
"""

LOOKS = {
    "cinematic": "colorbalance=rs=-0.05:gs=0.02:bs=0.06:rh=0.06:gh=0.02:bh=-0.06,"
                 "eq=contrast=1.10:saturation=1.05",
    "warm":      "colorbalance=rm=0.05:gm=0.02:bm=-0.06:rh=0.04:bh=-0.05,"
                 "eq=saturation=1.06:brightness=0.01",
    "cool":      "colorbalance=rs=-0.03:bs=0.04:rm=-0.05:bm=0.06,"
                 "eq=saturation=0.95:contrast=1.04",
    "film":      "curves=all='0/0.04 0.5/0.5 1/0.96',"
                 "eq=saturation=0.90:contrast=1.06",
    "mono":      "hue=s=0,eq=contrast=1.08",
}

OFF = ("", "none", "off", "no")


def grade_filter(name):
    """ffmpeg filter string for a named look, or None when no grade was asked for."""
    key = (name or "").strip().lower()
    if key in OFF:
        return None
    if key not in LOOKS:
        raise ValueError(f"unknown grade look {name!r}; choose one of: {', '.join(LOOKS)}")
    return LOOKS[key]


if __name__ == "__main__":
    for k, v in LOOKS.items():
        print(f"{k:10} {v}")
