#!/usr/bin/env python3
"""cleanyap.py — the canonical CLEAN YAP build ENGINE for Naptime Creator Studio.

The TRIMMED-BACK lane, separate from the Super Yap engine on purpose.
A Clean Yap is: the locked rough cut, full-screen, + ONE hook (the pack's hook font) + thought bubbles
(the pack's thought font) + matched/trimmed SFX. Everything stays individually editable in CapCut. NOTHING loaded.

Deliberately does NOT expose the Super Yap machinery (full-screen pack-takeover-font takeover, doodle-sticker
layers, b-roll cutaways/bursts, stat cards, punch-in zooms). If a reel needs those, it's a Super Yap →
use superyap.py. Keeping the lanes separate in CODE is the point (the creator's rule #6, fix the system).

DONENESS != FORMAT (locked). "Clean vs Super" is the LOADED-NESS axis. "raw / medium /
well-done" is a SEPARATE doneness axis that applies to Clean Yaps too — don't assume Clean Yap == raw.
This module is the RAW Clean Yap engine (editable CapCut text). A Clean Yap can also ship medium
(build-hf-captions.py -> named .mov type layers) or well-done (build-reel-type.py -> baked MP4).

Shares the same engine mechanics/gotchas as superyap.py (VectCutAPI on :9001, font patch, main-track
normalize, register). Kept as a standalone module so the Super Yap engine is never in a Clean Yap's
import path. CapCut MUST be quit before finalize().
"""
import os, json, time, glob, shutil, subprocess, math
import sys as _sys   # force UTF-8: a cp1252 Windows console can't print ✓ or →
for _s in (_sys.stdout, _sys.stderr):   # (this module prints them, and so does the motion line below)
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
import requests
from PIL import Image


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

# ---- LOCKED CLEAN-YAP DEFAULTS ----
WHITE, BUTTER, BLACK = "#FFFFFF", "#FFFFC2", "#000000"
# FONTS — ALL shipped typography comes from the buyer's CHOSEN style pack, resolved per-role via
# hook_font()/thought_font() (Editorial/Playful/Butter, or a custom pack). There is NO hardcoded font
# default — a build with no resolved pack RAISES (see _pack_or_default); the engine never reaches for a font
# that is not part of a pack. The creator's own reels pass her personal fonts EXPLICITLY (fallback_font),
# never from a shipped constant. (the creator: "for the yaps we ship, dont default to playfair. the user
# gets to choose their default style".) personal fonts vs ship fonts
# FONT_THOUGHT is kept ONLY as an identity marker for the thought-bubble line-spacing on the creator's own
# personal thought font — never a default, never stamped, so it cannot leak (a buyer's pack thought font
# never equals it). A buyer's thought bubbles get the same spacing through the pack's thought font
# (is_thought_font below); this marker only keeps the creator's own reels exactly as they were.
FONT_THOUGHT = f"{FONTS_DIR}/UglyDaveAlternates.otf"  # personal thought font — spacing-comparison marker only, never a default

# ---- SHIP STYLE PACKS (buyer chooses; switchable) ----
import packbuild                                        # pack -> per-role font/size/case (creative-vault/style-packs.json)
import learned                                         # preferences the creator has TAUGHT (brand-kit.md Part C)
import capcut_fonts                                     # font_path + CapCut library resource_id resolution (buyer portability)
_USER_STYLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "user-style.json")

def default_pack():
    """The buyer's saved default style pack, or None if they haven't chosen yet (first-edit chooser)."""
    try: return json.load(open(_USER_STYLE, encoding="utf-8")).get("default_pack")
    except Exception: return None

def set_default_pack(name):
    """Persist the buyer's default pack (validated). Keeps a switch history. First-edit chooser calls this."""
    if name not in packbuild.names():
        raise ValueError(f"unknown pack {name!r}; choose one of {packbuild.names()}")
    try: d = json.load(open(_USER_STYLE, encoding="utf-8"))
    except Exception: d = {"default_pack": None, "history": []}
    d.setdefault("history", []).append(d.get("default_pack"))
    d["default_pack"] = name
    json.dump(d, open(_USER_STYLE, "w", encoding="utf-8"), indent=2)
    return name

