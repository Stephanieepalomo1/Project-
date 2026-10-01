#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pillow"]   # requests: talks to VectCut · pillow: cleanyap.finalize imports it
# ///
"""capcut_handoff.py — the CapCut project that ships ALONGSIDE a well-done reel.

WHY THIS EXISTS. Well-done bakes everything into one finished MP4, so when a creator wanted to change
her zooms there was nothing left to hand over: a baked file has no separate layers. The first PC tester
hit exactly that, asked three times to move to CapCut, and it took most of a day to get her a project she
could work in. Route A's spec said "nothing editable afterward" and there was no supported way to switch.
So well-done now hands over BOTH: the finished video, and a CapCut project beside it.

WHAT'S IN THE PROJECT (and what is not):
  • footage    — the engine's clean cut, one clip, scale 1.0. THIS is the point: hers to split and zoom.
  • layers     — with --layer NAME=FILE (repeatable) each KIND of element gets its OWN track, stacked
                 in the order given, so captions / hook / screens move, retime and switch off
                 independently. Reach for this whenever she asks for elements separated; do NOT answer
                 that with "that route is baked."
  • graphics   — the rendered overlay, one transparent clip sitting over the footage on the timeline.
                 On this route the type is already rendered, so it moves and retimes as a whole; it does
                 not come apart into individual words. That is what well-done means. Someone who wants
                 every element separate wants the medium route, and should be told so rather than sold this.
  • sound      — each cue as its OWN audio clip, never one pre-mixed wav, so a single cue can be moved,
                 swapped or turned down without touching the rest.

WHAT THIS DOES NOT DO: it does not export. The finished MP4 is already the deliverable and the engine's
job ends there. This project is for HER changes; if she makes one, she exports it herself from CapCut.
Nothing here drives a CapCut export.

  uv run product/capcut_handoff.py <JOB> [--overlay <file.mov>] [--base <cut.mp4>] [--name <draft name>]\n\nRUN IT WITH `uv run`, not python3. This talks to the editing engine over HTTP, so it needs the\n`requests` package, and the system Python does not necessarily have it — on this very machine it\ndoes not. The script header above declares the dependency so `uv run` fetches it once and every\nmachine behaves the same, which is the same reason head-framing.py survived a PC where hook-burst.py\ndied with a missing import.

Needs the VectCut editing engine running (product/engine/VectCutAPI/start-editor.command, SETUP.md §1b)
and CapCut QUIT — CapCut's next save silently overwrites anything written while it is open.
"""
import argparse, json, os, sys, glob

for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try:
        if (getattr(_s, "encoding", "") or "").lower().replace("-", "") != "utf8":
            _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
BASE_URL = "http://localhost:9001"


def call(ep, **kw):
    try:
        import requests
    except ModuleNotFoundError:
        sys.exit("  \u26d4 this needs the `requests` package. Run it with `uv run product/capcut_handoff.py "
                 "<JOB>` (uv fetches it from the header at the top of this file), not with python3.")
    try:
        r = requests.post(f"{BASE_URL}/{ep}", json=kw, timeout=180)
    except Exception:
        sys.exit("  ⛔ the editing engine is not running. Start it once "
                 "(product/engine/VectCutAPI/start-editor.command — SETUP.md §1b), then re-run this.")
    try:
        j = r.json()
    except ValueError:   # a 404 / crash page is a failed call, not a reason to dump HTML at her
        sys.exit(f"  ⛔ {ep} did not reply with JSON (HTTP {r.status_code}): {r.text[:160]!r}")
    # VectCut wraps every reply as {success, error, output}. Read the envelope, never the top level:
    # treating `output` as the result is how a caller ends up with a KeyError on a call that worked.
    if not j.get("success"):
        sys.exit(f"  ⛔ {ep} failed: {j.get('error') or j}")
    return j.get("output") or {}


def _dur(p):
    import subprocess
    try:
        return float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
            text=True).strip())
    except Exception:
        return 0.0


