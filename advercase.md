# Theme: Advercase
the creator's tweak of Modern (2026-07-23). Changes = the fonts.

- **Headline / hook:** the pack's hook font (resolved by name from CapCut's user Fonts folder),
  **WHITE `#ffffff`**, **Title case or lowercase — NEVER all caps** (hard rule, the creator),
  above head. *(← changed from the Modern theme's hook font; white + no-caps supersedes the earlier butter/ALL-CAPS spec)*
  - ⚠️ **Font must carry the hook font's RESOURCE, not just `font_path`.** Build the hook material from the
    `tpl_textmat.json` shell (it has `font_resource_id: 7525275079106776337` + a populated `fonts[]`) —
    NOT the `zy_mat` shell (empty resource → CapCut falls back to a wider default font that reads as
    "weird/wide tracking"). `letter_spacing: 0.0` is her default. (Learned from an example reel, 2026-07-23.)
- **Captions:** CapCut **Bold Text–Popup** template — the creator's tweaks:
  - Font: **Helvetica** (`/System/Library/Fonts/Helvetica.ttc`)
  - **Tracking reduced** (tighter) · **custom font size set** · **highlight style set**
  - Auto highlight keywords ON, under mouth (~−0.33)
  - ⚠️ CapCut's caption-template format doesn't expose these values in the file reliably. **Save this look as a CapCut caption PRESET** (name it e.g. "Advercase") → then it's one-click exact reapply. That preset IS the Advercase caption spec.
- **Ad-libs / thoughts / checklist:** the pack's thought font, white *(unchanged)*.
- **Emphasis words:** yellow (via caption highlight).

Everything else (positions, animations, sounds, punch-in zoom, doodles) = same as Modern.
