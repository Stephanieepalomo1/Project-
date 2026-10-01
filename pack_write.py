#!/usr/bin/env python3
"""pack_write.py — apply a generated style pack to the two files that define it, or refuse.

The recipe tools print two paste-ready blocks and ask the creator to copy them into
`creative-vault/style-packs.json` and `pack_palettes.py` by hand. That is six separate entries across
two files, and the failure is silent: miss one and the pack falls back to ANOTHER pack's values in the
designed lanes, which looks like a broken pack rather than a missing line. This does it in one step.

Safety, because this edits files the whole engine reads:
  * every existing pack must survive byte-identical — verified by re-reading after the write
  * a launch-kit pack is never touched, and an existing name needs an explicit overwrite
  * both files are written, or neither: each is staged, parsed, verified, and only then moved into place
  * the previous version of each file is kept next to it as .bak before anything moves

Every pack written here is also recorded in the protected `creative-vault/user-packs.json` via
pack_persist, because BOTH files below are shipped and an update overwrites them.

A QUICK pack (the `style-pack` skill: her three fonts and one accent colour on a shipped pack's locked
layout) has no palette of its own, so it lives in style-packs.json alone. It is saved through this same
writer with no recipe, which is what records it in the protected copy too. Before this route existed the
skill had Claude edit style-packs.json by hand, nothing recorded it, and the next update deleted it:

    python3 product/pack_write.py --name "My Pack" --block my-pack.json [--system-font "Font=/abs/path"]

"Keep Butter but make the blue pink" is a NEW pack of hers started from a shipped one, never an edit to the
shipped pack (every update resets those):

    python3 product/pack_write.py --name "Butter Blush" --from Butter --set palette.dark=#C2527A

(Windows: python, never python3.) It warns when text in a new colour will not read on its background.

Used by frame_to_pack.py --write, pack_recipe.py --write and the style-pack skill; pack_persist puts a pack
back after an update through `restore_pack` / `replace_pack`, the same writer without re-recording it, and
saves a shipped pack she edited in place as her own ("My Butter") through `apply`.
"""
import ast, json, os, re, shutil, collections, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACKS_JSON = os.path.join(HERE, "creative-vault", "style-packs.json")
PALETTES = os.path.join(HERE, "pack_palettes.py")

# name -> how that entry is rendered into pack_palettes.py
_DICTS = ("GROUNDS", "HANDS_OFF_ACCENT", "PALETTE", "TREATMENTS", "PACK_ELEMENTS", "CARD_THEME")


class PackWriteError(Exception):
    """Raised before anything is written. The message is what the creator sees."""


def _read_packs():
    return json.loads(open(PACKS_JSON, encoding="utf-8").read(),
                      object_pairs_hook=collections.OrderedDict)


def _insert_into_dict(src, dict_name, line):
    """Insert `line` just before the closing brace of a top-level `NAME = {` dict literal."""
    m = re.search(rf"^{dict_name}\s*=\s*\{{", src, flags=re.M)
    if not m:
        raise PackWriteError(f"{PALETTES}: could not find the '{dict_name}' dict — file shape changed, "
                             f"not writing anything. Paste the printed blocks by hand.")
    close = re.compile(r"^\}$", flags=re.M).search(src, m.end())
    if not close:
        raise PackWriteError(f"{PALETTES}: '{dict_name}' has no closing brace at column 0 — not writing.")
    return src[:close.start()] + line + src[close.start():]


