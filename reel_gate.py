#!/usr/bin/env python3
"""reel_gate.py — the pre-render GATE for a rendered reel composition.

RELIES ON HYPERFRAMES, DOES NOT REINVENT IT. The gate is `hyperframes check` — HyperFrames' own native
verifier: lint, runtime, layout/overflow, motion, and WCAG contrast, sampled across the timeline AND at
transition seams (so content that grows by animating — a takeover stacking word-by-word, a karaoke line
filling — is checked at its true peak, not one frame). HyperFrames already solved geometry/layout/motion
correctness; a parallel custom measurer was a reinvention and is retired.

Style packs are INJECTIONS on top of HyperFrames (fonts / colors / shadow / sizes — like custom CSS on a
site), never new build logic. So this one native check governs EVERY pack (built by the creator or a buyer)
identically; the only deviations from HyperFrames are buyer-facing terminology and the raw editable-CapCut
route (which follows the creator's CapCut gold standards, not HyperFrames, and is exempt here).

  python3 product/reel_gate.py <composition_dir_or_html> [--canvas 1080x1920] [--pack Butter] \
      [--fmt yap] [--route well-done] [--register teaching] [--strict]

Exit 0 = clean (safe to render). Exit non-zero = check found errors — do NOT render until they are fixed.
reel_layout.py still resolves the pack dressing (safe zones, type floors, palette) the build injects.
"""
import argparse, os, subprocess, sys
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reel_layout as rl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from npx_run import npx_argv

from npx_run import hf_version
HF_VERSION = hf_version()   # single source: product.json "hyperframes" (pinned with the vendored skills)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="the composition directory (or index.html) to gate")
    ap.add_argument("--draft", help="path to the CapCut draft's timeline JSON (reads the real canvas for the dressing log)")
    ap.add_argument("--canvas", help="WxH if no draft, e.g. 1080x1920")
    ap.add_argument("--pack"); ap.add_argument("--fmt", default="yap")
    ap.add_argument("--route", default="well-done"); ap.add_argument("--register", default="teaching")
    ap.add_argument("--strict", action="store_true", help="fail on warnings too, not just errors")
    ap.add_argument("--no-contrast", action="store_true",
        help="skip the WCAG contrast pass — for a plate that reproduces a site "
             "verbatim, where the styling is not authored here")
    a = ap.parse_args()

    # RAW / editable-CapCut route is EXEMPT: there is no rendered composition to gate — the creator sizes and
    # places editable text in CapCut, governed by the CapCut gold standards, not HyperFrames.
    if a.route.lower() in ("raw", "c", "editable", "capcut"):
        print("[gate] raw / editable-CapCut route — no rendered composition to gate "
              "(the CapCut gold standards govern, not HyperFrames). Nothing to do.")
        return 0

    # Log the resolved pack dressing (safe zones / floors / palette) — the injection the build applies on top
    # of HyperFrames. Non-fatal if it cannot resolve; the gate itself is the native check below.
    try:
        canvas = tuple(int(x) for x in a.canvas.lower().split("x")) if a.canvas else None
        ctx = rl.resolve(draft_info_path=a.draft, canvas=canvas, pack=a.pack, fmt=a.fmt,
                         register=a.register, route=a.route)
        print(ctx.describe()); print()
    except Exception as e:
        print(f"[gate] (pack-dressing resolve skipped: {e})")

    # THE GATE = HyperFrames' native check. --at-transitions samples every tween boundary (catches transient
    # and peak overlaps); --frame-check flags text breaching a frame edge. Same command for every pack.
    # `hyperframes check` reads <dir>/index.html, so it needs the composition DIRECTORY. Accept either form
    # (a dir OR a path to index.html) and normalize to the dir — passing the file yields "Not a directory"
    # and the gate would then FAIL every build for a defect in its own invocation, not in the composition.
    target = a.target
    if os.path.isfile(target) or (not os.path.isdir(target) and target.endswith(".html")):
        target = os.path.dirname(os.path.abspath(target))
    if not os.path.isdir(target):
        print(f"  ⛔ gate: composition directory not found: {target!r} "
              f"(pass the composition dir, or its index.html).")
        return 2
    from npx_run import hf_check_argv   # the ONE argv builder (flag order is load-bearing on 0.8.43)
    from npx_run import NO_NODE, npx_path
    cmd = hf_check_argv(HF_VERSION, target, strict=a.strict, contrast=not a.no_contrast)
    # Node first. Without it the check never runs, and the gate must not report that as a problem in the
    # composition: on Windows the missing command comes back as an ordinary exit 1 from `cmd`, on a Mac as
    # a traceback. Exit 4 is the same "could not run the check" code reel_render.py uses.
    if not npx_path():
        print(f"  ⛔ gate: the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong.")
        return 4
    print("[gate] HyperFrames native check:", " ".join(cmd[1:]))
    print()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"  ⛔ gate: the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong.")
        return 4
    rc = res.returncode
    text = (res.stdout or "") + (res.stderr or "")
    sys.stdout.write(text)
    # Same promotion reel_render.py makes, for the same reason: an animation whose selector matches nothing is
    # a silent no-op. HyperFrames reports it as a warning, which passes without --strict. It is never intended,
    # so the gate does not call a composition safe to render while one is in it.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from reel_render import _dead_animation_targets, _offframe_text, _offframe_message
    dead = _dead_animation_targets(text)
    if dead and os.environ.get("REEL_ALLOW_DEAD_TARGETS") == "1":
        print(f"\n  ⚠ {len(dead)} animation target(s) match nothing; allowed by REEL_ALLOW_DEAD_TARGETS=1.")
        dead = []
    if rc == 0 and dead:
        print(f"\n  ⛔ {len(dead)} animation target(s) match nothing — these animations would not run, and the "
              f"render would come out silently missing them:")
        for sel in dead[:8]:
            print(f"       {sel}")
        if len(dead) > 8:
            print(f"       … and {len(dead) - 8} more")
        print("     Usually the selector and the element's real id/attribute have drifted apart. Fix one to "
              "match the other, then re-run. Deliberate? REEL_ALLOW_DEAD_TARGETS=1.")
        return 1
    # Text stuck past the frame edge: the same refusal reel_render.py makes, so "safe to render" means it.
    off = _offframe_text(text)
    if off and os.environ.get("REEL_ALLOW_OFFFRAME_TEXT") == "1":
        print(f"\n  ⚠ {len(off)} piece(s) of text run off the edge; allowed by REEL_ALLOW_OFFFRAME_TEXT=1.")
        off = []
    if rc == 0 and off:
        print(_offframe_message(off))
        return 1
    if rc == 0:
        print("\n  ✅ HyperFrames check clean — safe to render.")
    else:
        print("\n  ⛔ HyperFrames check found issues — fix them before rendering (see above). "
              "Packs may only change dressing (fonts/colors); layout, motion and overflow are HyperFrames' job.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
