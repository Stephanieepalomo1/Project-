#!/usr/bin/env python3
"""clean_cut.py — the ONE required pre-stitch gate. Runs the engine's existing acoustic cut tools in
order; it does NOT reimplement them.

Root cause it exists to kill: a CUSTOM build that bypasses `stitch-cut.sh` (cold-open / rewind / VHS / any
bespoke stitch, or resuming an old hand-authored cut) silently skips the cut-cleaning that the normal
rough-cut path gets for free — so double-takes and clipped words come straight back. There was no single
gate a custom build could call, so it got skipped by omission. This is that gate.

It chains the two existing tools:
  1. trim-restarts.py  — acoustic MFCC/DTW removal of quick restarts / duplicate takes the transcript
                         can't see (needs the WhisperX venv Python for torch)
  2. snap-to-sound.py    — snap every boundary to the word's real acoustic onset/offset (stdlib)

Both are idempotent-safe to re-run, so calling this on an already-clean cut is a near no-op.

CLI:      python product/clean_cut.py <job>
Import:   from clean_cut import clean_cut ; segs = clean_cut(job)   # writes cuts.json in place
Any custom builder MUST call this after editing cuts.json and before stitching (CLAUDE.md rule 8).
"""
import json, os, sys, subprocess
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass


def _venv_py(venv):
    """Interpreter inside a venv, whatever this OS named it (bin/ on mac+linux, Scripts/ on Windows).
    Checks what EXISTS rather than guessing by os.name, then falls back to the historic bin/python."""
    for _c in ("Scripts/python.exe", "bin/python", "bin/python3", "Scripts/python3.exe"):
        _p = os.path.join(venv, _c)
        if os.path.exists(_p):
            return _p
    return os.path.join(venv, "bin/python")


def _venv_home(leaf):
    """Where the transcription venv lives, including one built under an earlier cache layout.

    A prior build is found by the engine's own completion marker rather than by folder name: the leaf
    is this engine's, so anything carrying it under ~/.cache is ours. That way no past layout has to be
    written down, nobody re-downloads a finished 3-5 GB build, and a fresh install matches nothing and
    gets the current path."""
    import glob
    new = os.path.expanduser(f"~/.cache/reels-editing-engine/{leaf}")
    if os.path.isdir(new):
        return new
    cands = [d for d in glob.glob(os.path.expanduser(f"~/.cache/*/{leaf}")) if os.path.isdir(d)]
    finished = [d for d in cands if os.path.exists(os.path.join(d, ".deps-ok"))]
    return finished[0] if finished else (cands[0] if cands else new)


def _seconds(cuts):
    """How long the cut in this file runs, in seconds, or None when the file cannot say."""
    try:
        with open(cuts, encoding="utf-8") as fh:
            return sum(float(s["end"]) - float(s["start"]) for s in json.load(fh)["segments"])
    except Exception:
        return None


ENG  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK   = f"{ENG}/.claude/skills/rough-cut/scripts"
VENV = _venv_py(_venv_home("whisperx-venv"))

