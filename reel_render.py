#!/usr/bin/env python3
"""reel_render.py — the ONE way to render a composition: GATED + CACHED + incremental.

  render    <comp_dir | index.html> -o out.mov [--strict] [--force]
      1) hashes the composition's source files; if unchanged since the last CLEAN render and the output still
         exists, SKIPS both the check and the render (instant no-op, says so).
      2) otherwise runs HyperFrames' native `check --at-transitions --frame-check` and REFUSES to render on
         errors. The gate is ENFORCED here, not advisory. --strict also fails on warnings — use it for any
         composition where every word must read (a transcript animation, captions).
      3) renders (mov = transparent overlay) and records the hash so the next identical run is a no-op.

  composite --base <footage> [--layers a.mov b.mov ...] [--audio x.mp3] -o final.mp4
      the cheap ffmpeg stack: base + transparent layers in order (+ optional audio track). Change ONE layer →
      re-render only that layer (cached by `render`) and re-run this (~15s). Never re-render the whole reel.

WHY (measured on a 30s 1080x1920 composition): check ≈ 40s, render ≈ 60s, and neither `-q draft` nor
`--gpu` changes that (the cost is frame CAPTURE). The only real speedups are to not repeat work that hasn't
changed, and to never re-render a full reel to change one layer. This wrapper makes both the default, and
makes the gate impossible to skip on the way to a render.
"""
import argparse, hashlib, json, os, platform, subprocess, sys, time
for _s in (sys.stdout, sys.stderr):   # force UTF-8: a cp1252 Windows console can't print ✓ or →
    try: _s.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from npx_run import npx_argv, hf_check_argv, hf_version
import npx_run as _npx_run
from video_grade import grade_filter   # optional footage grade for `composite --grade`; never applied unasked
from video_encoder import pick_encoder  # NVENC on a Windows GPU box; libx264 kept on Mac for this quality path


def _npx_path_here():
    """Where `npx` is, or None when Node is missing. npx.cmd on Windows: `cmd /c npx` runs that, and `cmd`
    itself always exists, so a missing npx never raises there."""
    import shutil
    return shutil.which("npx.cmd" if os.name == "nt" else "npx")


# Shared with reel_gate.py through npx_run, so a missing Node reads the same wherever it surfaces. An
# npx_run.py from before these two existed gets the same check and the same words from here.
npx_path = getattr(_npx_run, "npx_path", _npx_path_here)
NO_NODE = getattr(_npx_run, "NO_NODE",
                  "Node is not installed on this computer, or this terminal was opened before it was installed "
                  "(a new install stays invisible until the terminal is closed and opened again). HyperFrames runs "
                  "on Node's `npx` command. Close the terminal and open a new one, then run this again; if it is "
                  "still missing, run ./check-setup.sh, which prints the install command for this machine.")


def _sz_box():
    """The safe box as a string, read from product/safe_zones.py — the numbers were hardcoded into two
    messages here and went stale the moment the band changed."""
    try:
        import safe_zones as SZ
        return f"x {SZ.LEFT}..{SZ.RIGHT}, y {SZ.TOP}..{SZ.BOTTOM}"
    except Exception:
        return "the safe zone in product/safe_zones.py"


