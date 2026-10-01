#!/usr/bin/env python3
"""post-update.py — the small repairs every update needs AFTER its files have landed.

Runs automatically at the end of scripts/apply-update.py. An install updating from an older version runs
an older updater that does not know this step, so the update skill also runs it once by hand:
  python3 scripts/post-update.py          (Windows: python scripts/post-update.py)
Safe to run at any time; each repair is a no-op when there is nothing to do.

1. Refresh the engine's own instructions in CLAUDE.md, keeping the creator's block (merge-claude-md.py).
2. Put the executable bit back on every shell script and hook. The zip an update travels in can lose file
   modes on the way through an older updater, and then "./check-setup.sh" answers "permission denied".
   (Windows does not use the bit; skipped there.)
3. Tidy CHANGELOG.md when the updater added a second heading for the version the shipped changelog already
   described: the shipped, fuller entry is kept.
4. Bring her own changes to the engine forward (product/keep_changes.py): every file of hers the update
   replaced is re-applied on top of the new version where it does not collide, a pack she edited in place
   is kept as her own, and all of it is written down in _local/my-changes.md.

It also puts back what is HERS inside files an update replaces, whichever updater applied it: every style
pack she built (the quick fonts-and-accent kind included, and one an earlier update deleted, found again
in _update-backups/), and the settings she made inside shipped files (her permission mode, the hook
defaults and headline font her brand kit set). See product/pack_persist.py and product/settings_persist.py.
Those run first; keep_changes runs after them, so it never re-merges a setting or a pack they already
put back.
"""
import json
import os
import re
import subprocess
import sys
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"node_modules", ".git", "projects", "_update-backups", "_local", "renders", "__pycache__"}


def read_text(path):
    """Read a text file this script does not own, without dying on how it happens to be encoded.

    A real install hit this: CHANGELOG.md carried one Windows-1252 em dash byte (0x97) from however it was
    authored upstream, and a bare encoding="utf-8" read raised UnicodeDecodeError and took the whole
    finishing step down with it. Nothing here is worth failing an update over, so: try UTF-8, then UTF-8
    with a byte-order mark, then Windows-1252 (which cannot fail), and say which one worked so a file that
    needs repairing can be repaired rather than worked around for ever.

    Returns (text, encoding_used). encoding_used is "utf-8" when the file was already clean."""
    raw = open(path, "rb").read()
    for enc in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8/replace"


_CLAUDE_BEFORE = None       # CLAUDE.md as she had it, just before the refresh (keep_her_changes needs it)


def refresh_claude_md():
    global _CLAUDE_BEFORE
    try:
        _CLAUDE_BEFORE = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        _CLAUDE_BEFORE = None
    m = os.path.join(ROOT, "scripts", "merge-claude-md.py")
    if os.path.exists(m):
        subprocess.run([sys.executable, m], check=False)


def keep_her_changes():
    """Re-apply what she changed in the engine's own files, on top of the version just installed."""
    sys.path.insert(0, os.path.join(ROOT, "product"))
    try:
        import keep_changes
    except ImportError:
        return
    finally:
        sys.path.pop(0)
    line = keep_changes.after_update(claude_before=_CLAUDE_BEFORE)
    if line:
        print(line)


def repair_exec_bits():
    if os.name == "nt":
        return
    fixed = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            is_script = fn.endswith((".sh", ".command")) or os.path.basename(dirpath) == "hooks"
            if not is_script:
                continue
            try:
                st = os.stat(p)
                if not (st.st_mode & 0o111):
                    os.chmod(p, st.st_mode | 0o111)
                    fixed += 1
            except OSError:
                pass
    if fixed:
        # Routine, not a fault: a zip can arrive without the runnable bit on a script (whichever updater unpacked it).
        print(f"scripts: made {fixed} shell script(s) runnable.")


def tidy_changelog():
    cl = os.path.join(ROOT, "CHANGELOG.md")
    pj = os.path.join(ROOT, "product.json")
    if not (os.path.exists(cl) and os.path.exists(pj)):
        return
    try:
        ver = json.load(open(pj, encoding="utf-8")).get("version", "")
    except Exception:
        return
    if not ver:
        return
    text, enc = read_text(cl)
    if enc != "utf-8":
        # Re-save it clean so this is the last time anything has to guess. Same characters, same content.
        open(cl, "w", encoding="utf-8").write(text)
        print(f"changelog: re-saved in the standard text encoding (it had been written as {enc}); content unchanged.")
    heads = [m.start() for m in re.finditer(rf"^## v{re.escape(ver)}\b.*$", text, re.M)]
    if len(heads) < 2:
        return
    # The updater's own short entry is the FIRST one (it prepends); the shipped, fuller entry follows.
    # Drop the first section: from its heading up to the next "## " heading.
    first = heads[0]
    nxt = re.search(r"^## ", text[first + 1:], re.M)
    end = first + 1 + nxt.start() if nxt else len(text)
    open(cl, "w", encoding="utf-8").write(text[:first] + text[end:])
    print(f"changelog: removed a duplicate v{ver} heading (kept the full entry).")