def _pack_or_default(pack):
    pack = pack or default_pack()
    if not pack:
        raise ValueError("no style pack chosen — pick one of " + ", ".join(packbuild.names()) +
                         " (cleanyap.set_default_pack(...)); shipped yaps never default to a font.")
    return pack

def hook_font(pack=None):
    """SHIP hook font for the chosen pack (headline role). No pack + no saved default => raises (no Playfair default)."""
    return packbuild.role(_pack_or_default(pack), "headline")["font_path"]

_THOUGHT_FONTS = set()   # every font thought_font() has handed this build


def thought_font(pack=None):
    """SHIP thought-bubble font for the chosen pack (thought role)."""
    font = packbuild.role(_pack_or_default(pack), "thought")["font_path"]
    _THOUGHT_FONTS.add(font)
    return font


def is_thought_font(font, pack=None):
    """Does text set in this font get the tight thought-bubble line spacing? The pack's thought font does: the
    one thought_font() handed this build, or the thought font of the pack this build runs in (`pack`, else the
    build's own context). So does FONT_THOUGHT, which only the creator's own reels pass. The spacing used to be
    keyed on FONT_THOUGHT alone, so no shipped pack, and no spacing a buyer taught with /learn, ever reached a
    thought bubble."""
    if font == FONT_THOUGHT or font in _THOUGHT_FONTS:
        return True
    pack = pack or learned.context().get("pack")
    if not pack:
        return False
    try:
        return font == packbuild.role(pack, "thought")["font_path"]
    except Exception:
        return False
STAND_IN = "Inter_Black"                               # engine built-in placeholder; patched in finalize
LINE_SPACING_THOUGHT = -0.15                           # thought-bubble line height — the creator's dialed-in value (2026-08-02, from her edits)
SIZE_THOUGHT = 12                                       # thought bubbles — the creator's dialed-in size (2026-08-02; 15 read oversized)
SIZE_HOOK = 17                                          # SHORT-hook default; long hooks shrink — use hook_size() below

def hook_size(text):
    """Hook size scales to hook LENGTH so it wraps to ≤3 lines and never runs off frame (the creator pays
    attention to this — she sized a 59-char POV hook to 14). Ladder calibrated to her edits.

    A size she has TAUGHT (`/learn`) wins over the ladder, because she looked at a real reel to pick it."""
    n = len(text)
    ladder = 17 if n <= 20 else 16 if n <= 40 else 14 if n <= 64 else 13
    learning_context()
    return learned.get("hook.size", ladder)


def thought_size():
    """Thought-bubble size: what she taught, else the dialed-in default."""
    learning_context()
    return learned.get("thought.size", SIZE_THOUGHT)


def thought_line_spacing():
    """Thought-bubble line spacing: what she taught, else the dialed-in default."""
    learning_context()
    return learned.get("thought.line_spacing", LINE_SPACING_THOUGHT)
# Slow zoom-in opener (the creator's default for clean yaps, ESP confessional): keyframe the first footage clip's
# scale from INTRO_ZOOM_FROM -> INTRO_ZOOM_TO over INTRO_ZOOM_SECS at the clip start, then hold TO.
INTRO_ZOOM_FROM, INTRO_ZOOM_TO, INTRO_ZOOM_SECS = 1.06, 1.22, 1.4
# Layer order (render_index; higher = on top). img_ = baked emoji / text glyphs only (NOT doodle stickers).
RI_FOOTAGE, RI_IMG, RI_TEXT = 0, 12000, 15000

# ---------------- ENGINE ----------------
def call(ep, _strict=True, **kw):
    """One VectCut call. FAIL LOUD by default: a failed add_video/add_text/add_audio used to print "ERR" and
    CONTINUE, so a missing clip or a bad text produced a PARTIAL draft that still reported success. Now it
    raises. Pass _strict=False only where a failure is benign (the idempotent re-save in finalize)."""
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

