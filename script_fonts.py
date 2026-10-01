#!/usr/bin/env python3
"""script_fonts.py — Cyrillic letters in a pack font that has none.

Most pack faces draw only the Latin alphabet. Handed a Bulgarian (or Russian, Ukrainian, Serbian...) word,
the headless browser that renders every graphic finds no glyph and quietly borrows the letter from a system
font, usually a serif, so a caption comes out half Poppins and half Times. Nothing errors.

The fix is the ordinary web one: a second @font-face under the SAME family name, limited by unicode-range
to Cyrillic and declared after the pack's, so the browser draws Cyrillic letters from a bundled face that
has them and every other letter from the pack face, exactly as before. The companion is picked to suit the
face it stands in for (handwritten for a script face, serif for a serif, Inter at the nearest weight for
the rest), read from the font file's own name, since pack faces leave their style metadata blank.

It only acts when the page actually shows Cyrillic AND a face on it lacks some of those letters. Anything
else comes back byte for byte as it went in, so a reel in English renders exactly as it always did.

    import script_fonts
    html, notes = script_fonts.add_companions(html, comp_dir)   # before writing index.html
    python3 product/script_fonts.py <composition_dir>            # patch an index.html in place
"""
import os, re, shutil, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "assets", "fonts")
MARK = "/* cyrillic-companions */"
RANGE = "U+0400-052F,U+1C80-1C8F,U+2DE0-2DFF,U+A640-A69F"
_CYR = re.compile("[Ѐ-ԯᲀ-᲏ⷠ-ⷿꙀ-ꚟ]")

# What a face is, from its own family name (letters only, lowercased, matched as a prefix). Anything not
# listed is treated as a sans and gets Inter at its weight.
_KIND = [
    ("prosecco", "hand"), ("pinyon", "hand"), ("uglydave", "hand"), ("caveat", "hand"), ("bloop", "hand"),
    ("playfair", "serif"), ("instrumentserif", "serif"),
    ("soupdujour", "display"), ("shrikhand", "display"), ("advercase", "display"), ("zymodern", "display"),
]


def _companion(kind, weight):
    """The bundled face that draws Cyrillic in place of a face of this kind and weight."""
    if kind == "hand":
        return "Caveat-VF.ttf"
    if kind == "serif":
        return "PlayfairDisplay-SemiBold.ttf" if weight >= 550 else "PlayfairDisplay-VF.ttf"
    if kind == "display" or weight >= 800:
        return "Inter-Black.otf"
    return "Inter-Bold.otf" if weight >= 550 else "Inter-Regular.otf"


# ── just enough of the font file format to answer three questions: name, weight, which letters ──────────
def _tables(data):
    off = struct.unpack(">I", data[12:16])[0] if data[:4] == b"ttcf" else 0   # a collection: its first font
    n = struct.unpack(">H", data[off + 4:off + 6])[0]
    t = {}
    for i in range(n):
        r = off + 12 + 16 * i
        t[data[r:r + 4].decode("latin-1")] = struct.unpack(">II", data[r + 8:r + 16])
    return t


def _codepoints(data, t):
    if "cmap" not in t:
        return set()
    base = t["cmap"][0]
    subs = {}
    for i in range(struct.unpack(">H", data[base + 2:base + 4])[0]):
        pid, eid, so = struct.unpack(">HHI", data[base + 4 + 8 * i:base + 12 + 8 * i])
        subs[(pid, eid)] = base + so
    for key in ((3, 10), (0, 6), (0, 4), (3, 1), (0, 3), (0, 2), (0, 1), (0, 0)):
        if key not in subs:
            continue
        s = subs[key]
        fmt = struct.unpack(">H", data[s:s + 2])[0]
        out = set()
        if fmt == 12:
            for g in range(struct.unpack(">I", data[s + 12:s + 16])[0]):
                a, b, gid = struct.unpack(">III", data[s + 16 + 12 * g:s + 28 + 12 * g])
                out.update(range(a + (gid == 0), b + 1))   # glyph 0 is "no glyph"
            return out
        if fmt == 4:
            seg = struct.unpack(">H", data[s + 6:s + 8])[0] // 2
            ends, starts = s + 14, s + 16 + 2 * seg
            deltas, ranges = starts + 2 * seg, starts + 4 * seg
            for k in range(seg):
                e = struct.unpack(">H", data[ends + 2 * k:ends + 2 * k + 2])[0]
                st = struct.unpack(">H", data[starts + 2 * k:starts + 2 * k + 2])[0]
                d = struct.unpack(">h", data[deltas + 2 * k:deltas + 2 * k + 2])[0]
                ro_at = ranges + 2 * k
                ro = struct.unpack(">H", data[ro_at:ro_at + 2])[0]
                for c in range(st, min(e, 0xFFFE) + 1):
                    if ro == 0:
                        gid = (c + d) & 0xFFFF
                    else:
                        at = ro_at + ro + 2 * (c - st)
                        gid = struct.unpack(">H", data[at:at + 2])[0]
                        gid = (gid + d) & 0xFFFF if gid else 0
                    if gid:
                        out.add(c)
            return out
    return set()