def _write_render_diagnostics(d, *, cached, check_seconds=None, render_seconds=None,
                               fmt=None, ok=None):
    """Real observed render timing on THIS machine — same 'get real data, don't guess' flywheel
    as .transcribe-diagnostics.json. Written into the composition's own .reel_render/ state dir
    (already exists for the render cache; no new folder convention needed). The hardware-diagnostic
    report (product/make-handoff.py) reads this alongside the transcribe one, best-effort — a
    write failure here must never fail a real render."""
    try:
        diag = {
            "cached": cached, "check_seconds": check_seconds, "render_seconds": render_seconds,
            "format": fmt, "ok": ok, "cpu_logical_cores": os.cpu_count(),
            "platform": sys.platform, "machine": platform.machine(),
        }
        path = os.path.join(d, STATE_DIR, "render-diagnostics.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(diag, f, indent=2)
    except Exception:
        pass

STALL_SECONDS = int(os.environ.get("REELS_RENDER_STALL_SECONDS", "600") or 0)


def _stall_human(seconds):
    """'12 minutes' / '45 seconds'. The default threshold is 10 minutes, but a shorter one set by hand
    must not print '0 minutes', which reads like a bug in the thing reporting the bug."""
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{seconds // 60} minutes"


def _stall_descendants(pid):
    """Every process under pid, depth-first. The renderer itself is node; the work is in the browser
    it spawns, and that is the tree worth sampling."""
    out = []
    try:
        kids = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:   # noqa: BLE001
        return out
    for k in kids:
        try:
            out.append(int(k)); out.extend(_stall_descendants(int(k)))
        except ValueError:
            pass
    return out


def _write_stall_report(pid, quiet_for, last_frame, last_phase, argv):
    """Write down what a hang used to destroy. Never raises: a stall report that fails must not also
    take down the render it is reporting on."""
    try:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "_handoff", f"render-stall-{stamp}.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        home = os.path.expanduser("~")
        lines = [
            "# Render stall report",
            "",
            f"Written {time.strftime('%Y-%m-%d %H:%M:%S')} because the renderer stopped producing output",
            f"for {_stall_human(quiet_for)}. **The render was NOT stopped** and may still finish.",
            "",
            f"- last progress seen: {last_frame or 'none — it never started producing frames'}",
            f"- last phase seen: {last_phase or 'unknown'}",
            f"- command: {' '.join(argv).replace(home, '~')}",
            "",
        ]
        machine = os.path.join(root, "_local", "machine.txt")
        if os.path.exists(machine):
            lines += ["## This machine", "", "```", open(machine, encoding="utf-8", errors="replace").read().strip(), "```", ""]
        if sys.platform == "darwin" and os.path.exists("/usr/bin/sample"):
            lines += ["## Where it is stuck", ""]
            for target in [pid] + _stall_descendants(pid)[:4]:
                try:
                    s = subprocess.run(["/usr/bin/sample", str(target), "2", "-mayDie"],
                                       capture_output=True, text=True, timeout=90).stdout
                except Exception as e:   # noqa: BLE001
                    s = f"(could not sample {target}: {e})"
                lines += [f"### pid {target}", "", "```", (s or "").replace(home, "~")[:20000].strip(), "```", ""]
        else:
            lines += ["## Where it is stuck", "", "(stack sampling is macOS only; not collected here)", ""]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path
    except Exception:   # noqa: BLE001
        return None


def _run_render_watched(argv, comp_dir=None):
    """Run the renderer, pass its output straight through, and notice if it goes silent.

    WHY THIS IS NOT A TIMEOUT. A long clip can legitimately render for a very long time, and that is
    truest on exactly the slow machines the caption hang lives on, so a deadline would abort real work.
    This never imposes one and never kills anything. What it does is notice silence.

    WHY IT READS THE STREAM. Measured 2026-09-22 on a real render: NOTHING changes on disk while a
    render runs. No frame directory appears, the renderer's cache does not move, and the output file
    does not grow — it appears complete only at the end. A filesystem watchdog would call every healthy
    render stuck. The renderer's stdout is the only continuous progress signal ("Streaming frame 13/55",
    plus [Render:trace] lines carrying framesCompleted/totalFrames/phase), so that is what is watched.

    Output is captured and written straight back out in raw chunks, never line by line, so the progress
    bar (which redraws with \\r and no newline) still animates exactly as before.

    Set REELS_RENDER_STALL_SECONDS=0 to turn the watcher off and run bare.

    THE TRAIL. Everything this watches also goes into a record in _local/render-log/ (product/render_log.py),
    rewritten every few seconds, so a render that is cancelled after running all night still says how far
    it got, how fast, and whether it froze or crawled. The timing file above is only written when a render
    ENDS; this is the part that survives a render that never does. /report-a-problem reads it.
    """
    import re, threading
    try:
        from render_log import Trail
        trail = Trail("graphics render", comp_dir)
    except Exception:   # noqa: BLE001 — the record is evidence, never a reason to fail a render
        trail = None

    def _close(result):
        if trail:
            trail.finish(result)

    if STALL_SECONDS <= 0:
        try:
            rc = subprocess.run(argv).returncode
        except KeyboardInterrupt:
            _close("stopped")
            raise
        _close("ok" if rc == 0 else f"failed (exit {rc})")
        return rc

    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    state = {"last": time.monotonic(), "frame": "", "phase": "", "fired": False}

    def watch():
        while p.poll() is None:
            time.sleep(15)
            quiet = int(time.monotonic() - state["last"])
            if state["fired"] or quiet < STALL_SECONDS or p.poll() is not None:
                continue
            state["fired"] = True
            if trail:
                trail.stalled(quiet)
            where = state["frame"] or "before the first frame"
            print(f"\n  ⏳ the renderer has not said anything for {_stall_human(quiet)}, stopped at {where}.",
                  flush=True)
            print("     Still waiting — a long clip on an older machine can take a while and nothing has been "
                  "stopped.", flush=True)
            path = _write_stall_report(p.pid, quiet, state["frame"], state["phase"], argv)
            if path:
                print(f"     Wrote what it is doing to {os.path.relpath(path)} — send me that file if this "
                      f"never finishes.", flush=True)

    threading.Thread(target=watch, daemon=True).start()

    tail = b""
    try:
        while True:
            chunk = p.stdout.read(1024)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk); sys.stdout.buffer.flush()
            state["last"] = time.monotonic()
            tail = (tail + chunk)[-4096:]
            try:
                text = tail.decode("utf-8", "replace")
            except Exception:   # noqa: BLE001
                continue
            done = total = None
            m = None
            for m in re.finditer(r"(?:Streaming|Capturing|Rendering) frame (\d+)/(\d+)", text):
                pass
            if m:
                state["frame"] = f"frame {m.group(1)} of {m.group(2)}"
                done, total = int(m.group(1)), int(m.group(2))
            else:   # the [Render:trace] lines carry the same count as JSON
                fc = re.findall(r'"framesCompleted"\s*:\s*(\d+)', text)
                tf = re.findall(r'"totalFrames"\s*:\s*(\d+)', text)
                if fc and tf:
                    done, total = int(fc[-1]), int(tf[-1])
                    state["frame"] = f"frame {done} of {total}"
            m = None
            for m in re.finditer(r'"phase"\s*:\s*"([^"]+)"', text):
                pass
            if m:
                state["phase"] = m.group(1)
            if trail:
                trail.output(done, total, state["phase"])
                # HOW it is rendering, in the renderer's own words. "software" drawing and a worker count
                # cut to 1 are the two facts that turn a minutes-long render into an hours-long one.
                # Wording taken from HyperFrames itself: "browserGpuMode probe → hardware|software (...)"
                # early on, and the closing summary "<mode> capture · hardware|software gpu · <stages>".
                g = re.findall(r"browserGpuMode probe\W+(hardware|software)", text)
                w = re.findall(r'"workerCount"\s*:\s*(\d+)', text)
                st = re.findall(r"(?:\w+ capture · )?(hardware|software) gpu · ([^\r\n]+)", text)
                trail.facts(gpu=g[-1] if g else (st[-1][0] if st else None),
                            workers=int(w[-1]) if w else None,
                            stages=re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", st[-1][1]).strip() if st else None)
        rc = p.wait()
    except KeyboardInterrupt:
        _close("stopped")
        raise
    _close("ok" if rc == 0 else f"failed (exit {rc})")
    return rc


HF_VERSION = hf_version()   # single source: product.json "hyperframes"
RENDER_EXT = (".mov", ".mp4", ".webm", ".gif", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".m4a", ".DS_Store")
STATE_DIR = ".reel_render"


def comp_dir_of(target):
    """`hyperframes check/render` read <dir>/index.html — accept a dir OR an index.html and normalize."""
    t = os.path.abspath(target)
    if os.path.isfile(t) or (not os.path.isdir(t) and t.endswith(".html")):
        t = os.path.dirname(t)
    return t


def comp_hash(d, extra="", skip=None):
    """Content hash of EVERY file in the composition dir (fonts, images, audio, video assets included — any of
    them changing must invalidate the cache) + the HF version. Excluded: the state dir and the output file
    itself (so a render written into the dir cannot invalidate its own cache in a loop)."""
    h = hashlib.sha256(f"hf={HF_VERSION}|{extra}".encode())
    skip = os.path.abspath(skip) if skip else None
    for root, dirs, files in os.walk(d):
        # skip the cache, deps, and a renders/ subdir (outputs by convention): hashing our own outputs would make
        # every render change the hash and re-render forever. Everything else — fonts, images, audio, clips — counts.
        dirs[:] = sorted(x for x in dirs if x not in (STATE_DIR, "node_modules", "renders"))
        for f in sorted(files):
            p = os.path.join(root, f)
            if f == ".DS_Store" or (skip and os.path.abspath(p) == skip):
                continue
            h.update(os.path.relpath(p, d).encode()); h.update(b"\0")
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def _state_path(d): return os.path.join(d, STATE_DIR, "state.json")
def _load(d):
    try: return json.load(open(_state_path(d), encoding="utf-8"))
    except Exception: return {}
def _save(d, st):
    os.makedirs(os.path.join(d, STATE_DIR), exist_ok=True)
    json.dump(st, open(_state_path(d), "w", encoding="utf-8"), indent=1)


_NOISE_KINDS = {  # editor-tooling hints the check emits per clip; safe to ignore for a render (never a defect)
    "studio_missing_editable_id": "editor hint, safe",
    "timeline_track_too_dense": "style hint, safe",
    "composition_file_too_large": "style hint, safe",
}

def _summarize_check(text):
    """A 90s reel emits ~240 warnings, ~236 of them the same per-clip editor hint — a real contrast/overlap/
    overflow item drowns in that. Collapse warnings by kind and surface every ✗ (contrast fail, overlap,
    overflow) as a REVIEW line so the signal is visible in one glance."""
    import re, collections
    kinds = collections.Counter(re.findall(r"^\s*⚠ ([a-z_]+):", text, flags=re.M))
    flags = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("✗")]
    if kinds:
        parts = [f"{n} {k}" + (f" ({_NOISE_KINDS[k]})" if k in _NOISE_KINDS else "") for k, n in kinds.most_common()]
        print("[gate summary] warnings by kind: " + " · ".join(parts))
    if flags:
        print(f"[gate summary] ⚠ REVIEW — {len(flags)} flagged item(s) (contrast / overlap / overflow):")
        for ln in flags[:8]:
            print("    " + ln)
        if len(flags) > 8:
            print(f"    … and {len(flags) - 8} more (see the full check output above)")


def _dead_animation_targets(text):
    """Selectors an animation drives that match NOTHING in the DOM, pulled from HyperFrames' own check output.

    HyperFrames reports these, correctly, as runtime console warnings ("GSAP target <sel> not found"). Warnings
    do not fail a check unless --strict is passed, and that is right for most of them. This one is different:
    a selector that resolves to zero elements is never what anybody meant. The animation simply does not run,
    the render succeeds, the video is watchable, and the effect is just missing. A real build shipped a
    word-by-word caption highlight that never fired and cost about a dozen seven-minute render cycles before a
    human watching the output noticed, because nothing on the way there treated it as a fault.

    So this promotes that ONE warning class to a refusal. It reads HyperFrames' own finding rather than
    re-deriving it -- nothing here parses the composition or reimplements a check.

    Returns the distinct selector strings, best-effort; an unnamed target is reported as "(unnamed target)"."""
    import re
    out, seen = [], set()
    for sel in re.findall(r"GSAP target (.*?) not found", text):
        sel = sel.strip() or "(unnamed target)"
        if sel not in seen:
            seen.add(sel); out.append(sel)
    return out


HOLD_S = 0.1   # how long text must sit past the frame edge, unmoved, to stop a render (see _offframe_text)


def _offframe_text(text):
    """Text that stays past the edge of the video, pulled from HyperFrames' own check output.

    HyperFrames reports it as a `canvas_overflow` WARNING, and warnings pass without --strict, so a word cut off
    at the frame edge rendered and shipped with nothing but a line in the terminal. It is never the intent: a
    word meant to hang off the edge carries data-layout-allow-overflow, which HyperFrames already honours, and
    a word only sliding through the edge as it animates in is reported as ℹ, not ⚠. So, like a dead animation
    target, the ⚠ kind is promoted to a refusal. Nothing here measures anything; it reads HyperFrames' finding.

    One more filter, from a survey of 106 real compositions: HyperFrames also merges the two samples it takes
    at the instant an animation ends (0.01s apart) into a ⚠ range, so a panel sliding out of frame on purpose
    reads like a stuck word. Only a range at least HOLD_S long counts: text sitting past the edge, unmoved, for
    longer than a frame. That is still shorter than any caption word stays on screen.

    Returns [(seconds, selector, direction, px, word)], one per element, the furthest it goes out."""
    import re
    worst = {}
    for t0, t1, sel, direction, px, word in re.findall(
            r"^\s*⚠ t=([\d.]+)(?:-([\d.]+))?s[^\n]*?canvas_overflow (\S+) [^\n]*?overflowed (\w+) ([\d.]+)px[^\"\n]*\"([^\"]*)\"",
            text, flags=re.M):
        if float(t1 or t0) - float(t0) < HOLD_S:
            continue
        t, px = t0, float(px)
        if px > worst.get(sel, (0, 0, "", 0.0))[3]:
            worst[sel] = (float(t), sel, direction, px, word)
    return sorted(worst.values())


def _offframe_message(items):
    """The plain explanation printed when off-frame text stops a render."""
    lines = [f"\n  ⛔ {len(items)} piece(s) of text run off the edge of the video — REFUSING to render. "
             f"They would come out cut off:"]
    for t, _sel, direction, px, word in items[:8]:
        lines.append(f"       \"{word}\" at {t:.1f}s, {round(px)}px past the {direction} edge")
    if len(items) > 8:
        lines.append(f"       … and {len(items) - 8} more")
    lines.append("     Make it fit: shorten the line, let it wrap, or bring the size down. Meant to hang off the "
                 "edge? Mark that element data-layout-allow-overflow. To render it anyway: REEL_ALLOW_OFFFRAME_TEXT=1.")
    return "\n".join(lines)


def _safe_zone_check(out):
    """LAYER 2 on the FINAL ARTIFACT. `hyperframes check` validates the composition against the CANVAS; it has
    no concept of Instagram's UI safe zone (product/safe_zones.py) — a caption sitting inside the bottom UI band
    passes it (measured: a lower-third at y=1559 passed with 0 errors). So after a transparent render, read the
    alpha plane in ONE native ffmpeg pass and take each frame's SOLID-ink bbox (alpha >= 128; a drop-shadow spill
    is not a key visual); assert it sits inside the safe zone. Full-bleed frames (ink >= 90% of the frame) are
    designed backgrounds, not overlays, and are skipped.
    Measurer notes (validated against a hand-measured card: x 70..1009, y 1295..1559): the ProRes 4444 alpha
    plane is 12-bit, so it is forced to 8-bit gray before thresholding; and ffmpeg's cropdetect judges a row/column
    by its AVERAGE, not its max, so the alpha is binarized at 128 FIRST and cropdetect runs at limit=1 on the
    binary mask (a sparse column of real ink still averages > 1; a transparent frame reports YMAX=0 and an
    inverted bbox, both ignored).
    Returns (status, breaches): status "ok" = measured; "empty" = no solid ink in ANY frame (a fully transparent
    overlay is usually a broken render, never silently "clean"); "skipped: <why>" = the tool could not measure.
    A skipped or empty measurement is NEVER reported as clean (the silent-no-op trap the audit named)."""
    import re
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import safe_zones as SZ
        L, R, T, B = int(SZ.LEFT), int(SZ.RIGHT), int(SZ.TOP), int(SZ.BOTTOM)
    except Exception as e:
        return (f"skipped: product/safe_zones.py not importable ({e})", [])
    try:
        w, h = (int(x) for x in subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
             "-of", "csv=p=0", out]).decode().strip().split(",")[:2])
        vf = ("alphaextract,format=gray,signalstats,lutyuv=y='if(gte(val\\,128)\\,255\\,0)',"
              "cropdetect=limit=1:round=1:reset=1:skip=0,metadata=print:file=-")
        pr = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vf", vf, "-f", "null", "-"],
                            capture_output=True, text=True)
        meta = pr.stdout
        if pr.returncode != 0 or "frame:" not in meta:
            return (f"skipped: ffmpeg could not read the alpha plane ({(pr.stderr or '').strip()[-160:] or 'no frames'})", [])
    except FileNotFoundError as e:
        return (f"skipped: {e.filename or 'ffmpeg/ffprobe'} not installed", [])
    except subprocess.CalledProcessError:
        return (f"skipped: ffprobe could not read {os.path.relpath(out)} (missing, or not a video)", [])
    except Exception as e:
        return (f"skipped: {type(e).__name__}: {str(e)[:160]}", [])
    x1 = y1 = 10**9; x2 = y2 = -1; solid = 0; cur = {}
    def flush():
        nonlocal x1, y1, x2, y2, solid
        if cur.get("YMAX", 0) >= 128 and all(k in cur for k in ("x1", "x2", "y1", "y2")):
            fx1, fx2, fy1, fy2 = cur["x1"], cur["x2"], cur["y1"], cur["y2"]
            if fx2 < fx1 or fy2 < fy1:                                     # inverted = nothing detected
                return
            if (fx2 - fx1 + 1) * (fy2 - fy1 + 1) < 0.9 * w * h:        # not a full-bleed designed frame
                solid += 1
                x1, y1, x2, y2 = min(x1, fx1), min(y1, fy1), max(x2, fx2), max(y2, fy2)
    for ln in meta.splitlines():
        if ln.startswith("frame:"):
            flush(); cur = {}
            continue
        m = re.match(r"\s*lavfi\.(?:signalstats\.(YMAX)|cropdetect\.(x1|x2|y1|y2))=(-?\d+)", ln)
        if m:
            cur[m.group(1) or m.group(2)] = int(m.group(3))
    flush()
    if not solid:
        return ("empty", [])
    # The box's TOP is the strictest edge across platforms; its BOTTOM is the creator's 300px call, looser than
    # every platform's band (safe_zones.PLATFORMS). Say which platform(s) actually bind so the message is true.
    def _plat(edge, v):
        hits = []
        for p, z in getattr(SZ, "PLATFORMS", {}).items():
            lim = z["top"] if edge == "top" else z["bottom"]
            over = (lim - v) if edge == "top" else (v - lim)
            if over > 0:
                hits.append(f"{p} by {over}px")
        return "; ".join(hits) if hits else "inside every platform's own band (strictest-box margin only)"
    br = []
    if x1 < L:     br.append(f"LEFT: ink starts at x={x1} (safe ≥ {L}) — {L - x1}px into the side margin")
    if x2 + 1 > R: br.append(f"RIGHT: ink ends at x={x2 + 1} (safe ≤ {R}) — {x2 + 1 - R}px into the side margin")
    if y1 < T:     br.append(f"TOP: ink starts at y={y1} (safe ≥ {T}) — under the header band: {_plat('top', y1)}")
    if y2 + 1 > B: br.append(f"BOTTOM: ink ends at y={y2 + 1} (safe ≤ {B}) — into the bottom UI band: {_plat('bottom', y2 + 1)}")
    return ("ok", br)