_JOB_DIR = None     # set by add_cut; the job folder the subject measurement lives in


_CTX_REGISTER = "confessional"   # the Clean Yap treatment's register; the reel's own plan, or learning_context(), overrides


def learning_context(register=None, pack=None):
    """State what this reel is, so a preference she taught for one kind of reel applies (and no other).
    A reel's build script calls this when it knows better than the default; add_cut also reads the job's
    caption-plan.json. Safe to call more than once."""
    global _CTX_REGISTER
    if register:
        _CTX_REGISTER = register
    learned.context_for_build("yap", register=_CTX_REGISTER, pack=pack,
                              job_dir=globals().get("_JOB_DIR"))


def add_cut(did, cuts, rawdir, punch=None):
    """Splice the locked rough cut onto the main track. punch={index: scale} for optional gentle push-ins
    (Clean Yaps usually stay still — leave punch empty)."""
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

def _anim(name):
    # Animation names resolve via getattr on the server enum, so a display name with SPACES
    # ("Random Typewriter") silently fails and the anim is dropped. Normalize display -> api form.
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
    """Hook or thought bubble (the pack's hook / thought font). fp = real font path (patched in at finalize)."""
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

def add_png(did, path, st, en, x, y, track, scale=None, target_w=None):
    """Minimal image overlay — for a BAKED EMOJI / text glyph only (custom fonts can't render emoji).
    NOT for doodle stickers; those are a Super Yap feature."""
    im = Image.open(path); cw, ch = im.size
    sc = scale if scale is not None else (target_w/cw if target_w else 0.2)
    call("add_image", draft_id=did, image_url=path, start=st, end=en, width=cw, height=ch,
         scale_x=sc, scale_y=sc, transform_x=x, transform_y=y, track_name=track)

def add_sfx(did, path, at, dur, volume=None, track="sfx", programme=None):
    """Matched/trimmed SFX — trim to EXACT length (dur), placed at timeline `at`. sfx must match motion duration

    LEVEL: volume=None (the default) AUTO-LEVELS via the shared `audio_levels` module. Do not hand-pick a
    multiplier: the bundled SFX span ~20 dB of intrinsic level, so the same number makes one cue slap and
    another inaudible, and it fails SILENTLY. `programme` = the cut, to place cues under the real voice.
    An explicit numeric volume is still honoured. sfx music must auto level"""
    import audio_levels
    if volume is None:
        volume = audio_levels.sfx_volume(path, audio_levels.peak_dbfs(programme) if programme else None, trim=dur)
        audio_levels.report([{"file": path, "gain_db": 20 * math.log10(max(volume, 1e-6)), "how": "auto"}],
                            prefix="[sfx]")
    call("add_audio", draft_id=did, audio_url=path, start=0, end=dur, target_start=at, volume=volume, track_name=track)

# SHARED base guardrails — called in EVERY format's finalize (Clean Yap / Super Yap / VO), never
# copy-pasted per format (the creator's rule 2026-08-02: base edits happen across every format, always consistent).
from capcut_ripple import enforce_maintrack_ripple, verify_maintrack_anchor   # magnet ALL tracks + audio to main track + fail-safe
from capcut_text import sanitize_draft_text           # repair corrupt text spans + 9:16 wrap safety
import capcut_color                                  # base guardrail: every video segment SDR (single source for hdr_settings)
import capcut_media                                   # FAIL-SAFE: every clip project-local + registered (media panel) + importable
import capcut_motion                                  # DEFAULT camera motion: opener zoom-in + jump-cut punches (strong default)
import cut_placement                                  # lays the cut as she set it (speed, zoom, split sound)


