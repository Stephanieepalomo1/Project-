#!/usr/bin/env python3
"""stylepack.py — load a swappable font STYLE PACK for either build (kinetic or CapCut).

A pack = 3 fonts by role (main/accent/caption) at LOCKED per-element formats, cloned from the creator's CapCut
mockup → product/creative-vault/style-packs.json. Both engines call this so a reel builds identically in
any pack. Users can also build their OWN pack (pick 3 fonts) — see font-picking-guardrails.md.

    from stylepack import load, element
    p = load("Editorial")                 # -> pack dict
    e = element("Editorial", "headline")  # -> {font,file(abs),size,tracking,line_height,y}

Element types: headline · takeover · caption · thought_bubble · accent_caption.
"""
import json, os
import sys
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, "product", "creative-vault", "style-packs.json")

LOCAL_SPEC = os.path.join(ROOT, "_local", "style-packs.json")

def _data():
    """The shipped packs, with any LOCAL packs merged over the top.

    A creator's own pack is personal: her licensed faces and her palette. It must never land in a
    buyer's bundle, so it lives in `_local/style-packs.json` (git-ignored, never staged by
    make-ship) and is merged here. This is also the supported route for a buyer who builds their
    own pack rather than picking one of the shipped three - same file, same shape.
    """
    data = json.load(open(SPEC, encoding="utf-8"))
    if os.path.exists(LOCAL_SPEC):
        local = json.load(open(LOCAL_SPEC, encoding="utf-8"))
        data.setdefault("packs", {}).update(local.get("packs", {}))
    return data

def names():
    """List available pack names (all in the launch kit)."""
    return list(_data()["packs"].keys())

def load(pack):
    d = _data()
    if pack not in d["packs"]:
        raise KeyError(f"unknown style pack {pack!r}; have {list(d['packs'])}. If it is a pack you built, an "
                       f"engine update may have removed it; bring it back with: python3 product/pack_persist.py recover")
    return d["packs"][pack]

def _abs(fileref):
    """Resolve a font file reference to an absolute path (handles SYSTEM: + assets/fonts).

    A blank reference is not a file, and resolves to "" (a path that never exists). Packs built by
    /studio recipe leave `file` blank on purpose, and frame_to_pack does for a font not added yet, so the
    font resolves BY NAME at build time. Joined onto assets/fonts, a blank used to come back as the fonts
    FOLDER, which exists: the name lookup and the fallback in element() never ran, and the text rendered in
    the browser's default typeface with nothing said."""
    if not fileref:
        return ""
    if fileref.startswith("SYSTEM:"):
        return _data()["system_fonts"][fileref[len("SYSTEM:"):]]
    return os.path.join(ROOT, "assets", "fonts", fileref)

# A pack may name a font that is NOT on this machine. The paid faces (script/display/handwritten) do not
# ship as files: they live in CapCut, added once from its font panel, and resolve from there by name.
# The BAKED lane renders in a headless browser, which cannot see CapCut's fonts and needs a real file. With
# no file the @font-face silently resolves to a browser default, so the reel renders in the WRONG typeface
# and nothing errors. A wrong-looking reel that shipped is worse than a loud failure.
# So: fall back to a BUNDLED face chosen to suit the role, and always render something intentional. A pack
# can name its own substitute per element via "fallback_file". The fallback stays (failing instead would stop
# every Editorial, Butter and Playful build on a buyer machine that has not added those faces in CapCut
# yet), but it is never quiet and never "fine": the stand-in is not part of the pack, so the message names
# the pack font that is missing, says the text will not have the pack's look, and says how to add it.
_ROLE_FALLBACK = {
    "headline":       "PlayfairDisplay-VF.ttf",
    "takeover":       "PlayfairDisplay-VF.ttf",
    "caption":        "Poppins-SemiBold.ttf",
    "thought_bubble": "PinyonScript-Regular.ttf",
    "accent_caption": "PinyonScript-Regular.ttf",
}
_warned = set()
_told_how = set()


def _how_to_add(pack, font):
    """The one plain line on how to get a missing pack font, said once per pack + font."""
    key = (pack, font)
    if key in _told_how:
        return ""
    _told_how.add(key)
    try:
        import capcut_font_doctor   # CapCut lists a few fonts under another name (Soup Du Jour -> "Solid")
        search = capcut_font_doctor._CAPCUT_SEARCH_NAME.get((font or "").strip().lower()) or font
    except Exception:
        search = font
    lic = {"pro": "; it comes with CapCut Pro", "free": "; it is free in CapCut"}.get(
        _FONT_LICENSE.get((font or "").strip().lower()), "")
    return (f"\n    To get it: add '{font}' in CapCut once (search '{search}' in the text panel{lic}), or point "
            f"the engine at a font file you have: python3 product/capcut_font_doctor.py --map "
            f"\"{font}=/path/to/the/font\"")


