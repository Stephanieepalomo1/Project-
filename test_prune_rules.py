#!/usr/bin/env python3
"""Guard: scripts/free-space.sh counts every byte once, reads -vN as a number, and survives a folder it cannot read.

What broke, one case each:
  - the dry run counted hf-graphics/renders/ twice (once as a whole, then its files again in the older-renders
    pass), so "would come back" promised far more than --apply ever freed
  - -v08 was an arithmetic error and -v010 counted as 8 (bash reads a leading 0 as octal), so the wrong render
    was kept as "the highest vN"
  - one folder du could not read ended the whole sweep on the spot, silently, with exit 1

Each case runs free-space.sh (a copy) against a throwaway projects/ folder, so nothing real is touched.

Run: python3 product/tests/test_prune_rules.py
"""
import os, re, shutil, stat, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  -- ' + str(detail)[-400:]) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def mkf(path, kib):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * (kib * 1024))


def run(eng, *args):
    r = subprocess.run(["bash", "scripts/free-space.sh", *args], cwd=eng, capture_output=True, text=True,
                       encoding="utf-8", env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"})
    return r.returncode, r.stdout, r.stderr


def engine(tmp):
    eng = os.path.join(tmp, "engine")
    os.makedirs(os.path.join(eng, "scripts"))
    shutil.copy(os.path.join(ROOT, "scripts", "free-space.sh"), os.path.join(eng, "scripts", "free-space.sh"))
    return eng


def listed(out):
    return [ln.split("  (")[0].split()[-1] for ln in out.splitlines() if ln.startswith("  ") and "  (" in ln]


def main():
    print("free-space.sh: every byte once, -vN as a number, no silent stop\n")

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        mkf(f"{P}/a/hf-graphics/renders/a.mp4", 200)
        mkf(f"{P}/a/hf-graphics/renders/b-v2.mp4", 200)
        mkf(f"{P}/a/hf-graphics/renders/c-final.mp4", 200)
        mkf(f"{P}/a/raw/archive/old.mp4", 100)
        mkf(f"{P}/a/raw/archive/raw/archive/deeper.mp4", 100)
        for n in ("r-v9.mp4", "r-v010.mp4", "r-v1.mp4"):
            mkf(f"{P}/b/renders/{n}", 10)
        for n in ("f-v08.mp4", "f-v1.mp4"):
            mkf(f"{P}/c/renders/{n}", 10)
        rc, out, err = run(eng)
        items = listed(out)
        check("hf-graphics/renders is counted once, as a whole",
              items.count("a/hf-graphics/renders") == 1 and not any(i.startswith("a/hf-graphics/renders/") for i in items), items)
        check("a folder inside a dropped raw/archive is not counted again",
              "a/raw/archive" in items and "a/raw/archive/raw/archive" not in items, items)
        check("-v010 is ten: it stays, and -v9 goes", "b/renders/r-v9.mp4" in items and "b/renders/r-v010.mp4" not in items, items)
        check("-v08 is eight, not an error: it stays, and -v1 goes",
              "c/renders/f-v1.mp4" in items and "c/renders/f-v08.mp4" not in items and "value too great" not in err, err or items)
        rc2, out2, err2 = run(eng, "--apply")
        check("the dry run and --apply list exactly the same items", rc == 0 and rc2 == 0 and listed(out2) == items,
              f"{listed(out2)} vs {items} {err2}")
        check("--apply finishes and says what it won back", re.search(r"Won back [0-9.]+ GB", out2) is not None, out2 + err2)
        check("--apply keeps the renders it said it would",
              os.path.exists(f"{P}/b/renders/r-v010.mp4") and os.path.exists(f"{P}/c/renders/f-v08.mp4")
              and not os.path.exists(f"{P}/b/renders/r-v9.mp4"))

    with tempfile.TemporaryDirectory() as tmp:
        eng = engine(tmp)
        P = os.path.join(eng, "projects")
        locked = f"{P}/j/node_modules/pkg/inner"
        mkf(f"{locked}/f.js", 1)
        mkf(f"{P}/k/node_modules/pkg/index.js", 4)
        os.chmod(locked, 0)
        try:
            if os.access(locked, os.R_OK):
                print("  SKIP  the unreadable-folder case (this account can read a mode-000 folder)")
            else:
                rc, out, err = run(eng, "--apply")
                check("a folder du cannot read is skipped with a plain note, and the sweep finishes",
                      rc == 0 and "j/node_modules" in out and "left in place" in out and "Won back" in out, f"rc={rc} {out} {err}")
                check("...and it is left where it was, while the next one is still cleared",
                      os.path.isdir(f"{P}/j/node_modules") and not os.path.exists(f"{P}/k/node_modules"))
        finally:
            os.chmod(locked, stat.S_IRWXU)

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("all good: prune counts once, keeps the right render, and never stops silently")
    return 0


if __name__ == "__main__":
    sys.exit(main())