def finalize(did, name, font_map, anim_durations=None, fallback_font=None, job=None, pack=None):
    """Register + normalize: patch custom fonts, put img_ overlays above footage, normalize the main
    track to CapCut's flag=0 shape. font_map = {exact_text: font_path}. CapCut MUST be quit first.
    anim_durations = {animation_name: seconds} overrides an intro ('in') animation's length,
    e.g. {"Random Typewriter": 1.25} to slow the hook type-on. pack = the style pack the reel is built in,
    so its thought font gets the thought-bubble line spacing (optional: see is_thought_font)."""
    import draft_safety; draft_safety.require_capcut_quit("build this reel")   # else CapCut's next save wipes it
    # VectCut holds the draft only in memory (keyed by draft_id) until /save_draft flushes it to
    # the CapCut projects folder. Do it here so the documented add_cut->add_text->add_sfx->finalize
    # flow works on its own; without it the os.rename below hits a path that was never written.
    # Idempotent: safe if the draft was already saved (non-strict: a re-save "failure" is benign here).
    call("save_draft", _strict=False, draft_id=did, draft_folder=CAP)
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
        # Unmatched text falls back to a PACK font, NEVER a personal font (the creator: "fallback should be the
        # pack font"). Explicit fallback_font wins; else the most-common font the caller PROVIDED (pack fonts for
        # ship, personal on her reels). If the map is EMPTY and no fallback_font was passed there is no font to
        # use: FAIL LOUD rather than reach for a non-pack default.
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
                "(cleanyap.hook_font(pack)/thought_font(pack)) or fallback_font=<pack font path>. "
                "The engine never defaults to a personal font.")
        for m in d["materials"].get("texts", []):
            txt = json.loads(m["content"]).get("text", "")
            font = fm.get(txt.upper(), default_font)
            capcut_fonts.apply(m, font)   # sets font_path + (for CapCut-library fonts) resource_id/platform so a buyer's CapCut resolves it
            m["alignment"] = 1; m["preset_has_set_alignment"] = True
            if is_thought_font(font, pack):
                m["line_spacing"] = thought_line_spacing()   # thought-bubble multi-line = tight, not loose
            c = json.loads(m["content"])
            for st in c.get("styles", []):
                if isinstance(st.get("font"), dict): st["font"]["path"] = font; st["font"]["id"] = ""
            m["content"] = json.dumps(c, ensure_ascii=False)
        if anim_durations:
            for ma in d["materials"].get("material_animations", []):
                for a in ma.get("animations", []):
                    if a.get("type") == "in" and a.get("name") in anim_durations:
                        a["duration"] = int(round(anim_durations[a["name"]] * US))
        for t in d["tracks"]:
            if t.get("name", "").startswith("img_"):
                for seg in t["segments"]:
                    seg["render_index"] = RI_IMG
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
        # Motion is a STRONG DEFAULT, never a gate she has to ask for — but "no push-in on my openers" is a
        # preference she can teach once instead of saying every reel.
        learning_context()
        if cut_placement.is_your_turn(globals().get("_JOB_DIR")):
            # her own CapCut timeline: every zoom and every still shot in it is her call, kept exactly
            print("[motion] your-turn cut — your own zooms and framing kept exactly, no default motion added")
        elif learned.get("motion.opener_zoom", True):
            _z, _p = capcut_motion.apply_default_motion(d)
            if _z or _p: print(f"[motion] intro zoom: {_z} · jump-cut punches: {_p}")
        else:
            print("[motion] opener push-in off (you taught me that) — say \"/learn forget\" to bring it back")
        # SCALE GUARDRAIL (locked): VectCut writes clip.scale but leaves uniform_scale.on=True (value hardcoded
        # 1.0), and uniform_scale OVERRIDES clip.scale — so every jump-cut zoom / b-roll inset silently renders at
        # 1.0 in CapCut. Turn uniform_scale OFF wherever a non-1.0 clip.scale or a scale keyframe is set.
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
        enforce_maintrack_ripple(d)                 # base guardrail: magnet ALL tracks + audio to main track
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
    print("CLEAN YAP built + registered:", name, "| tracks v/img/text:",
          sum(t["type"] == "video" for t in d["tracks"]), "/",
          sum(t.get("name", "").startswith("img_") for t in d["tracks"]), "/",
          sum(t["type"] == "text" for t in d["tracks"]))
