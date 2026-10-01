#!/usr/bin/env python3
"""build-captions.py (v3) — SLEEK editable kinetic captions, 3 modes + smooth per-word animations:
  - single  : one word at a time (the pack's caption font, chest-height), each with a smooth Rise Fade-In.
  - build   : the SENTENCE grows word by word (cumulative, wraps to lines, the pack's accent font), fades in
              on the first word, fades out clean on the last (middle grows instantly, synced to speech).
  - takeover: full-screen — each word Lift-Ins in, stacked LARGE + centered (the pack's takeover font), all fade out together.
Every clip is an editable CapCut text element (NO baking). REPLACES the prior captions track. CapCut quit.
OPT-IN ONLY: this is NOT the default caption path (that is native CapCut Auto Captions) and is never
suggested — run it only when the creator explicitly asks for animated captions that stay editable. Every
font + the accent come entirely from the REQUIRED STYLE_PACK; there is no personal-font default.
Job/target: JOB env var = project slug under projects/ (REQUIRED); CAPCUT_DRAFT env var = the CapCut
draft folder name (defaults to the JOB slug).
Per-reel caption content (mode ranges + keywords) loads from projects/<JOB>/caption-plan.json if present,
else safe defaults (all single-mode, no forced highlights) — nothing reel-specific is hardcoded here.
"""
import json, os, glob, copy, uuid

