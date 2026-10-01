#!/usr/bin/env python3
"""superyap.py — the canonical Super Yap build ENGINE + LOCKED defaults for Naptime Creator Studio.

Every Super Yap imports this so all reels come out CONSISTENT by construction. Per-reel build scripts
supply only CONTENT (the cut, text beats, sticker placements, b-roll moments); THIS module owns the
DEFAULTS + engine mechanics (fonts, brand colors, sticker scale, layer order, mute, finalize/register).

Design rule — EDITABLE-FIRST: the AI does the tedious work, then
hands off a hand-editable CapCut project. Her brand assets stay as individual editable layers, never baked.

DONENESS != FORMAT (locked): "Clean vs Super" is loaded-ness; "raw / medium / well-done" is a
SEPARATE doneness axis. Both formats support all three — this editable-first path is the RAW Super Yap;
medium routes type through build-hf-captions.py, well-done bakes via build-reel-type.py.

Docs: ../SUPERYAP.md (workflow) · memory super yap feature template · vectcut build recipe.
CapCut MUST be quit before finalize().
"""
import os, json, time, glob, shutil, subprocess
import sys as _sys   # force UTF-8: a cp1252 Windows console can't print ✓ or →
for _s in (_sys.stdout, _sys.stderr):   # (this module prints them, and so does the motion line below)
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
from collections import deque
import requests
from PIL import Image
from capcut_ripple import enforce_maintrack_ripple, verify_maintrack_anchor  # magnet ALL tracks + audio to main (shared, single source) + fail-safe
from capcut_text import sanitize_draft_text          # base guardrail: repair corrupt text spans + 9:16 wrap
import capcut_color                                  # base guardrail: every video segment SDR (single source for hdr_settings)
import capcut_fonts                                  # font_path + CapCut library resource_id resolution (buyer portability)
import capcut_media                                  # FAIL-SAFE: every clip project-local + registered (links in media panel) + importable
import capcut_motion                                 # DEFAULT camera motion: opener zoom-in + jump-cut punches (strong default)
import cut_placement                                  # lays the cut as she set it (speed, zoom, split sound)
import learned                                       # preferences the creator has TAUGHT (brand-kit.md Part C)


import sys as _sys, os as _os_ds
_sys.path.insert(0, _os_ds.path.join(_os_ds.path.dirname(_os_ds.path.abspath(__file__)), "."))
import draft_safety as _ds  # CapCut's timeline-JSON filename is platform-specific
def _capcut_fonts_dir():
    """Where CapCut keeps the fonts the creator has added, on whichever OS this is.
    Existence-checked, never guessed: tries the Windows locations first, and if none of them are
    present falls back to the macOS container path, which is exactly the old behaviour."""
    import os as _os
    if _os.name == "nt":
        _la = _os.environ.get("LOCALAPPDATA", "")
        for _c in (_os.path.join(_la, "CapCut", "User Data", "Cache", "effect"),
                   _os.path.join(_la, "Microsoft", "Windows", "Fonts"),
                   _os.path.join(_os.environ.get("WINDIR", r"C:\Windows"), "Fonts")):
            if _c and _os.path.isdir(_c):
                return _c
    return _os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts")