def _subject_box(comp_dir):
    """The measured subject box for this job, or None when her footage was never measured."""
    try:
        import subject_guard
        zp = subject_guard.find_zones(comp_dir)
        return subject_guard.box_from_zones(zp) if zp else None
    except SystemExit:
        # box_from_zones raises SystemExit on a malformed measurement. SystemExit is a BaseException, so a
        # bare `except Exception` lets it through and a bad JSON file kills the render before it starts.
        return None
    except Exception:
        return None


def _subject_check(out, comp_dir, max_cov=None):
    """LAYER 2, SUBJECT-RELATIVE, on the FINAL ARTIFACT. The safe-zone check asks whether ink is inside the
    PLATFORM's band; this asks whether it is on HER. Nothing else in the pipeline can: the overlay renders
    transparent and the footage is not in the composition, so `hyperframes check` measures a canvas with no
    person in it and passes a hook sitting on a forehead.

    Returns (status, lines). "ok" = measured and clear; "breach" = it lands on her; "skipped: <why>" = her
    footage was never measured, which is reported as NOT MEASURED and never as clean."""
    try:
        import subject_guard
    except Exception as e:
        return (f"skipped: product/subject_guard.py not importable ({e})", [])
    zp = subject_guard.find_zones(comp_dir)
    if not zp:
        return ("skipped: her footage was never measured for this job — run "
                "`uv run workflows/subject-zones.py projects/<job>/outputs/<job>.mp4`", [])
    try:
        box = subject_guard.box_from_zones(zp)
        # owns_from: the takeover windows are looked up from the COMPOSITION (its builder writes a copy of
        # owns-screen.json there). Walking up from the output alone found nothing whenever -o pointed outside
        # the job folder, so a takeover that covers her by design was refused as a stray graphic.
        rc, lines = subject_guard.report(out, box, max_cov if max_cov is not None else subject_guard.DEFAULT_MAX,
                                         owns_from=comp_dir)
    except SystemExit as e:
        return (f"skipped: {e}", [])
    except Exception as e:
        return (f"skipped: {type(e).__name__}: {str(e)[:160]}", [])
    return ("breach" if rc else "ok", lines)