def restore_engine_settings():
    """0. Put back any engine setting product.json is missing. An updater from v1.0.64 or earlier writes back
    the product.json it read before installing, which drops every new key the release shipped (the HyperFrames
    pin, first). The release's own copy rides along at product/templates/product.engine.json. Only MISSING
    keys are added; nothing already in her product.json is changed, and the version stays hers."""
    pj = os.path.join(ROOT, "product.json")
    tpl = os.path.join(ROOT, "product", "templates", "product.engine.json")
    if not (os.path.exists(pj) and os.path.exists(tpl)):
        return
    try:
        cur = json.load(open(pj, encoding="utf-8"))
        ship = json.load(open(tpl, encoding="utf-8"))
    except Exception:
        return
    added = [k for k in ship if k not in cur and k != "version"]
    if not added:
        return
    for k in added:
        cur[k] = ship[k]
    open(pj, "w", encoding="utf-8").write(json.dumps(cur, indent=2) + "\n")
    print(f"settings: restored {', '.join(added)} in product.json (an older updater had dropped it).")


def _hf_pin():
    try:
        v = str(json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("hyperframes", "")).strip()
        if v:
            return v
    except Exception:
        pass
    try:
        return str(json.load(open(os.path.join(ROOT, "product", "templates", "product.engine.json"),
                                  encoding="utf-8")).get("hyperframes", "")).strip()
    except Exception:
        return ""


def ensure_render_browser():
    """4. The graphics renderer needs its own headless browser, and a new HyperFrames version needs a new
    one. Fetch it now (once per version, ~150 MB, announced) so her first reel after an update never stalls
    on a download mid-build. The marker lives in _local/, which updates never touch."""
    if os.environ.get("REELS_ENGINE_SKIP_BROWSER_ENSURE") == "1":   # tests only
        return
    ver = _hf_pin()
    if not ver:
        return
    marker_dir = os.path.join(ROOT, "_local")
    marker = os.path.join(marker_dir, f"hf-browser-{ver}.ok")
    if os.path.exists(marker):
        return
    print(f"render engine: fetching the browser HyperFrames {ver} renders with (~150 MB, one time) so your next reel does not wait on it...")
    cmd = (["cmd", "/c", "npx"] if os.name == "nt" else ["npx"]) + ["--yes", f"hyperframes@{ver}", "browser", "ensure"]
    try:
        rc = subprocess.run(cmd, check=False).returncode
    except Exception as e:   # noqa: BLE001
        rc = 1
        print(f"  (could not start npx: {e})")
    if rc == 0:
        os.makedirs(marker_dir, exist_ok=True)
        open(marker, "w", encoding="utf-8").write("ok\n")
        print("render engine: ready.")
    else:
        print(f"render engine: the browser download did not finish; it will be fetched on the first render instead "
              f"(or run: npx hyperframes@{ver} browser ensure).")