def element(pack, kind):
    """Full spec for one element in a pack: font, abs file path, size, tracking, line_height, y.

    A missing face falls back to a bundled stand-in (see above) and says so. The only path returned that
    does not exist is when that bundled stand-in is missing too, and that is said loudly as well."""
    raw = dict(load(pack)["elements"][kind])
    e = dict(raw)
    e["file"] = _abs(e["file"])
    if not os.path.exists(e["file"]):
        # Before falling back, try the SAME resolver the CapCut lanes use — it finds a font the buyer added
        # in CapCut's own catalog (cached under an opaque id as font.ttf) by its real family name. This is
        # what closes the RAW-vs-BAKED gap: CapCut draws Bloop from the buyer's library in the editable lane,
        # so the baked lane must be able to find that SAME cached file instead of dropping to Coolvetica.
        # capcut catalog font scan — the font-cache scan lives in capcut_userfonts.resolve_font_file.
        try:
            import capcut_userfonts
            real = capcut_userfonts.resolve_font_file(raw.get("font"), None)
        except Exception:
            real = None
        if real and os.path.exists(real):
            e["file"] = real
            return e
        sub = raw.get("fallback_file") or _ROLE_FALLBACK.get(kind, "Poppins-SemiBold.ttf")
        sub_path = _abs(sub)
        e["requested_font"] = raw.get("font")
        e["fallback"] = True
        key = (pack, kind, raw.get("font"))
        if os.path.exists(sub_path):
            e["file"] = sub_path
            e["font"] = os.path.splitext(os.path.basename(sub))[0]
            if key not in _warned:
                _warned.add(key)
                print(f"  ⚠ {pack}/{kind}: the {pack} pack's font '{raw.get('font')}' was not found on this computer, so "
                      f"the stand-in '{e['font']}' is used in its place. The stand-in is not part of the pack, so "
                      f"this text will not have the {pack} look.{_how_to_add(pack, raw.get('font'))}")
        else:
            e["fallback_missing"] = True
            if key not in _warned:
                _warned.add(key)
                print(f"  ⚠ {pack}/{kind}: the {pack} pack's font '{raw.get('font')}' was not found on this computer, and "
                      f"its bundled stand-in '{sub}' is missing from assets/fonts too, so this text has no font "
                      f"file and will show in a default typeface.{_how_to_add(pack, raw.get('font'))}")
    return e

def audit(pack=None):
    """Which elements would fall back on THIS machine. Returns [(pack, kind, requested, using)]."""
    out = []
    for pk in ([pack] if pack else names()):
        for kind in load(pk)["elements"]:
            e = element(pk, kind)
            if e.get("fallback"):
                out.append((pk, kind, e.get("requested_font"), e.get("font")))
    return out

# How each non-bundled pack font is added, for the honest delivery note (source of truth = the `licensing`
# note in style-packs.json). "pro" = a paid face that comes with CapCut Pro; "free" = a no-cost face the
# buyer adds from CapCut's font panel (never call these "Pro" — Bloop/Ugly Dave are free; bloop is free).
_FONT_LICENSE = {
    "prosecco and baguette": "pro", "prosecco": "pro", "soup du jour": "pro",
    "bloop": "free", "ugly dave": "free",
}