def _ink_vf(out):
    """The ffmpeg filter that turns "is anything visible here" into a gray plane: the ALPHA channel for
    an overlay, the luma for a baked file."""
    try:
        pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", out],
                                     text=True).strip()
    except Exception:
        return None
    alpha = pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya"))
    return ("alphaextract," if alpha else "format=gray,") + "scale=96:-1"


def _visible_fraction(out, t, vf):
    """Fraction of pixels that are actually visible in the frame at t, or None if unreadable."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", out, "-vf", vf,
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    return (sum(1 for b in raw if b > 8) / len(raw)) if raw else None


def _plan_visual_items(comp_dir):
    """(kind, index, at) for every item the job's caption-plan says should be ON SCREEN: the list it sits
    in, its place in that list, and its time. Discovered by walking up to the job folder, so no caller has
    to pass them. Any dict with a numeric "at" counts, which survives the plan growing new element kinds."""
    d = os.path.abspath(comp_dir)
    for _ in range(4):
        d = os.path.dirname(d)
        cand = os.path.join(d, "caption-plan.json")
        if not os.path.exists(cand):
            continue
        try:
            plan = json.load(open(cand, encoding="utf-8"))
        except Exception:
            return []
        # ONLY the containers that hold TIMED VISUAL elements. A caption-plan also times SOUND
        # (`sfx`, `music`) and carries style blocks, and every one of those has an `at` too — so
        # collecting every `at` in the file demands a picture at the moment of a whoosh. On a reel
        # where that whoosh lands over bare footage the frame is legitimately empty, and a perfectly
        # good render gets refused. Verified against the real plans on this machine: they carry `at`
        # under elements, breakaways, sfx, music AND persistent_label_style.
        #
        # An ALLOWLIST, deliberately, because the two mistakes are not equal: missing a check lets one
        # bad render through, while a false refusal blocks a buyer from finishing work that is fine.
        # A visual kind that is not listed here is simply not checked — add it when it is confirmed
        # visual, never by assuming.
        VISUAL = ("elements", "breakaways", "graphics", "beats", "cards", "notes", "takeovers")
        items = []
        for key in VISUAL:
            node = plan.get(key)
            for i, item in enumerate(node if isinstance(node, list) else []):
                if isinstance(item, dict) and isinstance(item.get("at"), (int, float)):
                    items.append((key, i, float(item["at"])))
        return items
    return []


def _plan_expect_times(comp_dir):
    """Timestamps the job's caption-plan says something should be ON SCREEN (every visual item's `at`)."""
    return sorted(set(t for _k, _i, t in _plan_visual_items(comp_dir)))


def _comp_clips(comp_dir):
    """Every timed element in the composition as (start, end, lane), or None when that cannot be read
    with certainty. HyperFrames' own rules: an element carrying data-start is a clip; it shows while
    start <= t < start + data-duration; with no data-duration it stays for the rest of the composition;
    data-track-index is its lane. The composition root is the canvas, not a clip, and <audio> draws
    nothing. None (so every plan time is checked, as before) when there is no index.html, no clip in it,
    a sub-composition (its clips run on their own clock), or a start or duration that is not a plain
    number (a clip reference such as "intro + 2")."""
    from html.parser import HTMLParser
    try:
        with open(os.path.join(comp_dir, "index.html"), encoding="utf-8", errors="ignore") as fh:
            src = fh.read()
    except OSError:
        return None
    clips, unsure = [], []

    class _Clips(HTMLParser):
        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag == "template" or a.get("data-composition-src") is not None:
                unsure.append(tag)
            if a.get("data-start") is None or tag == "audio":
                return
            if a.get("data-composition-id") is not None:
                return                                   # the root: the whole canvas, not a clip
            try:
                s = float(a["data-start"])
                d = a.get("data-duration")
                e = s + float(d) if d not in (None, "") else float("inf")
                lane = a.get("data-track-index")
                clips.append((s, e, int(lane) if lane not in (None, "") else None))
            except ValueError:
                unsure.append(tag)

    try:
        _Clips(convert_charrefs=True).feed(src)
    except Exception:
        return None
    return None if (unsure or not clips) else clips


# The lanes build-reel-type.py puts the plan's own items on: a breakaway card is lane 6 and element i is
# lane 7 + i (its `_etrk`; product/layer_probe.py keeps the same map). The plan's other visual kinds are not
# tied to a lane, so for them any clip on screen at that moment counts.
_PLAN_LANES = {"breakaways": lambda i: {6}, "elements": lambda i: {7 + i}}
_PLAN_LAYER = {"breakaways": lambda lane: lane == 6, "elements": lambda lane: lane >= 7}   # any lane of that layer
_CLIP_SLACK = 0.05   # data-start/data-duration are written to 2 decimals: never lose a plan time to that rounding


def _render_expect_times(comp_dir):
    """The plan's on-screen times that THIS composition holds.

    A render of only some of the reel's layers (LAYER=<group> for separate layers, the hook / front split
    behind mode renders, a one-style caption overlay) holds only some of the plan's items. Asking it for all
    of them refused renders that were right ("EMPTY where the plan says..." at a moment that layer never
    draws). So a plan time is kept when the composition has a clip on that item's own lane whose window
    covers it. A full composition holds every item, so it is checked exactly as before, and when the
    composition cannot be read with certainty every plan time is checked, as before."""
    items = _plan_visual_items(comp_dir)
    clips = _comp_clips(comp_dir) if items else None
    if clips is None:
        return sorted(set(t for _k, _i, t in items))
    held = set()
    present = {lane for _s, _e, lane in clips}
    for kind, i, t in items:
        lanes = _PLAN_LANES[kind](i) if kind in _PLAN_LANES else None
        if lanes is not None and any(_PLAN_LAYER[kind](lane) for lane in present):
            # This composition draws that kind of item (every element is one layer, "elements"; the card is
            # "breakaway"), so it draws them ALL: one without its lane here was dropped by the builder, never
            # left out on purpose, and its moment is checked like any other.
            held.add(t)
            continue
        if any(s - _CLIP_SLACK <= t < e + _CLIP_SLACK for s, e, lane in clips if lanes is None or lane in lanes):
            held.add(t)
    return sorted(held)


EMPTY = 0.0005      # below this fraction of visible pixels, a frame is blank


def _verify_render_has_content(out, comp_dir, strict=False, samples=16):
    """Check the RENDERED FILE, not the composition. Returns (ok, lines).

    This is the hole the gate never covered: `check` validates the composition and passes BEFORE a
    single frame exists, so a render that silently drops elements goes straight through it. A real
    incident (2026-09-16) produced an overlay holding only the hook, captions and takeover — every
    note and graphic missing — and the engine reported it built and good without a frame ever being
    looked at. Alpha was real and the safe zones were clean, so the two existing output checks passed
    as well. Reading what is actually in the file is the only thing that catches this."""
    vf = _ink_vf(out)
    dur = _dur(out) or 0
    if not vf or dur <= 0:
        return True, []
    msgs = []

    # 1) HARD: empty exactly where the plan says an element is showing (of the elements this composition
    #    holds: a render of one layer is never asked for another layer's elements).
    empty_at = []
    for t in [t for t in _render_expect_times(comp_dir) if 0 < t < dur]:
        f = _visible_fraction(out, min(t + 0.25, dur - 0.05), vf)
        if f is not None and f < EMPTY:
            empty_at.append(t)
    if empty_at:
        msgs.append("  \u26d4 the render is EMPTY where the plan says an element is on screen: "
                    + ", ".join(f"{t:.2f}s" for t in empty_at[:8])
                    + (f" (+{len(empty_at) - 8} more)" if len(empty_at) > 8 else ""))
        msgs.append("     The composition passed the gate, so this is the RENDER losing content, not a bad plan.")
        msgs.append("     Re-run it once; if it repeats, render the same comp with a bare "
                    f"`npx hyperframes@{HF_VERSION} render <comp> --format mov` and compare the two.")
        return False, msgs

    # 2) SOFT: mostly-blank output. Legitimate for a sparse overlay, and also what a dropped-element
    #    render looks like, so it is said out loud rather than assumed either way.
    prof = [(t, _visible_fraction(out, t, vf))
            for t in (dur * (i + 0.5) / samples for i in range(samples))]
    prof = [(t, f) for t, f in prof if f is not None]
    if not prof:
        return True, []
    blank = sum(1 for _t, f in prof if f < EMPTY)
    if blank == len(prof):
        return False, ["  \u26d4 the render contains NOTHING — every sampled frame is empty."]
    if blank > len(prof) * 0.6:
        msgs.append(f"  \u26a0 {blank} of {len(prof)} sampled frames are completely empty. That can be normal for "
                    f"a sparse overlay, but it is also what a render that dropped its elements looks like. "
                    f"Look at a frame before shipping it.")
        if strict:
            return False, msgs
    return True, msgs


def _alpha_is_real(out, samples=5):
    """True if this overlay actually has transparent pixels, False if it is uniformly opaque,
    None if the question does not apply (no alpha channel) or ffmpeg could not answer.

    WHY this is not just a pix_fmt check: a broken transparent render still writes a yuva pix_fmt
    AND the container's alpha_mode tag, so every piece of metadata says "transparent" while every
    pixel decodes solid. The only honest test is to read the alpha plane itself. Sampled across the
    timeline because an overlay may legitimately be opaque during one full-frame beat — only a file
    that is opaque EVERYWHERE is the bug. Set REEL_SKIP_ALPHA_CHECK=1 to bypass."""
    if os.environ.get("REEL_SKIP_ALPHA_CHECK") == "1":
        return None
    try:
        pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                      "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", out],
                                     text=True).strip()
        if not pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")):
            return None                                    # not an alpha format: nothing to verify
        dur = _dur(out) or 0
        if dur <= 0:
            return None
        lo = 255
        for i in range(samples):
            t = dur * (i + 0.5) / samples
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", out,
                                  "-vf", "alphaextract,scale=64:-1", "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                 capture_output=True).stdout
            if raw:
                lo = min(lo, min(raw))
            if lo < 250:
                return True                                # found real transparency, done
        return False if lo >= 250 else True
    except Exception:
        return None


def cmd_render(a):
    d = comp_dir_of(a.target)
    if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "index.html")):
        print(f"  ⛔ composition not found (need <dir>/index.html): {d}"); return 2
    out = os.path.abspath(a.output)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)   # a missing output dir is never a reason to fail late
    # Follow the OUTPUT EXTENSION unless --format was given explicitly. Asking for `-o preview.mp4` and
    # silently getting a transparent-overlay mov is the trap: a full-frame composition (a pack preview, a
    # designed card, anything with its own ground) then trips the opaque-overlay guard, and the error talks
    # about alpha when the real answer is "you wanted an mp4". An explicit --format always wins.
    if a.format is None:
        a.format = {".mp4": "mp4", ".webm": "webm", ".mov": "mov"}.get(os.path.splitext(out)[1].lower(), "mov")
    # FAIL LOUD on a missing font FILE: compositions load fonts by RELATIVE url('x.ttf'). If the file is absent the
    # browser silently substitutes a system font, `check` cannot know the intended face, and the render ships in
    # the wrong typography. Refuse before spending a minute on it. (Premium faces are staged into the comp dir
    # from the buyer's CapCut cache by stage_hands_off_fonts — this catches a skipped staging step.)
    import re
    html_src = open(os.path.join(d, "index.html"), encoding="utf-8", errors="ignore").read()
    missing = []
    for ref in set(re.findall(r"url\(\s*['\"]?([^'\")]+\.(?:ttf|otf|woff2?))['\"]?\s*\)", html_src, flags=re.I)):
        if "://" in ref or ref.startswith("/"):
            continue                                            # absolute / remote: not a co-located file
        if not os.path.exists(os.path.join(d, ref)):
            missing.append(ref)
    if missing:
        print("  ⛔ REFUSING to render: font file(s) referenced by the composition are missing from its folder — "
              "the render would silently use the wrong typeface:\n" + "".join(f"     • {m}\n" for m in sorted(missing))
              + "     Stage them first (python3 product/stage_hands_off_fonts.py <pack>) or fix the @font-face path.")
        return 3
    # A composition built outside the reel builders (a hands-off template with her words typed in) gets the
    # same Cyrillic companions they add. A page with no Cyrillic, or one already done, is left untouched.
    import script_fonts
    script_fonts.patch_dir(d)
    sz_mode = "off" if a.no_safe_zone else ("strict" if a.safe_zone_strict else "report")
    # The subject measurement lives in the JOB folder, outside the composition comp_hash covers. Fold the
    # measured box into the key so re-measuring her footage invalidates a cached "clean" instead of
    # reusing a verdict that was reached against the old numbers.
    subj_key = "off" if a.no_subject else str(_subject_box(d))
    # Every setting that loosens or retunes a check is in the key too. Without them a render that passed
    # with a check switched off (--no-contrast, --subject-max, REEL_ALLOW_DEAD_TARGETS=1,
    # REEL_SKIP_ALPHA_CHECK=1) was handed back as "gated clean" to a later run that asked for the full gate.
    # Only a setting actually in force adds to the key, so a run with none keeps the key it always had.
    relaxed = "".join(f"|{k}" for k, on in (
        ("contrast=off", a.no_contrast),
        (f"subject_max={a.subject_max!r}", a.subject_max is not None),
        ("dead_targets=allowed", os.environ.get("REEL_ALLOW_DEAD_TARGETS") == "1"),
        ("offframe_text=allowed", os.environ.get("REEL_ALLOW_OFFFRAME_TEXT") == "1"),
        ("alpha_check=skipped", os.environ.get("REEL_SKIP_ALPHA_CHECK") == "1"),
    ) if on)
    key = comp_hash(d, extra=f"strict={int(a.strict)}|format={a.format}|sz={sz_mode}|subj={subj_key}{relaxed}",
                    skip=out)
    st = _load(d)
    prev = st.get(key)
    if not a.force and prev and prev.get("out") == out and prev.get("ok") and os.path.exists(out):
        print(f"  ✅ unchanged since last clean render — reusing {os.path.relpath(out)} (no check, no render).")
        if prev.get("sz"):   # a report-mode breach is re-said on every reuse, never a one-shot warning
            print("  ⚠ SAFE-ZONE (from that render — still true, the file is unchanged):")
            for b in prev["sz"]:
                print(f"     • {b}")
        _write_render_diagnostics(d, cached=True, fmt=a.format, ok=True)
        return 0

    # Node first. Without it the check never runs, and that must not read as a fault in the composition: on
    # Windows the check runs as `cmd /c npx ...`, and `cmd` always exists, so a missing npx came back as an
    # ordinary exit 1 and this said "Fix the composition" (most often Node installed, Git Bash not reopened).
    if not npx_path():
        print(f"  ⛔ the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong."); return 4
    # `check` waits for scripts and media to settle before it measures (default 3000 ms). That default was
    # measured on Apple Silicon; an Intel Mac or a budget PC can miss it and fail a composition that is fine,
    # and this gate REFUSES to render on a failed check. Give slow hardware headroom; the env override is
    # for a tester whose machine needs more.
    chk = hf_check_argv(HF_VERSION, d, strict=a.strict, contrast=not a.no_contrast)   # order is load-bearing; see npx_run.hf_check_argv
    print("[gate]", " ".join(chk[1:]))
    _t_check = time.monotonic()
    try:
        res = subprocess.run(chk, capture_output=True, text=True)
    except FileNotFoundError:   # npx found but would not start: the same plain answer, never a traceback
        print(f"  ⛔ the check could not run. {NO_NODE}\n"
              f"     Nothing was checked, and nothing here says the composition is wrong."); return 4
    check_seconds = round(time.monotonic() - _t_check, 1)
    chk_rc = res.returncode
    text = (res.stdout or "") + (res.stderr or "")
    sys.stdout.write(text)
    _summarize_check(text)
    if chk_rc != 0:
        # npx itself can fail before HyperFrames ever starts (it could not get the package: offline with
        # nothing cached, a proxy, a cache it may not write). npm then prints its own "npm error code ..."
        # and HyperFrames never gives a verdict, so nothing was checked and the composition is not at fault.
        # Only when BOTH hold: a real check failure always ends in HyperFrames' own "Check failed".
        _npm = re.search(r"^npm (?:error|ERR!) code (\S+)", text, flags=re.M)
        if _npm and not re.search(r"Check (?:failed|passed)", text):
            print(f"\n  ⛔ the check could not run: npx could not start HyperFrames {HF_VERSION} (npm said "
                  f"{_npm.group(1)}, above). Nothing was checked, and nothing here says the composition is wrong.\n"
                  f"     With an internet connection, run `npx hyperframes@{HF_VERSION} browser ensure` once "
                  f"(it downloads HyperFrames), then run this again.")
            return 4
        print("\n  ⛔ check found issues — REFUSING to render. Fix the composition (see above), then re-run. "
              "Packs may only change dressing; layout, motion and overflow are HyperFrames' job.")
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # An animation aimed at nothing is a silent no-op, not a style choice: the render succeeds and the effect
    # is just absent. HyperFrames names it as a warning, which passes without --strict; refuse on it anyway.
    _dead = _dead_animation_targets(text)
    if _dead and os.environ.get("REEL_ALLOW_DEAD_TARGETS") == "1":
        print(f"\n  ⚠ {len(_dead)} animation target(s) match nothing; rendering anyway "
              f"(REEL_ALLOW_DEAD_TARGETS=1). Those animations will not appear: {', '.join(_dead[:4])}")
        _dead = []
    if _dead:
        print(f"\n  ⛔ {len(_dead)} animation target(s) match nothing in this composition — REFUSING to render. "
              f"These animations would not run and the render would come out silently missing them:")
        for sel in _dead[:8]:
            print(f"       {sel}")
        if len(_dead) > 8:
            print(f"       … and {len(_dead) - 8} more")
        print("     Usually the selector and the element's real id/attribute have drifted apart (a built id gets "
              "a prefix the selector was not given). Fix the selector, or the element, then re-run.")
        print("     If the element really is created later and this is deliberate, set REEL_ALLOW_DEAD_TARGETS=1.")
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # Text stuck past the edge of the video would render cut off. HyperFrames names it as a warning, which passes
    # without --strict; refuse on it anyway (see _offframe_text).
    _off = _offframe_text(text)
    if _off and os.environ.get("REEL_ALLOW_OFFFRAME_TEXT") == "1":
        print(f"\n  ⚠ {len(_off)} piece(s) of text run off the edge of the video; rendering anyway "
              f"(REEL_ALLOW_OFFFRAME_TEXT=1). They will come out cut off.")
        _off = []
    if _off:
        print(_offframe_message(_off))
        st[key] = {"out": out, "ok": False}; _save(d, st)
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds, fmt=a.format, ok=False)
        return 1

    # ISOLATED render (locked): on a FAILED render HyperFrames 0.8.43 rolls its transaction back and has DELETED
    # the composition dir and sibling job files (a real incident: it took the job's outputs/ and cut backups with
    # it, and reverted cuts.json). So render a scratch COPY outside projects/; a failure there can only harm the
    # copy. A comp that reaches outside its own dir (`../`) cannot be isolated and renders in place, said out loud.
    import tempfile, shutil
    _idx = os.path.join(d, "index.html")
    _html = open(_idx, errors="ignore", encoding="utf-8").read() if os.path.exists(_idx) else ""
    work = None; src = d
    if "../" in _html:
        print("  ⚠ composition references paths outside its dir (`../`) — rendering IN PLACE (no isolation).")
    else:
        work = tempfile.mkdtemp(prefix="reel-render-")
        src = os.path.join(work, "comp")
        shutil.copytree(d, src, ignore=shutil.ignore_patterns(".reel_render", "renders", ".DS_Store"))
    _rnd_extra = ["--low-memory-mode"] if getattr(a, "low_memory", False) else []
    if _rnd_extra:
        print("  streaming frames instead of buffering them to disk (--low-memory-mode).")
    rnd = npx_argv(f"hyperframes@{HF_VERSION}", "render", src, "--format", a.format, "--output", out, *_rnd_extra)
    print("[render]", " ".join(rnd[1:]), "" if work is None else "(isolated copy; job dir untouched)")
    _t_render = time.monotonic()
    try:
        rc = _run_render_watched(rnd, comp_dir=d)
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)
    render_seconds = round(time.monotonic() - _t_render, 1)
    if rc != 0 or not os.path.exists(out):
        # The renderer prints its own reason directly above; do not talk over it with a guess. This
        # line used to assert the cause was a browser that failed to start, which sent anyone whose
        # render died of a full disk off to reinstall a browser that was working fine.
        _free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free / 1e9
        print("\n  ⛔ render failed. The reason is in the renderer's own output just above.")
        print(f"     Two things worth checking first — free disk here: {_free_gb:.1f} GB.")
        print("     • Out of temporary space? A minute of transparent 1080x1920 runs to roughly 15 GB of")
        print("       frames. Re-run with --low-memory to stream them instead of buffering.")
        print(f"     • HyperFrames did not start? `npx hyperframes@{HF_VERSION} browser ensure` once, then "
              f"`npx hyperframes@{HF_VERSION} doctor`.")
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                   render_seconds=render_seconds, fmt=a.format, ok=False)
        return rc or 1
    if a.format in ("mov", "webm"):
        verdict = _alpha_is_real(out)
        if verdict is False:
            print(f"\n  ⛔ this overlay rendered FULLY OPAQUE. The file says it carries alpha and the container "
                  f"tag agrees, but every pixel is solid — dropped on the footage it would black the reel out.\n"
                  f"     Cause: some HyperFrames builds only apply the transparent-background capture when the\n"
                  f"     output format is png, so mov/webm come back opaque while still LOOKING correct in\n"
                  f"     ffprobe. This engine pins {HF_VERSION}, which renders alpha correctly; an unpinned\n"
                  f"     `npx hyperframes render` picks up whatever is latest and can hit it.\n"
                  f"     Fix: render the frames, then encode them yourself —\n"
                  f"       npx hyperframes@{HF_VERSION} render <comp> --format png-sequence --output frames/\n"
                  f"       ffmpeg -framerate 30 -i frames/%05d.png -c:v prores_ks -profile:v 4 "
                  f"-pix_fmt yuva444p10le {out}")
            _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                       render_seconds=render_seconds, fmt=a.format, ok=False)
            return 1
    # THE RENDER MUST PROVE ITSELF. Everything above this line checked the composition or the file's
    # metadata; none of it opens the rendered video and looks. That is how a render with every note
    # missing was reported as finished and good.
    _ok, _lines = _verify_render_has_content(out, d, strict=a.strict)
    for _l in _lines:
        print(_l)
    if not _ok:
        _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                   render_seconds=render_seconds, fmt=a.format, ok=False)
        st[key] = {"out": out, "ok": False}; _save(d, st)
        return 1

    sz_report = []
    if a.format == "mov" and not a.no_safe_zone:
        status, br = _safe_zone_check(out)
        sz_report = list(br)
        if status != "ok":
            # never a silent pass: say plainly that nothing was measured (or that the overlay is fully transparent)
            why = ("the overlay has NO solid ink in any frame — a fully transparent render is usually a broken one "
                   "(fonts? timeline?); inspect it before using it" if status == "empty" else status)
            print(f"\n  ⚠ SAFE-ZONE: not measured — {why}. This is NOT evidence of a clean overlay.")
        elif br:
            # REPORT mode by default (locked): this is a Layer-2 measurement of the FINAL alpha — `hyperframes check`
            # validates the canvas and has no concept of the platforms' UI bands. It never blocks a render that the
            # native check passed unless the caller opts into --safe-zone-strict, so an existing working build keeps
            # working while the breach is made visible.
            tag = "⛔" if a.safe_zone_strict else "⚠"
            print(f"\n  {tag} SAFE-ZONE: solid ink in the rendered overlay sits outside the safe zone "
                  "(product/safe_zones.py, strictest across Reels/TikTok/Shorts; measured on the final alpha — "
                  "the native check validates the canvas only):")
            for b in br:
                print(f"     • {b}")
            print(f"     Fix = move/fit the element inside safe_zones ({_sz_box()}) and re-render. "
                  "--safe-zone-strict makes this refuse; --no-safe-zone skips it for a deliberate full-canvas design.")
            if a.safe_zone_strict:
                print("     REFUSING (--safe-zone-strict). The file was kept for inspection but is NOT marked clean.")
                st[key] = {"out": out, "ok": False}; _save(d, st)
                _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                           render_seconds=render_seconds, fmt=a.format, ok=False)
                return 5
        else:
            print(f"  ✓ safe zone: every frame's solid ink is inside {_sz_box()}")

    # SUBJECT CHECK — REFUSES by default, unlike the safe-zone one. That check reports because it post-dates
    # working builds it would otherwise break; this one exists precisely to stop the defect it catches, and a
    # layer sitting on her face is never something to ship past with a warning. --no-subject opts out for a
    # deliberate over/behind-the-subject treatment.
    if a.format == "mov" and not a.no_subject:
        s_status, s_lines = _subject_check(out, d, a.subject_max)
        if s_status.startswith("skipped"):
            print(f"\n  ⚠ SUBJECT: not measured — {s_status[9:]}.\n"
                  "     This is NOT evidence the layer is clear of her face.")
        elif s_status == "breach":
            print("")
            for ln in s_lines:
                print(f"  {ln}")
            print("     Fix = move it into an open zone (subject-zones.json → zones.above / below / left / "
                  "right, each already inside the platform band) and re-render that layer.")
            print("     REFUSING. The file was kept for inspection but is NOT marked clean. "
                  "--no-subject skips this for a deliberate over-the-subject design.")
            st[key] = {"out": out, "ok": False}; _save(d, st)
            _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                                       render_seconds=render_seconds, fmt=a.format, ok=False)
            return 6
        else:
            for ln in s_lines:
                print(f"  {ln}")
    st[key] = {"out": out, "ok": True, "sz": sz_report}; _save(d, st)
    print(f"\n  ✅ rendered → {os.path.relpath(out)}  (gated clean; cached — an identical re-run is a no-op)")
    _write_render_diagnostics(d, cached=False, check_seconds=check_seconds,
                               render_seconds=render_seconds, fmt=a.format, ok=True)
    return 0


def _dur(path):
    try:
        return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                              "-of", "csv=p=0", path]).strip())
    except Exception:
        return 0.0


def cmd_composite(a):
    base = os.path.abspath(a.base); layers = [os.path.abspath(x) for x in (a.layers or [])]
    out = os.path.abspath(a.output)
    for p in [base] + layers + ([os.path.abspath(a.audio)] if a.audio else []):
        if not os.path.exists(p):
            print(f"  ⛔ missing input: {p}"); return 2
    vdur = _dur(base)
    # The layers ARE the reel canvas (rendered at the composition size). If the base footage is a different
    # size (a 4K phone clip, a landscape source), overlay=0:0 pins the layer top-left unscaled — silently
    # misaligned (measured on a 2160x3840 base). Scale the base to the first layer's size and say so.
    cw = ch = None
    if layers:
        try:
            cw, ch = (int(x) for x in subprocess.check_output(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", layers[0]]).decode().strip().split(",")[:2])
        except Exception:
            cw = ch = None
    bw = bh = None
    try:
        import os as _o, sys as _s; _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
        from probe import display_dims as _display_dims   # the base is real footage: use its DISPLAYED size
        bw, bh = _display_dims(base)
        if not bw: bw = bh = None
    except Exception:
        pass
    if not bw:   # no video stream (an audio file, a corrupt clip) — say so instead of leaving a junk output behind
        print(f"  ⛔ --base has no video stream: {os.path.relpath(base)}  (pass the footage, not an audio file)")
        return 2
    base_fix = ""
    if cw and bw and (bw, bh) != (cw, ch):
        base_fix = f"scale={cw}:{ch}:force_original_aspect_ratio=increase,crop={cw}:{ch},setsar=1,"
        print(f"  ⚠ base footage is {bw}x{bh} but the layers are {cw}x{ch}: scaling the base to the reel canvas "
              f"(cover + center-crop) so the graphics line up. Reframe the footage upstream for full control.")
    # VARIABLE frame rate (every raw phone clip: r=30/1 but avg=52000/1733) keeps variable timing through the
    # composite unless normalized; the spliced rough-cut is already CFR, but raw footage fed straight in is not.
    # Lock the base to the layers' constant rate so frame timing is deterministic.
    try:
        rfr, afr = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate",
             "-of", "csv=p=0", base]).decode().strip().split(",")[:2]
        # exact fraction compare: an iPhone grab reports r=30/1 vs avg=52000/1733 (30.006) — a float threshold
        # missed it; any mismatch between nominal and actual rate IS variable timing
        if rfr.strip() != afr.strip():
            lfr = "30"
            if layers:
                try: lfr = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                                    "stream=r_frame_rate", "-of", "csv=p=0", layers[0]]).decode().strip() or "30"
                except Exception: pass
            base_fix += f"fps={lfr},"
            print(f"  ⚠ base footage is variable frame rate (nominal {rfr}, actual {afr}): locking it to {lfr} fps "
                  f"so the graphics stay frame-accurate. (Footage that went through the rough cut is already constant.)")
    except Exception:
        pass
    # OPTIONAL grade, footage only: goes into the base chain, so every transparent layer composited on top
    # keeps its pack colors exactly. Never applied unless --grade was passed (locked: optional, not built in).
    if a.grade:
        try:
            _g = grade_filter(a.grade)   # None for "none"/"off"/"no": an explicit no-grade is not an error
        except ValueError as e:
            sys.exit(f"  ✗ {e}")
        if _g:
            base_fix += _g + ","
            print(f"  ✓ grade '{a.grade}' on the footage only (layers untouched)")
    # A layer with NO alpha channel is not an overlay — it will fully cover the base and every layer under it.
    for l in layers:
        try:
            pf = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                          "stream=pix_fmt", "-of", "csv=p=0", l]).decode().strip()
            if pf and not pf.startswith(("yuva", "rgba", "bgra", "argb", "abgr", "gbrap", "ya")):   # the alpha-carrying families
                print(f"  ⚠ layer {os.path.relpath(l)} has no alpha channel ({pf}) — it is not transparent and will "
                      f"fully cover the base. Render overlays with --format mov (ProRes 4444) if that isn't intended.")
        except Exception:
            pass
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", base]
    for l in layers: cmd += ["-i", l]
    if a.audio: cmd += ["-i", a.audio]
    # stack: base, then each transparent layer on top in order. eof_action=pass: when a layer ENDS before the
    # base, release it (default 'repeat' FREEZES the layer's last frame over the rest of the reel — measured).
    fc, prev = "", "[0:v]"
    if base_fix:
        fc += f"[0:v]{base_fix.rstrip(',')}[b0];"; prev = "[b0]"
    for i in range(len(layers)):
        o = f"[v{i}]"; fc += f"{prev}[{i+1}:v]overlay=0:0:format=auto:eof_action=pass{o};"; prev = o
    fc += f"{prev}format=yuv420p[vout]"
    cmd += ["-filter_complex", fc, "-map", "[vout]"]
    # Audio is ALWAYS transcoded to AAC (as the shipped build-reel-mp4.py does). `-c:a copy` wrote a PCM stream
    # into the .mp4 when the source was a ProRes/PCM export — non-standard, and Instagram/QuickTime reject or
    # mute it — while reporting success (measured).
    if a.audio:
        # NEVER let a short audio cut the video (-shortest did exactly that, silently). The VIDEO governs length;
        # a shorter audio simply ends (silent tail) and we say so.
        adur = _dur(a.audio)
        if adur and vdur and adur < vdur - 0.25:
            print(f"  ⚠ audio ({adur:.1f}s) is shorter than the video ({vdur:.1f}s): the last {vdur - adur:.1f}s "
                  f"will be silent. No video was cut.")
        cmd += ["-map", f"{len(layers)+1}:a:0"]
    else:
        # FIRST audio stream only: an iPhone .mov carries a timed-metadata stream (codec "none") that ffmpeg
        # classes as audio, and a broad `0:a?` selected it -> "no decoder found for: none" (measured).
        cmd += ["-map", "0:a:0?"]
    cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    cmd += pick_encoder(vbr="16M", crf=a.crf, preset="medium", hw_on_mac=False)
    if vdur: cmd += ["-t", f"{vdur:.3f}"]      # video length governs; never -shortest
    cmd += [out]
    print("[composite]", os.path.relpath(base), "+", len(layers), "layer(s)", "+ audio" if a.audio else "", "→", os.path.relpath(out))
    try:
        rc = subprocess.run(cmd).returncode
    except FileNotFoundError:
        print("  ⛔ ffmpeg not found on PATH — run ./check-setup.sh (it prints the install command)."); return 4
    if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        print("  ✅ composited"); return 0
    # never leave a junk / partial output behind that a later step could mistake for a finished reel
    try: os.remove(out)
    except OSError: pass
    print("  ⛔ composite failed (see ffmpeg error above) — no output written.")
    return rc or 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("render", help="gated + cached render of one composition")
    r.add_argument("target", help="composition dir or its index.html")
    r.add_argument("-o", "--output", required=True)
    r.add_argument("--format", default=None,
                   help="mov (transparent overlay) | mp4 (opaque) | webm. Default: inferred from the output extension.")
    r.add_argument("--strict", action="store_true", help="fail on check WARNINGS too (every-word-must-read comps)")
    r.add_argument("--no-contrast", action="store_true",
        help="skip the WCAG contrast pass — for a plate that reproduces a site "
             "verbatim, where the styling is not authored here")
    r.add_argument("--low-memory", action="store_true",
                   help="stream frames instead of buffering them to disk — slower, but a long transparent "
                        "comp needs ~15 GB of scratch per minute and will otherwise die partway through")
    r.add_argument("--force", action="store_true", help="ignore the cache; re-check + re-render")
    r.add_argument("--no-safe-zone", action="store_true",
                   help="skip the post-render Instagram safe-zone measurement (only for a deliberate full-canvas design)")
    r.add_argument("--safe-zone-strict", action="store_true",
                   help="REFUSE (exit 5) when the rendered overlay's solid ink leaves the safe zone (default: report only)")
    r.set_defaults(fn=cmd_render)
    r.add_argument("--no-subject", action="store_true",
                   help="skip the subject check (a deliberate over-the-subject or behind-the-subject treatment)")
    r.add_argument("--subject-max", type=float, default=None,
                   help="allowed fraction of the measured subject box a layer may cover (default 0.01)")
    c = sp.add_parser("composite", help="cheap ffmpeg stack: base + transparent layers (+ audio)")
    c.add_argument("--base", required=True); c.add_argument("--layers", nargs="*")
    c.add_argument("--audio"); c.add_argument("-o", "--output", required=True)
    c.add_argument("--crf", type=int, default=20)
    c.add_argument("--grade", default=None,
                   help="optional footage color grade, only when asked for: cinematic | warm | cool | film | mono")
    c.set_defaults(fn=cmd_composite)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
