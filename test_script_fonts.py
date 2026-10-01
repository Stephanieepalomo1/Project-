#!/usr/bin/env python3
"""Regression guard for script_fonts — Cyrillic on screen in a pack face that has none.

The bug this locks down: a Bulgarian reel set in a Latin-only pack face (Poppins, Prosecco, Soup Du Jour)
rendered its Cyrillic letters in whatever system font the browser borrowed, usually a serif, and the text
was sized by measuring placeholder boxes, so a Playful takeover ran 200px off the frame. Nothing errored.

What must hold: an English page comes back byte for byte; a Cyrillic page gains a unicode-range companion
for each face that lacks the letters and none for a face that has them; the companion suits the face; and
text is measured on the face that will actually draw it. Only fonts that ship are used, so this passes on
a buyer machine too.

Run: python3 product/tests/test_script_fonts.py
"""
import os, sys, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import script_fonts as SF
import hooksplit

FONTS = SF.FONTS
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def page(text, faces):
    rules = "".join(f"@font-face{{font-family:'{fam}';src:url('fonts/{f}');}}" for fam, f in faces)
    return f"<html><head><style>{rules}\nbody{{}}</style></head><body><div>{text}</div></body></html>"


def comp_dir(faces):
    d = tempfile.mkdtemp(prefix="script-fonts-")
    os.makedirs(os.path.join(d, "fonts"))
    for _, f in faces:
        shutil.copy(os.path.join(FONTS, f), os.path.join(d, "fonts", f))
    return d


def main():
    faces = [("Cap", "Poppins-SemiBold.ttf"), ("Head", "PlayfairDisplay-VF.ttf"), ("Aside", "PinyonScript-Regular.ttf")]
    d = comp_dir(faces)
    try:
        en = page("Hello there, $300", faces)
        out, notes = SF.add_companions(en, d)
        check("an English page comes back byte for byte", out == en and notes == [])

        bg = page("Като макраме, когато плетеш много-много", faces)
        out, notes = SF.add_companions(bg, d)
        check("a Bulgarian page gains the companion block", SF.MARK in out)
        check("Poppins SemiBold gets Inter Bold for its Cyrillic",
              "font-family:'Cap';src:url('fonts/cyr-Inter-Bold.otf');unicode-range:" in out, out[:600])
        check("a script face gets the handwritten companion", "font-family:'Aside';src:url('fonts/cyr-Caveat-VF.ttf')" in out)
        check("a face that has Cyrillic (Playfair) is left alone", "font-family:'Head';src:url('fonts/cyr-" not in out)
        check("companions come after the pack faces, so they win for Cyrillic",
              out.index("unicode-range") > out.index("PinyonScript-Regular.ttf"))
        check("the companion file is copied next to the page",
              os.path.exists(os.path.join(d, "fonts", "cyr-Inter-Bold.otf")))
        check("it says in plain words which font draws the Cyrillic", any("Poppins" in n for n in notes), str(notes))
        again, notes2 = SF.add_companions(out, d)
        check("running it twice changes nothing", again == out and notes2 == [])
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # the companion picked for each Latin-only face that ships
    for face, want in (("Poppins-SemiBold.ttf", "Inter-Bold.otf"), ("Inter-Medium.ttf", "Inter-Regular.otf"),
                       ("Poppins-Black.ttf", "Inter-Black.otf"), ("PinyonScript-Regular.ttf", "Caveat-VF.ttf"),
                       ("SpaceGrotesk-VF.ttf", "Inter-Regular.otf")):
        got = SF.companion_for(os.path.join(FONTS, face), "ж")
        check(f"{face} -> {want}", got and os.path.basename(got) == want, str(got))

    # every companion ships and really has the letters it is there to draw
    for comp in ("Caveat-VF.ttf", "PlayfairDisplay-VF.ttf", "PlayfairDisplay-SemiBold.ttf",
                 "Inter-Regular.otf", "Inter-Bold.otf", "Inter-Black.otf"):
        p = os.path.join(FONTS, comp)
        check(f"companion {comp} ships and covers Cyrillic",
              os.path.exists(p) and SF.companion_for(p, "БъЛгарскиЖЩЮЯ") is None)

    # measuring: English untouched, Cyrillic measured on the face that draws it
    pop = os.path.join(FONTS, "Poppins-SemiBold.ttf")
    check("English text is one run on its own face", SF.split(pop, "hello") == [(pop, "hello")])
    runs = SF.split(pop, "да ok")
    check("mixed text splits by alphabet", [os.path.basename(p) for p, _ in runs] ==
          ["Inter-Bold.otf", "Poppins-SemiBold.ttf"] and runs[0][1] == "да" and runs[1][1] == " ok", str(runs))
    try:
        import PIL  # noqa: F401
        inter = os.path.join(FONTS, "Inter-Bold.otf")
        w = hooksplit._measure("РАЗЛИЧНИ", pop, 100)
        check("a Cyrillic word is measured on its companion",
              abs(w - hooksplit._measure("РАЗЛИЧНИ", inter, 100)) < 0.5, f"{w}")
        from PIL import ImageFont
        check("an English word is measured exactly as before",
              hooksplit._measure("different", pop, 100) == ImageFont.truetype(pop, 100).getlength("different"))
    except ImportError:
        print("  (Pillow not installed here, so the measuring checks were skipped)")

    if fails:
        print(f"\nFAIL: {len(fails)} check(s) failed")
        sys.exit(1)
    print("\n✓ script_fonts: Cyrillic gets a matching companion, English is untouched")


if __name__ == "__main__":
    main()
