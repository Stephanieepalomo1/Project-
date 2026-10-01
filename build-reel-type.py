#!/usr/bin/env python3
"""build-reel-type.py — SHIPPABLE animated-type overlay for a whole reel (Route A / baked-MP4 path).

Reads projects/<JOB>/outputs/<JOB>.transcript.json (word timings) + projects/<JOB>/caption-plan.json
(hook / takeover_keys / keywords / duration) and a STYLE PACK, and emits ONE transparent HyperFrames
composition with the FIXED layouts skinned by the pack:
  • hook (headline)  — fragment build, holds through the open, fades at hook_end
  • caption (snap)   — one word at a time, low, read-along EVERYWHERE
  • takeover         — the key phrase as a full-screen vertical word stack, held
Render transparent (mov) through product/reel_render.py (gated), then finish with product/build-reel-mp4.py
(footage + overlay + punch-ins + SFX) — or reel_render.py composite for a quick re-stack.

  JOB=my-reel STYLE_PACK=Butter python3 product/build-reel-type.py

Nothing reel-specific is hardcoded — JOB required, pack from style-packs.json, content from caption-plan.

caption-plan.json "elements" (star · block · rule · counter) time like this, and the build SAYS what it did:
  at        when the element animates in (seconds).
  duration  how long it stays on screen after `at`. (Older plans wrote `duration` as the moment the element
            LEAVES; that still works whenever it is later than `at`. If `duration` is not later than `at`, it is
            read as on-screen length, so a plan written the natural way can never make an element vanish
            before it appears.)
  counter   a count-up card: {"kind":"counter","at","duration","x","y","w","from","to","count_duration",
            "group":true,"label","prefix","suffix","decimals","ground","color","label_color","size","label_size","front"}.
PHRASE CAPTIONS (all opt-in; a plan without these keys builds exactly as before):
  caption_mode "phrase"   a short phrase at a time (breaks after , . ! ? or phrase_max_words, default 5, and never
                          across a cut in transcript/cuts.json); instant on and off like snap captions.
  accent_words            [{"w","t"}] marks ONE occurrence (the word nearest t) for the pack's keyword face
                          (keyword_font_file, e.g. a serif italic) in the accent color at welldone.keyword_scale;
                          a bare string marks every occurrence.
  caption_treatments      mode "spotlight": the whole phrase shows and the word being said cross-fades into the
                          keyword face (karaoke without the build). mode "single" in a phrase reel = one-word phrases.
  caption_skip            [[t0, t1]] windows where another graphic carries the words; captions stand aside.
  caption_chin_lock       {"offset": 80, "follow": ["spotlight"]}: letters sit that many px under her chin
                          (chin_lock.py). Modes in "follow" track her frame by frame through their own window;
                          every other caption holds one spot per shot, under the lowest her chin gets in it.
                          Default follow = every mode. "others": "fixed" puts every non-follow caption in
                          ONE spot for the whole reel (the measured open zone below her), for a creator who
                          positions them herself per scene in CapCut.
  caption_fixed_y         "center" or a y in px: where the non-following captions sit (centre of the letters).
  phrase_max_words 1      one word at a time in the phrase look (accent words, baseline, chin lock all apply);
                          pair_quick_words true joins a word said too fast to read with the next.
Every text color a plan names is checked against its ground at build time; a token that would fail the
legibility floor is swapped for the pack's ink (or cream on a dark ground) and the swap is printed.

TYPE JUDGMENTS CROSS-REFERENCE `product/IMPECCABLE-TYPE-PRINCIPLES.md` (impeccable's text/layout/readability/
placement guidelines, adapted to the reel). Because the well-done render is self-verifiable, check every
sizing/placement/hierarchy call against it FROM THE RENDERED FRAME before calling it done: hierarchy obvious at
a glance, squint test passes, meaning-bearing text reads over footage, headline balanced (no orphans), the hook
group is grouped (proximity + rhythm), shadow soft, supporting line readable (one line or balanced two, never tiny).
"""
import os, sys, json, re, html, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stylepack
import safe_zones   # SHARED: where the PLATFORM draws its own UI. Never place meaning-bearing text there.
import text_effects  # SHARED named text-animation vocabulary (hook/takeover intro motion; rendered-output only)
from pack_palettes import PALETTE, resolve_color, GROUNDS, GROUND, INK, CARD_THEME, text_safe, contrast_ratio   # locked per-pack palette + card themes (single source of truth) for the element library + breakaways

JOB = os.environ.get("JOB") or (os.path.basename(os.path.normpath(os.environ["JOB_DIR"])) if os.environ.get("JOB_DIR") else None)
if not JOB:
    raise SystemExit("Set JOB=<your reel folder under projects/>   e.g.  JOB=my-reel STYLE_PACK=Butter python3 product/build-reel-type.py")