def _dict_entries(src):
    """{DICT_NAME: {key: (line, col, end_line, end_col)}} for every top-level `NAME = {...}` dict, by AST.

    Lines are 1-based; columns are UTF-8 byte offsets, as the ast module gives them."""
    out = {}
    for node in ast.parse(src).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = {k.value: (k.lineno, k.col_offset, v.end_lineno, v.end_col_offset)
                                  for k, v in zip(node.value.keys, node.value.values)
                                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return out


def _render_recipe(recipe):
    """The six pack_palettes.py entries of a recipe, rendered exactly as the recipe tools always have."""
    return {
        "GROUNDS": f'"{recipe["ground"]}"',
        "HANDS_OFF_ACCENT": f'"{recipe["hands_off_accent"]}"',
        "PALETTE": repr(recipe["palette"]),
        "TREATMENTS": repr(recipe["treatment"]),
        "PACK_ELEMENTS": repr(recipe["elements"]),
        "CARD_THEME": repr(recipe["card"]),
    }


def _render_value(value):
    """One saved pack_palettes.py value back as Python source (a string as a JSON string: same text, safe)."""
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else repr(value)


def system_font_refs(block):
    """The `system_fonts` keys a pack points at ("SYSTEM:<key>" anywhere in its block)."""
    refs = []
    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and v.startswith("SYSTEM:") and v[7:] not in refs:
            refs.append(v[7:])
    walk(block)
    return refs


def _write(name, block, entries, system_fonts, force):
    """The one writer both routes share. `entries` maps a pack_palettes.py dict to the Python source of this
    pack's value in it — empty for a quick pack, which lives in style-packs.json alone and never touches
    pack_palettes.py. Returns (dicts whose entry did not land, notes for the report)."""
    cfg = _read_packs()
    existing = cfg.get("packs", {})
    if name in existing:
        if isinstance(existing[name], dict) and existing[name].get("in_launch_kit"):
            raise PackWriteError(f"'{name}' is a LAUNCH pack. Those are hand-tuned and shipped; this will "
                                 f"not overwrite one. Pick another name.")
        if not force:
            raise PackWriteError(f"'{name}' already exists. Re-run with --force to replace it, or pick "
                                 f"another name. (Its current values are not backed up anywhere else.)")

    before_packs = {k: json.dumps(v, sort_keys=True) for k, v in existing.items() if k != name}
    notes = []

    # ---- stage style-packs.json -------------------------------------------------------------
    cfg.setdefault("packs", collections.OrderedDict())[name] = json.loads(
        json.dumps(block), object_pairs_hook=collections.OrderedDict)
    for key, path in (system_fonts or {}).items():
        have = cfg.setdefault("system_fonts", collections.OrderedDict())
        if key not in have:
            have[key] = path
        elif have[key] != path:
            notes.append(f"    system font '{key}' already points at {have[key]}; kept that one")
    staged_json = json.dumps(cfg, indent=1, ensure_ascii=False) + "\n"
    reparsed = json.loads(staged_json)
    if name not in reparsed.get("packs", {}):
        raise PackWriteError("internal: staged style-packs.json did not round-trip — nothing written.")
    for k, v in before_packs.items():
        if json.dumps(reparsed["packs"].get(k), sort_keys=True) != v:
            raise PackWriteError(f"internal: writing '{name}' would have altered the existing pack "
                                 f"'{k}' — nothing written.")

    # ---- stage pack_palettes.py (a pack with a palette of its own) ---------------------------
    staged_py = None
    if entries:
        src = open(PALETTES, encoding="utf-8").read()
        for d in _DICTS:
            if re.search(rf'^\s*"{re.escape(name)}"\s*:', src, flags=re.M) and not force:
                raise PackWriteError(f"'{name}' already appears in {os.path.basename(PALETTES)} — "
                                     f"remove it or use --force.")
        staged_py = src
        for d, literal in entries.items():
            staged_py = _insert_into_dict(staged_py, d, f'    {json.dumps(name, ensure_ascii=False)}: {literal},\n')
        compile(staged_py, PALETTES, "exec")          # syntax-check before it can reach disk

    # ---- commit: back up, then move both ----------------------------------------------------
    writes = [(PACKS_JSON, staged_json)] + ([(PALETTES, staged_py)] if staged_py is not None else [])
    for path, _text in writes:
        shutil.copy2(path, path + ".bak")
    for path, text in writes:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)

    # ---- verify what actually landed ---------------------------------------------------------
    missing = []
    if staged_py is not None:
        landed = _dict_entries(open(PALETTES, encoding="utf-8").read())
        missing = [d for d in entries if name not in landed.get(d, {})]
    after = _read_packs().get("packs", {})
    if name not in after:
        raise PackWriteError(f"wrote the files but '{name}' is not in style-packs.json — restore from .bak")
    for k, v in before_packs.items():
        if json.dumps(after.get(k), sort_keys=True) != v:
            raise PackWriteError(f"wrote the files but existing pack '{k}' changed — restore from .bak")
    return missing, notes