def delivery_font_note(pack):
    """Warm, buyer-facing HANDOFF note for when a pack's premium font will NOT render on this buyer's
    machine and a replacement is used instead. Returns the message string, or None when every pack font
    resolves (a CapCut Pro buyer, or one who already added the free face) so nothing needs saying.

    Honest by design: it only fires for fonts that genuinely do not resolve for THIS buyer (checked through
    the same resolver every build uses, so a Pro user who has the font is never nagged), and it says the
    RIGHT fix per font — "comes with CapCut Pro" for a paid face, "free to add in CapCut" for a free one,
    and no claim either way for a font of a pack she built (the engine cannot know its plan).
    No em dashes (buyer-facing). Surfaced at delivery by the CapCut-export handoff. See QA-log item #14."""
    try:
        import capcut_userfonts as cu
    except Exception:
        cu = None
    data = load(pack)
    subs, seen = [], set()                       # (requested, substitute, license) per distinct requested font
    for kind, raw in data["elements"].items():
        requested = raw.get("font")
        if not requested or requested in seen:
            continue
        bundled = _abs(raw.get("file"))
        resolved = (cu.resolve_font_file(requested, bundled if os.path.exists(bundled) else None)
                    if cu else (bundled if os.path.exists(bundled) else None))
        if resolved:                             # ships bundled, or the buyer has it in CapCut — nothing to say
            continue
        seen.add(requested)
        e = element(pack, kind)                  # what substitute actually renders
        subs.append((requested, e.get("font"), _FONT_LICENSE.get(requested.strip().lower())))
    if not subs:
        return None
    lines = [f"A quick heads up on fonts for your **{pack}** pack:"]
    for requested, sub, lic in subs:
        if lic == "pro":
            lines.append(f"- **{requested}** comes with CapCut Pro, and it looks like it is not on your "
                         f"setup yet, so I used **{sub}** in its place. It still looks clean. If you would "
                         f"rather have the exact pack look, add {requested} in CapCut with Pro, or just tell "
                         f"me another font you would like and I will swap it.")
        elif lic == "free":
            lines.append(f"- **{requested}** is free in CapCut but is not added on your machine yet, so I "
                         f"used **{sub}** for now. To get the real look, add {requested} in CapCut (it is "
                         f"free, no Pro needed), or tell me another font you would prefer and I will use it.")
        else:   # a font of her own pack's choosing: whether CapCut carries it, and on which plan, is unknown
            lines.append(f"- **{requested}** is not added in CapCut on your machine yet, so I used **{sub}** "
                         f"for now. To get the real look, add {requested} in CapCut, or tell me another font "
                         f"you would prefer and I will use it.")
    return "\n".join(lines)

def roles(pack):
    """{main, accent, caption} font names for the pack."""
    return load(pack)["fonts"]

# LEGIBILITY FLOOR (Layer 1, locked 2026-09-09): rendered text over footage ALWAYS carries a soft drop
# shadow so it stays readable on any footage. It is a RULE, not a style choice — a pack may TUNE the shadow
# value (its `welldone.text_shadow`) but can never remove it. A pack that declares none gets the HyperFrames
# white-on-video default. There is deliberately NO on/off toggle: legibility is not optional (the creator:
# "regardless of style pack, there should be a soft drop shadow behind all text you render").
HF_TEXT_SHADOW = "0 6px 32px rgba(0,0,0,.55)"   # HyperFrames default (composition-patterns.md) — soft + wide

def text_shadow(pack):
    """The drop-shadow VALUE for a pack's rendered text over footage — always a REAL shadow, never 'none'.
    The pack's own `welldone.text_shadow` when declared (a pack TUNES the floor), else the HyperFrames floor."""
    p = _data().get("packs", {}).get(pack, {})
    return p.get("text_shadow") or (p.get("welldone") or {}).get("text_shadow") or HF_TEXT_SHADOW

if __name__ == "__main__":
    for p in names():
        r = roles(p)
        print(f"{p:10s} main={r['main']:20s} accent={r['accent']:20s} caption={r['caption']}")
        for k in ("headline", "takeover", "caption", "thought_bubble", "accent_caption"):
            e = element(p, k)
            ok = "✓" if os.path.exists(e["file"]) else "✗MISSING"
            print(f"   {k:15s} {e['font']:22s} sz={e['size']:<3} trk={e['tracking']:<5} lnH={e['line_height']:<6} y={e['y']:<5} {ok}")


def font_box_ratio(font_file, default=1.0):
    """(ascent + descent) / font-size for a face — the height of the box a browser gives ONE line.

    Stacked display type (the takeover word-stack) needs a line-height at least this tall or adjacent
    word boxes overlap and `hyperframes check` fails with content_overlap. The value is a property of
    the FONT, not a taste call: Soup Du Jour is 1.00, Inter 1.22, Playfair 1.34, Anton 1.51. A constant
    floor tuned against one face silently collides under a taller one.

    Falls back to `default` when PIL is unavailable or the file will not open, so a build never dies
    over a metric it can do without.
    """
    try:
        from PIL import ImageFont
        a, d = ImageFont.truetype(font_file, 200).getmetrics()
        return (a + d) / 200.0
    except Exception:
        return default


def font_ink_ratio(font_file, sample="hgxy Hd", default=0.72):
    """Height of the actual INK for `sample`, as a fraction of font-size.

    The floor for a deliberately tight line-height: type may be set tighter than its box (that is how
    stacked display type reads as one unit) but never tighter than its own ink, or ascenders and
    descenders of neighbouring lines physically cross. Soup Du Jour is 0.68, Anton 0.98 — a constant
    tuned on the first collides under the second.
    """
    try:
        from PIL import ImageFont
        bb = ImageFont.truetype(font_file, 200).getbbox(sample)
        return (bb[3] - bb[1]) / 200.0
    except Exception:
        return default
