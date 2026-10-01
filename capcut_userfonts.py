#!/usr/bin/env python3
"""capcut_userfonts.py — resolve a font NAME to a real file on this machine, using CapCut's own font map.

Why: the animated engine (HyperFrames @font-face) needs the font FILE to render type outside CapCut.
CapCut already downloads every font the user adds — cloud-library fonts to
`…/User Data/Cache/effect/<id>/<hash>/font.ttf`, imported ones to the container `Library/Fonts/` — and
records them ALL in `…/User Data/Config/userFontData` as `<Font Name>=<absolute path>` (names URL-encoded).
So the engine can animate ANY font the buyer has in CapCut (premium / proprietary / free) WITHOUT us
shipping the file: the buyer adds it in CapCut once, and we read userFontData to find it.

Resolution order for a font (most reliable first):
  1) a bundled OFL file we ship (redistributable, machine-independent) — caller passes it
  2) CapCut's userFontData map (the buyer added the font in CapCut)
  3) CapCut's Library/Fonts by basename guess
  4) CapCut's in-app catalog cache (a font added via CapCut's text-panel search downloads to
     …/User Data/Cache/effect/<resource id>/<hash>/font.ttf, keyed by an opaque numeric id, not the
     name — so we open each cached file and read its REAL family name to match)
Returns None if the font isn't obtainable, so the caller can fall back to a pack default.
"""
import os, glob
from urllib.parse import unquote

try:  # PIL is a hard dependency of the engine; guard the import so the resolver still works if it's absent
    from PIL import ImageFont
except Exception:                       # pragma: no cover
    ImageFont = None

if os.name == "nt":
    # com.lemon.lvoverseas is a macOS app-sandbox container path and has no Windows equivalent;
    # the Windows CapCut data root is simply %LocalAppData%\CapCut.
    _DATA    = os.environ["LOCALAPPDATA"]
    _USERFD  = os.path.join(_DATA, "CapCut/User Data/Config/userFontData")
    # No per-app Fonts container on Windows -- point at a path that never exists so that lookup stage
    # cleanly falls through to the catalog scan below.
    _LIBFON  = os.path.join(_DATA, "CapCut/_no_container_fonts")
    _CATALOG = os.path.join(_DATA, "CapCut/User Data/Cache/effect")
else:
    _DATA   = os.path.expanduser("~/Library/Containers/com.lemon.lvoverseas/Data")
    _USERFD = os.path.join(_DATA, "Movies/CapCut/User Data/Config/userFontData")
    _LIBFON = os.path.join(_DATA, "Library/Fonts")
    # Fonts the buyer adds through CapCut's in-app catalog (search-and-add in the text panel) download here,
    # one folder per font keyed by an opaque numeric resource id, with the file always literally `font.ttf`.
    _CATALOG = os.path.join(_DATA, "Movies/CapCut/User Data/Cache/effect")
# Buyer's manual escape hatch: font_name -> file path, written by product/capcut_font_doctor.py when
# CapCut auto-resolution fails for some reason. Consulted right after the bundled OFL file, before CapCut.
_OVERRIDES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "creative-vault", "font-overrides.json")


def load_overrides():
    """Parse the hand-map file -> {lowercased font name: path}. Empty if absent/malformed."""
    import json
    try:
        with open(_OVERRIDES, encoding="utf-8") as fh:
            return {str(k).strip().lower(): v for k, v in json.load(fh).items()}
    except (FileNotFoundError, ValueError):
        return {}


