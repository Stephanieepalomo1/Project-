#!/usr/bin/env python3
"""The Clean Captions hook card sits below the platform's top band, and that band comes from safe_zones.

The preset used to carry its own numbers: a top band of 200 and the card's top edge at y250, which is inside
the 270px band where Instagram draws its Reels header. Its own check compared against its own 200, so it
passed. The card now takes the band from product/safe_zones.py and sits just under it. This pins that, reads
where a real rendered card's ink starts, and checks the line onboarding writes the creator's hook into kept
its exact form (the updater saves and restores that line as written).

Run: python3 product/tests/test_clean_captions_band.py
"""
import importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "product"))
import safe_zones

fails, total = [], 0


def check(name, cond, detail=""):
    global total
    total += 1
    if not cond:
        fails.append(f"{name}{('  -- ' + detail) if detail else ''}")


BUILD = os.path.join(ROOT, "presets", "clean-captions", "build.py")
spec = importlib.util.spec_from_file_location("clean_captions_build", BUILD)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

check("the top band is safe_zones.TOP", cc.SAFE_TOP == safe_zones.TOP, f"{cc.SAFE_TOP} != {safe_zones.TOP}")
check("the bottom line is safe_zones.BOTTOM", cc.SAFE_BOT == safe_zones.BOTTOM, f"{cc.SAFE_BOT} != {safe_zones.BOTTOM}")
check("the card's top edge is below the band", cc.HOOK_TOP_Y >= safe_zones.TOP, f"HOOK_TOP_Y {cc.HOOK_TOP_Y}")
check("no longer the old y250 inside the band", cc.HOOK_TOP_Y != 250)

probe = cc.ImageDraw.Draw(cc.blank())
font = cc.open_face(cc.HOOK_SIZE, cc.HOOK_WEIGHT)
for copy in ("the part nobody tells you",
             "this hook is deliberately far too long for one line so the card has to wrap it over and over"):
    img, x, y = cc.render_hook(copy, font, probe)
    box = img.getbbox()
    top, bottom = y + box[1], y + box[3]
    check(f"rendered card clears the top band ({copy[:20]}...)", top >= safe_zones.TOP, f"ink starts at y{top}")
    check(f"rendered card ends above the bottom line ({copy[:20]}...)", bottom <= safe_zones.BOTTOM,
          f"ink ends at y{bottom}")

# The card never moves or shrinks on its own; being high in the frame, or a long hook, is only raised with her
import json, tempfile


def notes(zones, rows=1):
    with tempfile.TemporaryDirectory() as job:
        if zones is not None:
            with open(os.path.join(job, "subject-zones.json"), "w", encoding="utf-8") as fh:
                json.dump(zones, fh)
        return cc.hook_notes(job, 280, 390, rows)


check("framed low: nothing to raise", notes({"subject": {"head_top": 520}}) == [])
high = notes({"subject": {"head_top": 316}})
check("framed high: raised as her choice, never a failure", len(high) == 1 and "y316" in high[0]
      and "placed as always" in high[0], high)
check("never measured: nothing to raise (and nothing moves)", notes(None) == [])
long_ = notes(None, rows=3)
check("a long hook: raised, still full size", len(long_) == 1 and "3 lines" in long_[0] and "full size" in long_[0], long_)
check("the preset has no code path that stops the build over the hook", "hook_clears_her" not in open(BUILD, encoding="utf-8").read())

with open(BUILD, encoding="utf-8") as fh:
    lines = fh.read().splitlines()
check("the onboarding hook line kept its exact form",
      any(l.startswith('DEFAULT_HOOK_TEXT = ""  #') for l in lines))
check("HOOK_END_WORDS is still a plain assignment", "HOOK_END_WORDS = ()" in lines)

if fails:
    print(f"test_clean_captions_band: FAILED {len(fails)}/{total}: " + " | ".join(fails))
    sys.exit(1)
print(f"test_clean_captions_band: all {total} checks passed")