def newest(pattern):
    hits = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--base", default=None, help="the clean footage cut (default: outputs/<JOB>.mp4)")
    ap.add_argument("--overlay", default=None, help="the transparent graphics .mov (default: newest in renders/)")
    ap.add_argument("--layer", action="append", default=[], metavar="NAME=FILE[@START]",
                    help="an EXTRA named overlay track, repeatable, laid bottom-to-top in the order given "
                         "(e.g. --layer screens=build/screens.mov --layer captions=build/caps.mov). "
                         "Use this when she wants each KIND of element on its own layer instead of one "
                         "flattened graphics track, so she can move, retime or switch off captions "
                         "without touching the hook. With --layer, --overlay is optional. "
                         "Append @SECONDS for a layer that starts part-way through (e.g. "
                         "--layer crossout=build/crossout.mov@11.0) - a short element belongs at its "
                         "own time on a full-length track, not padded out with transparent video.")
    ap.add_argument("--name", default=None, help="draft name (default: <JOB>)")
    ap.add_argument("--pack", default=None, help="style pack (default: read off the overlay's name)")
    a = ap.parse_args()

    jd = os.path.join(ROOT, "projects", a.job)
    if not os.path.isdir(jd):
        sys.exit(f"  ⛔ no job at {jd}")
    base = a.base or os.path.join(jd, "outputs", f"{a.job}.mp4")
    # VectCut stages media by the path it is handed, so a relative one silently stages nothing and the
    # build only fails later, at finalize, naming a missing asset instead of the path that was wrong.
    base = os.path.abspath(base if os.path.isabs(base) else
                           (base if os.path.exists(base) else os.path.join(jd, base)))
    # With --layer the layers ARE the graphics. Reaching for the newest render as well laid the whole flattened
    # overlay on top of them, so every separated element showed twice. --overlay still adds one on purpose.
    overlay = a.overlay or (None if a.layer else newest(os.path.join(jd, "renders", "*.mov")))
    if overlay:
        overlay = os.path.abspath(overlay if os.path.isabs(overlay) else
                                  (overlay if os.path.exists(overlay) else os.path.join(jd, overlay)))
    if not os.path.exists(base):
        sys.exit(f"  ⛔ no footage cut at {base} — well-done builds one before it bakes; run the build first.")
    layers = []
    for spec in a.layer:
        if "=" not in spec:
            sys.exit(f"  ⛔ --layer wants NAME=FILE, got {spec!r}")
        nm, _, rest = spec.partition("=")
        fp, at = rest, 0.0
        if "@" in rest:
            fp, _, at_s = rest.rpartition("@")
            try:
                at = float(at_s)
            except ValueError:
                sys.exit(f"  ⛔ layer {nm!r}: {at_s!r} is not a start time in seconds")
        fp = fp if os.path.isabs(fp) else os.path.join(jd, fp)
        if not os.path.exists(fp):
            sys.exit(f"  ⛔ layer {nm!r}: no file at {fp}")
        layers.append((nm.strip(), os.path.abspath(fp), at))
    if not overlay and not layers:
        sys.exit(f"  ⛔ no rendered overlay in {jd}/renders/ — nothing to lay over the footage.")

    # CapCut must be quit BEFORE anything is written, or its next save wipes the draft.
    import draft_safety
    draft_safety.require_capcut_quit("hand this reel over to CapCut")
    name = draft_safety.next_version(draft_safety.base_of(a.name or a.job))

    bdur = _dur(base)
    odur = _dur(overlay) if overlay else 0.0
    # A zero duration means ffprobe could not read the file. Building on it produces an empty draft
    # that reports success — refuse instead, and name the file that could not be read.
    checks = [("footage", base, bdur)]
    if overlay:
        checks.append(("graphics", overlay, odur))
    checks += [(nm, fp, _dur(fp)) for nm, fp, _at in layers]
    for label, f, d in checks:
        if d <= 0:
            sys.exit(f"  \u26d4 could not read the {label} file's length: {f}\n"
                     f"     It may be corrupt or still being written. Nothing was created.")
    print(f"  footage : {os.path.relpath(base, ROOT)}  ({bdur:.1f}s)")
    if overlay:
        print(f"  graphics: {os.path.relpath(overlay, ROOT)}  ({odur:.1f}s)")
    for nm, fp, at in layers:
        when = f"  @ {at:.2f}s" if at else ""
        print(f"  {nm:<16}: {os.path.relpath(fp, ROOT)}  ({_dur(fp):.1f}s){when}")

    did = call("create_draft", name=name, width=1080, height=1920)["draft_id"]
    call("add_video", draft_id=did, video_url=base, start=0, end=bdur, target_start=0, track_name="main")
    if overlay:
        call("add_video", draft_id=did, video_url=overlay, start=0, end=odur,
             target_start=0, track_name="graphics")
    # Extra layers stack in the order given, so the caller controls what sits over what.
    for nm, fp, at in layers:
        call("add_video", draft_id=did, video_url=fp, start=0, end=_dur(fp),
             target_start=at, track_name=nm)

    # Sound cues as INDIVIDUAL clips. The tester's package glued every cue into one wav and she could not
    # move, swap or lower a single one — the thing she most wanted to adjust was the thing most welded shut.
    plan_p = os.path.join(jd, "caption-plan.json")
    cues = 0
    sfx_lanes = []          # per-track "free from" time, so overlapping cues get their own lane
    if os.path.exists(plan_p):
        try:
            plan = json.load(open(plan_p, encoding="utf-8"))
        except ValueError:
            plan = {}
        import capcut_sfx
        pal = capcut_sfx.palette()          # the buyer's own sfx/ folder, then the bundled library
        sfx_dir = os.path.join(jd, "sfx")
        for s in plan.get("sfx", []) or []:
            ref = s["file"]
            # Same resolution order the bake uses (build-reel-mp4.resolve_sfx): an absolute path, then the
            # job's own sfx/ folder, then the shared palette by cue NAME. A cue in a plan is usually a name
            # like "whoosh-short", not a file — looking only for a file finds nothing and drops every cue.
            f = (ref if os.path.isabs(ref) and os.path.exists(ref) else None)
            # a plan may name a cue WITHOUT its extension (the mixer appends one), and the job's
            # levelled copies live in sfx/norm - look for both before falling back to the palette,
            # or every one of the job's own sounds is silently skipped.
            if not f:
                for d in (os.path.join(sfx_dir, "norm"), sfx_dir):
                    for cand in (ref, ref + ".wav", ref + ".mp3"):
                        p = os.path.join(d, cand)
                        if os.path.exists(p):
                            f = p
                            break
                    if f:
                        break
            if not f:
                # resolve_cue returns (path, stem, ext) or None; only the path is wanted here.
                f = pal.get(os.path.splitext(os.path.basename(ref))[0]) or (capcut_sfx.resolve_cue(ref, pal) or (None,))[0]
            if not f or not os.path.exists(f):
                print(f"  · cue skipped (no sound file for it): {ref}")
                continue
            d = _dur(f)
            if d <= 0:
                continue
            # CapCut refuses two clips that overlap on ONE track, and a dense sound design has
            # cues within a few frames of each other. Lay each cue on the first sfx track that is
            # free at that moment, so nothing has to be nudged off its beat to fit.
            at = float(s.get("at", 0))
            lane = next((i for i, free_at in enumerate(sfx_lanes) if at >= free_at), len(sfx_lanes))
            if lane == len(sfx_lanes):
                sfx_lanes.append(0.0)
            sfx_lanes[lane] = at + d + 0.02
            call("add_audio", draft_id=did, audio_url=f, start=0, end=d,
                 target_start=at, volume=1.0,
                 track_name="sfx" if lane == 0 else f"sfx{lane+1}")
            cues += 1

    # REGISTER through the engine's own finalize, never a bare save_draft. VectCut writes the draft into a
    # folder named after its internal id and bakes THAT path into every asset reference, so a draft that is
    # merely saved lands as "dfd_cat_1789687033_b9f51556" and is not the project she was told to open.
    # finalize() does the save, the rename, the raw-text asset-path rewrite (including the Windows
    # backslash form), the never-overwrite fail-safe and the build record. There is no text in this draft,
    # so the font map is empty; the fallback is required and unused.
    # No baked camera moves in a handover draft: the footage track is the whole point of giving it to her.
    os.environ["REEL_NO_DEFAULT_MOTION"] = "1"
    import cleanyap, packbuild
    # finalize() needs a pack because it will not default a font — a shipped reel never reaches for a
    # personal one. There is no text in THIS draft, so the font is genuinely unused, but the rule still
    # holds and guessing would be the wrong habit. Read the pack off the render she already has.
    pack = a.pack or os.environ.get("STYLE_PACK")
    if not pack:
        # read it off whatever rendered file this draft was built from - with --layer there may be no
        # single "overlay", so look across every layer name too rather than crashing on None.
        for cand in ([overlay] if overlay else []) + [fp for _, fp, _a in layers]:
            low = os.path.basename(cand).lower()
            pack = next((n for n in packbuild.names() if n.lower() in low), None)
            if pack:
                break
    if not pack:
        sys.exit("  ⛔ cannot tell which style pack this reel used. Pass --pack "
                 + " | ".join(packbuild.names()))
    print(f"  pack    : {pack}")
    # job=: the face check reads THIS job's measurement. Without it finalize had only the CapCut draft folder to
    # search from, found none, and reported a measured job as "never measured" (so it never checked).
    cleanyap.finalize(did, name, {}, fallback_font=cleanyap.hook_font(pack), job=jd)
    print(f"\n  ✅ CapCut project ready: {name}")
    if layers:
        print(f"     footage on the main track; "
              + ", ".join(nm for nm, _f, _a in layers) + f" each on its own track; "
              + f"{cues} sound cue(s) on their own clips.")
    else:
        print(f"     footage on the main track, the graphics over it, {cues} sound cue(s) on their own clips.")
    if sfx_lanes and len(sfx_lanes) > 1:
        print(f"     sound spread over {len(sfx_lanes)} tracks so overlapping cues keep their timing.")
    print(f"     Open CapCut and it is at the top of your projects.")
    print(f"     Your finished video is already done — this is only here if you want to change something")
    print(f"     yourself (your own zooms on the footage clip). If you do change it, export it from CapCut.")


if __name__ == "__main__":
    main()