def load_user_fonts():
    """Parse CapCut's userFontData ini -> {lowercased font name: absolute file path}."""
    out = {}
    try:
        with open(_USERFD, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("[") or "=" not in line:
                    continue
                name, _, path = line.partition("=")
                name = unquote(name.strip())
                path = path.strip()
                if not path or name.lower() == "order":
                    continue
                out.setdefault(name.lower(), path)
    except FileNotFoundError:
        pass
    return out


def _norm(name):
    """Match key for a font name: lowercased with surrounding/internal whitespace collapsed."""
    return " ".join((name or "").split()).lower()


def font_family(path):
    """The font file's own embedded family name (e.g. 'Bloop'), or None. Guarded — PIL is optional and a
    file may be unreadable. The one collision-proof identity a catalog-cached font has (its folder is an
    opaque id and its filename is often the generic 'font.ttf')."""
    if ImageFont is None or not path or not os.path.exists(path):
        return None
    try:
        return ImageFont.truetype(path, 40).getname()[0] or None
    except Exception:
        return None


def stable_basename(src):
    """A COLLISION-PROOF filename to copy `src` under into CapCut's Library/Fonts. The source basename is
    NOT safe any more: every font added through CapCut's in-app catalog caches as the generic 'font.ttf',
    so two different fonts would copy onto the SAME name and silently alias each other (round 11 Bug A).
    Derive the name from the font's own embedded family instead (spaces stripped, so it stays close to the
    pack's expected filenames like Bloop.ttf / SoupDuJour.ttf), falling back to the source basename only
    when PIL cannot read the family."""
    fam = font_family(src)
    if fam:
        safe = "".join(c for c in fam if c.isalnum() or c in "-_") or "font"
        return f"{safe}{os.path.splitext(src)[1] or '.ttf'}"
    return os.path.basename(src)


_catalog_cache = None

# Some catalog fonts cache MULTIPLE variants under the SAME embedded family name, differing only by
# subfamily (e.g. Soup Du Jour "Solid" vs its hollow/regular cut). Keyed by family name alone, whichever
# folder sorts first wins by luck — which handed the buyer the wrong variant. For a known-ambiguous family,
# prefer the named subfamily. Extend as new collisions turn up. capcut catalog font scan
_PREFERRED_SUBFAMILY = {"soup du jour": "solid"}


def scan_capcut_catalog_fonts(container=None):
    """Index every font CapCut's in-app catalog has downloaded, keyed by the font's REAL family name.

    A catalog-added font is cached at …/Cache/effect/<resource id>/<hash>/<file>. The folder is keyed by an
    opaque numeric id (not the font name) and the file is often the generic `font.ttf` but can also carry a
    descriptive name (e.g. `Ugly-Dave-Alternates.otf`), so we glob ANY .ttf/.otf there — NOT just `font.*`,
    which silently missed the descriptively-named ones — and read each file's real family name via PIL.
    When two files share a family name, a `_PREFERRED_SUBFAMILY` entry picks the right variant instead of
    alphabetical luck. Returns {normalized family name: path}. Cached within a run; skips unopenable files."""
    global _catalog_cache
    default = container is None
    if default and _catalog_cache is not None:
        return _catalog_cache
    root = container or _CATALOG
    variants = {}   # normalized family -> [(subfamily_lower, path), ...]
    if ImageFont is not None:
        for path in sorted(glob.glob(os.path.join(root, "*", "*", "*.ttf")) +
                           glob.glob(os.path.join(root, "*", "*", "*.otf"))):
            try:
                fam, sub = ImageFont.truetype(path, 40).getname()
            except Exception:
                continue
            if fam:
                variants.setdefault(_norm(fam), []).append(((sub or "").strip().lower(), path))
    found = {}
    for nfam, vs in variants.items():
        pref = _PREFERRED_SUBFAMILY.get(nfam)
        chosen = next((p for s, p in vs if s == pref), None) if pref else None
        found[nfam] = chosen or vs[0][1]   # preferred subfamily if present, else first (sorted) path
    if default:
        _catalog_cache = found
    return found


def resolve_font_file(name, bundled_file=None):
    """Return a real font-file path for `name`, or None. `bundled_file` (an assets/fonts path) wins if it
    exists — that's the shippable OFL case. Otherwise fall back to what CapCut has on the machine."""
    if bundled_file and os.path.exists(bundled_file):
        return bundled_file
    # buyer's hand-map wins over CapCut auto-resolution (their explicit fix when auto fails)
    ov = load_overrides().get((name or "").strip().lower())
    if ov:
        ov = os.path.expanduser(ov)
        if os.path.exists(ov):
            return ov
    p = load_user_fonts().get((name or "").strip().lower())
    if p and os.path.exists(p):
        return p
    if name:
        for cand in (name, name.replace(" ", ""), name.replace(" ", "-"), name.replace(" ", "_")):
            for ext in (".ttf", ".otf", ".ttc"):
                fp = os.path.join(_LIBFON, cand + ext)
                if os.path.exists(fp):
                    return fp
        # last resort: a font added via CapCut's in-app catalog is cached by an opaque id (not by name),
        # so the by-name checks above all miss it. Match on the cached file's real family name instead.
        cp = scan_capcut_catalog_fonts().get(_norm(name))
        if cp and os.path.exists(cp):
            return cp
    return None


def source_of(name, bundled_file=None):
    """Human-readable where-from for a resolved font: 'bundled' | 'capcut' | 'libfonts' | 'MISSING'."""
    if bundled_file and os.path.exists(bundled_file):
        return "bundled"
    p = resolve_font_file(name, None)
    if not p:
        return "MISSING"
    return "capcut" if "/Cache/effect/" in p else "libfonts"


if __name__ == "__main__":
    um = load_user_fonts()
    print(f"userFontData: {len(um)} fonts CapCut has on this machine")
    for k, v in um.items():
        where = "cloud-cache" if "/Cache/effect/" in v else "lib-fonts"
        print(f"  {k:20s} [{where}] {os.path.basename(v)}")