def _saved_pack():
    """Her saved default style pack (creative-vault/user-style.json "default_pack", the one
    cleanyap.set_default_pack writes), or None when she has not chosen one. The CapCut lanes read the same
    field through cleanyap.default_pack, so every route agrees on which pack is hers."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "user-style.json"),
                  encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("default_pack") or None
    except Exception:
        return None
# The pack is STYLE_PACK when given, else her saved default. With neither there is no pack to build in, and
# the build stops rather than reaching for one she never chose: every font on screen comes from a pack.
PACK = os.environ.get("STYLE_PACK") or _saved_pack()
if not PACK:
    raise SystemExit("No style pack chosen. Set STYLE_PACK=<pack> (one of: " + ", ".join(stylepack.names())
                     + ") or save a default pack first; reels never fall back to a pack she did not pick.\n"
                     "   e.g.  JOB=my-reel STYLE_PACK=Butter python3 product/build-reel-type.py")
COMP = os.environ.get("COMP", "reel")
LAYER = os.environ.get("LAYER", "all")   # "hook" = hook only · "front" = everything BUT the hook · "all" = normal
                                         # (behind mode renders hook + front separately so a subject cutout can sit between them)
                                         # ALSO: a group name (or comma list) from _GROUP_TRACKS near the bottom of this
                                         # file — captions / vibe / label / takeover / breakaway / elements — to render ONE kind of
                                         # element to its own transparent layer. That is what puts each kind on its own
                                         # CapCut track. See product/separate_layers.sh and the separate-layers skill.
SIZE_SCALE = float(os.environ.get("SIZE_SCALE", "6.0"))
# LOCKED well-done type standard (the creator, 2026-08-08): stacked/wrapped display type (headline, split
# headline, eyebrow, takeover word-stack) uses ONE tight line-height so multi-line type reads as a unit, not
# loosely-spaced rows. This is how well-done animated type is executed. One knob, applied everywhere.
TIGHT_LH = float(os.environ.get("TIGHT_LH", "0.92"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# JOB_DIR: the job folder itself, for a job that does not sit directly under projects/ (a pull-reels clip lives
# at projects/<parent>/clips/<name>/). Its files are still named after the folder: outputs/<name>.mp4 and so on.
# Unset, everything is read from projects/<JOB>/ exactly as before.
JOB_DIR = os.environ.get("JOB_DIR") or f"{ROOT}/projects/{JOB}"
JOB_NAME = os.path.basename(os.path.normpath(JOB_DIR)) if os.environ.get("JOB_DIR") else JOB
OUT = f"{JOB_DIR}/hf-reel-type-{PACK.lower()}"   # per-pack dir so packs don't clobber each other
FDIR = f"{OUT}/fonts"
os.makedirs(FDIR, exist_ok=True)

TR = json.load(open(f"{JOB_DIR}/outputs/{JOB_NAME}.transcript.json", encoding="utf-8"))
WORDS = [{"w": w["text"], "t": float(w["start"]), "e": float(w["end"])} for w in TR["words"]]
cp_path = f"{JOB_DIR}/caption-plan.json"
CP = json.load(open(cp_path, encoding="utf-8")) if os.path.exists(cp_path) else {}
import learned as _learned_ctx     # name this build BEFORE any preference is read, so scoped ones can match
_learned_ctx.context_for_build("yap", register=CP.get("register"), pack=PACK)
# NAMED TEXT-ANIMATION EFFECTS (rendered-overlay vocabulary, per role). Default per
# text_effects.DEFAULTS; override per reel with caption-plan "effects":{"hook":...,"takeover":...}.
# Pin the engine's original fade+rise with "rise". Rendered-output only — never the CapCut text path.
HOOK_FX = text_effects.resolve(CP, "hook")
TK_FX   = text_effects.resolve(CP, "takeover")
DUR = float(os.environ.get("DUR_OVERRIDE") or CP.get("duration") or (WORDS[-1]["e"] + 0.6 if WORDS else 0))   # DUR_OVERRIDE = fast sandbox previews only
if os.environ.get("DUR_OVERRIDE"):   # a stale shell var would silently truncate a real reel — say it every time
    print(f"  ⚠ DUR_OVERRIDE={os.environ['DUR_OVERRIDE']} is set: this build is TRUNCATED to {DUR:.1f}s (sandbox "
          f"preview only). Unset it (`unset DUR_OVERRIDE`) before building a real reel.")
HOOK = (CP.get("hook_by_pack") or {}).get(PACK) or CP.get("hook") or []   # per-pack hook (display fonts want short)
HOOK_END = float(CP.get("hook_end", 9.0))
# PERSISTENT HOOK: the hook that does NOT fade. It is not a separate element with its own styling — it is
# the ordinary hook (headline, or headline + subhead when the text is long enough to split) held for the
# whole reel. So it inherits the pack's locked headline treatment automatically and cannot drift per reel.
HOOK_PERSIST = bool(CP.get("hook_persist", False))
HOOK_SPLIT = os.environ.get("HOOK_SPLIT", "0") == "1"   # long hook -> headline + eyebrow/subhead (Route A baked)
HOOK_LONG = CP.get("hook_long", "")                     # the long hook to split
HOOK_EMPH = CP.get("hook_emphasis", "second")           # which half carries the emphasis (set in the style plan)
# per-line caption treatments (/studio single|karaoke|takeover <line>): each {"text","mode"} swaps ONE
# transcript line's on-screen style. takeover-mode lines join the takeover keys (full-screen stacks);
# single/karaoke-mode lines are handled after span-finding via a per-word mode override.
CAP_TREAT = [t for t in CP.get("caption_treatments", []) if t.get("text") and t.get("mode")]
TK_EXACT = bool(CP.get("takeover_exact", False))   # True = hold ONLY the matched phrase, do NOT swallow its sentence
TK_HOLD  = float(CP.get("takeover_hold", 0.8))     # seconds the stack holds after its last word
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})
def norm(w):
    """One word as the matcher sees it. Every phrase the plan names (takeover keys, caption treatments,
    keywords, an emphasis word) goes through this AND so does each transcript word it is looked for in.
    Case folded; a typographic apostrophe becomes the plain one (a plan typed on a Mac carries ’ where
    WhisperX writes '); then only letters, digits and the apostrophe stay, in ANY script. The first version
    kept a-z alone, so a Russian or Greek transcript normalised to empty strings, one caption treatment
    matched every line, and an accented key ("está bien") could never match at all."""
    w = unicodedata.normalize("NFKC", str(w)).translate(_APOSTROPHES).casefold()
    return "".join(c for c in w if c == "'" or unicodedata.category(c)[0] in "LMN")
TK_KEYS = [[norm(t) for t in k.split()] for k in CP.get("takeover_keys", []) if isinstance(k, str)] \
    + [[norm(x) for x in str(t["text"]).split()] for t in CAP_TREAT if t["mode"] == "takeover"]
KEYWORDS = {norm(k) for k in CP.get("keywords", []) if isinstance(k, str)} - {""}
# PHRASE CAPTIONS (opt-in, caption_mode "phrase"): a short phrase on screen at a time instead of one word,
# broken after a comma or sentence end or at phrase_max_words. Accent words inside a phrase switch to the
# pack's KEYWORD face (keyword_font_file, e.g. a serif italic) in the accent color, keyword_scale x the size.
# "accent_words" picks them per OCCURRENCE: {"w": "edit", "t": 1.52} marks the transcript word nearest that
# time (so "edit" can be the accent on one line and plain on another); a bare string marks every occurrence.
PHRASE_MAX = int(CP.get("phrase_max_words", 5))   # 1 = one word at a time in the phrase look (her "static" captions)
PAIR_QUICK = bool(CP.get("pair_quick_words", False))
SPOT_MAX = int(CP.get("spotlight_max_words", 5))    # a karaoke (spotlight) line keeps its phrase even in a one-word reel   # opt-in: a one-word caption said too fast to read joins the next
_ACC_SPEC = CP.get("accent_words", [])
# caption_skip: [[t0, t1], ...] windows where no caption shows because another graphic carries the words
# (a designed title, a takeover built as its own layer). Captions yield to them like they yield to a takeover.
CAP_SKIP = [(float(a), float(b)) for a, b in CP.get("caption_skip", [])]
# caption_chin_lock: {"offset": 80} keeps every phrase/spotlight caption's letters that many px under her chin,
# measured frame by frame over the caption's own window (product/chin_lock.py). Rendered routes only.
CHIN_LOCK = CP.get("caption_chin_lock") or None
# caption_fixed_y: where a caption that is NOT chin-following sits, as the centre of its letters in px
# ("center" = the middle of the frame). Clamped to the platform safe band like every placement.
_fy = CP.get("caption_fixed_y")
FIXED_Y = None if _fy is None else (960 if _fy == "center" else float(_fy))
if FIXED_Y is not None:
    FIXED_Y = min(max(FIXED_Y, safe_zones.TOP + 60), safe_zones.BOTTOM - 60)
# A phrase never crosses a CUT: a caption straddling a jump cut reads as two thoughts glued together. The cut
# points come from the frame-snapped EDL (transcript/cuts.json), in cut-timeline seconds, each clip counted
# for as long as it actually plays (a sped clip plays shorter). No EDL -> no cut breaks, as before.
CUT_TIMES = []
try:
    _edl = json.load(open(f"{JOB_DIR}/transcript/cuts.json", encoding="utf-8"))
    _edl = _edl.get("segments", []) if isinstance(_edl, dict) else _edl
    _acc = 0.0
    for _sg in _edl[:-1]:
        _acc += float(_sg.get("played") or (float(_sg["end"]) - float(_sg["start"])) / float(_sg.get("speed") or 1))
        CUT_TIMES.append(_acc)
except (OSError, ValueError, KeyError, TypeError):
    CUT_TIMES = []
def _clip_of(t):
    import bisect
    return bisect.bisect_right(CUT_TIMES, t)
CAP_LIFT = float(CP.get("caption_lift_px", 0))   # per-reel framing nudge: raise captions toward the chin
# CHIN-TRACKED CAPTIONS: a talking head's chin moves (she leans in and back), but a fixed caption y cannot,
# so ONE number is always either riding onto the face or floating far below it. caption_track lets the plan
# pass a per-window caption CENTRE measured off the real chin, so captions sit under it the whole reel.
# Shape: [[t0, t1, y], ...] — the window containing a caption clip's START sets that clip's y.
# Additive + BACKWARD-SAFE: no CP["caption_track"] -> every clip uses the pack y, output byte-identical.
CAP_TRACK = [(float(a), float(b), float(y)) for a, b, y in CP.get("caption_track", [])]
# SIDE-PLACED CAPTIONS (per-reel): sit captions BESIDE the face at mouth height instead of under the chin.
# Shape: [[t0, t1, face_right_px, mouth_y_px], ...]. The gap is a GUIDE, not a hard rule: a long word starts
# closer rather than shrinking below the legibility floor, so nothing ever gets small or leaves the safe box.
CAP_SIDE = [(float(a), float(b), float(r), float(m)) for a, b, r, m in CP.get("caption_side_track", [])]
CAP_SIDE_GAP = float(CP.get("caption_side_gap", 10))
# The captions HOLD the empty side; they do not follow the subject. Face clearance is a MINIMUM that can
# only push them further into the gap, never back toward her — otherwise, when she drifts toward the
# middle, the captions slide with her and the frame stops being balanced. captions balance offcentre subject
CAP_SIDE_ANCHOR = float(CP.get("caption_side_anchor", 0))

def cap_side(t):
    for a, b, r, m in CAP_SIDE:
        if a <= t < b:
            return r, m
    return None, None
HOOK_LIFT = float(CP.get("hook_lift_px", 0))     # per-reel framing nudge: nudge the top-anchored hook up
HOOK_TOP = round(280 - HOOK_LIFT)                # hook TOP-anchored (grows down); y280 sits just under the top-270px platform-UI band (safe_zones.TOP) — never let the hook creep to the top edge (locked, all styles)
HOOK_MAXH = float(CP.get("hook_max_h", 330))     # hook height budget (top ~206 -> bottom ~536, above the hairline)
HOOK_SCALE = float(CP.get("hook_scale", 1.0))    # /studio punch (>1) / hush (<1): scale the fitted hook size, re-wrap + floor-check
VIBE = CP.get("vibe") or {}                       # /studio vibe: the delight touch (read here so the hook block can use the typographic kinds)
CAPTION_MODE = os.environ.get("CAPTION_MODE", CP.get("caption_mode", "single"))   # "single" snap | "build" karaoke

pack = stylepack.load(PACK)
# The launch packs were hand-tuned against their own faces over many real reels; their typographic numbers
# are deliberate and their output must not move. The font-metric floors below are a SAFETY NET for packs
# built by a buyer (/studio recipe, style-pack), which clone a base pack's numbers onto a face those
# numbers were never tuned for. Shipped pack => trust the tuning. Custom pack => measure the face.
_TUNED = bool(pack.get("in_launch_kit"))
# The accent: this reel's own (the plan's accent_by_pack / accent), else her saved default (user-style.json
# default_accent, set with /studio accent), else the pack's own accent. Same order as every other route,
# because the saved default is read by the one reader packbuild keeps for it.
import packbuild as _packbuild
ACCENT = ((CP.get("accent_by_pack") or {}).get(PACK) or CP.get("accent") or _packbuild.saved_accent()
          or pack.get("accent_color") or "#ffffff")
LH_OVR = (CP.get("line_height_by_pack") or {}).get(PACK) or pack.get("line_height_override")   # per-reel override, else the pack default
HOOK_LH = float(LH_OVR) if LH_OVR else 1.08
# Per-pack well-done SCALE tuning (fonts render at different visual sizes, so each pack can nudge): headline
# size budget, eyebrow scale, caption scale, headline tracking. Defaults = the Butter gold standard.
WD = pack.get("welldone", {})
HL_MAXH_MULT = float(WD.get("headline_maxh", 0.70))   # bigger -> larger headline (watch the safe zone)
EYE_MULT = float(WD.get("eyebrow_scale", 1.0))         # bigger -> larger eyebrow
CAP_MULT = float(WD.get("caption_scale", 1.0))         # bigger -> larger caption (base for both modes)
BUILD_MULT = float(WD.get("build_scale", CAP_MULT))    # karaoke caption size mult (separate from single)
SINGLE_MULT = float(WD.get("single_scale", CAP_MULT))  # single/snap caption size mult
KAR_WEIGHT = str(WD.get("karaoke_weight", "600"))      # karaoke weight ("400" for single-weight display faces, e.g. Ugly Dave)
SINGLE_WEIGHT = str(WD.get("single_weight", "600"))    # single caption weight
SINGLE_LS = WD.get("single_tracking", 0)               # single caption letter-spacing (em), e.g. -0.02 to tighten
HL_TRACK = WD.get("headline_tracking")                 # em letter-spacing on the headline (e.g. -0.02), or None
HEAD_LH_WD = float(WD.get("line_height", 0.92))        # headline block line-height (tighter for tall/hollow fonts)
EYE_GAP = float(WD.get("eyebrow_gap", 0))              # px gap so a big headline's top line never touches the eyebrow
SHADOW = WD.get("text_shadow")                         # per-pack softer/blurrier drop shadow, or None (per-element default)
TK_SCALE = float(WD.get("takeover_scale", 1.0))        # takeover word-stack size multiplier
TK_WHITE = bool(WD.get("takeover_white", False))       # takeover stays all-white (no accent on the keyword)
SUB_WEIGHT = str(WD.get("subhead_weight", "600"))      # eyebrow weight; "normal" for handwritten fonts (no faux-bold)
SUB_LS = WD.get("subhead_tracking", 0)                 # eyebrow letter-spacing (em)
SUB_COLOR = WD.get("subhead_color")                    # eyebrow color override (else inherits hook color)
_SUBCOL = f"color:{SUB_COLOR};" if SUB_COLOR else ""
HOOK_COLOR = WD.get("hook_color") or "#fff"             # per-pack rendered HOOK text color (default white)
HEAD_WEIGHT = WD.get("headline_weight")                 # optional CSS weight for the hook HEADLINE (e.g. "800")
_HW = f"font-weight:{HEAD_WEIGHT};" if HEAD_WEIGHT else ""
import shutil
_css = [text_effects.CSS]; _faces = {}   # helper classes for split (per-char/word) effects
def face(e):
    # Key the CSS family on the FILE, not the display name — two variants can share a name (Soup Du Jour has a
    # solid AND a hollow file both named "Soup Du Jour"); keying by name collides them and the takeover falls
    # back to whichever loaded first (the solid). By file basename, solid vs hollow stay distinct.
    # Two DIFFERENT files can still share a basename: every font CapCut's catalog downloads is cached as
    # font.ttf / font.otf, so on a buyer machine whose pack faces come from there one @font-face served every
    # role and each rendered in the first one's glyphs. A second file under a name already taken gets a
    # numbered family of its own; the same file asked for twice keeps its one family, as before.
    base = "".join(c for c in os.path.splitext(os.path.basename(e["file"]))[0] if c.isalnum()) or "F"
    fam, n = base, 2
    while fam in _faces and _faces[fam] != e["file"]:
        fam, n = f"{base}{n}", n + 1
    if fam not in _faces:
        ext = os.path.splitext(e["file"])[1] or ".ttf"
        try: shutil.copy(e["file"], f"{FDIR}/{fam}{ext}")
        except Exception as ex: print(f"  ⚠ font copy failed {e['font']}: {ex}")
        _css.append(f"@font-face{{font-family:'{fam}';src:url('fonts/{fam}{ext}');}}")
        _faces[fam] = e["file"]
    return fam
def px(e): return max(20, round(e["size"] * SIZE_SCALE))
def caseit(s, e):
    m = e.get("case", "lower"); return s.upper() if m == "upper" else (s.title() if m == "title" else s.lower())
H = stylepack.element(PACK, "headline"); C = stylepack.element(PACK, "caption"); TK = stylepack.element(PACK, "takeover")
BLD = stylepack.element(PACK, "accent_caption")   # accent_caption drives the CARD KICKER (kept for cute accents, e.g. Bloop)
fH, fC, fTK, fBLD = face(H), face(C), face(TK), face(BLD)
# Stacked display type is set deliberately tight so multi-line copy reads as ONE unit — but never tighter
# than the face's own ink, or ascenders and descenders of neighbouring lines physically cross. The 0.92
# default was set against a 0.67-ink face; Anton is 0.985. Raise-only, so a short face keeps its tight value.
_H_INK = stylepack.font_ink_ratio(H["file"])
if not _TUNED and HEAD_LH_WD < _H_INK:
    print(f"  ↻ headline line-height {HEAD_LH_WD} is tighter than {H['font']}'s ink ({_H_INK:.3f}), raised so lines cannot cross")
    HEAD_LH_WD = round(_H_INK, 3)
KAR = dict(BLD)   # KARAOKE caption font — defaults to accent_caption, but a pack can point it at a different face
if pack.get("karaoke_font_file"):   # so karaoke can be clean (e.g. Inter) while the kicker stays cute (e.g. Bloop).
    import hooksplit as _HSpin      # the pinned face is found like any pack face: file, then by name, then its stand-in
    KAR["file"], KAR["font"] = _HSpin.pinned_font(PACK, "karaoke_font_file", "karaoke_font_name", "Karaoke")
fKAR = face(KAR)
bpx = px(KAR)
# KEYWORD face: the accent-word / spotlight face for phrase captions. A pack pins it with keyword_font_file
# (found like any pack face); without one it is the pack's accent_caption face.
KW = dict(BLD)
if pack.get("keyword_font_file"):
    import hooksplit as _HSkw
    KW["file"], KW["font"] = _HSkw.pinned_font(PACK, "keyword_font_file", "keyword_font_name", "Keyword")
fKW = face(KW)
KW_SCALE = float(WD.get("keyword_scale", 1.30))

import hooksplit as _HSm
def _HS_measure(txt, fontpath, size):
    try: return _HSm._measure(txt, fontpath, size)
    except Exception: return len(txt) * size * 0.55

# WHERE SHE IS decides the captions' height, not the pack. The pack's fixed height (about y1152) is chest on
# a subject framed high and chin on one framed low, so a caption sat on her collar. With a measurement on
# file (workflows/subject-zones.py) and no per-reel track, the captions sit at the top of the open zone
# below her, which starts 60px under her lowest chin: "about 60px below the chin", measured per reel. Her
# taught caption.zone picks the zone (below is the default); any other choice, or no measurement, keeps
# the pack's height.
def _measured_caption_top():
    try:
        with open(f"{JOB_DIR}/subject-zones.json", encoding="utf-8") as fh:
            zones = json.load(fh)
    except (OSError, ValueError):
        return None, "no subject-zones.json for this job, so the pack's caption height"
    import learned as _lz
    want = _lz.get("caption.zone", "below")
    below = (zones.get("zones") or {}).get("below") or {}
    if want != "below":
        return None, f"caption zone '{want}' is set, so the pack's caption height"
    if not below.get("usable"):
        return None, "no open zone below her on this framing, so the pack's caption height"
    return int(below["top"]), f"just under her chin (the open zone below her starts at y{int(below['top'])})"


CAP_BELOW_TOP, _cap_where = _measured_caption_top() if not CAP_TRACK else (None, "the per-reel caption track")
print(f"  captions: {_cap_where}")


def cap_top(t, base, half=0):
    """Caption centre for a clip starting at t: the tracked chin-aware y, else just under her measured chin,
    else the pack's fixed y. Clamped into the platform safe box — a chin-tracked value must never push text
    under the app's UI."""
    y = base if CAP_BELOW_TOP is None else CAP_BELOW_TOP + half - CAP_LIFT
    for a, b, ty in CAP_TRACK:
        if a <= t < b:
            y = ty
            break
    lo, hi = safe_zones.TOP + half, safe_zones.BOTTOM - half
    return round(min(max(y, lo), hi))
def esc(s): return html.escape(s)

# CapCut normalized y (fraction of half-height, +up) -> CSS pixel center on the 1080x1920 canvas.
# headline y=0.59 -> ~394px (above head) · caption y=-0.2 -> ~1152px (chest) · takeover y=0 -> 960 (center).
def ypx(e): return round(960 - float(e.get("y", 0.0)) * 960)
SAFE_W = 780   # x150..930
HOOK_W = 960   # the hook is TOP-anchored (above the head) so it can use more width than the caption safe zone -> bigger hook
HOOK_MAXW = float(WD.get("hook_maxw", HOOK_W))   # per-pack hook width cap (lower -> narrower, for wide faces / safe zone)
import math
for _s in (sys.stdout, sys.stderr):   # Status lines print symbols like ✓ and →.
    try:                              # A Windows console set to cp1252 can't write
        if (getattr(_s, "encoding", "") or "").lower().replace("-", "") != "utf8":
            _s.reconfigure(encoding="utf-8")   # them, so switch to UTF-8 before the first one.
    except Exception:
        pass
def _wraps(line, size, maxw, cw=0.56):
    per = max(1, int(maxw / (size * cw)));  return max(1, math.ceil(len(line) / per))
def fit_wrap(lines, start, maxh, maxw=SAFE_W, lh=1.12, floor=30):
    """Size the wrapped block to FILL maxh: GROW to the largest font where the wrapped stack still fits the band
    (capped by per-line width). The hook fills the above-head band regardless of the pack's base size, so a pack
    with a small base (Editorial=20) no longer renders tiny. `start` is ignored (kept for signature). Never
    overflows the band; never below floor."""
    best = floor; s = floor
    while s <= maxh:
        if sum(_wraps(l, s, maxw) for l in lines) * s * lh <= maxh:
            best = s
        s += 4
    return best
def fit_stack(words, start, maxh, maxw=SAFE_W, lh=1.15, cw=0.6, floor=30):
    """takeover: one word per line — fit N lines in maxh AND each word within maxw."""
    s = start
    while s > floor:
        if len(words) * s * lh <= maxh and all(len(w) * cw * s <= maxw for w in words): return s
        s -= 4
    return s
def fit_hook(frags, start, maxh, maxw=SAFE_W, lh=1.08, cw=0.60, floor=44):
    """hook: largest size where EVERY fragment is ONE line (no mid-fragment wrap = fewer breaks) and the
    stack fits maxh. A long fragment (long hook) caps the size — display fonts want short hooks."""
    s = start
    while s > floor:
        if all(len(f) * cw * s <= maxw for f in frags) and len(frags) * s * lh <= maxh: return s
        s -= 2
    return floor

# ---- MEASURED + BALANCED headline fit: delegates to the ONE shared brain in hooksplit, so the baked engine
# and the CapCut engine can NEVER drift (a single measure+balance implementation feeds both). ---------------
def _fontpath(e):
    f = e.get("file", "")
    if f and os.path.exists(f):
        return f
    try:
        import packbuild as _PB
        return _PB.capcut_font_path(f)
    except Exception:
        return None
def fit_headline(text, e, maxh, maxw=SAFE_W, lh=1.08, start=None, floor=48, max_lines=2):
    """Largest font size where `text` balances into <= max_lines within maxw (MEASURED) and fits maxh.
    Balanced = no orphan words. Returns (size, [lines]). Shared logic = hooksplit.fit_balanced."""
    import hooksplit as _HS
    return _HS.fit_balanced(text, _fontpath(e), maxw, start or px(e), floor_px=floor, max_lines=max_lines, lh=lh, maxh_px=maxh)

# ---- find takeover spans (key phrase → extend to end of its sentence) ----
nrm = [norm(w["w"]) for w in WORDS]
consumed = set(); spans = []
i = 0
while i < len(WORDS):
    matched = False
    for key in TK_KEYS:
        L = len(key)
        if any(key) and nrm[i:i+L] == key:
            j = i + L - 1
            if not TK_EXACT:                          # default: extend to the end of the sentence (legacy)
                while j + 1 < len(WORDS) and not WORDS[j]["w"].strip().endswith((".", "!", "?")):
                    j += 1
            spans.append((i, j)); consumed.update(range(i, j + 1)); i = j + 1; matched = True; break
    if not matched: i += 1
# FAIL LOUD on a stale plan: a takeover key that matches no transcript span used to vanish silently (only a
# "takeovers=0" in the summary). Say it plainly so a re-cut transcript doesn't quietly lose the payoff.
if TK_KEYS and not spans:
    print(f"  ⚠ NO takeover will render: key(s) {[' '.join(k) for k in TK_KEYS]} matched nothing in the "
          f"transcript. caption-plan.json is stale vs the current cut — fix the text or the takeover is gone.")

# A PERSISTENT hook (teaching banner) must YIELD (hide) during every full-screen takeover — otherwise the
# banner sits under/over the takeover word-stack and collides. Non-persistent hooks already fade at HOOK_END
# (before the takeovers), so this only applies when HOOK_PERSIST. Windows match the takeover clips below.
TK_WINDOWS = [(WORDS[a]["t"], WORDS[b]["e"] + TK_HOLD) for (a, b) in spans]
# Full-screen breakaway CARDS own the screen too — the persistent hook must yield across those windows as well.
_BK_WINDOWS = [(float(_b.get("at", 0.0)), float(_b.get("out", float(_b.get("at", 0.0)) + 2.6)))
               for _b in CP.get("breakaways", [])]
YIELD_WINDOWS = sorted(TK_WINDOWS + _BK_WINDOWS)
def _hook_yield_js(sel):
    """Tweens that hide `sel` just before each full-screen moment (takeover or breakaway card) and restore
    it after (persistent hook only)."""
    out = []
    for (wa, wb) in YIELD_WINDOWS:
        # hide (with a tl.set hard-kill so non-linear seeking can't leave the banner stale), then restore after.
        out.append(f'tl.to("{sel}",{{autoAlpha:0,duration:0.3}},{max(0.0, wa - 0.3):.2f});'
                   f'tl.set("{sel}",{{autoAlpha:0}},{wa:.2f});'
                   f'tl.to("{sel}",{{autoAlpha:1,duration:0.3}},{wb:.2f});')
    return out

# per-word caption mode override: default None (=global CAPTION_MODE); a single/karaoke treatment stamps its
# span's words with that mode, so ONE line renders differently from the rest of the reel.
word_mode = [None] * len(WORDS)
for t in CAP_TREAT:
    md = {"karaoke": "build", "single": "single", "build": "build", "phrase": "phrase",
          "spotlight": "spotlight"}.get(t["mode"])
    if not md: continue                                   # takeover handled via TK_KEYS above
    ph = [norm(x) for x in str(t["text"]).split()]; L = len(ph)
    if not L: continue
    i = 0; _hit = False
    while any(ph) and i < len(WORDS):          # all punctuation: nothing to match, so it is reported below
        if nrm[i:i+L] == ph:
            _hit = True
            j = i + L - 1
            while j + 1 < len(WORDS) and not WORDS[j]["w"].strip().endswith((".", "!", "?")):
                j += 1
            for k in range(i, j + 1):
                if k not in consumed:
                    word_mode[k] = md
            i = j + 1
        else:
            i += 1
    if not _hit:   # same stale-plan trap as the takeover key: say it, don't silently drop the treatment
        print(f"  ⚠ caption treatment {t['mode']!r} for {str(t['text'])!r} matched nothing in the transcript — "
              f"it will NOT render. caption-plan.json is stale vs the current cut.")

clips = []; tljs = []; gi = 0

# ---- HOOK: fragment build, hold, fade at hook_end (or hold the whole reel if hook_persist) ----
HOOK_SHOW = DUR if HOOK_PERSIST else HOOK_END
_hk_ovr = (CP.get("hook_size_by_pack") or {}).get(PACK) or CP.get("hook_size_px")   # optional manual size
HOOKN = int(_hk_ovr) if _hk_ovr else (fit_wrap([caseit(t, H) for t in HOOK], px(H), HOOK_MAXH, maxw=HOOK_MAXW, lh=HOOK_LH) if HOOK else px(H))   # BIG headline: grow-to-fill the band, using the wider HOOK_W budget (top-anchored, above the head)
TK_BOX = stylepack.font_box_ratio(TK["file"]) if not _TUNED else 0.0   # this FACE's real one-line box height
TK_LH = max(1.06, TK_BOX, float(LH_OVR) if LH_OVR else TIGHT_LH)   # takeover word-stack: individually-animated block
# words need line-height >= ~1.0 or adjacent word boxes overlap (hyperframes check: content_overlap). The
# headline keeps the tight 0.92 (it is a wrapped unit, not stacked block words); the takeover floors at 1.06.
# The 1.06 constant was calibrated against a 1.00-box face (Soup Du Jour). A taller face needs a taller
# floor or its stacked word boxes overlap no matter what the pack asks for, so the floor is MEASURED from
# the face itself: Inter 1.22, Playfair 1.34, Anton 1.51. 1.06 stays as the minimum for short faces.
HOOK_PX = HOOKN                     # the hook is the ANCHOR; captions size DOWN from its ACTUAL size (scale.md)
if HOOK_SPLIT and HOOK_LONG:
    # long hook -> two reading-order lines (first half on top, second below); emphasis half = big headline,
    # other half = quiet eyebrow(above)/subhead(below) in the pack caption font. Sizes fit each half to ONE
    # line in the safe width; the quiet line steps down by the pack's caption:headline ratio.
    import hooksplit as HS
    # The auto-splitter balances by LENGTH, which can break a phrase mid-thought
    # ("for the mom who feels / like she doesn't fit"). A plan may state the two halves itself so the
    # break lands on meaning. Falls back to the splitter when not given.
    _halves = CP.get("hook_halves")
    if _halves and len(_halves) == 2:
        fst, snd = str(_halves[0]).strip(), str(_halves[1]).strip()
    else:
        fst, snd = HS.split_hook(HOOK_LONG)
    head_text = snd if HOOK_EMPH == "second" else fst
    eye_text = fst if HOOK_EMPH == "second" else snd
    # eyebrow font = the pack's chosen subhead source (caption by default; some packs use their accent font,
    # e.g. Editorial -> Prosecco). One pack field, both engines read it.
    SUB = dict(stylepack.element(PACK, pack.get("subhead_source", "caption")))
    if pack.get("subhead_font_file"):                     # pack can point the subhead at any font (e.g. Ugly Dave)
        # found like any pack face (bundled file, then by name in her CapCut, then the pack's stand-in for it)
        SUB["file"], SUB["font"] = HS.pinned_font(PACK, "subhead_font_file", "subhead_font_name", "Subhead")
    fSUB = face(SUB)
    # emphasis half = BIG headline. PREFER ONE LINE (you: a short phrase like "before it starts" shouldn't wrap
    # to 2 lines just to grow — it fits). Try one line at the wider top-anchored hook width; keep it unless that
    # forces the size below a readable-hook floor, then fall back to a balanced 2 lines (no orphan words).
    _HEAD_ONE_MIN = float(WD.get("head_one_min", 100))
    Sh, head_lines = fit_headline(caseit(head_text, H), H, round(HOOK_MAXH * HL_MAXH_MULT), maxw=HOOK_MAXW, lh=HOOK_LH, max_lines=1)
    if len(head_lines) > 1 or Sh < _HEAD_ONE_MIN:
        Sh, head_lines = fit_headline(caseit(head_text, H), H, round(HOOK_MAXH * HL_MAXH_MULT), maxw=HOOK_MAXW, lh=HOOK_LH, max_lines=2)
    # eyebrow reads as ONE line (impeccable: a supporting line shouldn't stack). It starts at its intended
    # pack size and, only if that would wrap, SHRINKS within a range to fit one line full-width — so packs whose
    # eyebrow already fits one line are untouched, and long/wide-font eyebrows (Prosecco, Opera Cake) size down
    # to sit on one line. Layout wins over an exact number.
    eye_cap = max(18, round(Sh * C["size"] * 0.92 / max(H["size"], 1) * EYE_MULT))
    EYE_MIN, EYE_COMFORT = 30, 40                                                 # floor + the size below which ONE line reads too small
    Sq, eye_lines = fit_headline(caseit(eye_text, H), SUB, HOOK_MAXH, lh=HOOK_LH, start=eye_cap, floor=EYE_MIN, max_lines=1)
    import hooksplit as _HSeye
    one_ok = len(eye_lines) == 1 and _HSeye._measure(eye_lines[0], _fontpath(SUB), Sq) <= SAFE_W and Sq >= EYE_COMFORT
    if not one_ok and len(caseit(eye_text, H).split()) > 1:
        # one line would be too small (or overflow) -> FORCE a balanced 2 lines (reads bigger). Note: a plain
        # max_lines=2 still prefers ONE line when it fits, so we pick the largest size whose balanced 2-line fits
        # the width. Creator's rule: prioritize one line, but two is fine when it doesn't fit; balanced, no orphan.
        _w = caseit(eye_text, H).split(); _fp = _fontpath(SUB); Sq, eye_lines = 18, [caseit(eye_text, H)]
        _ceil = max(eye_cap, round(Sh * 0.6))    # 2 lines carry less width pressure, so they can be BIGGER than the
        for _s in range(int(_ceil), 17, -2):     # cramped one-line ceiling — capped below the headline for hierarchy
            _b = _HSeye._balanced(_w, _fp, _s, 2)
            if _b and _b[0] <= SAFE_W:
                Sq, eye_lines = _s, _b[1]; break
    HOOK_PX = Sh                    # the emphasis headline is the anchor for the whole frame
    _trk = f"letter-spacing:{HL_TRACK}em;" if HL_TRACK is not None else ""
    def _block(lns, big):
        inner = "<br>".join(esc(l) for l in lns)
        if big:
            return f'<div class="hkhead" style="color:{HOOK_COLOR};{_HW}font-size:{Sh}px;{_trk}">{inner}</div>'
        return f'<div class="hkquiet" style="font-family:{fSUB};font-size:{Sq}px">{inner}</div>'
    head_block, eye_block = _block(head_lines, True), _block(eye_lines, False)
    lines = (eye_block + head_block) if HOOK_EMPH == "second" else (head_block + eye_block)   # reading order: 1st half on top
    clips.append(f'<div class="clip" id="clip-hooksplit" data-start="0" data-duration="{HOOK_SHOW:.2f}" data-track-index="2"><div id="hooksplit" data-layout-allow-overlap>{lines}</div></div>')
    tljs.append(text_effects.intro_sel("#hooksplit > div", HOOK_FX, 0.2, stagger=0.16))
    if not HOOK_PERSIST:
        tljs.append(f'tl.to("#hooksplit",{{autoAlpha:0,duration:0.4}},{HOOK_END-0.5:.2f});tl.set("#hooksplit",{{autoAlpha:0}},{HOOK_END-0.1:.2f});')
    else:
        tljs.extend(_hook_yield_js("#hooksplit"))
elif HOOK:
    # SINGLE headline (gold standard, same as the split): one string -> MEASURED balance to <=2 lines, no orphan,
    # sized big to fill the band, all in the accent color. Multiple fragments stay one-per-line (intentional).
    if len(HOOK) == 1:
        HOOKN, _hlines = fit_headline(caseit(HOOK[0], H), H, HOOK_MAXH, lh=HOOK_LH, max_lines=2)
        if abs(HOOK_SCALE - 1.0) > 1e-3:
            # punch/hush: scale the fitted anchor, then re-wrap to the FEWEST lines that keep every line inside
            # the safe width, and step DOWN if the taller stack would reach the face (the floor still wins).
            import hooksplit as _HSs
            _txt = caseit(HOOK[0], H); _fp = _fontpath(H); _words = _txt.split()
            _hcap = HOOK_MAXH * (1.35 if HOOK_SCALE > 1 else 1.0)   # punch may grow taller, never onto the face
            _size = max(20, round(HOOKN * HOOK_SCALE)); _pick = None
            while _size >= 20 and _pick is None:
                for _n in range(1, 5):
                    if _n == 1:
                        _w = _HSs._measure(_txt, _fp, _size); _b = (_w, [_txt]) if _w <= SAFE_W else None
                    else:
                        _b = _HSs._balanced(_words, _fp, _size, _n) if len(_words) >= _n else None
                    if _b and _b[0] <= SAFE_W:
                        if _size * _n * HOOK_LH <= _hcap:
                            _pick = (_size, _b[1])
                        break
                _size -= 2
            if _pick:
                if _pick[0] == HOOKN:
                    print(f"[type] hook_scale {HOOK_SCALE} left the hook at {HOOKN}px (no visible change).")
                HOOKN, _hlines = _pick
            else:
                # Nothing in the ladder fit, so the hook stays exactly as it was. Silently returning the
                # same size is what made a 23-minute re-render look like a broken feature: say it instead.
                print(f"[type] hook_scale {HOOK_SCALE} could not be applied — no size from "
                      f"{max(20, round(HOOKN * HOOK_SCALE))}px down fits the safe width and stays off "
                      f"the face. The hook stays {HOOKN}px; shorten it to change the size.")
        HOOK_PX = HOOKN
    else:
        _hlines = [caseit(t, H) for t in HOOK]
        if abs(HOOK_SCALE - 1.0) > 1e-3:
            # hook_scale ALSO applies to a multi-fragment hook. It used to be read only on the
            # single-headline path above, so on any hook with more than one fragment the value was
            # silently ignored: a PC tester spent 22.9 minutes on a re-render chain that produced a
            # byte-identical hook (measured, 214 px of ink before and after hook_scale 0.86) because
            # her hook had three fragments and this branch never looked at it. A silent no-op that
            # costs a full re-render is worse than an error.
            # Fragments stay one per line by design, so there is no re-wrap to do — just move the size
            # and step DOWN until every line clears the safe width and the stack stays off the face.
            import hooksplit as _HSm
            _fpm, _capm = _fontpath(H), HOOK_MAXH * (1.35 if HOOK_SCALE > 1 else 1.0)
            _szm = max(20, round(HOOKN * HOOK_SCALE))
            _wantm = _szm
            while _szm > 20 and (
                    max(_HSm._measure(_l, _fpm, _szm) for _l in _hlines) > SAFE_W
                    or _szm * len(_hlines) * HOOK_LH > _capm):
                _szm -= 2
            if _szm != _wantm:
                print(f"[type] hook_scale {HOOK_SCALE} asked for {_wantm}px; the safe width allows "
                      f"{_szm}px, so the hook is {_szm}px. Shorten a fragment to go bigger.")
            elif _szm == HOOKN:
                print(f"[type] hook_scale {HOOK_SCALE} left the hook at {HOOKN}px (no visible change).")
            HOOKN = _szm
        HOOK_PX = HOOKN
    # vibe typographic emphasis on ONE hook word: italic-accent (Editorial), solid+hollow pairing (Playful),
    # or a clean underline. Real type treatments, not drawn art.
    _ek = VIBE.get("kind") if VIBE.get("kind") in ("emphasis", "hollow", "underline", "marker_underline") else None
    _ew = norm(str(VIBE.get("word", "")))
    _munder_ids = []                                   # marker-underline path ids to WRITE ON (stroke-draw)
    _ugap = float(VIBE.get("underline_gap", 0.04))     # em below the word, tunable
    def _wrapword(line):
        if not _ek or not _ew:
            return esc(line)
        out = []
        for tok in line.split(" "):
            if norm(tok) == _ew:
                if _ek == "emphasis":
                    out.append(f'<span style="font-style:italic">{esc(tok)}</span>')
                elif _ek == "hollow":
                    out.append(f'<span style="color:transparent;-webkit-text-stroke:3px {ACCENT}">{esc(tok)}</span>')
                elif _ek == "marker_underline":
                    # hand-drawn WHITE marker underline anchored under the ACTUAL word — an SVG wavy stroke that
                    # WRITES ON (stroke-draw). Tight line-height clamps the wrapper to the caps so it sits close.
                    _mid = f"mu{len(_munder_ids)}"; _munder_ids.append(_mid)
                    _mk = (f'<span style="position:absolute;left:-2%;right:-2%;top:100%;margin-top:{_ugap}em;height:0.16em;overflow:visible">'
                           f'<svg width="100%" height="100%" viewBox="0 0 100 14" preserveAspectRatio="none">'
                           f'<path id="{_mid}" d="M2 9 Q25 3 50 8 T98 7" fill="none" stroke="#fff" stroke-width="2.6" '
                           f'stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/></svg></span>')
                    out.append(f'<span style="position:relative;display:inline-block;line-height:0.76">{esc(tok)}{_mk}</span>')
                else:  # clean underline
                    out.append(f'<span style="text-decoration:underline;text-decoration-color:{ACCENT};text-decoration-thickness:7px;text-underline-offset:10px">{esc(tok)}</span>')
            else:
                out.append(esc(tok))
        return " ".join(out)
    if VIBE.get("kind") == "arc":
        # word-on-an-arc (playful): render the hook as SVG text along a gentle upward curve.
        _atxt = esc(" ".join(_hlines)); _asz = round(HOOKN * float(VIBE.get("arc_scale", 0.92)))
        _arc = (f'<svg width="1080" height="540" viewBox="0 0 1080 540" style="position:absolute;left:0;top:{HOOK_TOP-60}px;overflow:visible">'
                f'<defs><path id="arcp" d="M 160 400 Q 540 150 920 400" fill="none"/></defs>'
                f"<text font-family='{fH}' font-size='{_asz}px' fill='{ACCENT}' text-anchor='middle'>"
                f'<textPath href="#arcp" startOffset="50%">{_atxt}</textPath></text></svg>')
        clips.append(f'<div class="clip" id="clip-hookarc" data-start="0" data-duration="{HOOK_SHOW:.2f}" data-track-index="2"><div id="hookarc" data-layout-allow-overlap>{_arc}</div></div>')
        # TRACE ON: reveal the arc text left-to-right along the curve
        tljs.append(f'tl.set("#hookarc",{{autoAlpha:1,clipPath:"inset(0 100% 0 0)"}},0);tl.to("#hookarc",{{clipPath:"inset(0 0% 0 0)",duration:0.6,ease:"power2.out"}},0.2);')
        if not HOOK_PERSIST:
            tljs.append(f'tl.to("#hookarc",{{autoAlpha:0,duration:0.4}},{HOOK_END-0.5:.2f});tl.set("#hookarc",{{autoAlpha:0}},{HOOK_END-0.1:.2f});')
        else:
            tljs.extend(_hook_yield_js("#hookarc"))
    else:
        lines = "".join(
            f'<span class="hkline" id="hk{k}" data-layout-allow-overlap style="color:{HOOK_COLOR};{_HW}">{_wrapword(l)}</span>'
            for k, l in enumerate(_hlines))
        clips.append(f'<div class="clip" id="clip-hookwrap" data-start="0" data-duration="{HOOK_SHOW:.2f}" data-track-index="2"><div id="hookwrap">{lines}</div></div>')
        for k in range(len(_hlines)):
            tljs.append(text_effects.intro_sel(f"#hk{k}", HOOK_FX, 0.2 + k * 0.42))
        for _mid in _munder_ids:                        # WRITE ON: draw the marker stroke left-to-right
            _wat = float(VIBE.get("at", 0.2 + len(_hlines) * 0.42 + 0.25))
            tljs.append(f'tl.set("#{_mid}",{{strokeDashoffset:1}},0);tl.to("#{_mid}",{{strokeDashoffset:0,duration:0.5,ease:"power1.inOut"}},{_wat:.2f});')
        if not HOOK_PERSIST:
            tljs.append(f'tl.to("#hookwrap",{{autoAlpha:0,duration:0.4}},{HOOK_END-0.5:.2f});tl.set("#hookwrap",{{autoAlpha:0}},{HOOK_END-0.1:.2f});')
        else:
            tljs.extend(_hook_yield_js("#hookwrap"))

# ---- TAKEOVER phrases (vertical word stack, held) ----
for (a, b) in spans:
    gid = f"tk{gi}"; gi += 1
    ws = WORDS[a:b+1]
    start = ws[0]["t"]; end = ws[-1]["e"] + TK_HOLD
    disp = [caseit(re.sub(chr(34), "", w["w"]).strip(".,!?"), TK) for w in ws]
    # MAX the takeover to the safe-zone width (MEASURED with the real font, not estimated): the longest word
    # fills SAFE_W; height (all words stacked) caps it if that binds first. TK_SCALE lets a pack fill a bit more/less.
    import hooksplit as _HStk
    _fptk = _fontpath(TK); _longw = max(disp, key=len) if disp else "x"; _tkmaxw = SAFE_W * TK_SCALE
    tksize = 640
    while tksize > 30 and (_HStk._measure(_longw, _fptk, tksize) > _tkmaxw or len(disp) * tksize * TK_LH > 1340):
        tksize -= 4
    kw = None
    for w in reversed(ws):
        if norm(w["w"]) in KEYWORDS: kw = id(w); break
    sp = []
    for n, w in enumerate(ws):
        wid = f"{gid}w{n}"
        cls = ' class="kw"' if id(w) == kw else ''
        _inner, _js = text_effects.render(wid, disp[n], TK_FX, w["t"], esc=esc)
        sp.append(f'<span id="{wid}"{cls}>{_inner}</span>')
        tljs.append(_js)
    # Its own lane (5), not the captions' (1): separating layers reads lanes, and a takeover filed under the
    # captions went out with the captions while the "takeover" layer held the breakaway card instead.
    clips.append(f'<div class="clip" id="clip-{gid}" data-start="{start:.2f}" data-duration="{end-start:.2f}" data-track-index="5"><div class="tkwrap" style="font-size:{tksize}px">{"".join(sp)}</div></div>')

# captions YIELD under a takeover: a full-screen takeover owns the screen, so no caption may bleed into its
# window. Clamp any caption clip's end to the next takeover's start (the takeover's own words are already
# consumed/skipped; this catches the hold-tail of the line right before it).
# A breakaway CARD dissolves in AND out over _BK_FADE (see the breakaway block). Captions must clear the WHOLE
# transition — the fade-in, the hold, AND the fade-out — or you see them revealing word-by-word THROUGH the
# translucent card and it reads like a glitch (2026-08-09). Guard the window by the fade on both sides so a
# caption never animates under a breakaway. (Takeovers are opaque instantly; they keep their tight window.)
_BK_FADE = 0.16
_BK_GUARD = _BK_FADE + 0.12
_bk_wins = [(float(_b.get("at", 0)) - _BK_GUARD, float(_b.get("out", float(_b.get("at", 0)) + 2.6)) + _BK_GUARD) for _b in CP.get("breakaways", [])]
_tk_wins = sorted([(WORDS[a]["t"], WORDS[b]["e"] + TK_HOLD) for (a, b) in spans] + _bk_wins)   # takeovers + full-screen breakaways both own the screen
_tk_wins = sorted(_tk_wins + CAP_SKIP)   # captions also stand aside for a caption_skip window
ACC_IDX = set()
for _a in _ACC_SPEC:
    if isinstance(_a, str):
        ACC_IDX.update(k for k, n in enumerate(nrm) if n == norm(_a))
        continue
    _aw, _at = norm(_a.get("w", "")), float(_a.get("t", -1))
    _hits = [k for k, n in enumerate(nrm) if n == _aw and abs(WORDS[k]["t"] - _at) <= 0.6]
    if _hits:
        ACC_IDX.add(min(_hits, key=lambda k: abs(WORDS[k]["t"] - _at)))
    else:
        print(f"  ⚠ accent word {_a.get('w')!r} near {_at:.2f}s matched nothing in the transcript, so it stays plain. "
              f"caption-plan.json may be stale vs the current cut.")
def _yield(s, e):
    for ts, te in _tk_wins:
        if ts <= s < te: s = te          # caption starts DURING a takeover -> wait until it fully clears (fixes the tail)
    for ts, te in _tk_wins:
        if s < ts < e: e = ts            # caption would bleed into a takeover's front -> end before it
    return s, e

# ---- CAPTIONS: per line — "single" = snap (no anim) · "build" = karaoke line-build (reveal + accent on the
# current word). Default is the global CAPTION_MODE; a /studio single|karaoke treatment overrides ONE line via
# word_mode[]. Non-consumed words are grouped into contiguous same-mode SEGMENTS, each rendered in its mode.
# With no overrides there is exactly one segment, so this reproduces the old global behavior verbatim.
# Captions normally size DOWN from the hook's ACTUAL rendered size, so a big hook card sets the hierarchy.
# But a PERSISTENT hook is CHROME, not a size reference: it has to be smaller (it holds the whole reel and
# usually wraps), and anchoring to it drags every caption down with it — measured 61px -> 43px on a Butter
# reel, a 30% shrink nobody asked for. When the hook persists, captions use the pack's own caption size.
anchor_scale = 1.0 if HOOK_PERSIST else (HOOK_PX / max(px(H), 1))
# FLOORED: a computed size can collapse silently (anchor drift, fit-to-band, width shrink). The old
# `max(20, ...)` was far below readable, so nothing caught it. Clamp to the legibility floor and SAY so.
_cap_raw = round(px(C) * anchor_scale * SINGLE_MULT)
_bld_raw = round(bpx * anchor_scale * BUILD_MULT)
# NEVER drift below the PACK'S OWN designed caption size (px(role) x the pack's single/build scale). The
# hook anchor may GROW captions with a big hook, but it must never SHRINK them below what the pack intended
# — that "it looked deliberate" drift is exactly what shipped 43px captions (and Ugly Dave, which reads
# small, needs the pack's 1.58 single_scale to land right). Floored at the HF in-feed baseline as the absolute.
# A caption size she has TAUGHT scales the pack's own designed size — it can make captions bigger, and it
# is still floored below by the pack's intent and the legibility baseline, so a taught preference can never
# reintroduce the shrink drift that shipped 43px captions.
import learned as _learned
_cap_scale = _learned.get("caption.size_scale", 1.0)
CAP_PX = max(safe_zones.MIN_PX["caption"], _cap_raw, round(px(C) * SINGLE_MULT * _cap_scale))
BLD_PX = max(safe_zones.MIN_PX["karaoke"], _bld_raw, round(bpx * BUILD_MULT * _cap_scale))
# Say WHICH of the three won, because two of the three are perfectly normal. The size is
# max(legibility floor, anchor-scaled, pack-designed): the pack's own size winning is the system
# working, not a rescue. The old line called every win "the legibility floor", so a pack size of 61
# beating an anchor of 43 printed as a warning about a floor of 58 that had not come into it at all —
# a correct outcome dressed as a defect, which is exactly what sends someone hunting a bug that is not
# there.
for _lbl, _raw, _fin, _floor, _pack in (("snap caption", _cap_raw, CAP_PX, safe_zones.MIN_PX["caption"],
                                         round(px(C) * SINGLE_MULT * _cap_scale)),
                                        ("karaoke caption", _bld_raw, BLD_PX, safe_zones.MIN_PX["karaoke"],
                                         round(bpx * BUILD_MULT * _cap_scale))):
    if _fin <= _raw:
        continue
    if _fin == _floor and _fin > _pack:
        print(f"  ⚠ {_lbl}: {_raw}px is under the {_floor}px legibility floor — raised to {_floor}px")
    else:
        print(f"  {_lbl}: using the pack's {_pack}px rather than the {_raw}px the anchor asked for")


# CATALOG CAPTION STYLE (opt-in, never a default): the plan names a HyperFrames catalog caption style
# ("catalog_captions": "Kinetic Slam") and it replaces the pack's captions on this lane. One sub-composition
# clip, words already cleared from every takeover/breakaway window, centred on the pack's caption height.
# See product/catalog_caption.py. A style that cannot be adapted stops the build and says why, rather than
# quietly handing back the pack's captions she did not ask for.
CAT_CAP = str(CP.get("catalog_captions") or "").strip()
if CAT_CAP:
    import catalog_caption as _catcap
    try:
        _cc_id, _cc_src, _cc_notes, _cc_half = _catcap.prepare(
            CAT_CAP, [w for k, w in enumerate(WORDS) if k not in consumed], OUT, duration=DUR,
            keywords=CP.get("keywords", []), windows=_tk_wins)
    except (LookupError, _catcap.Unsupported) as _e:
        sys.exit(f"  ⛔ catalog caption style '{CAT_CAP}': {_e}")
    clips.append(_catcap.clip_html(_cc_id, _cc_src, DUR, cap_top(0, round(ypx(C) - CAP_LIFT), half=_cc_half + CAP_LIFT)))   # big type ignores the per-reel lift toward her chin
    print(f"  captions: HyperFrames catalog style '{CAT_CAP}' ({_cc_id}) instead of the pack's"
          + "".join(f"\n    · {n}" for n in _cc_notes))

_DEF = CAPTION_MODE if CAPTION_MODE in ("build", "phrase", "spotlight") else "single"
_segs = []; _cur = []; _cm = None
for k, w in enumerate([] if CAT_CAP else WORDS):   # a catalog style already owns the captions lane
    if k in consumed:
        if _cur: _segs.append((_cm, _cur)); _cur = []; _cm = None
        continue
    m = word_mode[k] or _DEF
    if _cm is None: _cm = m
    if m != _cm:
        _segs.append((_cm, _cur)); _cur = []; _cm = m
    _cur.append((k, w))
if _cur: _segs.append((_cm, _cur))

_bci = 0
_PH = []   # phrase/spotlight captions, laid out after the loop (they need every window to measure her chin once)
# CLEAN HANDOFF at every caption STYLE SHIFT (karaoke <-> single): no clip may cross into the next segment, or the
# outgoing style's held tail overlaps the incoming style's first word (reads as overlapping/dropped words). Clamp
# each segment's last clip to the next segment's first-word time (minus a hair), so styles never stack.
_seg_starts = [seg[0][1]["t"] for (_m, seg) in _segs]
for _si, (_mode, _seg) in enumerate(_segs):
    _bnd = (_seg_starts[_si + 1] - 0.04) if _si + 1 < len(_segs) else 1e9
    if _mode in ("phrase", "spotlight") or (_mode == "single" and _DEF in ("phrase", "spotlight")):
        # a /studio single line inside a phrase-caption reel is a phrase of ONE word: same face, same baseline,
        # same chin lock as the phrases around it, instead of a differently placed snap caption
        _pmax = 1 if _mode == "single" else (SPOT_MAX if _mode == "spotlight" else PHRASE_MAX)
        _bnd = _seg_starts[_si + 1] if _si + 1 < len(_segs) else 1e9   # phrases hand straight off at a style shift too
        _mode = "phrase" if _mode == "single" else _mode
        chunks, cur = [], []
        for _n, (k, w) in enumerate(_seg):
            cur.append((k, w))
            _nx = _seg[_n + 1][1] if _n + 1 < len(_seg) else None
            _mid = lambda x: (x["t"] + x["e"]) / 2
            # one-word phrases: a word said too fast to read on its own (under 0.22s until the next word) pairs
            # with the next word instead of flashing by, so fast speech never shows as a flicker
            _tooquick = PAIR_QUICK and _pmax == 1 and _nx is not None and _nx["t"] - cur[0][1]["t"] < 0.22 and len(cur) < 2
            if (w["w"].strip().endswith((",", ".", "!", "?", ";", ":")) or (len(cur) >= _pmax and not _tooquick)
                    or (_nx is not None and _clip_of(_mid(_nx)) != _clip_of(_mid(w)))):
                chunks.append(cur); cur = []
        if cur: chunks.append(cur)
        for ci, ch in enumerate(chunks):
            gid = f"ph{_bci}"; _bci += 1
            c_start = ch[0][1]["t"]
            # hand STRAIGHT off to the next caption (no gap): even 30ms of nothing shows as a flicker between words
            c_end = chunks[ci+1][0][1]["t"] if ci+1 < len(chunks) else min(ch[-1][1]["e"] + 0.6, _bnd)
            c_end = min(c_end, ch[-1][1]["e"] + 1.2, _bnd)
            c_start, c_end = _yield(c_start, c_end)
            if c_end - c_start < 0.05: continue
            if c_start > ch[-1][1]["e"]: continue   # its words were all said under the other graphic: never pop back after it
            _PH.append(dict(gid=gid, mode=_mode, words=ch, start=c_start, end=c_end))
    elif _mode == "build":
        chunks, cur = [], []
        for (k, w) in _seg:
            cur.append(w)
            if w["w"].strip().endswith((".", "!", "?")) or len(cur) >= 4:
                chunks.append(cur); cur = []
        if cur: chunks.append(cur)
        for ci, ch in enumerate(chunks):
            gid = f"bd{_bci}"; _bci += 1; c_start = ch[0]["t"]
            c_end = chunks[ci+1][0]["t"] if ci+1 < len(chunks) else min(ch[-1]["e"] + 0.6, _bnd)
            c_start, c_end = _yield(c_start, c_end)      # clear a takeover on BOTH sides (front + held tail)
            if c_end - c_start < 0.05: continue          # fully under a takeover → drop it
            sp = []
            for j, w in enumerate(ch):
                wid = f"{gid}w{j}"; disp = caseit(re.sub(chr(34), "", w["w"]).strip(".,!?;:"), BLD)
                sp.append(f'<span id="{wid}">{esc(disp)} </span>')
                wt = max(w["t"], c_start)                # if the chunk was pushed past a takeover, don't reveal early
                nt = ch[j+1]["t"] if j+1 < len(ch) else None
                nt = max(nt, c_start) if nt is not None else None
                js = (f'tl.set("#{wid}",{{autoAlpha:0,color:"#fff"}},0);'
                      f'tl.to("#{wid}",{{autoAlpha:1,duration:0.08}},{wt:.2f});'
                      f'tl.set("#{wid}",{{color:"{ACCENT}"}},{wt:.2f});')
                if nt is not None: js += f'tl.set("#{wid}",{{color:"#fff"}},{nt:.2f});'
                tljs.append(js)
            _fr, _mo = cap_side(c_start)
            if _fr is not None:
                _lx = max(safe_zones.LEFT, min(max(CAP_SIDE_ANCHOR, _fr + CAP_SIDE_GAP), safe_zones.RIGHT - 160))
                _sty = f"left:{round(_lx)}px;right:{1080 - safe_zones.RIGHT}px;text-align:left;top:{round(_mo)}px"
            else:
                _sty = f"top:{cap_top(c_start, round(ypx(C) - CAP_LIFT), half=90)}px"
            clips.append(f'<div class="clip" id="clip-{gid}" data-start="{c_start:.2f}" data-duration="{c_end-c_start:.2f}" data-track-index="1"><div class="buildwrap" style="{_sty}">{"".join(sp)}</div></div>')
    else:
        for (k, w) in _seg:
            disp = caseit(re.sub(chr(34), "", w["w"]).strip(".,!?;:"), C)
            if not disp: continue
            start = w["t"]; nxt = WORDS[k+1]["t"] if k+1 < len(WORDS) else (w["e"] + 0.3)
            # hold until the next word, MINUS a 30ms guard so two adjacent clips never overlap after the
            # data-start/data-duration values are rounded to 2 decimals (0.01s rounding was tripping
            # hyperframes check's overlapping_clips_same_track). Imperceptible on an instant snap.
            end = min(nxt - 0.03, start + 1.5, _bnd)
            start, end = _yield(start, end)      # clear a takeover on BOTH sides (front + held tail)
            if end - start < 0.05: continue      # fully under a takeover → drop it
            wid = f"cw{k}"; cls = "capword kw" if norm(w["w"]) in KEYWORDS else "capword"
            _fr, _mo = cap_side(start)
            if _fr is not None:
                # a single word cannot wrap: keep it whole and inside the safe box, easing the gap if needed
                _ww = _HS_measure(disp, _fontpath(C), CAP_PX)
                _lx = max(CAP_SIDE_ANCHOR, _fr + CAP_SIDE_GAP)   # hold the gap; clear the face
                if _lx + _ww > safe_zones.RIGHT:                  # a long word eases in rather than shrinking
                    _lx = max(safe_zones.LEFT, safe_zones.RIGHT - _ww)
                _sty = f"left:{round(_lx)}px;right:auto;text-align:left;top:{round(_mo)}px"
            else:
                _sty = f"top:{cap_top(start, round(ypx(C) - CAP_LIFT), half=45)}px"
            clips.append(f'<div class="clip" id="clip-{wid}" data-start="{start:.2f}" data-duration="{end-start:.2f}" data-track-index="1"><div class="{cls}" style="{_sty}"><span id="{wid}">{esc(disp)}</span></div></div>')
            # NO ANIMATION on snap captions (locked): instant on, instant off at the next — no fade/pop.
            tljs.append(f'tl.set("#{wid}",{{autoAlpha:0}},0);tl.set("#{wid}",{{autoAlpha:1}},{start:.2f});tl.set("#{wid}",{{autoAlpha:0}},{end:.2f});')

# ---- PHRASE / SPOTLIGHT layout. Each word sits in its own box on ONE shared baseline, so a word in the keyword
# face (bigger, a different font) lines up with its neighbours, and "N px under her chin" can be measured to the
# TOP OF THE INK rather than to a CSS box: the tallest letter in the phrase, in whichever face it can appear in
# (a spotlight word can flip to the keyword face, so its keyword ink counts too).
if _PH:
    from PIL import ImageFont as _IF
    _fpC, _fpK = _fontpath(C), KW["file"]
    def _fm(fp, size):
        f = _IF.truetype(fp, max(8, int(size))); a, d = f.getmetrics(); return f, a / size, d / size
    def _ink(f, txt):
        return -f.getbbox(txt, anchor="ls")[1] if txt.strip() else 0
    _ls = float(SINGLE_LS or 0)
    _fits = {}
    for P in _PH:
        disp = [caseit(re.sub(chr(34), "", w["w"]), C) for (k, w) in P["words"]]
        F = CAP_PX if P["mode"] == "phrase" else max(safe_zones.MIN_PX["karaoke"], round(px(C) * BUILD_MULT * _cap_scale))
        while True:
            KF = round(F * KW_SCALE)
            fC_, aC, dC = _fm(_fpC, F); fK_, aK, dK = _fm(_fpK, KF)
            acc = [P["mode"] == "phrase" and k in ACC_IDX for (k, w) in P["words"]]
            wid = [(fK_ if a_ else fC_).getlength(t) + _ls * (KF if a_ else F) * len(t) for t, a_ in zip(disp, acc)]
            gap = round(0.26 * F)
            if sum(wid) + gap * (len(wid) - 1) <= 1080 - 2 * safe_zones.LEFT or F <= safe_zones.MIN_PX["caption"]:
                break
            F -= 2                                   # a long phrase steps down to fit, never below the floor
        B = round(0.34 * F); HR = round(2.0 * F)     # shared baseline B px above the box bottom
        # ONE baseline per size, whatever the word: measured to the tallest letter either face can draw, so
        # consecutive captions ("we" / "learned") never step up and down, and a word that switches to the keyword
        # face keeps the same clearance under her chin.
        _REF = "bdfhklt"
        inkC = _ink(fC_, _REF)
        inkK = _ink(fK_, _REF) if (any(acc) or P["mode"] == "spotlight" or ACC_IDX) else 0
        P.update(disp=disp, acc=acc, wid=wid, F=F, KF=KF, gap=gap, B=B, HR=HR, ink=max(inkC, inkK),
                 botC=round(B - F * (1 - aC + dC) / 2), botK=round(B - KF * (1 - aK + dK) / 2))
    _locks = [None] * len(_PH)
    if CHIN_LOCK:
        import subprocess, tempfile
        _vid = f"{JOB_DIR}/outputs/{JOB_NAME}.mp4"
        with tempfile.TemporaryDirectory() as _td:
            # WHERE each caption is measured. Following her frame by frame reads as bouncing when she shifts in
            # her seat, so by default a caption holds ONE spot per SHOT: under the lowest her chin gets in that
            # shot. Only the modes named in "follow" (e.g. ["spotlight"] for a karaoke line where she stands
            # up or sits down) track her through their own window.
            _follow = set(CHIN_LOCK.get("follow", ["phrase", "spotlight"]))
            _edges = [0.0] + CUT_TIMES + [DUR]
            def _shot(t):
                i = _clip_of(t); return (_edges[i], _edges[i + 1])
            _fixed = CHIN_LOCK.get("others") == "fixed"   # every non-follow caption in ONE spot (her call: she moves them in CapCut)
            _wins = [[P["start"], P["end"]] if P["mode"] in _follow else (None if _fixed else list(_shot(P["start"])))
                     for P in _PH]
            _uniq = sorted({tuple(w_) for w_ in _wins if w_})          # a shot is measured once, however many words it holds
            json.dump([list(w_) for w_ in _uniq], open(f"{_td}/w.json", "w", encoding="utf-8"))
            _r = subprocess.run(["uv", "run", "-q", f"{ROOT}/product/chin_lock.py", _vid, "--windows", f"{_td}/w.json",
                                 "--offset", str(int(CHIN_LOCK.get("offset", 40))), "--json", f"{_td}/k.json"],
                                capture_output=True, text=True)
            if _r.returncode == 0:
                _byw = dict(zip(_uniq, json.load(open(f"{_td}/k.json", encoding="utf-8"))))
                _locks = [json.loads(json.dumps(_byw[tuple(w_)])) if w_ else None for w_ in _wins]   # each phrase its own copy
                for P, L in zip(_PH, _locks):   # held captions: one spot for the shot, clear of her lowest chin
                    if L and P["mode"] not in _follow:
                        L["mode"], L["keys"] = "hold", [max(L["keys"], key=lambda k_: k_["y"])]
                _nf = sum(1 for x in _locks if x and x["mode"] == "follow")
                _nh = sum(1 for x in _locks if x and x["mode"] == "hold")
                _nx = sum(1 for w_ in _wins if not w_)
                print(f"  captions: chin lock, {int(CHIN_LOCK.get('offset', 40))}px under her chin: {_nh} held in place "
                      f"for their shot, {_nf} following her" + (f", {_nx} in one fixed spot" if _nx else "")
                      + (f", {len(_locks) - _nf - _nh - _nx} with no face found" if len(_locks) - _nf - _nh - _nx else ""))
            else:
                print(f"  ⚠ chin lock could not run, so captions use the usual caption height instead:\n"
                      f"    {(_r.stderr or _r.stdout).strip()[-400:]}")
    _lowest = safe_zones.BOTTOM
    for P, L in zip(_PH, _locks):
        gid, F, KF = P["gid"], P["F"], P["KF"]
        up = P["HR"] - P["B"] - P["ink"]             # CSS top = ink top - up
        base_ink = (FIXED_Y if FIXED_Y is not None else cap_top(P["start"], round(ypx(C) - CAP_LIFT), half=45)) - P["ink"] / 2
        maxtop = _lowest - P["HR"] + P["B"] - round(0.25 * F)   # descenders stay above the bottom band
        def _top(ink_y):
            return round(min(ink_y - up, maxtop))
        boxes = []
        for n, (t, a_, w_) in enumerate(zip(P["disp"], P["acc"], P["wid"])):
            wid = f"{gid}w{n}"
            if P["mode"] == "spotlight":
                boxes.append(f'<span class="pw" id="{wid}" style="width:{round(w_)}px">'
                             f'<span class="ph-h" style="bottom:{P["botC"]}px">{esc(t)}</span>'
                             f'<span class="ph-s" style="bottom:{P["botK"]}px;font-size:{KF}px">{esc(t)}</span></span>')
            elif a_:
                boxes.append(f'<span class="pw" id="{wid}" style="width:{round(w_)}px"><span class="ph-k" '
                             f'style="bottom:{P["botK"]}px;font-size:{KF}px">{esc(t)}</span></span>')
            else:
                boxes.append(f'<span class="pw" id="{wid}" style="width:{round(w_)}px"><span class="ph-h" '
                             f'style="bottom:{P["botC"]}px">{esc(t)}</span></span>')
        first = _top(L["keys"][0]["y"]) if L else _top(base_ink)
        P["start"], P["end"] = round(P["start"], 2), round(P["end"], 2)   # abutting captions abut to the frame
        clips.append(f'<div class="clip" id="clip-{gid}" data-start="{P["start"]:.2f}" data-duration="{P["end"]-P["start"]:.2f}" '
                     f'data-track-index="1"><div class="phrase" id="{gid}" style="top:{first}px;height:{P["HR"]}px;'
                     f'gap:{P["gap"]}px;font-size:{F}px" data-layout-allow-overlap>{"".join(boxes)}</div></div>')
        js = ""
        if P["mode"] == "spotlight":   # the whole phrase eases on; the word being said cross-fades into the keyword face
            js += (f'tl.fromTo("#{gid}",{{opacity:0}},{{opacity:1,duration:.12,ease:"power1.out",immediateRender:true}},{P["start"]:.2f});')
            for n, (k, w) in enumerate(P["words"]):
                t0 = max(w["t"], P["start"]); t1 = P["words"][n+1][1]["t"] if n + 1 < len(P["words"]) else P["end"] - 0.02
                sel = f"#{gid}w{n}"
                # a CLEAN swap, never a cross-fade: words are said in ~0.15s, so a 0.1s dissolve leaves both faces
                # half-visible for most of every word and it reads as a glitch. One face at a time, same frame;
                # only a tiny settle in size on the keyword face.
                js += (f'tl.set("{sel} .ph-h",{{opacity:0}},{t0:.3f});'
                       f'tl.set("{sel} .ph-s",{{opacity:1}},{t0:.3f});'
                       f'tl.fromTo("{sel} .ph-s",{{scale:.96}},{{scale:1,duration:.08,ease:"power2.out",immediateRender:false}},{t0:.3f});'
                       f'tl.set("{sel} .ph-s",{{opacity:0}},{t1:.3f});'
                       f'tl.set("{sel} .ph-h",{{opacity:1}},{t1:.3f});')
        else:                          # NO ANIMATION on phrase captions (locked, like snap): on, then off
            js += f'tl.set("#{gid}",{{autoAlpha:0}},0);tl.set("#{gid}",{{autoAlpha:1}},{P["start"]:.2f});'
        js += f'tl.set("#{gid}",{{autoAlpha:0}},{P["end"]:.2f});'
        if L and L["mode"] == "follow":
            js += "".join(f'tl.set("#{gid}",{{top:{_top(k_["y"])}}},{k_["t"]:.3f});' for k_ in L["keys"][1:]
                          if P["start"] < k_["t"] < P["end"])
        tljs.append(js)

# optional preview background (a still of the footage) — ONLY for browser-verifying position vs. the face.
# The real transparent render leaves it empty (PREVIEW_BG unset) so nothing bakes into the overlay.
# The hook is the anchor: when fit_hook shrank it to fit, shrink the captions by the SAME factor so the pack
# ratio holds and the HEADLINE IS ALWAYS THE LOUDEST THING (never smaller than a caption). anchor_scale <= 1.
# ---- vibe: the delight pass. ONE touch per earned beat, from a palette of REAL elements (never generated art;
# her doodles/gifs are supplied, not faked). CP "vibe": {"kind": ..., ...}. Kinds rendered here:
#   emoji      one real emoji pop            {"kind":"emoji","emoji":"❤️","x","y","size","at"}
#   sparkles   a cluster of a real glyph     {"kind":"sparkles","glyph":"✨","x","y","size","at"}   (✦ diamond for Editorial)
#   bubble     an iMessage-style aside       {"kind":"bubble","text":"me: 🥹","x","y","at"}
# Decoration MAY sit outside the safe zone (only meaning-bearing text is bound), never on the face or the words.
# The typographic emphasis kinds (italic-accent word, solid+hollow pairing) are applied in the HOOK block above
# via VIBE_EMPH. Her-asset kinds (daisy doodle, marker underline, gif) await her pack — not generated here.
VIBE = CP.get("vibe") or {}
_vibe_css = ""
if VIBE.get("kind") in ("emoji", "sparkles", "bubble", "daisy", "marker_sparkle") or VIBE.get("emoji"):
    _kind = VIBE.get("kind") or "emoji"
    _at = float(VIBE.get("at", 0.85))
    _vdur = max(HOOK_END, _at + 3.0)     # a vibe cued after hook_end still gets its moment (never a silent no-show)
    if VIBE.get("out") is not None:      # optional: the plan says when it leaves (e.g. before a breakaway that follows)
        _vdur = max(_at + 0.8, float(VIBE["out"]))
    _vx = round(1080 * float(VIBE.get("x", 0.5))); _vy = round(1920 * float(VIBE.get("y", 0.245)))
    if _kind == "sparkles":
        _g = esc(VIBE.get("glyph", "✨")); _sz = int(VIBE.get("size", 54))
        _pts = [(0, 0, 1.0), (round(_sz * 0.95), round(_sz * 0.55), 0.72), (round(-_sz * 0.5), round(_sz * 0.8), 0.6)]
        _spans = []
        for _i, (_dx, _dy, _s) in enumerate(_pts):
            _vibe_css += f"#vibeS{_i}{{position:absolute;left:{_vx+_dx}px;top:{_vy+_dy}px;font-size:{round(_sz*_s)}px;transform:translate(-50%,-50%);}}"
            _spans.append(f'<div id="vibeS{_i}">{_g}</div>')
            _t0 = _at + _i * 0.12                       # TWINKLE ON: overshoot then settle, staggered
            tljs.append(f'tl.set("#vibeS{_i}",{{autoAlpha:0,scale:0,rotation:-40}},0);'
                        f'tl.to("#vibeS{_i}",{{autoAlpha:1,scale:1.25,rotation:0,duration:0.22,ease:"power2.out"}},{_t0:.2f});'
                        f'tl.to("#vibeS{_i}",{{scale:1,duration:0.22,ease:"power2.inOut"}},{_t0+0.22:.2f});')
        clips.append(f'<div class="clip" id="clip-vibe" data-start="0" data-duration="{_vdur:.2f}" data-track-index="3">{"".join(_spans)}</div>')
    elif _kind == "bubble":
        _txt = esc(VIBE.get("text", "me: 🥹"))
        # real iMessage SENT bubble: blue gradient, white text, rounded, tail on the bottom-right
        _vibe_css += (f"#vibeB{{position:absolute;left:{_vx}px;top:{_vy}px;"   # centred by GSAP xPercent/yPercent below:
                      # a CSS translate here is overwritten by the scale tween and fails `hyperframes check`
                      f"background:linear-gradient(180deg,#25B4FF 0%,#0A84FF 100%);color:#fff;"
                      f"font-family:Helvetica,Arial,sans-serif;font-weight:500;font-size:40px;letter-spacing:-0.01em;"
                      f"padding:18px 32px;border-radius:34px;white-space:nowrap;box-shadow:0 8px 22px rgba(0,0,0,.28);}}"
                      f"#vibeB::after{{content:'';position:absolute;bottom:2px;right:-8px;width:0;height:0;"
                      f"border:13px solid transparent;border-left-color:#0A84FF;border-bottom:0;}}")
        clips.append(f'<div class="clip" id="clip-vibe" data-start="0" data-duration="{_vdur:.2f}" data-track-index="3"><div id="vibeB">{_txt}</div></div>')
        tljs.append(f'tl.fromTo("#vibeB",{{xPercent:-50,yPercent:-50,autoAlpha:0,scale:0.6,y:18}},{{xPercent:-50,yPercent:-50,autoAlpha:1,scale:1,y:0,duration:0.45,ease:"back.out(2)"}},{_at:.2f});')
    elif _kind == "daisy":
        _sz = int(VIBE.get("size", 130)); _dc = VIBE.get("color", "#ffffff")   # doodles default WHITE
        _petals = "".join(f'<ellipse id="pt{_i}" cx="50" cy="24" rx="11" ry="20" transform="rotate({_a} 50 50)" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>' for _i, _a in enumerate(range(0, 360, 60)))
        _svg = (f'<svg width="{_sz}" height="{_sz}" viewBox="0 0 100 100" style="overflow:visible">'
                f'<g fill="none" stroke="{_dc}" stroke-width="5" stroke-linecap="round">{_petals}'
                f'<circle id="pctr" cx="50" cy="50" r="8" fill="{_dc}" stroke="none"/></g></svg>')
        _vibe_css += f"#vibeD{{position:absolute;left:{_vx}px;top:{_vy}px;transform:translate(-50%,-50%);}}"
        clips.append(f'<div class="clip" id="clip-vibe" data-start="0" data-duration="{_vdur:.2f}" data-track-index="3"><div id="vibeD">{_svg}</div></div>')
        # DRAW ON: each petal strokes on, staggered, then the center pops — hand-drawn feel, not a hard pop
        for _i in range(6):
            tljs.append(f'tl.to("#pt{_i}",{{strokeDashoffset:0,duration:0.26,ease:"power1.inOut"}},{_at + _i*0.07:.2f});')
        tljs.append(f'tl.set("#pctr",{{scale:0,transformOrigin:"50% 50%"}},0);tl.to("#pctr",{{scale:1,duration:0.3,ease:"back.out(3)"}},{_at + 6*0.07:.2f});')
    elif _kind == "marker_sparkle":
        _sz = int(VIBE.get("size", 96)); _kc = VIBE.get("color", "#ffffff")   # doodles default WHITE
        _star = f'<path d="M50 3 C57 38 62 43 97 50 C62 57 57 62 50 97 C43 62 38 57 3 50 C38 43 43 38 50 3 Z" fill="{_kc}"/>'
        _pts = [(0, 0, 1.0), (round(_sz * 0.85), round(_sz * 0.6), 0.55)]
        _spans = []
        for _i, (_dx, _dy, _s) in enumerate(_pts):
            _d = round(_sz * _s)
            _vibe_css += f"#vibeK{_i}{{position:absolute;left:{_vx+_dx}px;top:{_vy+_dy}px;transform:translate(-50%,-50%);}}"
            _spans.append(f'<div id="vibeK{_i}"><svg width="{_d}" height="{_d}" viewBox="0 0 100 100">{_star}</svg></div>')
            _t0 = _at + _i * 0.14                       # TWINKLE ON: overshoot then settle
            tljs.append(f'tl.set("#vibeK{_i}",{{autoAlpha:0,scale:0,rotation:-40}},0);'
                        f'tl.to("#vibeK{_i}",{{autoAlpha:1,scale:1.2,rotation:0,duration:0.22,ease:"power2.out"}},{_t0:.2f});'
                        f'tl.to("#vibeK{_i}",{{scale:1,duration:0.24,ease:"power2.inOut"}},{_t0+0.22:.2f});')
        clips.append(f'<div class="clip" id="clip-vibe" data-start="0" data-duration="{_vdur:.2f}" data-track-index="3">{"".join(_spans)}</div>')
    else:
        _sz = int(VIBE.get("size", 78))
        _vibe_css += f"#vibeE{{position:absolute;left:{_vx}px;top:{_vy}px;font-size:{_sz}px;line-height:1;transform:translate(-50%,-50%);}}"
        clips.append(f'<div class="clip" id="clip-vibe" data-start="0" data-duration="{_vdur:.2f}" data-track-index="3"><div id="vibeE">{esc(VIBE.get("emoji","✨"))}</div></div>')
        tljs.append(f'tl.set("#vibeE",{{autoAlpha:0,scale:0.4,rotation:-10}},0);tl.to("#vibeE",{{autoAlpha:1,scale:1,rotation:0,duration:0.5,ease:"back.out(2)"}},{_at:.2f});')

# ---- element library: pack-parameterized decorative shapes placed by the plan (the "soft touches" in vibe +
# medium + well-done, across every pack). Kinds: star (hand-drawn puffy), block (square-behind-text), rule (thin
# mark). Colors resolve via the LOCKED pack palette (accent/muted/pop2/dark/light, or a raw #hex). Additive +
# BACKWARD-SAFE: no CP["elements"] -> nothing renders, default output byte-identical. Grain + full color grounds
# live in the full-frame generator (Hands-Off / Animation), not this transparent over-footage overlay.
for _ei, _el in enumerate(CP.get("elements", [])):
    _ekind = _el.get("kind"); _ecol = resolve_color(PACK, _el.get("color", "accent"), ACCENT)
    _eat = float(_el.get("at", 0.4)); _edur = float(_el.get("duration", HOOK_END))
    if _edur <= _eat:                        # written the natural way ("appear at 6.5, stay 3s") — honor it
        _edur = _eat + max(float(_el.get("duration", HOOK_END)), 0.5)
        print(f"  ↻ element {_ei} ({_el.get('kind')}): 'duration' read as on-screen length, it holds until {_edur:.2f}s")
    _ex = round(1080 * float(_el.get("x", 0.5))); _ey = round(1920 * float(_el.get("y", 0.5)))
    _etrk = 7 + _ei     # its OWN lane: lanes are an overlap rule + a Studio display row, not z-order (z = DOM order,
                        # so elements draw above captions and below the label/breakaway). `front` is accepted but a no-op.
    _eid = f"el{_ei}"
    if _ekind == "star":                     # puffy 6-point hand-drawn star, pops on (Vintage discarded)
        _es = round(1080 * float(_el.get("size", 0.09))); _erot = float(_el.get("rotate", 0))
        _esvg = (f'<svg width="{_es}" height="{_es}" viewBox="0 0 100 100" style="overflow:visible">'
                 f'<polygon points="50,3 61,33 93,26 70,50 93,74 61,67 50,97 39,67 7,74 30,50 7,26 39,33" '
                 f'fill="{_ecol}" stroke="{_ecol}" stroke-width="3" stroke-linejoin="round"/></svg>')
        _vibe_css += f"#{_eid}{{position:absolute;left:{_ex}px;top:{_ey}px;transform:translate(-50%,-50%) rotate({_erot}deg);}}"
        clips.append(f'<div class="clip" id="clip-{_eid}" data-start="0" data-duration="{_edur:.2f}" data-track-index="{_etrk}"><div id="{_eid}">{_esvg}</div></div>')
        tljs.append(f'tl.set("#{_eid}",{{autoAlpha:0,scale:0,transformOrigin:"50% 50%"}},0);tl.to("#{_eid}",{{autoAlpha:1,scale:1,duration:0.4,ease:"back.out(2.4)"}},{_eat:.2f});')
    elif _ekind == "block":                  # the "square/rectangle behind the text" she loves — grows in from left
        _ew = round(1080 * float(_el.get("w", 0.4))); _eh = round(1920 * float(_el.get("h", 0.1))); _erad = int(_el.get("radius", 0))
        _vibe_css += (f"#{_eid}{{position:absolute;left:{_ex}px;top:{_ey}px;width:{_ew}px;height:{_eh}px;"
                      f"transform:translate(-50%,-50%);background:{_ecol};border-radius:{_erad}px;}}")
        clips.append(f'<div class="clip" id="clip-{_eid}" data-start="0" data-duration="{_edur:.2f}" data-track-index="{_etrk}"><div id="{_eid}"></div></div>')
        tljs.append(f'tl.set("#{_eid}",{{autoAlpha:0,scaleX:0,transformOrigin:"50% 50%"}},0);tl.to("#{_eid}",{{autoAlpha:1,scaleX:1,duration:0.35,ease:"power3.out"}},{_eat:.2f});')
    elif _ekind == "counter":                # count-up card: a number ticks from `from` to `to`, label beneath
        _ew = round(1080 * float(_el.get("w", 0.63)))
        _from = float(_el.get("from", 0)); _to = float(_el.get("to", 100)); _cd = max(0.2, float(_el.get("count_duration", 1.6)))
        _grp = "true" if _el.get("group", True) else "false"; _dec = max(0, int(_el.get("decimals", 0)))
        _pre = esc(str(_el.get("prefix", ""))); _suf = esc(str(_el.get("suffix", ""))); _lbl = str(_el.get("label", "")).strip()
        _gbg = resolve_color(PACK, _el.get("ground", "light"), GROUNDS.get(PACK, GROUND))
        _nsz = max(90, int(_el.get("size", 140))); _lsz = max(26, int(_el.get("label_size", 40)))   # in-feed floors
        _ncol = resolve_color(PACK, _el.get("color", "dark"), INK); _lcol = resolve_color(PACK, _el.get("label_color", "dark"), INK)
        for _nm, _val, _pxs in (("number", _ncol, _nsz), ("label", _lcol, _lsz)):
            _fix, _chg = text_safe(PACK, _val, _gbg, _pxs)
            if _chg:
                print(f"  ↻ counter {_nm} {_val} on {_gbg} reads {contrast_ratio(_val, _gbg):.2f}:1, swapped to {_fix} so it stays legible")
                if _nm == "number": _ncol = _fix
                else: _lcol = _fix
        _fmt = (f'Number(v.toFixed({_dec})).toLocaleString("en-US",{{minimumFractionDigits:{_dec},maximumFractionDigits:{_dec}}})'
                if _dec else 'Math.round(v).toLocaleString("en-US")') if _grp == "true" else \
               (f'v.toFixed({_dec})' if _dec else 'String(Math.round(v))')
        # `line-height:1` holds the numeral tight, but a face whose box is taller than its em (Anton 1.51,
        # Playfair 1.34) spills that extra height PAST the line box, straight into the label underneath —
        # the fixed 14px gap was calibrated on a 1.00-box face. Push the label clear by the real overflow.
        _clgap = 14 if _TUNED else 14 + round(max(0.0, stylepack.font_box_ratio(H["file"]) - 1.0) / 2.0 * _nsz)
        _vibe_css += (f"#{_eid}{{position:absolute;left:{_ex}px;top:{_ey}px;width:{_ew}px;transform:translate(-50%,-50%);"
                      f"background:{_gbg};border-radius:28px;padding:34px 40px;text-align:center;opacity:0;visibility:hidden;"
                      f"box-shadow:0 14px 44px rgba(0,0,0,.26);}}"
                      f"#{_eid} .cn{{font-family:{fH};font-size:{_nsz}px;line-height:1;font-weight:800;letter-spacing:-0.02em;color:{_ncol};}}"
                      f"#{_eid} .cl{{font-family:{fC};font-size:{_lsz}px;line-height:1.2;margin-top:{_clgap}px;color:{_lcol};}}")
        _lblhtml = f'<div class="cl" id="{_eid}l">{esc(_lbl)}</div>' if _lbl else ""
        _init = (f"{_from:.{_dec}f}" if _dec else f"{int(round(_from)):,}") if _grp == "true" else (f"{_from:.{_dec}f}" if _dec else str(int(round(_from))))
        clips.append(f'<div class="clip" id="clip-{_eid}" data-start="0" data-duration="{_edur:.2f}" data-track-index="{_etrk}"><div id="{_eid}"><div class="cn" id="{_eid}n">{_pre}{_init}{_suf}</div>{_lblhtml}</div></div>')
        # seek-safe count: a GSAP proxy object tweened with onUpdate (HyperFrames' own count-up pattern), so a scrub to t
        # shows the value at t. CSS starts it hidden + fromTo brings it in (no frame-0 flash); a hard set kills it at exit.
        tljs.append(f'tl.fromTo("#{_eid}",{{autoAlpha:0,scale:0.92,y:18}},{{autoAlpha:1,scale:1,y:0,duration:0.45,ease:"back.out(1.6)",immediateRender:false}},{_eat:.2f});'
                    f'var o_{_eid}={{v:{_from}}};'
                    f'tl.to(o_{_eid},{{v:{_to},duration:{_cd:.2f},ease:"power2.out",immediateRender:false,onUpdate:function(){{var v=o_{_eid}.v;document.getElementById("{_eid}n").textContent="{_pre}"+({_fmt})+"{_suf}";}}}},{_eat + 0.1:.2f});'
                    f'tl.to("#{_eid}",{{autoAlpha:0,duration:0.3,ease:"power2.in",immediateRender:false}},{max(_edur - 0.35, _eat + 0.5):.2f});'
                    f'tl.set("#{_eid}",{{autoAlpha:0}},{max(_edur - 0.02, _eat + 0.52):.2f});')
    elif _ekind == "rule":                   # Editorial's refined thin mark — draws out from center
        _ew = round(1080 * float(_el.get("w", 0.2))); _eth = int(_el.get("thick", 3))
        _vibe_css += (f"#{_eid}{{position:absolute;left:{_ex}px;top:{_ey}px;width:{_ew}px;height:{_eth}px;"
                      f"transform:translate(-50%,-50%);background:{_ecol};}}")
        clips.append(f'<div class="clip" id="clip-{_eid}" data-start="0" data-duration="{_edur:.2f}" data-track-index="{_etrk}"><div id="{_eid}"></div></div>')
        tljs.append(f'tl.set("#{_eid}",{{scaleX:0,transformOrigin:"50% 50%"}},0);tl.to("#{_eid}",{{scaleX:1,duration:0.5,ease:"power2.out"}},{_eat:.2f});')
    else:
        # A kind this builder does not draw (a typo, or one invented while planning) used to be skipped without a
        # word, so the reel came out without it and nothing said so. Say it, by name, every time.
        print(f"  ⛔ element {_ei}: kind {_ekind!r} is not one this engine draws (star, block, counter, rule), so it "
              f"is NOT in this reel. Change its kind in caption-plan.json, or remove it.", file=sys.stderr)

# ---- PERSISTENT CATEGORY LABEL: the measured reach mechanic for a talking head. It names the unnamed thing
# (WHO + the condition) on screen for the WHOLE runtime, which is what frees the spoken opener to be a slow
# burn — the hook card fades at hook_end, this does not. Renders as the pack's kicker chip (block-behind-text)
# on its own track, top-anchored ABOVE the hook. Set hook_lift_px negative to push the hook down and clear it.
# Additive + BACKWARD-SAFE: no CP["persistent_label"] -> nothing renders, default output byte-identical.
_PLBL = str(CP.get("persistent_label", "") or "").strip()
if _PLBL:
    _pl = CP.get("persistent_label_style", {}) or {}
    _plel = stylepack.element(PACK, _pl.get("font_role", "caption"))   # clean workhorse: must stay legible small, over moving footage
    if _pl.get("font_file"):
        _plel = dict(_plel); _plel["file"] = stylepack._abs(_pl["font_file"]); _plel["font"] = _pl.get("font_name", "Label")
    _plfam = face(_plel)
    _plsz = int(_pl.get("size", 38))
    _plbg = resolve_color(PACK, _pl.get("bg", "dark"), "#212c1b")      # the block; ink/dark ground carries any footage
    _plfg = resolve_color(PACK, _pl.get("color", "light"), "#F2EDE4")  # cream on the dark block (contrast floor holds)
    _plfix, _plchg = text_safe(PACK, _plfg, _plbg, int(_pl.get("size", 38)))
    if _plchg:
        print(f"  ↻ persistent label {_plfg} on {_plbg} reads {contrast_ratio(_plfg, _plbg):.2f}:1, swapped to {_plfix} so it stays legible"); _plfg = _plfix
    _ply = None   # set below, once the padding is known: default = just inside the top safe band
    _plcase = _pl.get("case", "upper")
    _pltxt = _PLBL.upper() if _plcase == "upper" else (_PLBL.title() if _plcase == "title" else _PLBL.lower())
    _plpv, _plph = int(_pl.get("pad_y", 14)), int(_pl.get("pad_x", 30))
    _plat = float(_pl.get("at", 0.4))
    _plhalf = _plsz / 2 + _plpv
    _ply = int(_pl["y"]) if "y" in _pl else int(safe_zones.TOP + _plhalf + 6)   # chip fully inside the safe zone by default
    if HOOK_LIFT == 0 and not HOOK_PERSIST:
        # the label is "top-anchored ABOVE the hook": with no explicit hook_lift_px, seat the hook right under it
        HOOK_TOP = max(HOOK_TOP, int(_ply + _plhalf + 12))
    _vibe_css += (f"#plabel{{position:absolute;left:40px;right:40px;top:{_ply}px;transform:translateY(-50%);text-align:center;}}"
                  f"#plabel span{{display:inline-block;font-family:{_plfam};font-size:{_plsz}px;"
                  f"font-weight:{_pl.get('weight', 500)};letter-spacing:{_pl.get('tracking', 0.12)}em;"
                  f"line-height:1;white-space:nowrap;color:{_plfg};background:{_plbg};"
                  f"padding:{_plpv}px {_plph}px;border-radius:{int(_pl.get('radius', 4))}px;}}")
    clips.append(f'<div class="clip" id="clip-plabel" data-start="0" data-duration="{DUR:.2f}" data-track-index="4"><div id="plabel"><span>{esc(_pltxt)}</span></div></div>')
    tljs.append(f'tl.set("#plabel",{{autoAlpha:0}},0);tl.to("#plabel",{{autoAlpha:1,duration:0.5,ease:"power2.out"}},{_plat:.2f});')
    for _ts, _te in _bk_wins:   # a breakaway card owns the screen: the label steps out before it and back in after
        tljs.append(f'tl.to("#plabel",{{autoAlpha:0,duration:0.14}},{max(_ts,0):.2f});tl.to("#plabel",{{autoAlpha:1,duration:0.14}},{_te:.2f});')

# ---- motion-graphic BREAKAWAY: cut from her footage to a full-screen designed pack CARD (solid ground) mid-reel,
# then cut back. The opaque ground on the TOP track covers everything (footage + captions) during [at,out]; the
# fade-in/out reads as a clean cut-to-card / cut-back. Captions already yield (breakaway windows folded into
# _tk_wins). Her audio keeps running underneath. This is ultra vibe's "breaks away to a motion graphic" — and it
# works on any medium/well/hands-off reel via CP["breakaways"]. Colors resolve from the LOCKED pack palette.
# THEME layer = each pack's distinct card recipe (pack_palettes.CARD_THEME); BUILD layer = the shared motion +
# reveal logic below, IDENTICAL for every pack (2026-08-09: themes distinct, build consistent). Font ROLES
# resolve to the pack's already-loaded fonts, so the theme never names a font. NO fabricated brand — a monogram
# renders ONLY from a client-supplied logo (_bk["monogram"]/theme override), never invented to fill space.
_ROLE_FONT = {"headline": fH, "label": fC, "script": fTK, "kicker": fBLD}
for _bi, _bk in enumerate(CP.get("breakaways", [])):
    _th = dict(CARD_THEME.get(PACK, CARD_THEME["Editorial"]))
    _bat = float(_bk.get("at", 0.0)); _bout = float(_bk.get("out", _bat + 2.6)); _bid = f"bk{_bi}"
    _struct = _bk.get("structure", _th.get("structure", "editorial"))
    _bg   = resolve_color(PACK, _bk.get("ground", _th.get("ground", "light")), GROUNDS.get(PACK, GROUND))
    _bink = resolve_color(PACK, _bk.get("ink",    _th.get("ink", "dark")),  INK)
    _bacc = resolve_color(PACK, _bk.get("accent", _th.get("accent", "accent")), ACCENT)
    _bsz0 = int(int(_bk.get("size", 130)) * float(_th.get("head_scale", 1.0)))
    for _nm, _val in (("ink", _bink), ("emphasis accent", _bacc)):
        _fix, _chg = text_safe(PACK, _val, _bg, _bsz0)
        if _chg:
            print(f"  ↻ breakaway {_bi} {_nm} {_val} on {_bg} reads {contrast_ratio(_val, _bg):.2f}:1, swapped to {_fix} so it stays legible")
            if _nm == "ink": _bink = _fix
            else: _bacc = _fix
    _blines = _bk.get("lines") or [str(_bk.get("text", ""))]
    _bemph = norm(str(_bk.get("emphasis", "")))
    _bsz = int(int(_bk.get("size", 130)) * float(_th.get("head_scale", 1.0)))   # per-pack breakaway headline size mult
    _kick = str(_bk.get("kicker", "")).strip()         # a short design label (NOT brand); renders only if provided
    if _bk.get("kicker_font_file"):
        _kfont = face({"file": stylepack._abs(_bk["kicker_font_file"]), "font": "K", "size": 20})
    else:
        _kfont = _ROLE_FONT.get(_th.get("kicker_role", "label"), fC)
    _bhas_rule = bool(_bk.get("rule", _th.get("rule", False)))
    _emph_ital = bool(_th.get("emphasis_italic", False))   # Biennale: the one accent word goes ITALIC, not a new color
    def _emph_html(_ln, _col):
        out = []
        for _wd in _ln.split():
            _hit = _bemph and norm(_wd) == _bemph
            _st = (("color:" + _col + ";") if _hit and not _emph_ital else "") + ("font-style:italic;" if _hit and _emph_ital else "")
            out.append(f'<span style="{_st}">{esc(_wd)}</span>')
        return " ".join(out)

    _inner = ""; _reveal_ids = []      # (id, kind) so the shared animator knows how to bring each part in
    # kicker (shared across structures) — Editorial=Poppins upper muted · Playful=Ugly Dave rotated accent
    if _kick:
        _kcol = resolve_color(PACK, _bk.get("kicker_color", _th.get("kicker_color", "pop2" if _struct == "block" else "muted")), _bacc)
        _krot = "-3deg" if _struct == "block" else "0deg"
        _kcase = "none" if _struct == "block" else "uppercase"; _ktrk = "0.02em" if _struct == "block" else "0.2em"
        _kw2 = _th.get("kicker_weight"); _kwcss = f"font-weight:{_kw2};" if _kw2 else ""
        # kicker size: bigger on the block (Playful's Ugly Dave reads small at a given px vs a clean sans) so the
        # label never looks tiny next to the display type (2026-08-10, permanent).
        _ksz = max(48, round(_bsz * (0.48 if _struct == "block" else 0.40)))
        _kfix, _kchg = text_safe(PACK, _kcol, _bg, _ksz)
        if _kchg:
            print(f"  ↻ breakaway {_bi} kicker {_kcol} on {_bg} reads {contrast_ratio(_kcol, _bg):.2f}:1, swapped to {_kfix} so it stays legible"); _kcol = _kfix
        _vibe_css += (f"#{_bid} .bkk{{font-family:{_kfont};color:{_kcol};{_kwcss}font-size:{_ksz}px;"
                      f"text-transform:{_kcase};letter-spacing:{_ktrk};margin-bottom:{round(_bsz*0.28)}px;"
                      f"display:inline-block;transform:rotate({_krot});}}")
        _inner += f'<div class="bkk" id="{_bid}k">{esc(_kick)}</div>'
        _reveal_ids.append((f"{_bid}k", "kick" if _struct == "block" else "drop"))

    if _struct == "block":            # Playful: bordered candy-block + hard OFFSET shadow holding the display type
        _fill = resolve_color(PACK, _bk.get("block_fill", _th.get("block_fill", "accent")), _bacc)
        _bord = resolve_color(PACK, _th.get("block_border", "dark"), _bink)
        _shad = resolve_color(PACK, _th.get("block_shadow", "dark"), _bink)
        _rows = "".join(f'<div class="bkln">{_emph_html(_ln, _bink)}</div>' for _ln in _blines)
        # Soup Du Jour floats high in a box (big internal ascent) — seat it lower: top-heavy padding + tight
        # line-height that hugs the caps (2026-08-10, global rule for display type on a candy block).
        _vibe_css += (f"#{_bid} .bkblock{{display:inline-block;background:{_fill};border:9px solid {_bord};"
                      f"box-shadow:20px 20px 0 {_shad};padding:{round(_bsz*0.46)}px {round(_bsz*0.5)}px {round(_bsz*0.15)}px;}}"
                      f"#{_bid} .bkln{{font-family:{fH};color:{_bink};font-size:{_bsz}px;line-height:{'0.72' if _TUNED else format(max(0.72, _H_INK), '.3f')};}}")
        _inner += f'<div class="bkblock" id="{_bid}blk">{_rows}</div>'
        _reveal_ids.append((f"{_bid}blk", "slap"))     # the sticker-slap scale-in carries the whole block
    else:                             # Editorial · Butter: centered display type + hairline rule
        _htrk = _th.get("headline_tracking", "0")   # e.g. Butter/BlockFrame Inter-900 at -0.03em
        _htt = "uppercase" if _th.get("headline_case") == "upper" else "none"
        for _li, _ln in enumerate(_blines):
            _vibe_css += f"#{_bid} .bkl{_li}{{font-family:{fH};color:{_bink};font-size:{_bsz}px;line-height:{HEAD_LH_WD};letter-spacing:{_htrk};text-transform:{_htt};}}"
            _inner += f'<div class="bkl{_li}" id="{_bid}l{_li}">{_emph_html(_ln, _bacc)}</div>'
            _reveal_ids.append((f"{_bid}l{_li}", "rise"))
        if _bhas_rule:
            _rulecol = resolve_color(PACK, _bk.get("rule_color", _th.get("rule_color", "accent")), _bacc)
            _vibe_css += f"#{_bid} .bkrule{{width:150px;height:5px;background:{_rulecol};margin:{round(_bsz*0.34)}px auto 0;border-radius:3px;}}"
            _inner += f'<div class="bkrule" id="{_bid}rule"></div>'
            _reveal_ids.append((f"{_bid}rule", "wipe"))

    _vibe_css += (f"#{_bid}{{position:absolute;inset:0;background:{_bg};display:flex;flex-direction:column;"
                  f"align-items:center;justify-content:center;text-align:center;padding:0 84px;will-change:transform;}}")
    clips.append(f'<div class="clip" id="clip-{_bid}" data-start="{_bat:.2f}" data-duration="{max(_bout-_bat,0.1):.2f}" data-track-index="6"><div id="{_bid}">{_inner}</div></div>')

    # ── SHARED motion (build logic, identical every pack): the CARD dissolves in/out AND pushes in (scale 1.06->1)
    # the whole hold so it's never static; then each part reveals with the vocabulary its KIND names — a slap-in
    # block, a rising line, a dropping kicker, a wiping rule — all staggered with a back.out overshoot. Captions
    # already yield the whole window (_BK_GUARD). Ground scale>=1 on inset:0 never shows edge gaps.
    _bfade = _BK_FADE; _bhold = max(_bout - _bat, 0.1)
    tljs.append(f'tl.set("#{_bid}",{{autoAlpha:0}},0);'
                f'tl.to("#{_bid}",{{autoAlpha:1,duration:{_bfade},ease:"power2.inOut"}},{_bat:.2f});'
                f'tl.fromTo("#{_bid}",{{scale:1.06}},{{scale:1,duration:{_bhold:.2f},ease:"power1.out"}},{_bat:.2f});'
                f'tl.to("#{_bid}",{{autoAlpha:0,duration:{_bfade},ease:"power2.inOut"}},{max(_bout-_bfade,_bat):.2f});')
    _breveal = _bat + _bfade * 0.6
    _EASE = "back.out(1.7)"
    for _ri, (_rid, _kind) in enumerate(_reveal_ids):
        _t = _breveal + 0.12 + _ri * 0.14
        if _kind == "slap":
            tljs.append(f'tl.set("#{_rid}",{{autoAlpha:0,scale:0.66,rotation:-2,transformOrigin:"50% 50%"}},0);'
                        f'tl.to("#{_rid}",{{autoAlpha:1,scale:1,rotation:0,duration:0.55,ease:"back.out(2.2)"}},{_t:.2f});')
        elif _kind == "kick":
            tljs.append(f'tl.set("#{_rid}",{{autoAlpha:0,scale:0.6,rotation:-16,transformOrigin:"50% 50%"}},0);'
                        f'tl.to("#{_rid}",{{autoAlpha:1,scale:1,rotation:-3,duration:0.5,ease:"back.out(2)"}},{_t:.2f});')
        elif _kind == "drop":
            tljs.append(f'tl.set("#{_rid}",{{autoAlpha:0,y:-16}},0);'
                        f'tl.to("#{_rid}",{{autoAlpha:1,y:0,duration:0.42,ease:"power3.out"}},{_t:.2f});')
        elif _kind == "wipe":
            tljs.append(f'tl.set("#{_rid}",{{scaleX:0,transformOrigin:"50% 50%"}},0);'
                        f'tl.to("#{_rid}",{{scaleX:1,duration:0.45,ease:"power3.out"}},{_t:.2f});')
        else:  # rise
            tljs.append(f'tl.set("#{_rid}",{{autoAlpha:0,y:52,scale:0.8,transformOrigin:"50% 50%"}},0);'
                        f'tl.to("#{_rid}",{{autoAlpha:1,y:0,scale:1,duration:0.55,ease:"{_EASE}"}},{_t:.2f});')
    if _bemph:      # the emphasis line gets a late accent pop for punch (works on both structures)
        _emids = [rid for (rid, k) in _reveal_ids if k in ("rise", "slap")]
        for _rid in _emids:
            tljs.append(f'tl.to("#{_rid}",{{keyframes:[{{scale:1.07,duration:0.16,ease:"power2.out"}},{{scale:1,duration:0.22,ease:"power2.inOut"}}]}},{_breveal + 0.55 + len(_reveal_ids)*0.14:.2f});')

# behind mode: split the overlay so a subject cutout can sit BETWEEN the hook and the rest.
_HOOK_MARK = ('id="hookwrap"', 'id="hooksplit"', 'id="hookarc"')

# SEGMENTED LAYERS. "Can I have the captions on their own layer", "split the hook out", "give me the
# animations separately" is a normal request, not an upgrade she had to pick in advance (CLAUDE.md, NO
# ROUTE IS A DEAD END). Rendering LAYER=<group> gives ONE kind of element its own transparent .mov, and
# capcut_handoff.py --layer puts each of those on its OWN CapCut track — so she can move, retime or
# switch one off without dragging the others. Every emitter above already stamps data-track-index, so
# the groups are read off that rather than re-tagged: lane assignments are set where the clips are
# built (captions=1, hook=2, vibe=3, label=4, takeover=5 (the full-screen word stacks), breakaway=6 (the
# designed cards), elements 7+i via _etrk). product/layer_probe.py keeps the same map for the checkbox list.
# NOTE ON COST: each group currently renders across the WHOLE comp duration, because HyperFrames renders
# the composition, not the clip. So N groups costs roughly N renders. Trimming each layer to the span it
# is actually on screen (a 6-second hook rendering 6 seconds) is the obvious win and is NOT done here yet.
# Do not tell a creator it is cheap because it is span-clipped; it is not, today.
_GROUP_TRACKS = {"bg": (0,), "captions": (1,), "hook": (2,), "vibe": (3,),
                 "label": (4,), "takeover": (5,), "breakaway": (6,)}
_ELEMENTS_FROM = 7          # el0, el1, ... each own lane 7+i — see _etrk where elements are emitted
_TRACKRX = re.compile(r'data-track-index="(\d+)"')


def _clip_track(c):
    m = _TRACKRX.search(c)
    return int(m.group(1)) if m else -1


# SAME-TRACK OVERLAP CLAMP: data-start and data-duration are each rounded to 2 dp independently, so two clips
# that abut in real time can round into a 10 ms overlap that `hyperframes check` rightly rejects
# (overlapping_clips_same_track). One post-pass over the assembled clips, after every emitter above and any
# future one: on each track, a clip that runs into the next one is shortened to end where the next starts.
# It only ever shortens, never extends, and drops a clip left with no time at all.
_CLIPRX = re.compile(r'data-start="(\d+(?:\.\d+)?)" data-duration="(\d+(?:\.\d+)?)" data-track-index="(\d+)"')
# Captions (1) and takeovers (5) are clamped as ONE lane: a takeover owns the screen, so a caption may never
# be showing in the same instant, even for the 10 ms a rounding overlap would leave on two separate lanes.
_CLAMP_LANE = {"5": "1"}
_bytrack = {}
for _ci, _c in enumerate(clips):
    if 'id="clip-catcap"' in _c: continue   # one whole-reel clip; its words already clear every takeover
    _m = _CLIPRX.search(_c)
    if _m: _bytrack.setdefault(_CLAMP_LANE.get(_m.group(3), _m.group(3)), []).append((float(_m.group(1)), float(_m.group(2)), _ci))
_clamped = 0; _dropped = set()
for _trk, _lst in _bytrack.items():
    _lst.sort()
    for _j in range(len(_lst) - 1):
        _st, _du, _ci = _lst[_j]; _nst = _lst[_j + 1][0]
        if _st + _du > _nst + 1e-9:
            _ndu = round(_nst - _st, 2)
            if _ndu <= 0: _dropped.add(_ci); continue
            clips[_ci] = _CLIPRX.sub(lambda m: f'data-start="{m.group(1)}" data-duration="{_ndu:.2f}" data-track-index="{m.group(3)}"', clips[_ci], count=1)
            _clamped += 1
if _dropped:
    _gone = set()
    for _i in _dropped:
        _gone.update(re.findall(r'id="([^"]+)"', clips[_i]))
    clips = [c for i, c in enumerate(clips) if i not in _dropped]
    tljs = [j for j in tljs if not any(f'"#{g}"' in j for g in _gone)]
if _clamped or _dropped:
    print(f"  ✓ clamped {_clamped} same-track clip overlap(s)" + (f", dropped {len(_dropped)} zero-length" if _dropped else ""))

if LAYER == "hook":
    clips = [c for c in clips if any(m in c for m in _HOOK_MARK)]
elif LAYER == "front":
    clips = [c for c in clips if not any(m in c for m in _HOOK_MARK)]
elif LAYER != "all":
    _want = [g.strip() for g in LAYER.split(",") if g.strip()]
    _unknown = [g for g in _want if g != "elements" and g not in _GROUP_TRACKS]
    if _unknown:
        sys.exit(f"  ⛔ LAYER: I do not know the group(s) {', '.join(_unknown)}. Known groups: "
                 f"{', '.join(sorted(_GROUP_TRACKS))}, elements. (Also: hook, front, all.)")
    _wtracks = set()
    for _g in _want:
        _wtracks.update(_GROUP_TRACKS.get(_g, ()))
    _want_elements = "elements" in _want
    clips = [c for c in clips
             if _clip_track(c) in _wtracks or (_want_elements and _clip_track(c) >= _ELEMENTS_FROM)]
    if not clips:
        # An empty layer is not an error, it just means this reel has none of that kind. Say so and stop
        # rather than rendering a fully transparent .mov the creator would then have to notice is empty.
        sys.exit(3)

if LAYER != "all":
    # A layer build keeps only some of the clips, so every timeline line aimed at a clip it left out would
    # drive nothing. HyperFrames reports each as "GSAP target ... not found", reel_render.py refuses to render
    # a composition that has one, and a counter's number update would throw outright. Keep exactly the lines
    # whose targets are still on the page. A full build (LAYER=all) keeps everything, as before.
    _here = set(re.findall(r'id="([^"]+)"', "".join(clips)))
    def _aims_at(js):
        return set(re.findall(r'\(\s*"#([A-Za-z0-9_-]+)', js)) | set(re.findall(r'getElementById\("([^"]+)"\)', js))
    tljs = [j for j in tljs if _aims_at(j) <= _here]

_ph_css = (f""".phrase{{position:absolute;left:0;width:1080px;display:flex;justify-content:center;align-items:flex-end;}}
.pw{{position:relative;display:inline-block;height:100%;}}
.pw span{{position:absolute;text-align:center;white-space:nowrap;line-height:1;letter-spacing:{SINGLE_LS}em;text-shadow:{SHADOW or "0 3px 12px rgba(0,0,0,.6)"};}}
.ph-h{{left:0;right:0;font-family:{fC};font-weight:{SINGLE_WEIGHT};color:#fff;}}
.ph-k,.ph-s{{left:-50%;right:-50%;font-family:{fKW};font-weight:normal;color:{ACCENT};}}
.ph-s{{opacity:0;}}
""" if _PH else "")   # only a reel with phrase captions carries their styles, so every other build is unchanged
PREVIEW_BG = os.environ.get("PREVIEW_BG", "")
BG_CLIP = ""
if PREVIEW_BG and os.path.exists(PREVIEW_BG):
    shutil.copy(PREVIEW_BG, f"{OUT}/_bg.jpg")
    BG_CLIP = f'<div class="clip" id="clip-bg" data-start="0" data-duration="{DUR:.2f}" data-track-index="0"><img src="_bg.jpg" style="position:absolute;inset:0;width:1080px;height:1920px;object-fit:cover"/></div>'

HTML = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"/>
<meta name="viewport" content="width=1080, height=1920"/>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
{os.linesep.join(_css)}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:transparent;}}
#root{{position:absolute;inset:0;}}
/* positions come from each pack element's REAL y (CapCut normalized -> px), never hand-picked:
   hook y={H.get('y')} -> {ypx(H)}px (above head) · caption y={C.get('y')} -> {ypx(C)}px (chest) · takeover y={TK.get('y')} -> {ypx(TK)}px (center) */