def _this_update_backup():
    """The folder in _update-backups/ that the update which installed THIS version made, or None.

    Every updater, old or new, writes applied.json there with the version it went to."""
    try:
        ver = str(json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version", "")).strip()
        names = os.listdir(os.path.join(ROOT, "_update-backups"))
    except Exception:
        return None
    best = None
    for n in names:
        if n.endswith(".rolledback"):
            continue
        try:
            log = json.load(open(os.path.join(ROOT, "_update-backups", n, "applied.json"), encoding="utf-8"))
        except Exception:
            continue
        m = re.search(r"(\d{8}-\d{6})", n)
        stamp = m.group(1) if m else ""
        if str(log.get("to", "")) == ver and (best is None or stamp > best[0]):
            best = (stamp, n)
    return os.path.join(ROOT, "_update-backups", best[1]) if best else None


def _first_run():
    """True until this version's finishing step has run once after the update that installed it.

    The marker mark_done() writes says the step ran; an update applied AFTER it (she undid this version and
    installed it again) needs the step again, so a marker older than that update's own record does not count."""
    try:
        ver = str(json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version", "")).strip()
    except Exception:
        return False
    marker = os.path.join(ROOT, "_local", f"post-update-{ver}.ok")
    if not ver:
        return False
    if not os.path.exists(marker):
        return True
    fresh = _this_update_backup()
    try:
        return bool(fresh) and os.path.getmtime(os.path.join(fresh, "applied.json")) > os.path.getmtime(marker)
    except OSError:
        return False


FIRST = _first_run()   # read before any step runs: mark_done() writes the marker at the very end


def _product(name):
    sys.path.insert(0, os.path.join(ROOT, "product"))
    try:
        return __import__(name)
    except ImportError:
        return None
    finally:
        sys.path.pop(0)


def rescue_style_packs():
    """Put back every style pack the creator BUILT that an update overwrote.

    A built pack lives inside two SHIPPED files (style-packs.json + pack_palettes.py), so an update
    replaces both. Current updaters save it first and replay it afterwards. The updater that applied THIS
    update is the copy that was already on the machine, though, and an older one knew none of that: it
    overwrote a quick (fonts-and-accent) pack outright, or put back an older saved copy of a pack she had
    changed since, while the protected `user-style.json` went on naming it, so the next build asked for a
    pack that no longer existed.

    This step ships INSIDE the update, so it runs even when the updater that ran was old. The first time it
    runs for a version it takes her packs from the backup THIS update made (her packs exactly as they were a
    moment before it) as the truth; every run also looks through every older update backup for a pack an
    earlier update deleted. A pack already present is left alone, so it is a no-op on a normal update."""
    pack_persist = _product("pack_persist")
    if pack_persist is None:
        return
    if not hasattr(pack_persist, "rescue"):          # an engine whose pack_persist predates rescue()
        pack_persist.harvest()
        restored, problems = pack_persist.restore()
        if restored:
            print(f"style packs: put {', '.join(restored)} back after the update.")
        for n, why in problems:
            print(f"style packs: '{n}' — {why}")
        return
    fresh = _this_update_backup() if FIRST else None
    r = pack_persist.rescue(os.path.join(fresh, "overwritten") if fresh else None)
    back = [n for n, _f in r["recovered"]]
    for name, folder in r["recovered"]:
        print(f"style packs: brought back '{name}'. An earlier update had removed it; it was still in the "
              f"backup {folder}.")
    for name in r["fixed"]:
        print(f"style packs: kept your latest version of '{name}'.")
    rest = [n for n in r["restored"] if n not in back]
    if rest:
        print(f"style packs: put {', '.join(rest)} back after the update.")
    for n, why in r["problems"]:
        print(f"style packs: '{n}' — {why}")
    name, ok = pack_persist.default_pack_status()
    if name and not ok:
        print(f"style packs: your default pack '{name}' is not in this engine or any update backup, so builds "
              f"will ask for another. Say \"build my own style pack\" to rebuild it, or pick another pack.")


def keep_settings():
    """Put back the settings she made inside files the update just replaced: her permission mode in
    .claude/settings.json, and the hook defaults and headline font her brand kit wrote into the presets.

    Only the first time this runs for a version (right after the update), from the backup that update
    made — so a setting she changes by hand later is never "restored" over by running this again."""
    if not FIRST:
        return
    settings_persist = _product("settings_persist")
    if settings_persist is None:
        return
    fresh = _this_update_backup()
    if fresh:
        settings_persist.harvest(os.path.join(fresh, "overwritten"))
    restored, problems = settings_persist.restore()
    if restored:
        print(f"your settings: put back {', '.join(restored)} after the update.")
    for what, why in problems:
        print(f"your settings: {what} — {why}")


def keep_her_files():
    """Put back a file of HERS that an older updater removed along with the engine's copy of that name.

    An update removes files the engine no longer ships. Older updaters removed whatever sat at those paths,
    including a file she had put there herself (her own pop.mp3 in the sound folder the library page tells
    her to fill). The update carries every version the engine ever shipped of each file it removes
    (product/templates/update-deletes.json): whatever an update backup holds that matches none of them was
    hers, and goes back where it was (newest backup first; never over a file that is there now). Current
    updaters never remove such a file in the first place. Once per version, on the first run."""
    if not FIRST:
        return
    try:
        table = json.load(open(os.path.join(ROOT, "product", "templates", "update-deletes.json"),
                               encoding="utf-8")).get("files") or {}
        names = os.listdir(os.path.join(ROOT, "_update-backups"))
    except Exception:
        return
    import hashlib, shutil
    order = []
    for n in names:
        m = re.search(r"(\d{8}-\d{6})", n)
        if os.path.isdir(os.path.join(ROOT, "_update-backups", n, "deleted")):
            order.append(((m.group(1) if m else ""), n))
    back = []
    for _stamp, n in sorted(order, reverse=True):
        gone = os.path.join(ROOT, "_update-backups", n, "deleted")
        for dirpath, _dirs, files in os.walk(gone):
            for fn in files:
                src = os.path.join(dirpath, fn)
                rel = os.path.relpath(src, gone).replace(os.sep, "/")
                dst = os.path.join(ROOT, *rel.split("/"))
                if rel not in table or os.path.exists(dst):
                    continue
                if hashlib.sha256(open(src, "rb").read()).hexdigest() in table[rel]:
                    continue                               # the engine's own copy: removing it was right
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                back.append(rel)
    if back:
        print(f"your files: put back {', '.join(back)}. The engine stopped shipping a file of that name, "
              f"and yours is your own, so it stays.")


def record_update_state():
    """Once, right after the update: what every file it wrote looks like now, her merges and settings included
    (incoming.json in its backup folder). `apply-update.py --rollback` compares against it: a file she changes
    after this is saved under _local/my-changes/ before an undo puts the older copy back, and one she never
    touches is not. Without it an undo still works, it just cannot tell the two apart."""
    if not FIRST:
        return
    fresh = _this_update_backup()
    if not fresh:
        return
    try:
        log = json.load(open(os.path.join(fresh, "applied.json"), encoding="utf-8"))
    except Exception:
        return
    import hashlib
    files = {}
    for rel in log.get("wrote") or []:
        p = os.path.join(ROOT, *str(rel).split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                files[rel] = hashlib.sha256(fh.read()).hexdigest()
    part = os.path.join(fresh, "incoming.json.part")
    with open(part, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"to": log.get("to"), "files": files}, indent=2, sort_keys=True) + "\n")
    os.replace(part, os.path.join(fresh, "incoming.json"))
    # CLAUDE.md is hers (the updater never writes it); the refresh above rewrote its engine instructions. Keep it as
    # it was just before, and as it is now, so an undo can put the older instructions back and carry over any line
    # she adds after this.
    try:
        now = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        now = None
    if _CLAUDE_BEFORE is not None and now is not None and now != _CLAUDE_BEFORE:
        for name, text in (("claude-md-before.md", _CLAUDE_BEFORE), ("claude-md-after.md", now)):
            with open(os.path.join(fresh, name + ".part"), "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(os.path.join(fresh, name + ".part"), os.path.join(fresh, name))


def mark_done():
    """Record that this version's finishing step ran. The session-start hook looks for this marker: an update
    installed by an older updater that never ran post-update.py gets finished the next time she opens the
    engine, so '/update' alone is always enough. Lives in _local/, which updates never touch."""
    try:
        ver = str(json.load(open(os.path.join(ROOT, "product.json"), encoding="utf-8")).get("version", "")).strip()
    except Exception:
        return
    if ver:
        os.makedirs(os.path.join(ROOT, "_local"), exist_ok=True)
        open(os.path.join(ROOT, "_local", f"post-update-{ver}.ok"), "w", encoding="utf-8").write("ok\n")


def _step(fn):
    """Run one finishing repair. These are independent of each other, so one that trips must not take the
    rest down with it: an install where the changelog tidy raised stopped before the render browser was
    fetched AND before the update marked itself finished, which left the engine asking to be updated again.
    Report the fault plainly, keep going, and let the caller decide what to do about it."""
    try:
        fn()
        return True
    except Exception as e:   # noqa: BLE001
        print(f"{fn.__name__}: this step could not finish ({type(e).__name__}: {e}). The rest of the update "
              f"is unaffected and continues. Say \"/report-a-problem\" if anything looks wrong afterwards.")
        return False


if __name__ == "__main__":
    ok = [_step(f) for f in (restore_engine_settings, rescue_style_packs, keep_settings, keep_her_files,
                             refresh_claude_md, keep_her_changes, repair_exec_bits, tidy_changelog,
                             record_update_state, ensure_render_browser)]
    mark_done()   # last, and only after the steps above have each had their turn
    sys.exit(0 if all(ok) else 1)