def clean_cut(job):
    jd    = job if job.startswith("/") else f"{ENG}/projects/{job}"
    name  = os.path.basename(jd.rstrip("/"))
    cuts  = f"{jd}/transcript/cuts.json"
    words = f"{jd}/transcript/words.json"
    if not os.path.exists(cuts):
        sys.exit(f"clean_cut: no cut to clean — {cuts} does not exist. Run the rough-cut skill first (it writes "
                 f"transcript/cuts.json); pass the job slug under projects/ or an absolute job path.")
    notes = []
    failed = []   # steps that crashed (reported loud; the CLI exits non-zero so a pipeline cannot mistake it for clean)
    # "Her trim wins" (Bug #3): if this cut is the creator's authoritative your-turn pull-back, NEVER run the
    # restart-detector over it — it could silently remove a deliberate acoustic repeat ("no. no. I mean it.").
    # Only refine boundaries. This is the SAME marker stitch-cut.sh honors, so every path (splice, clean_cut, and a
    # standalone `python product/clean_cut.py <job>`) agrees. A fresh rough cut (transcript-cut) clears it.
    yourturn = os.path.exists(f"{jd}/transcript/.your-turn-cut")
    # 1) double-takes / quick restarts (acoustic) — needs the WhisperX venv (torch/torchaudio)
    if yourturn:
        notes.append("trim-restarts: SKIPPED (your-turn cut — her trim wins)")
    elif os.path.exists(VENV):
        was = _seconds(cuts)
        r = subprocess.run([VENV, f"{SK}/trim-restarts.py", name], capture_output=True, text=True)
        if r.returncode != 0:
            # never report a crashed detector as "no restarts" (it used to): say it FAILED and why
            why = (r.stderr.strip().splitlines() or r.stdout.strip().splitlines() or ["no output"])[-1][:200]
            notes.append(f"trim-restarts: ⚠ FAILED — double-takes NOT removed ({why})")
            failed.append("trim-restarts")
        else:
            # Its real run prints nothing on stdout, so this used to say "no restarts" every time, including
            # the times it cut some. What it did is read off the cut itself, before and after.
            now = _seconds(cuts)
            gone = None if was is None or now is None else was - now
            if gone is None:
                notes.append("trim-restarts: ran")
            elif gone > 0.0005:
                notes.append(f"trim-restarts: ran, removed {gone:.2f}s of restarted takes")
            else:
                notes.append("trim-restarts: ran, found no quick restarts to remove")
            # and its ⚠ lines (a kept line whose word timing is unreliable: re-listen there) are passed on
            notes.extend("trim-restarts: " + line.strip() for line in r.stderr.splitlines() if "⚠" in line)
    else:
        # On an Intel Mac this venv is never built (WhisperX needs a torch with no Intel build) and
        # trim-restarts genuinely cannot run there, so "venv missing" reads as a broken install when
        # it is actually a permanent, explainable limit. Name the real cause.
        _nofw = os.path.expanduser(os.environ.get("REELS_ENGINE_NOFW_VENV", _venv_home("fasterwhisper-venv")))
        if os.path.exists(_venv_py(_nofw)):
            notes.append("trim-restarts: SKIPPED (not available on an Intel Mac — "
                         "double-takes NOT removed, listen back for restarts)")
        else:
            notes.append("trim-restarts: SKIPPED (WhisperX venv missing — double-takes NOT checked)")
    # 2) boundary onset/offset refinement (stdlib) — temp then atomic replace. Not on a your-turn cut: she set
    #    those edges by ear, frame by frame, in CapCut, and the snap would move nearly every one of them (on one
    #    pulled-back reel it moved 29 of 31, some by 0.2s). Her trim wins, edges included.
    if yourturn:
        notes.append("snap-to-sound: SKIPPED (your-turn cut — her edges are kept exactly as she set them)")
        for n in notes: sys.stderr.write("  " + n + "\n")
        clean_cut.failed = failed
        return json.load(open(cuts, encoding="utf-8"))["segments"]
    tmp = cuts + ".clean.tmp"
    # sys.executable, not "python3": on Windows "python3" can resolve to the Microsoft Store stub.
    r = subprocess.run([sys.executable, f"{SK}/snap-to-sound.py", f"{jd}/raw", words, cuts, tmp],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(tmp):
        os.replace(tmp, cuts); notes.append("snap-to-sound: boundaries snapped to acoustic onset/offset")
    else:
        why = (r.stderr.strip().splitlines() or ["no output"])[-1][:200]
        notes.append(f"snap-to-sound: ⚠ FAILED — boundaries left as authored ({why})")
        failed.append("snap-to-sound")
        if os.path.exists(tmp): os.remove(tmp)
    for n in notes: sys.stderr.write("  " + n + "\n")
    clean_cut.failed = failed
    return json.load(open(cuts, encoding="utf-8"))["segments"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python product/clean_cut.py <job>")
    segs = clean_cut(sys.argv[1])
    if clean_cut.failed:
        sys.exit(f"clean_cut: {len(segs)} segments, but {', '.join(clean_cut.failed)} FAILED (see above) — "
                 f"NOT clean; fix the step and re-run before stitching")
    print(f"clean_cut: {len(segs)} segments cleaned (trim-restarts → snap-to-sound) — safe to stitch")