#hookwrap{{position:absolute;left:60px;right:60px;top:{HOOK_TOP}px;text-align:center;font-family:{fH};color:{HOOK_COLOR};text-shadow:{SHADOW or "0 5px 18px rgba(0,0,0,.62)"};}}
#hookwrap .hkline{{display:block;font-size:{HOOKN}px;line-height:{TIGHT_LH};}}
#hooksplit{{position:absolute;left:60px;right:60px;top:{HOOK_TOP}px;text-align:center;font-family:{fH};color:{HOOK_COLOR};text-shadow:{SHADOW or "0 5px 18px rgba(0,0,0,.62)"};}}
#hooksplit .hkhead,#hooksplit .hkquiet{{display:block;margin:0;line-height:{HEAD_LH_WD};}}
#hooksplit .hkquiet{{{_SUBCOL}font-weight:{SUB_WEIGHT};letter-spacing:{SUB_LS}em;margin:{EYE_GAP}px 0;}}
.capword{{position:absolute;left:90px;right:90px;top:{round(ypx(C)-CAP_LIFT)}px;transform:translateY(-50%);text-align:center;font-family:{fC};font-weight:{SINGLE_WEIGHT};letter-spacing:{SINGLE_LS}em;font-size:{CAP_PX}px;color:#fff;text-shadow:{SHADOW or "0 3px 12px rgba(0,0,0,.6)"};}}
.capword.kw{{color:{ACCENT};}}
{_ph_css}.buildwrap{{position:absolute;left:120px;right:120px;top:{round(ypx(C)-CAP_LIFT)}px;transform:translateY(-50%);text-align:center;font-family:{fKAR};font-weight:{KAR_WEIGHT};letter-spacing:{SINGLE_LS}em;font-size:{BLD_PX}px;line-height:1.2;color:#fff;text-shadow:0 3px 12px rgba(0,0,0,.6);}}
.tkwrap{{position:absolute;left:130px;right:130px;top:{ypx(TK)}px;transform:translateY(-50%);text-align:center;font-family:{fTK};color:#fff;text-shadow:{SHADOW or "0 4px 16px rgba(0,0,0,.65)"};}}
.tkwrap span{{display:block;line-height:{TK_LH};}}
.tkwrap span.kw{{color:{"#fff" if TK_WHITE else ACCENT};}}
{_vibe_css}
</style></head>
<body>
<div id="root" data-composition-id="{COMP}" data-start="0" data-duration="{DUR:.2f}" data-width="1080" data-height="1920">
{BG_CLIP}
{os.linesep.join(clips)}
</div>
<script>
window.__timelines=window.__timelines||{{}};
const tl=gsap.timeline({{paused:true}});
{os.linesep.join(tljs)}
window.__timelines["{COMP}"]=tl;
</script>
</body></html>'''

# SAFE-ZONE GUARD: a UI collision is invisible in the render and in QuickTime. You only see it in the app,
# after posting. So check it here, every build, and say so loudly.
_placed = []
if _PLBL:
    _lh = _plsz / 2 + _plpv
    _placed.append(("persistent label", _ply - _lh, _ply + _lh))
if HOOK or (HOOK_SPLIT and HOOK_LONG):
    _placed.append(("hook", HOOK_TOP, HOOK_TOP + HOOK_MAXH))
_viol = safe_zones.violations(_placed)
if _viol:
    for _n, _edge, _by, _pf in _viol:
        print(f"  ⚠ SAFE ZONE: '{_n}' crosses the {_edge} band by {_by}px — the platform draws its UI there")
else:
    print(f"  ✓ safe zones ok (y {safe_zones.TOP}-{safe_zones.BOTTOM})")

_tpl = f"{ROOT}/product/templates/hf-reel"
for _f in ("hyperframes.json", "package.json"):
    if os.path.exists(f"{_tpl}/{_f}") and not os.path.exists(f"{OUT}/{_f}"):
        shutil.copy(f"{_tpl}/{_f}", f"{OUT}/{_f}")
open(f"{OUT}/meta.json", "w", encoding="utf-8").write(json.dumps({"id": COMP, "name": "reel-type"}))
# Record the moments that OWN the screen — takeovers and full-screen breakaway cards. They cover the
# creator on purpose; that is the mechanic, not a defect. subject_guard.py reads this so it can tell a
# designed takeover from a stray graphic drifting onto her face. It used to try to infer that from pixel
# coverage (>=90% of the canvas), which a word stack can never reach: measured on a real takeover, it
# covered 39.7% of her face and only 7.0% of the canvas, and the busiest frame in the whole layer was
# 19.8%. So the waiver could never fire for type, and every takeover read as a defect.
_owns = {"_doc": "moments that cover the subject BY DESIGN (takeovers + full-screen breakaways), "
                 "written by build-reel-type.py for subject_guard.py. Seconds, [start, end].",
         "windows": [[round(float(a), 3), round(float(b), 3)] for (a, b) in YIELD_WINDOWS]}
# Written to the JOB folder, beside subject-zones.json, because that is where subject_guard walks
# UP to. The comp dir is a sibling of renders/, not an ancestor of it, so a copy there is invisible
# to a guard checking a rendered .mov. The windows come from the transcript and the plan, so they
# are the same whichever pack rendered.
for _p in (f"{OUT}/owns-screen.json", f"{JOB_DIR}/owns-screen.json"):
    json.dump(_owns, open(_p, "w", encoding="utf-8"), indent=1)
import script_fonts   # Cyrillic on screen in a pack face that has none: drawn from a matching bundled face
HTML, _script_notes = script_fonts.add_companions(HTML, OUT)
for _n in _script_notes:
    print(f"  {_n}")
open(f"{OUT}/index.html", "w", encoding="utf-8").write(HTML)
print(f"wrote {OUT}/index.html  pack={PACK} dur={DUR:.1f}s  hook={'yes' if HOOK else 'no'}  takeovers={len(spans)}  snaps={len([c for c in clips if 'capword' in c])}  phrases={len([c for c in clips if 'class="phrase"' in c])}")