def _family(data, t):
    if "name" not in t:
        return ""
    base = t["name"][0]
    count, strings = struct.unpack(">HH", data[base + 2:base + 6])
    found = {}
    for i in range(count):
        pid, eid, lid, nid, ln, off = struct.unpack(">HHHHHH", data[base + 6 + 12 * i:base + 18 + 12 * i])
        if nid in (1, 16) and nid not in found:
            raw = data[base + strings + off:base + strings + off + ln]
            try:
                found[nid] = raw.decode("utf-16-be") if pid in (0, 3) else raw.decode("mac_roman")
            except UnicodeDecodeError:
                pass
    return found.get(16) or found.get(1) or ""


_info = {}


def face_info(path):
    """(family name, weight, set of code points) for a font file, cached. None if it cannot be read."""
    if path not in _info:
        try:
            with open(path, "rb") as f:
                data = f.read()
            t = _tables(data)
            weight = struct.unpack(">H", data[t["OS/2"][0] + 4:t["OS/2"][0] + 6])[0] if "OS/2" in t else 400
            _info[path] = (_family(data, t), weight or 400, _codepoints(data, t))
        except Exception:
            _info[path] = None
    return _info[path]


def companion_for(path, letters):
    """The bundled file to draw `letters` in, when the face at `path` lacks any of them. None when it
    covers them all, or when it cannot be read (then nothing is changed)."""
    info = face_info(path)
    if not info or {ord(c) for c in letters} <= info[2]:
        return None
    name = "".join(c for c in info[0].lower() if c.isalnum())
    kind = next((k for p, k in _KIND if name.startswith(p)), "sans")
    return os.path.join(FONTS, _companion(kind, info[1]))


def split(path, text):
    """[(font file, run of text)]: how the browser will draw `text` set in the face at `path`, so a width
    can be measured on the letters actually drawn. A face lacking the Cyrillic letters in `text` hands those
    runs to its companion; every other case is the one run [(path, text)], exactly as before."""
    letters = set(_CYR.findall(text or ""))
    comp = companion_for(path, letters) if letters and path else None
    if not comp:
        return [(path, text)]
    runs = []
    for ch in text:
        p = comp if _CYR.match(ch) else path
        if runs and runs[-1][0] == p:
            runs[-1] = (p, runs[-1][1] + ch)
        else:
            runs.append((p, ch))
    return runs


def pil_width(font, text):
    """Width of `text` on a loaded PIL font once any Cyrillic it lacks comes from its companion, or None
    when nothing needs a companion (then measure as usual)."""
    parts = split(getattr(font, "path", None), text)
    if len(parts) == 1:
        return None
    from PIL import ImageFont
    return sum(ImageFont.truetype(p, font.size).getlength(s) for p, s in parts)


# ── the page ───────────────────────────────────────────────────────────────────────────────────────────
_FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.I)


def _desc(body, name):
    m = re.search(name + r"\s*:\s*([^;]+)", body, re.I)
    return m.group(1).strip() if m else None


def add_companions(html, comp_dir):
    """Return (html, notes). Adds a Cyrillic companion after each @font-face whose file lacks letters the
    page shows. Unchanged (and notes empty) when the page has no Cyrillic, or has been through here."""
    if MARK in html:
        return html, []
    letters = set(_CYR.findall(html))
    if not letters:
        return html, []
    rules, notes, done = [], [], set()
    for m in _FACE.finditer(html):
        body = m.group(1)
        fam = (_desc(body, "font-family") or "").strip("'\" ")
        url = re.search(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", body)
        if not fam or not url or _desc(body, "unicode-range"):
            continue
        src = url.group(1)
        src = src[7:] if src.startswith("file://") else src
        path = src if os.path.isabs(src) else os.path.join(comp_dir, src)
        comp = companion_for(path, letters) if os.path.exists(path) else None
        if not comp or not os.path.exists(comp):
            continue
        rel = "fonts/cyr-" + os.path.basename(comp)
        os.makedirs(os.path.join(comp_dir, "fonts"), exist_ok=True)
        dst = os.path.join(comp_dir, rel)
        if not os.path.exists(dst):
            shutil.copy(comp, dst)
        extra = "".join(f"{d}:{_desc(body, d)};" for d in ("font-weight", "font-style") if _desc(body, d))
        rules.append(f"@font-face{{font-family:'{fam}';src:url('{rel}');unicode-range:{RANGE};{extra}}}")
        key = (face_info(path)[0], os.path.basename(comp))
        if key not in done:
            done.add(key)
            notes.append(f"Cyrillic letters in {key[0] or os.path.basename(path)} are drawn from "
                         f"{os.path.splitext(key[1])[0]}, since that font has none of its own.")
    if not rules:
        return html, []
    block = MARK + "\n" + "\n".join(rules) + "\n"
    at = html.find("</style>")
    html = html[:at] + block + html[at:] if at >= 0 else html.replace("</head>", f"<style>{block}</style></head>", 1)
    return html, notes


def patch_dir(comp_dir):
    """Apply add_companions to <comp_dir>/index.html in place; print what it did. Returns the notes."""
    index = os.path.join(comp_dir, "index.html")
    if not os.path.exists(index):
        return []
    with open(index, encoding="utf-8") as f:
        html = f.read()
    new, notes = add_companions(html, comp_dir)
    if new != html:
        with open(index, "w", encoding="utf-8") as f:
            f.write(new)
    for n in notes:
        print(f"  {n}")
    return notes


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: script_fonts.py <composition_dir>")
    patch_dir(sys.argv[1])