import sys as _sys, os as _os_ds
for _s in (_sys.stdout, _sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
JOB   = os.environ.get("JOB")                     # projects/<JOB> — REQUIRED (runs on YOUR reel, not a sample)
if not JOB:
    raise SystemExit("Set JOB=<your reel folder under projects/>   e.g.  JOB=my-reel python3 product/build-captions.py")
DRAFT = os.environ.get("CAPCUT_DRAFT", JOB)       # CapCut draft folder (defaults to the job slug)
CAP = (os.path.join(os.environ["LOCALAPPDATA"], "CapCut/User Data/Projects/com.lveditor.draft").replace("\\", "/")
       if os.name == "nt" else
       os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft"))
D = f"{CAP}/{DRAFT}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "caption-templates")
if not os.path.exists(f"{TEMPLATES}/text-templates.json"):
    raise SystemExit(f"Caption templates missing at {TEMPLATES}\nRe-derive them once with:  python3 product/capture-templates.py \"<one of your drafts that has text in it>\"")
TPL = json.load(open(f"{TEMPLATES}/text-templates.json", encoding="utf-8"))
ANIM = json.load(open(f"{TEMPLATES}/anim-objects.json", encoding="utf-8"))
# FONTS + ACCENT come ENTIRELY from the active STYLE PACK (Layer 3 dressing) — REQUIRED, no hardcoded
# default. A build with no STYLE_PACK fails loud rather than reach for a font that is not part of a pack.
# This is the OPT-IN animated-editable-caption builder; it is never the default caption path and never
# suggested unless the creator explicitly asks for it. personal fonts vs ship fonts
import packbuild
STYLE_PACK = os.environ.get("STYLE_PACK")
if not STYLE_PACK:
    raise SystemExit(
        "Set STYLE_PACK=<pack> before running   e.g.  JOB=my-reel STYLE_PACK=Butter python3 product/build-captions.py\n"
        "(one of " + ", ".join(packbuild.names()) + "). This builder never defaults to a font.")
def _rgb(hexc):
    """#RRGGBB -> [r,g,b] in 0..1 for make_text's fill triple."""
    h = (hexc or "#FFFFFF").lstrip("#")
    return [int(h[i:i+2], 16) / 255 for i in (0, 2, 4)]
CAP_FONT   = packbuild.role(STYLE_PACK, "caption")["font_path"]    # single / read-along snap
BUILD_FONT = packbuild.role(STYLE_PACK, "accent")["font_path"]     # sentence build + karaoke (accent role)
TAKE_FONT  = packbuild.role(STYLE_PACK, "takeover")["font_path"]   # full-screen takeover + punch emphasis
W, ACCENT = [1.0, 1.0, 1.0], _rgb(packbuild.accent_color(STYLE_PACK))   # white + the buyer's chosen pack accent
US = 1_000_000

# per-reel caption content — loaded from projects/<JOB>/caption-plan.json if present, else safe defaults
# (no forced modes/highlights). NEVER hardcode one reel's ranges/keywords here.
_cp_path = f"{ROOT}/projects/{JOB}/caption-plan.json"
_cp = json.load(open(_cp_path, encoding="utf-8")) if os.path.exists(_cp_path) else {}
YIELD         = tuple(_cp.get("yield", (0.0, 0.0)))
# MULTI-YIELD (locked): a reel with 2+ takeovers/bubbles needs captions to hide under EACH overlay window,
# not just one range. `yields` is a list of [start,end] windows; `yield` stays for the single-window case.
YIELDS        = [tuple(r) for r in _cp.get("yields", [])]
BUILD_RANGES  = [tuple(r) for r in _cp.get("build_ranges", [])]
TAKEOVER_KEYS = _cp.get("takeover_keys", [])
KEYWORDS      = set(_cp.get("keywords", []))
PUNCH         = set(_cp.get("punch", []))

def yielded(t):
    """True if word-time t falls in ANY yield window (the single `yield` OR any of `yields`) — captions
    hide there so an overlay (takeover / thought bubble) never collides with a caption."""
    if YIELD[0] <= t < YIELD[1]: return True
    return any(a <= t < b for a, b in YIELDS)

def norm(w): return w.lower().strip(".,!?;:\"'")
def NID(): return str(uuid.uuid4()).upper()
def nid(): return uuid.uuid4().hex

def make_text(text, font, rgb, size, x, y, start, end, intro=None, out=None, fixed_w=None):
    m = copy.deepcopy(TPL["material"]); m["id"] = nid()
    c = json.loads(m["content"]); st = c["styles"][0]
    c["text"] = text; st["range"] = [0, len(text)]; st["size"] = size
    st["fill"]["content"]["solid"]["color"] = rgb
    st.setdefault("font", {})["path"] = font; st["font"]["id"] = ""
    c["styles"] = [st]                          # CRITICAL: collapse to ONE span — the captured template
    m["content"] = json.dumps(c, ensure_ascii=False)   # carries multiple stale style ranges (different
                                                        # size/color) that corrupt any multi-char text.
    hexc = "#%02x%02x%02x" % tuple(int(v*255) for v in rgb)
    m.update(text_color=hexc, font_size=float(size), font_path=font, font_id="", font_resource_id="",
             font_name="", line_spacing=0.0, font_source_platform=0, alignment=1)
    # 9:16 SAFETY: CapCut auto-wraps at 82% of frame width (an example reel's known-good on-screen config).
    # NEVER a positive fixed_width — that forces an oversized text box and runs off the reel frame.
    m["fixed_width"] = -1.0; m["line_max_width"] = 0.82; m["force_apply_line_max_width"] = False
    anim = None
    if intro or out:
        anim = copy.deepcopy(TPL["animation"]); anim["id"] = nid(); anims = []
        if intro and ANIM.get(f"{intro}|in"):
            a = copy.deepcopy(ANIM[f"{intro}|in"]); a["start"] = 0; a["duration"] = 300000; anims.append(a)
        if out and ANIM.get(f"{out}|out"):
            a = copy.deepcopy(ANIM[f"{out}|out"]); a["start"] = 0; a["duration"] = 300000; anims.append(a)
        anim["animations"] = anims
    s = copy.deepcopy(TPL["segment"]); s["id"] = NID(); s["material_id"] = m["id"]
    s["extra_material_refs"] = [anim["id"]] if anim else []
    dur = max(end - start, 0.12)
    s["target_timerange"] = {"start": int(start*US), "duration": int(dur*US)}
    s["source_timerange"] = {"start": 0, "duration": int(dur*US)}
    s.setdefault("clip", {}).setdefault("transform", {}).update({"x": x, "y": y})
    s["render_index"] = 16000; s["common_keyframes"] = []; s["keyframe_refs"] = []
    return m, anim, s

def sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if w["w"].strip().endswith((".", "!", "?")): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def mode_for(sent):
    txt = " ".join(w["w"] for w in sent).lower(); t0 = sent[0]["t"]
    if any(k in txt for k in TAKEOVER_KEYS): return "takeover"
    if any(a <= t0 < b for a, b in BUILD_RANGES): return "build"
    return "single"

def build_clips():
    tl = json.load(open(f"{ROOT}/projects/{JOB}/edit-timeline.json", encoding="utf-8"))
    words = sorted([w for b in tl["beats"] for w in b["words"]], key=lambda w: w["t"])
    clips = []
    for sent in sentences(words):
        sent = [w for w in sent if not yielded(w["t"])]
        if not sent: continue
        mode = mode_for(sent); s_end = sent[-1]["e"]
        if mode == "takeover":
            n = len(sent); step = 0.11; top = (n - 1) / 2 * step; end = s_end + 0.8
            for k, w in enumerate(sent):
                clips.append(make_text(w["w"], TAKE_FONT, W, 22, 0.0, round(top - k*step, 3), w["t"], end,
                                       intro="Lift In", out="Text Fade"))
        elif mode == "build":
            for i, w in enumerate(sent):
                text = " ".join(x["w"] for x in sent[:i+1])
                start = w["t"]; end = sent[i+1]["t"] if i+1 < len(sent) else s_end + 0.7
                intro = "Rise Fade-In" if i == 0 else None
                out = "Text Fade" if i == len(sent)-1 else None
                clips.append(make_text(text, BUILD_FONT, W, 13, 0.0, -0.16, start, end, intro, out, fixed_w=850))
        else:
            for i, w in enumerate(sent):
                start = w["t"]; end = sent[i+1]["t"] if i+1 < len(sent) else min(s_end + 0.4, s_end + 1.0)
                nn = norm(w["w"])
                if nn in PUNCH: font, rgb, size = TAKE_FONT, ACCENT, 18
                else: font, rgb, size = CAP_FONT, (ACCENT if nn in KEYWORDS else W), 13
                clips.append(make_text(w["w"], font, rgb, size, 0.0, -0.12, start, end, intro="Rise Fade-In", out=None))
    return clips

def inject(path):
    d = json.load(open(path, encoding="utf-8"))
    old = next((t for t in d["tracks"] if t.get("name") == "captions"), None)
    if old:
        ids = {s["material_id"] for s in old["segments"]}
        refs = {r for s in old["segments"] for r in s.get("extra_material_refs", [])}
        d["materials"]["texts"] = [m for m in d["materials"]["texts"] if m["id"] not in ids]
        d["materials"]["material_animations"] = [a for a in d["materials"].get("material_animations", []) if a["id"] not in refs]
        d["tracks"] = [t for t in d["tracks"] if t is not old]
    clips = build_clips()
    track = {"type": "text", "attribute": 0, "flag": 0, "id": NID(), "is_default_name": False, "name": "captions", "segments": []}
    for m, anim, s in clips:
        d["materials"]["texts"].append(m)
        if anim: d["materials"].setdefault("material_animations", []).append(anim)
        track["segments"].append(s)
    d["tracks"].append(track)
    from capcut_ripple import enforce_maintrack_ripple
    from capcut_text import sanitize_draft_text
    sanitize_draft_text(d)                      # base guardrail: 1 span/text, white fallback, 9:16 hard-wrap
    enforce_maintrack_ripple(d)                 # magnet ALL tracks (overlays/text/b-roll) + audio to main track
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return len(clips)

if __name__ == "__main__":
    import draft_safety
    draft_safety.require_capcut_quit("write captions into the draft")   # else CapCut's next save wipes it
    _ed, _why = draft_safety.edited_in_capcut(DRAFT, why=True)          # rule-7 net (warn, not block — additive)
    if _ed:
        _nv = draft_safety.next_version(draft_safety.base_of(DRAFT))
        print(f"⚠ {DRAFT!r} looks edited in CapCut since it was built ({_why}). This add is additive/safe, "
              f"but for a clean version history build to {_nv!r} instead.")
    _files = _ds.draft_json_copies(D, require=False)
    if not _files:   # never print "done" on a draft that does not exist (it used to)
        raise SystemExit(f"⛔ no CapCut draft at {D} (no {' or '.join(_ds.DRAFT_JSON_NAMES)}). "
                         f"Check CAPCUT_DRAFT / JOB — nothing was written.")
    for f in _files:
        n = inject(f)
        print(f"rebuilt SLEEK captions ({n} clips) -> {f}")
    print("done — single-word (Rise Fade-In) + accent-font sentence-BUILD + full-screen TAKEOVER (Lift In, stacked).")
