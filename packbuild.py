#!/usr/bin/env python3
"""packbuild.py — CapCut-lane style-pack integration for superyap / cleanyap builds.

Maps a style pack (creative-vault/style-packs.json) -> CapCut text roles so a native, editable CapCut
draft renders in ANY pack. Returns per-role font_path + size + CASE + y-position + tracking. Sizes are
CapCut-native units (the pack was cloned from a CapCut mockup; VectCutAPI add_text `size` uses the same
scale, e.g. takeover ~26). Apply caseit() to the display text BEFORE add_text, and register each
{display_text: font_path} into finalize's font_map so the real font is patched in.

    from packbuild import role, caseit, accent_color
    sp = role("Editorial", "headline")   # -> {font_path, size, case, y, tracking}
    disp = caseit("here's the truth", sp["case"])

Engine roles: headline · takeover · thought · caption · accent.
"""
import os, sys, shutil, json
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
from PIL import ImageFont, ImageDraw, Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stylepack


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

WHITE = "#FFFFFF"
CANVAS_W = 1080
_MEAS = ImageDraw.Draw(Image.new("RGB", (8, 8)))

def wrap_for_canvas(text, font_path, capcut_size, maxw=860, px_per_unit=2.2, tracking=0.0):
    """Break `text` into lines that fit the CapCut canvas width at this font/size (CapCut runs text
    off-canvas otherwise). Returns text with \\n inserted. Larger fonts naturally get more breaks.
    px_per_unit CALIBRATED to CapCut's real rendering (2026-08-08, from the creator's manual hook edit:
    a 58-char hook at size 20 wraps to 2 wide lines, break after '...after i'). The old 6.0 was the MP4
    render scale, ~3x too big for CapCut, so hooks over-broke into narrow lines / cramped boxes."""
    px = max(8, round(capcut_size * px_per_unit))
    try:
        f = ImageFont.truetype(font_path, px)
    except Exception:
        return text
    tr = tracking * px                          # letter-spacing per gap; negative = tighter = more fits/line
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        width = _MEAS.textlength(t, font=f) + tr * max(0, len(t) - 1)   # account for tracking
        if width <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)
# CapCut only renders fonts whose FILES live in its own font dir. Point font_path here (copy if needed).
CAPCUT_FONTS = _capcut_fonts_dir()

def capcut_font_path(src):
    """Resolve a pack font file to a path CapCut can actually load (its Library/Fonts, or a system font)."""
    if src.startswith("/System/"):
        return src                                  # system font — CapCut loads directly
    import capcut_userfonts
    # Name the copy by the font's OWN family, never the source basename: catalog fonts all cache as the
    # generic 'font.ttf', so a basename-named copy would collide in Library/Fonts and silently render one
    # font with another's glyphs (round 11 Bug A). stable_basename makes the destination unique per font.
    dst = os.path.join(CAPCUT_FONTS, capcut_userfonts.stable_basename(src))
    if not os.path.exists(dst):
        try: shutil.copy(src, dst)
        except Exception: pass
    return dst

# engine role -> pack element key
ROLE_ELEM = {
    "headline": "headline",
    "takeover": "takeover",
    "thought":  "thought_bubble",
    "caption":  "caption",
    "accent":   "accent_caption",
}

def caseit(text, case):
    return text.upper() if case == "upper" else (text.title() if case == "title" else text.lower())

def role(pack, r):
    """Full CapCut spec for an engine role in a pack: font_path (abs), size (CapCut units), case, y, tracking."""
    if r not in ROLE_ELEM:   # was a bare KeyError('nosuchrole') — name the valid roles instead
        raise KeyError(f"unknown engine role {r!r}; have {list(ROLE_ELEM)}")
    e = stylepack.element(pack, ROLE_ELEM[r])
    return {"font_path": capcut_font_path(e["file"]), "size": int(round(e["size"])), "case": e["case"],
            "y": e["y"], "tracking": e["tracking"], "line_height": e["line_height"],
            "bold": bool(e.get("bold", False)), "step": e.get("step")}

def saved_accent():
    """The buyer's saved default accent (hex) from creative-vault/user-style.json, or None if unset.
    Chosen at onboarding, changed anytime via '/studio accent <color>'."""
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "user-style.json")
        return (json.load(open(p, encoding="utf-8")).get("default_accent") or None)
    except Exception:
        return None

def accent_color(pack):
    """The CLIENT's accent/highlight color for this pack. Accents are always the buyer's chosen color,
    NEVER the creator's personal butter (locked). Resolution order: the buyer's saved default_accent →
    per-pack `accent_color` → global default → **white** (neutral fallback, never an imposed yellow — the
    buyer picks their accent, same as fonts, see personal fonts vs ship fonts). A per-reel accent is
    passed explicitly by the caller and wins over all of these; the creator's own reels pass butter that way."""
    d = stylepack._data()
    packs = d.get("packs", {})
    return saved_accent() or packs.get(pack, {}).get("accent_color") or d.get("accent_color", {}).get("default") or "#FFFFFF"

def names():
    return stylepack.names()

if __name__ == "__main__":
    for p in names():
        print(p, "accent_color", accent_color(p))
        for r in ("headline", "takeover", "thought", "caption", "accent"):
            s = role(p, r)
            print(f"   {r:9s} sz={s['size']:<3} case={s['case']:<6} y={s['y']:<6} {os.path.basename(s['font_path'])}")