def _persist():
    try:
        import pack_persist
    except ImportError:
        import importlib.util
        _spec = importlib.util.spec_from_file_location("pack_persist", os.path.join(HERE, "pack_persist.py"))
        pack_persist = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(pack_persist)
    return pack_persist


def apply(name, block, recipe=None, force=False, system_fonts=None):
    """Write pack `name` into both files. `block` is the style-packs.json body, `recipe` the
    pack_recipe/frame_to_pack result carrying ground/ink/palette/treatment/elements/card.

    recipe=None writes a QUICK pack (fonts + accent, no palette of its own) into style-packs.json only.
    `system_fonts` ({key: absolute path}) adds the "SYSTEM:<key>" fonts the pack points at.

    Returns a short report string. Raises PackWriteError before touching anything if it is not safe."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,31}", name or ""):
        raise PackWriteError(f"pack name {name!r} is not a plain name — refusing to write it into code.")

    entries = _render_recipe(recipe) if recipe is not None else {}
    missing, notes = _write(name, block, entries, system_fonts, force)

    # ---- record it where an update cannot reach -------------------------------------------
    # Both files above are SHIPPED, so the next engine update overwrites them. The sidecar is protected,
    # and the updater replays it afterwards, which is the only reason a pack built today still exists
    # after "update me". The record is read back from what just landed, system fonts included.
    persist = _persist()
    kept = persist.record_live(name) if hasattr(persist, "record_live") else persist.record(name, block, recipe)

    where = (f"into {os.path.relpath(PACKS_JSON, os.path.dirname(HERE))} "
             f"and all {len(_DICTS)} entries in {os.path.relpath(PALETTES, os.path.dirname(HERE))}"
             if recipe is not None else
             f"into {os.path.relpath(PACKS_JSON, os.path.dirname(HERE))} (your fonts and accent on the "
             f"shipped layout; a quick pack has no palette entries of its own)")
    return (f"  ✓ wrote '{name}' {where}\n"
            f"    every existing pack verified unchanged · previous versions kept as .bak\n"
            + ("    saved to user-packs.json, so an engine update keeps it"
               if kept else
               "    ⚠ could NOT save it to user-packs.json — an engine update would lose this pack")
            + (f"\n    ⚠ check these dicts by hand: {missing}" if missing else "")
            + ("\n" + "\n".join(notes) if notes else ""))


def _saved_entries(saved):
    """The pack_palettes.py entries a saved pack carries, as {DICT: source}."""
    palette = saved.get("palette")
    if isinstance(palette, dict) and palette:
        return {d: _render_value(v) for d, v in palette.items()}
    if isinstance(saved.get("recipe"), dict):
        return _render_recipe(saved["recipe"])
    return {}


def restore_pack(name, saved):
    """Put a SAVED pack back after an update (pack_persist.restore). Same writer, no re-recording, and no
    new-name rule: the pack already exists under this name on her machine, so it comes back under it.

    Entries still present in pack_palettes.py (an update that left that file alone) are not written twice.
    A dict the engine no longer has is reported, never guessed at. Returns a list of problems (empty = all
    of it is back)."""
    block = saved.get("block")
    if not isinstance(block, dict):
        raise PackWriteError("its saved copy has no pack block")
    wanted = _saved_entries(saved)
    problems = []
    if wanted:
        have = _dict_entries(open(PALETTES, encoding="utf-8").read())
        for d in list(wanted):
            if d not in have:
                problems.append(f"the engine no longer has a {d} table, so that part of it was not put back "
                                f"(it is still saved in user-packs.json)")
                wanted.pop(d)
            elif name in have[d]:
                wanted.pop(d)                       # already there: never a second copy
    missing, notes = _write(name, block, wanted, saved.get("system_fonts"), force=True)
    problems += [f"the {d} entry did not land; it is still saved in user-packs.json" for d in missing]
    return problems


def _remove_entries(src, name):
    """pack_palettes.py source with every entry filed under `name` taken out (by AST line spans).

    Refuses (PackWriteError) rather than guess when an entry shares a line with another one."""
    table = _dict_entries(src)
    lines = src.splitlines(keepends=True)
    drop = set()
    for d, keys in table.items():
        if name not in keys:
            continue
        a, col, b, end_col = keys[name]
        if any(not (s[2] < a or s[0] > b) for k, s in keys.items() if k != name):
            raise PackWriteError(f"its {d} entry shares a line with another pack's, so it was left as it is")
        head = lines[a - 1].encode("utf-8")[:col]
        tail = lines[b - 1].encode("utf-8")[end_col:].decode("utf-8", "replace")
        if head.strip() or not re.fullmatch(r"\s*,?\s*(#.*)?\s*", tail):
            raise PackWriteError(f"its {d} entry does not sit on lines of its own, so it was left as it is")
        drop.update(range(a - 1, b))
    return "".join(l for i, l in enumerate(lines) if i not in drop)


def replace_pack(name, saved):
    """Swap the pack called `name` for a saved copy of it (pack_persist, when an older updater put back an
    older copy than the one she had). Its old palette entries are taken out first, so nothing is left
    doubled. Returns a list of problems, like restore_pack."""
    src = open(PALETTES, encoding="utf-8").read()
    cleaned = _remove_entries(src, name)
    if cleaned != src:
        compile(cleaned, PALETTES, "exec")
        shutil.copy2(PALETTES, PALETTES + ".bak")
        tmp = PALETTES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
        os.replace(tmp, PALETTES)
    return restore_pack(name, saved)


def remove_pack(name):
    """Take a creator-built pack out of both files (pack_persist.forget). A launch pack is never removed."""
    cfg = _read_packs()
    packs = cfg.get("packs", {})
    if name in packs and isinstance(packs[name], dict) and packs[name].get("in_launch_kit"):
        raise PackWriteError(f"'{name}' is a LAUNCH pack; it is not yours to remove.")
    src = open(PALETTES, encoding="utf-8").read()
    cleaned = _remove_entries(src, name)
    if name in packs:
        del packs[name]
        shutil.copy2(PACKS_JSON, PACKS_JSON + ".bak")
        tmp = PACKS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(cfg, indent=1, ensure_ascii=False) + "\n")
        os.replace(tmp, PACKS_JSON)
    if cleaned != src:
        compile(cleaned, PALETTES, "exec")
        shutil.copy2(PALETTES, PALETTES + ".bak")
        tmp = PALETTES + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(cleaned)
        os.replace(tmp, PALETTES)


def _luminance(hexcolor):
    h = str(hexcolor).lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    ch = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    ch = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in ch]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _readability(recipe):
    """A plain warning when the pack's ink will not read on its own ground (WCAG contrast, 3:1 floor for
    large type). The render check would refuse it later anyway; saying so now saves a build."""
    if not recipe:
        return ""
    pal = recipe.get("palette") or {}
    grounds = [pal.get("light"), recipe.get("ground")]
    for role in ("dark", "muted"):                     # the two text colours; both must clear 3:1
        ink = pal.get(role)
        li = _luminance(ink)
        for g in grounds:
            lg = _luminance(g)
            if li is None or lg is None:
                continue
            ratio = (max(li, lg) + 0.05) / (min(li, lg) + 0.05)
            if ratio < 3.0:
                return (f"  ⚠ {role} {ink} on {g} reads at {ratio:.1f}:1, under the 3:1 floor for large type. Text "
                        f"in this colour will be hard to read on that background; pick a deeper shade.")
    return ""


def _set_values(block, recipe, pairs):
    """--set KEY=VALUE, one value at a time: palette/ground/... keys change the designed palette, anything
    else (accent_color, elements.caption.size ...) the pack block. A value that parses as JSON is used as
    JSON (numbers, true/false), anything else as text."""
    for kv in pairs:
        key, sep, val = kv.partition("=")
        if not sep or not key:
            raise PackWriteError(f"--set wants KEY=VALUE, got {kv!r}")
        parts = key.split(".")
        if parts[0] in ("ground", "hands_off_accent", "palette", "treatment", "elements", "card"):
            if recipe is None:
                raise PackWriteError(f"{key}: this pack has no designed palette to change")
            target = recipe
        else:
            target = block
            parts = parts[1:] if parts[0] == "block" else parts
        for p in parts[:-1]:
            target = target.setdefault(p, {})
        try:
            target[parts[-1]] = json.loads(val)
        except ValueError:
            target[parts[-1]] = val


def main(argv=None):
    """Save a pack through the recorded path: a QUICK pack (the style-pack skill, --block), or a new pack of
    hers started from an existing one (--from Butter --set palette.dark=#C2527A)."""
    import argparse
    for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
        try: _s.reconfigure(encoding="utf-8")
        except Exception: pass
    ap = argparse.ArgumentParser(description="Save a style pack you built into the engine, and keep a "
                                             "protected copy so an update can never delete it.")
    ap.add_argument("--name", required=True, help='the pack name she chose, e.g. "My Pack"')
    ap.add_argument("--block",
                    help="the pack's style-packs.json block as a JSON file (or - to read it from stdin)")
    ap.add_argument("--from", dest="from_pack",
                    help="start from an existing pack (e.g. Butter): its fonts, settings and palette")
    ap.add_argument("--recipe", help="optional JSON file with the designed palette (pack_recipe output)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="change one value on the way, e.g. palette.dark=#E8A0B4 or accent_color=#F4C2C2")
    ap.add_argument("--system-font", action="append", default=[], metavar='"Font Name=/absolute/path"',
                    help='a system font a role uses as "SYSTEM:<Font Name>" (repeatable)')
    ap.add_argument("--force", action="store_true", help="replace her pack of the same name")
    a = ap.parse_args(argv)
    block, recipe = None, None
    if a.from_pack:
        # "Keep Butter but make the blue pink" is a NEW pack of hers, never an edit to Butter itself: a
        # shipped pack is reset by every update, and hers is kept.
        src = _read_packs().get("packs", {}).get(a.from_pack)
        if not isinstance(src, dict):
            print(f"  ⛔ not written: there is no pack called {a.from_pack!r} to start from")
            return 1
        block = json.loads(json.dumps(src), object_pairs_hook=collections.OrderedDict)
        with open(PALETTES, encoding="utf-8") as fh:
            ent = _persist().palette_entries_in(fh.read(), a.from_pack) or {}
        recipe = ent if len(ent) == len(_DICTS) else None
    try:
        if a.block:
            block = json.load(sys.stdin if a.block == "-" else open(a.block, encoding="utf-8"),
                              object_pairs_hook=collections.OrderedDict)
        if a.recipe:
            with open(a.recipe, encoding="utf-8") as fh:
                recipe = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"  ⛔ not written: could not read the pack block ({e})")
        return 1
    if block is None:
        print("  ⛔ not written: give --block (a pack body) or --from (a pack to start from)")
        return 1
    if not isinstance(block, dict) or not isinstance(block.get("elements"), dict):
        print("  ⛔ not written: that is not a pack block (it needs its \"elements\").")
        return 1
    block["in_launch_kit"] = False                 # hers, never a launch pack, whatever it was cloned from
    fonts = {}
    for pair in a.system_font:
        if "=" not in pair:
            print(f'  ⛔ not written: --system-font needs "Font Name=/absolute/path", got {pair!r}')
            return 1
        k, v = pair.split("=", 1)
        fonts[k.strip()] = os.path.expanduser(v.strip())
    try:
        _set_values(block, recipe, a.set)
        print(apply(a.name, block, recipe, force=a.force, system_fonts=fonts))
    except PackWriteError as e:
        print(f"  ⛔ not written: {e}")
        return 1
    warn = _readability(recipe)
    if warn:
        print(warn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