BASE = "http://localhost:9001"
CAP = (os.path.join(os.environ["LOCALAPPDATA"], "CapCut/User Data/Projects/com.lveditor.draft").replace("\\", "/")
       if os.name == "nt" else
       os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft"))
FONTS_DIR = _capcut_fonts_dir()
CANVAS_W, CANVAS_H = 1080, 1920
US = 1_000_000

# ---------------- LOCKED BRAND DEFAULTS (change here → changes everywhere, consistently) ----------------
# Colors: YELLOW + WHITE + BLACK only. NO brown. an example reel palette butter yellow
WHITE, BUTTER, BLACK = "#FFFFFF", "#FFFFC2", "#000000"
# Fonts: ALL typography comes from the buyer's CHOSEN style pack, resolved per-role via
# cleanyap.hook_font()/thought_font() and packbuild.role(pack, <role>) (Editorial/Playful/Butter, or a
# custom pack). There is NO hardcoded font default in this builder — a build with no resolved font FAILS
# LOUD rather than ever reaching for a font that is not part of a pack. The creator's own reels pass her
# personal fonts EXPLICITLY (via fallback_font / takeover_font) from her non-shipped personal setup, never
# from a shipped constant here. personal fonts vs ship fonts
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAND_IN = "Inter_Black"                                # engine built-in placeholder; patched in finalize
# Stickers: her doodle PNGs, dropped as INDIVIDUAL editable layers at 20% build png editability
STICKER_SCALE = 0.20
BROLL_SCALE = 1.05
# Layer order (render_index; higher = on top). Fixes the "PNG hides behind footage" bug.
RI_FOOTAGE, RI_BROLL, RI_IMG, RI_TEXT = 0, 8000, 12000, 15000
# Thought bubbles in the pack's thought font get a tight line height, the same value the Clean Yap engine uses
# (cleanyap.LINE_SPACING_THOUGHT); a spacing she taught with /learn wins over it.
LINE_SPACING_THOUGHT = -0.15


def _thought_fonts(pack=None):
    """The fonts that count as the pack's thought font in this build: the thought font of `pack` (else of the
    pack the build's context names), plus any font cleanyap.thought_font() handed out when a reel's driver took
    its fonts from there. cleanyap is only read if the driver already loaded it; this engine never imports it."""
    fonts = set(getattr(_sys.modules.get("cleanyap"), "_THOUGHT_FONTS", ()) or ())
    pack = pack or learned.context().get("pack")
    if pack:
        try:
            import packbuild
            fonts.add(packbuild.role(pack, "thought")["font_path"])
        except Exception:
            pass
    return fonts

# ---------------- ENGINE ----------------
def call(ep, _strict=True, **kw):
    """One VectCut call. FAIL LOUD by default: a failed add_video/add_text/add_audio used to print "ERR" and
    CONTINUE, producing a PARTIAL draft that still reported success. Now it raises. Pass _strict=False only
    where a failure is benign (the idempotent re-save in finalize)."""
    try:
        r = requests.post(f"{BASE}/{ep}", json=kw, timeout=180)
    except requests.exceptions.ConnectionError:   # the #1 buyer state: forgot to start the editor engine
        raise RuntimeError(f"The editor engine (VectCut) is not running at {BASE}. Start it with "
                           "product/engine/VectCutAPI/start-editor.command (SETUP.md §1b), then re-run.") from None
    except requests.exceptions.Timeout:           # a very large clip transcoding — say so, don't dump a traceback
        raise RuntimeError(f"VectCut took longer than 180s on {ep} — usually a very large clip being transcoded. "
                           "Let the editor engine finish and re-run; if it repeats, trim that clip first.") from None
    try:
        j = r.json()
    except ValueError:   # 404 / crash page / HTML — not a JSON reply: treat as a failed call, not a raw traceback
        j = {"success": False, "error": f"non-JSON reply (HTTP {r.status_code}): {r.text[:120]!r}"}
    if not j.get("success"):
        msg = f"VectCut {ep} failed: {str(j.get('error'))[:200]}"
        if _strict:
            raise RuntimeError(msg + "  (the draft would be INCOMPLETE — fix the input, do not hand this off)")
        print("ERR", msg)
    return j

def probe_dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", p]).strip())

def ko_white(src, ko_dir):
    """Edge-connected white→transparent knockout; cache to ko_dir. Returns original if already transparent."""
    im = Image.open(src).convert("RGBA"); px = im.load(); Wd, Hd = im.size
    corners = [px[1, 1], px[Wd-2, 1], px[1, Hd-2], px[Wd-2, Hd-2]]
    if not all(p[3] > 250 and p[0] > 242 and p[1] > 242 and p[2] > 242 for p in corners):
        return src
    os.makedirs(ko_dir, exist_ok=True)
    out = f"{ko_dir}/{os.path.splitext(os.path.basename(src))[0]}.png"
    def w(p): return p[0] > 242 and p[1] > 242 and p[2] > 242 and p[3] > 250
    seen = [[False]*Hd for _ in range(Wd)]; dq = deque()
    for x in range(Wd):
        for y in (0, Hd-1):
            if w(px[x, y]): dq.append((x, y)); seen[x][y] = True
    for y in range(Hd):
        for x in (0, Wd-1):
            if w(px[x, y]) and not seen[x][y]: dq.append((x, y)); seen[x][y] = True
    while dq:
        x, y = dq.popleft(); px[x, y] = (0, 0, 0, 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x+dx, y+dy
            if 0 <= nx < Wd and 0 <= ny < Hd and not seen[nx][ny] and w(px[nx, ny]):
                seen[nx][ny] = True; dq.append((nx, ny))
    im.save(out); return out

_JOB_DIR = None     # set by add_cut; the job folder the subject measurement lives in


_CTX_REGISTER = "teaching"   # the Super Yap treatment's register; the reel's own plan, or learning_context(), overrides


def learning_context(register=None, pack=None):
    """State what this reel is, so a preference she taught for one kind of reel applies (and no other).
    A reel's build script calls this when it knows better than the default; add_cut also reads the job's
    caption-plan.json. Safe to call more than once."""
    global _CTX_REGISTER
    if register:
        _CTX_REGISTER = register
    learned.context_for_build("yap", register=_CTX_REGISTER, pack=pack,
                              job_dir=globals().get("_JOB_DIR"))


def thought_line_spacing():
    """Thought-bubble line spacing: what she taught, else the dialed-in default (the Clean Yap engine's too)."""
    learning_context()
    return learned.get("thought.line_spacing", LINE_SPACING_THOUGHT)


def add_cut(did, cuts, rawdir, punch=None):
    """Splice the locked rough cut onto the main track (+ optional punch-in zoom per index)."""
    punch = punch or {}
    # Remember the JOB this draft is being built from. finalize() only has the CapCut draft folder, which
    # lives under ~/Movies/CapCut and can never be walked up to reach projects/<job>/subject-zones.json — so
    # without this the subject guard would look in the wrong tree, find nothing, and report "not measured"
    # forever while quietly passing every build. Every build calls add_cut, so the hint costs nothing and
    # works for build scripts that already exist.
    global _JOB_DIR
    _JOB_DIR = os.path.dirname(os.path.abspath(rawdir))
    learning_context()                # now the job is known, its plan's register wins
    # her speed / zoom / split-off sound / audio clips, when the cut was pulled back from her own timeline
    cut_placement.place(call, did, cuts, rawdir, punch)

def add_broll(did, path, at, src, dur):
    """A muted b-roll cutaway from a GOOD in-clip moment (src). Never grab from 0s. margins broll burst"""
    call("add_video", draft_id=did, video_url=path, start=src, end=src+dur, target_start=at,
         scale_x=BROLL_SCALE, scale_y=BROLL_SCALE, volume=0.0, track_name="broll")

def add_png(did, path, st, en, x, y, track, scale=None, target_w=None):
    """Drop a PNG as an INDIVIDUAL editable layer. Stickers default to 20%; pass target_w for covers/screens."""
    im = Image.open(path); cw, ch = im.size
    sc = scale if scale is not None else (target_w/cw if target_w else STICKER_SCALE)
    call("add_image", draft_id=did, image_url=path, start=st, end=en, width=cw, height=ch,
         scale_x=sc, scale_y=sc, transform_x=x, transform_y=y, track_name=track)

def _anim(name):
    # Animation names resolve via getattr on the server's enum (Text_intro/outro), so a display name with
    # SPACES ("Random Typewriter") silently fails and the anim is dropped. Normalize display -> api form.
    return name.replace(" ", "_") if name else name

_STYLE_SAID = set()
_STYLE_TEXT = {}
_STYLE_ROLE_PENDING = {}    # normalized text -> role, for text that got a taught animation (finalize swaps stand-ins)

def _taught_anim(track, kind):
    """The text animation she taught with "learn this style" (favorites.py learn-style), for text the reel's
    own plan leaves unanimated. Takeover words never get one: they reveal in place, unanimated, by rule."""
    t = (track or "").lower()
    if t.startswith(("tk", "takeover")):
        return None
    role = "hook" if t.startswith("hook") else "text"
    try:
        import favorites
        a = favorites.style_animation(role, kind)
    except Exception:
        return None
    if a:
        _STYLE_ROLE_PENDING[kind] = role
    if a and (role, kind) not in _STYLE_SAID:
        _STYLE_SAID.add((role, kind))
        print(f"  from the style you taught me: {role} text {'comes in' if kind == 'in' else 'leaves'} with {a.replace('_', ' ')}")
    return a

def add_text(did, t, s, e, fp, sz, x, y, track, color=WHITE, intro=None, outro=None):
    if intro is None:
        intro = _taught_anim(track, "in")
    if outro is None:
        outro = _taught_anim(track, "out")
    if _STYLE_ROLE_PENDING:
        import re as _re
        _STYLE_TEXT[_re.sub(r"\s+", " ", str(t)).strip()] = next(iter(_STYLE_ROLE_PENDING.values()))
        _STYLE_ROLE_PENDING.clear()
    call("add_text", draft_id=did, text=t, start=s, end=e, font=STAND_IN, color=color, size=sz,
         transform_x=x, transform_y=y, intro_animation=_anim(intro), outro_animation=_anim(outro), track_name=track)

def takeover(did, words, end, size, step, tag, takeover_font=None):
    """FULL-SCREEN TAKEOVER: LARGE, NO animation, each word appears as spoken, stacked+centered. One
    sentence = one takeover (clears before the next). words = [(word, start), ...]. takeover_font is
    REQUIRED — the active pack's takeover font, packbuild.role(pack, "takeover")["font_path"] (the creator's
    own reels pass her personal takeover font here explicitly). No default, so no non-pack font can ever
    leak into a takeover. super yap feature template"""
    if not takeover_font:
        raise RuntimeError(
            "takeover(): no takeover_font given — pass the pack's takeover font "
            "(packbuild.role(pack, 'takeover')['font_path']). The engine never defaults to a personal font.")
    font = takeover_font
    n = len(words); top = (n - 1) / 2 * step
    for k, (wd, st) in enumerate(words):
        add_text(did, wd, st, end, font, size, 0.0, top - k*step, f"{tag}{k}", color=WHITE, intro="", outro="")

def finalize(did, name, font_map, fallback_font=None, job=None, pack=None):
    """Register + normalize the draft: patch custom fonts, layer order (img above footage), MUTE b-roll,
    normalize the main track. font_map = {exact_text: font_path}. CapCut MUST be quit first. pack = the style
    pack the reel is built in, so its thought font gets the thought-bubble line spacing (optional)."""
    import draft_safety; draft_safety.require_capcut_quit("build this reel")   # else CapCut's next save wipes it
    # VectCut holds the draft only in memory (keyed by draft_id) until /save_draft flushes it to
    # the CapCut projects folder. Do it here so the documented add_cut->add_text->add_sfx->finalize
    # flow works on its own; without it the os.rename below hits a path that was never written.
    # Idempotent: safe if the draft was already saved (call() never raises, just reports).
    call("save_draft", _strict=False, draft_id=did, draft_folder=CAP)   # idempotent re-save: benign if already saved
    name = name.replace("/", "-").replace(":", "-")   # a path separator in a draft name would break the rename below
    # Built with os.path.join, matching EXACTLY how util.build_draft_asset_path() constructed the asset
    # paths baked into the draft's JSON (it appends draft_id/asset segments onto CAP as-is, without
    # normalizing CAP's own separators) -- an f-string "/" join produces a DIFFERENT literal string on
    # Windows (CAP already mixes slash styles), so the string-replace fixup below would silently never
    # match and every asset path would still point at the pre-rename draft_id folder.
    old = os.path.join(CAP, did); D = os.path.join(CAP, name)
    if os.path.isdir(D) and D != old:
        # FAIL-SAFE (locked): NEVER destroy an existing draft. A rebuild must go to a NEW name so
        # a creator's by-hand edits can never be wiped. Refuse instead of rmtree'ing their work.
        shutil.rmtree(old, ignore_errors=True)
        try:
            import draft_safety
            nxt = draft_safety.next_version(draft_safety.base_of(name))
        except Exception:
            nxt = f"{name} 1.1"
        raise RuntimeError(
            f"REFUSING to overwrite existing draft {name!r}: a rebuild would wipe the creator's in-app "
            f"edits (CapCut has NO version history). Build to {nxt!r} instead (never reuse a name), or "
            f"LAYER the change on top of the existing draft. See product/draft_safety.py.")
    # SUBJECT GUARDRAIL (base, every format): no text ends up ON her. The placement numbers on this route
    # are hand-written, so this is the only thing standing between a copied-forward transform_y and a hook
    # across her forehead.
    # It runs HERE, before the rename below, because that rename is the point of no return: after it the
    # folder owns the final draft name, so refusing later would leave an invisible folder squatting that
    # name — and the next build, with the placement fixed, would be told it must not overwrite the
    # creator's work. Two confusing errors for one real one. Refusing before the rename leaves nothing.
    # Warns (never refuses) when her footage was not measured — an unmeasured job is not a defect, but it
    # is not a clean bill of health either, and it says so. The CHECK degrades to a warning if it cannot
    # run; only a real breach refuses. A guardrail that can itself break a working build is a worse bug
    # than the one it catches.
    _sbr = []
    try:
        import subject_place
        _sbr, _slines = subject_place.report(
            json.load(open(_ds.draft_json(old), encoding="utf-8")), job or _JOB_DIR or old)
        for _l in _slines:
            print(_l)
    except Exception as _e:
        print(f"  \u26a0 SUBJECT: placement not checked ({type(_e).__name__}: {str(_e)[:120]}). "
              "NOT evidence that text is clear of her.")
    if _sbr and os.environ.get("SUBJECT_ALLOW_OVERLAP") != "1":
        shutil.rmtree(old, ignore_errors=True)   # refused before the rename: nothing half-built survives
        raise RuntimeError("text is placed on her face \u2014 build refused:\n  - " + "\n  - ".join(_sbr)
                           + "\n  Move it to a measured open zone (subject_place.y_for), or set "
                             "SUBJECT_ALLOW_OVERLAP=1 if this one is deliberate.")

    os.rename(old, D)
    try:
        # On Windows, `old`/`D` contain backslashes, but we are doing a RAW-TEXT replace on the file's bytes
        # BEFORE it is JSON-parsed -- and JSON escapes a literal backslash as two characters ("\\"). So the file's
        # raw text has every backslash doubled, and a plain-string search for the unescaped path silently never
        # matches, leaving every asset path pointed at the pre-rename draft_id folder forever. Mac paths use "/",
        # which JSON does not escape, which is exactly why this never surfaced there. Replace both the raw form
        # (a no-op check on Mac/Windows alike when no backslash is present) and the JSON-escaped form.
        def _json_escaped(p): return p.replace("\\", "\\\\")
        old_json, D_json = _json_escaped(old), _json_escaped(D)
        for f in glob.glob(f"{D}/*.json") + _ds.draft_json_copies(D, require=False):
            s = open(f, encoding="utf-8").read()
            changed = False
            if old in s: s = s.replace(old, D); changed = True
            if old_json in s: s = s.replace(old_json, D_json); changed = True
            if changed: open(f, "w", encoding="utf-8").write(s)
        p = _ds.draft_json(D); d = json.load(open(p, encoding="utf-8"))
        fm = {k.upper(): v for k, v in font_map.items()}   # case-insensitive (VectCut may uppercase single words)
        # Unmatched text falls back to a PACK font, NEVER a personal font — explicit fallback_font wins, else the
        # most-common caller-provided font (pack fonts for ship). If the map is EMPTY and no fallback_font was
        # passed there is no font to use: FAIL LOUD rather than reach for a non-pack default.
        if fallback_font:
            default_font = fallback_font
        elif fm:
            default_font = max(fm.values(), key=list(fm.values()).count)
        else:
            # Refused after the rename: hand back the name so a corrected rebuild is not told it must
            # not overwrite "existing work" that is really this failed attempt (draft_safety refuses to
            # touch anything registered, and registration is the last step of a SUCCESSFUL build).
            _ds.discard_unfinished(D)
            raise RuntimeError(
                "finalize(): no fonts resolved for this draft and no fallback_font given — pass a pack font "
                "or fallback_font=<pack font path>. The engine never defaults to a personal font.")
        thought_fonts = _thought_fonts(pack)
        for m in d["materials"].get("texts", []):
            txt = json.loads(m["content"]).get("text", "")
            font = fm.get(txt.upper(), default_font)
            capcut_fonts.apply(m, font)   # sets font_path + (for CapCut-library fonts) resource_id/platform so a buyer's CapCut resolves it
            m["alignment"] = 1; m["preset_has_set_alignment"] = True
            if font in thought_fonts:     # thought-bubble multi-line = tight, not loose (it never was here)
                m["line_spacing"] = thought_line_spacing()
            c = json.loads(m["content"])
            for st in c.get("styles", []):
                if isinstance(st.get("font"), dict): st["font"]["path"] = font; st["font"]["id"] = ""
            m["content"] = json.dumps(c, ensure_ascii=False)
        for t in d["tracks"]:
            nm = t.get("name", "")
            ri = RI_IMG if nm.startswith("img_") else (RI_BROLL if nm == "broll" else None)
            if ri is not None:
                for seg in t["segments"]:
                    seg["render_index"] = ri
                    if nm == "broll": seg["volume"] = 0.0
        d["tracks"] = [t for t in d["tracks"] if not (t["type"] == "video" and len(t["segments"]) == 0)]
        vids = [t for t in d["tracks"] if t["type"] == "video"]
        if vids:
            footage = max(vids, key=lambda t: len(t["segments"]))
            footage["flag"] = 0; footage["name"] = ""; footage["is_default_name"] = False  # anchor identity (magnet)
        # DEFAULT MOTION (locked strong-default): a slow zoom-in on the opener + gentle jump-cut punches, so the
        # frame never sits dead still. EVERY move reframes on her face in THAT shot (measured off the
        # footage the draft points at): a scale keyframe alone zooms about the frame centre, which slides
        # an off-centre creator toward the edge on every push-in. Only touches clips still at scale 1.0
        # AND transform 0/0 — any punch the build passed to add_cut, and any zoom or nudge the creator
        # set herself, is preserved. Must run BEFORE the guardrail below (it flips
        # uniform_scale off for exactly these scale changes so they render). See capcut_motion.py.
        learning_context()
        if cut_placement.is_your_turn(globals().get("_JOB_DIR")):
            # her own CapCut timeline: every zoom and every still shot in it is her call, kept exactly
            print("[motion] your-turn cut — your own zooms and framing kept exactly, no default motion added")
        elif learned.get("motion.opener_zoom", True):     # strong default, but she can teach it off once
            _z, _p = capcut_motion.apply_default_motion(d)
            if _z or _p: print(f"[motion] intro zoom: {_z} · jump-cut punches: {_p}")
        else:
            print("[motion] opener push-in off (you taught me that) — say \"/learn forget\" to bring it back")
        # SCALE GUARDRAIL (locked): VectCut writes clip.scale but leaves uniform_scale.on=True (value hardcoded
        # 1.0), and uniform_scale OVERRIDES clip.scale — so every jump-cut zoom / b-roll inset silently renders at
        # 1.0 in CapCut (broke ALL scale changes; the creator saw zero zooms). Turn uniform_scale OFF wherever a
        # non-1.0 clip.scale or a scale keyframe is set, so the scale actually renders.
        for t in vids:
            for seg in t["segments"]:
                sc = seg.get("clip", {}).get("scale", {})
                scaled = abs(sc.get("x", 1.0) - 1.0) > 1e-3 or abs(sc.get("y", 1.0) - 1.0) > 1e-3
                kf = any(k.get("property_type") in ("KFTypeScaleX", "KFTypeScaleY")
                         for k in seg.get("common_keyframes", []))
                if (scaled or kf) and isinstance(seg.get("uniform_scale"), dict):
                    seg["uniform_scale"]["on"] = False
                # SDR COLOR FIX (locked): see product/capcut_color.py for why. The sweep below
                # (enforce_sdr) is the draft-wide guarantee; this keeps the per-segment pass in step.
                if capcut_color.needs_correction(seg):
                    seg["hdr_settings"] = capcut_color.sdr_settings()
        sanitize_draft_text(d)                      # base guardrail: no corrupt text spans, 9:16 wrap-safe
        capcut_color.enforce_sdr(d)                 # base guardrail: no segment reaches CapCut tagged HDR
        enforce_maintrack_ripple(d)                 # base guardrail: magnet ALL tracks (overlays/text/b-roll) + audio
        _mp = verify_maintrack_anchor(d)            # FAIL-SAFE: never ship a dead magnet again (2026-08-12 regression)
        if _mp:
            _ds.discard_unfinished(D)      # same reason: a refused build must not squat the name
            raise RuntimeError("magnet anchor broken — build refused:\n  - " + "\n  - ".join(_mp))
        _media = capcut_media.ensure_shippable(d, D)  # FAIL-SAFE: every clip project-local + registered (links in the
        if _media:                                    # media panel) + importable — never ship "not linked" / ProRes again
            _ds.discard_unfinished(D)      # same reason: a refused build must not squat the name
            raise RuntimeError("media won't link/import in CapCut — build refused:\n  - " + "\n  - ".join(_media))
        try:                                           # the style she taught: her real CapCut animation in for the stand-in
            import favorites
            _sw = favorites.apply_style_swaps(d, _STYLE_TEXT)
            if _sw:
                print(f"  swapped in {_sw} of your own CapCut animation{'s' if _sw != 1 else ''} from the style you taught me")
        except Exception as _e:
            print(f"  (could not apply your taught animations: {_e}; the stand-in stays)")
        # The face measurement above can run for many minutes per clip, and CapCut may have been opened in
        # the meantime. Check again right before the draft is written: written under an open CapCut, the
        # whole build is silently dropped by its next save.
        _ds.require_capcut_quit("build this reel")
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        capcut_media.write_cover(d, D)              # FAIL-SAFE: the drafts grid needs a real draft_cover.jpg or the
                                                   # new draft can be INVISIBLE with no error (draft-not-visible bug)
        now = int(time.time())
        dm = json.load(open(f"{D}/draft_meta_info.json", encoding="utf-8")); dm["draft_name"] = name
        # FRESH TIMESTAMPS (locked): CapCut sorts + shows the drafts grid by draft_meta_info's own tm fields, not
        # root_meta. A DUPLICATE+rebuild (new version) inherits the source's stale times here, so the new draft
        # sorted to the end / went unseen. Stamp real current time so a new version always lands at the top.
        dm["tm_draft_create"] = dm["tm_draft_modified"] = now * US
        dm["tm_duration"] = d.get("duration", dm.get("tm_duration", 0))
        json.dump(dm, open(f"{D}/draft_meta_info.json", "w", encoding="utf-8"), ensure_ascii=False)
        # Register in root_meta_info.json (the drafts grid). Shared guard handles a brand-new CapCut whose
        # all_draft_store is [] (first-ever buyer build) instead of crashing on [0]. now/US threaded in so
        # the timestamp matches the draft_meta_info write above (CapCut sorts the grid off both).
        capcut_media.register_draft(CAP, name, D, p, dm.get("draft_id", did), d.get("duration", 0), now, US)
    except BaseException:
        # Anything that stops the build between the rename and the registration would leave a folder CapCut
        # cannot show that still owns the name, and the next build to that name would be refused as the
        # creator's existing work. Hand the name back first. discard_unfinished never touches a draft that
        # got registered, and the original error is the one worth showing.
        try:
            _ds.discard_unfinished(D)
        except Exception:
            pass
        raise
    try:                                     # snapshot so later in-app edits are detectable (never-replace fail-safe)
        import draft_safety; draft_safety.record_build(name)
    except Exception:
        pass
    for _ln in learned.report():                 # what came from her saved preferences (never applied silently)
        print(_ln)
    print("built + registered:", name, "| tracks v/img/text:",
          sum(t["type"] == "video" for t in d["tracks"]), "/",
          sum(t.get("name", "").startswith("img_") for t in d["tracks"]), "/",
          sum(t["type"] == "text" for t in d["tracks"]))
