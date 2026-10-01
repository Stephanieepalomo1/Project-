#!/usr/bin/env python3
"""emoji-to-png.py — emoji as flat PNGs, so no graphic ever asks the renderer to draw a live one.

A raw emoji character in graphic markup stops the headless render dead: no error and no timeout, just a
font lookup that never returns while the build sits there looking busy (workflows/graphics-part-by-part.md
has the full story). So graphics never contain emoji characters. Either draw the shape in the brand
font, or bake the glyph here once and place the PNG as an image.

Each PNG is trimmed to the drawn pixels and then centred on a transparent square with the same margin on
every side, so it drops into a layout without nudging.

    python3 emoji-to-png.py <name>=<emoji> [<name>=<emoji> ...] [--out DIR]

    python3 emoji-to-png.py sparkle=✨ bolt=⚡ gift=🎁
    python3 emoji-to-png.py coffee=☕ --out ./assets/emoji

Writes <name>.png for every pair, into ./assets/emoji unless --out says otherwise.
"""
import os
import sys

for _stream in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Whichever color-emoji font this machine has; the first one found is used.
COLOR_FONTS = (
    "/System/Library/Fonts/Apple Color Emoji.ttc",         # macOS
    "C:\\Windows\\Fonts\\seguiemj.ttf",                    # Windows, Segoe UI Emoji
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",   # Linux, fonts-noto-color-emoji
)
# Apple's emoji font holds a handful of fixed bitmap sizes and refuses any other. 160 is its largest.
GLYPH_SIZE = 160
SCRATCH = 320          # the sheet each glyph is drawn on; a centred anchor rides high, so leave room
MARGIN_RATIO = 0.12    # margin put back around the trimmed ink, as a share of its longest side

NO_FONT = (
    "[emoji] This machine has no color-emoji font. macOS and Windows already ship one; on Linux or WSL,\n"
    "    get one with:  sudo apt install fonts-noto-color-emoji\n"
    "Or skip baking entirely and draw the shape in your brand font instead (see workflows/graphics-part-by-part.md)."
)


def requests(argv):
    """The (name, glyph) pairs asked for, in order, and the folder they go to.

    `--out` takes the word after it, whatever that word is; an `--out` with nothing after it is an
    IndexError. Anything else must be name=glyph, split at its first "=".
    """
    pairs, folder, skip = [], Path("assets/emoji"), False
    for at, token in enumerate(argv):
        if skip:
            skip = False
            continue
        if token == "--out":
            folder, skip = Path(argv[at + 1]), True
            continue
        name, sep, glyph = token.partition("=")
        if not sep:
            sys.exit(f"[emoji] every argument looks like name=emoji. This one does not: {token!r}")
        pairs.append((name, glyph))
    if pairs:
        return pairs, folder
    raise SystemExit(__doc__)   # nothing asked for: the usage at the top of this file is the answer


def color_font():
    """Path of the first color-emoji font on this machine, or None."""
    for path in COLOR_FONTS:
        if os.path.exists(path):
            return path
    return None


def stamp(glyph, font):
    """The glyph drawn in color, cut down to its ink, then centred on a square with an even margin."""
    sheet = Image.new("RGBA", (SCRATCH, SCRATCH), (0, 0, 0, 0))
    ImageDraw.Draw(sheet).text((SCRATCH // 2, SCRATCH // 2), glyph, font=font, anchor="mm",
                               embedded_color=True)
    box = sheet.getbbox()
    if box is None:
        sys.exit(f"[emoji] {glyph!r} drew nothing. Either it is not a real glyph, or this font has no "
                 f"color version of it.")
    ink = sheet.crop(box)
    longest = max(ink.width, ink.height)
    side = longest + 2 * int(round(longest * MARGIN_RATIO))
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(ink, ((side - ink.width) // 2, (side - ink.height) // 2), ink)
    return square


def main():
    pairs, folder = requests(sys.argv[1:])
    folder.mkdir(parents=True, exist_ok=True)
    font_path = color_font()
    if font_path is None:
        sys.exit(NO_FONT)
    font = ImageFont.truetype(font_path, GLYPH_SIZE)
    for name, glyph in pairs:
        png = stamp(glyph, font)
        png.save(folder / f"{name}.png")
        print(f"[emoji] {glyph} -> {name}.png ({png.width}x{png.height})")
    print("done ->", folder)


if __name__ == "__main__":
    main()
